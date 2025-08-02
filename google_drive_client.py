import os
import json
import io
import mimetypes
from typing import List, Dict, Any, Optional, Set
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
import logging
from datetime import datetime, timedelta
import requests
import re

from config import config

logger = logging.getLogger(__name__)

class GoogleDriveClient:
    """Client for accessing all Google Drive content"""
    
    # Required scopes for Drive access
    SCOPES = [
        'https://www.googleapis.com/auth/drive.readonly',
        'https://www.googleapis.com/auth/documents.readonly',
        'https://www.googleapis.com/auth/spreadsheets.readonly'
    ]
    
    # Supported file types
    SUPPORTED_TYPES = {
        'application/vnd.google-apps.document': 'google_doc',
        'application/vnd.google-apps.spreadsheet': 'google_sheet',
        'application/vnd.google-apps.presentation': 'google_slides',
        'application/pdf': 'pdf',
        'text/plain': 'text',
        'text/markdown': 'markdown',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
        'application/msword': 'doc',
    }
    
    def __init__(self):
        self.drive_service = None
        self.docs_service = None
        self.sheets_service = None
        self.credentials = None
        self.cache = {}
        self.cache_expiry = timedelta(hours=1)
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google APIs"""
        creds = None
        
        # Check if token file exists
        if os.path.exists(config.google_token_path):
            creds = Credentials.from_authorized_user_file(config.google_token_path, self.SCOPES)
        
        # If there are no valid credentials, request authorization
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(config.google_credentials_path):
                    raise FileNotFoundError(f"Google credentials file not found at {config.google_credentials_path}")
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    config.google_credentials_path, self.SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save credentials for future runs
            with open(config.google_token_path, 'w') as token:
                token.write(creds.to_json())
        
        self.credentials = creds
        
        # Build service objects
        self.drive_service = build('drive', 'v3', credentials=creds)
        self.docs_service = build('docs', 'v1', credentials=creds)
        self.sheets_service = build('sheets', 'v4', credentials=creds)
        
        logger.info("Google Drive authentication successful")
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache entry is still valid"""
        if cache_key not in self.cache:
            return False
        
        cache_entry = self.cache[cache_key]
        return datetime.now() - cache_entry['timestamp'] < self.cache_expiry
    
    def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        """Get data from cache if valid"""
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]['data']
        return None
    
    def _set_cache(self, cache_key: str, data: Any):
        """Set data in cache"""
        self.cache[cache_key] = {
            'data': data,
            'timestamp': datetime.now()
        }
    
    def list_files(self, folder_id: str = None, file_type: str = None, query: str = None) -> List[Dict[str, Any]]:
        """List files in Google Drive"""
        try:
            cache_key = f"files_{folder_id}_{file_type}_{query}"
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                return cached_result
            
            # Build query
            q_parts = []
            
            if folder_id:
                q_parts.append(f"'{folder_id}' in parents")
            
            if file_type:
                if file_type in self.SUPPORTED_TYPES:
                    q_parts.append(f"mimeType = '{file_type}'")
                else:
                    # Search by file extension
                    q_parts.append(f"name contains '.{file_type}'")
            
            if query:
                q_parts.append(f"name contains '{query}'")
            
            # Only get files we can process
            supported_types = list(self.SUPPORTED_TYPES.keys())
            mime_query = " or ".join([f"mimeType = '{mime}'" for mime in supported_types])
            q_parts.append(f"({mime_query})")
            
            # Exclude trashed files
            q_parts.append("trashed = false")
            
            query_string = " and ".join(q_parts)
            
            # Execute query
            results = self.drive_service.files().list(
                q=query_string,
                fields="files(id, name, mimeType, parents, modifiedTime, size, webViewLink)",
                pageSize=1000
            ).execute()
            
            files = results.get('files', [])
            
            # Cache the result
            self._set_cache(cache_key, files)
            
            logger.info(f"Found {len(files)} files in Drive")
            return files
            
        except HttpError as e:
            logger.error(f"Error listing files: {e}")
            return []
    
    def get_folder_structure(self, folder_id: str = None) -> Dict[str, Any]:
        """Get folder structure from Google Drive"""
        try:
            cache_key = f"folder_structure_{folder_id}"
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                return cached_result
            
            # Get folders
            query = "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            if folder_id:
                query += f" and '{folder_id}' in parents"
            
            folders = self.drive_service.files().list(
                q=query,
                fields="files(id, name, parents)",
                pageSize=1000
            ).execute().get('files', [])
            
            # Build folder structure
            structure = {
                'folders': folders,
                'files': self.list_files(folder_id=folder_id)
            }
            
            # Cache the result
            self._set_cache(cache_key, structure)
            
            return structure
            
        except HttpError as e:
            logger.error(f"Error getting folder structure: {e}")
            return {'folders': [], 'files': []}
    
    def get_file_content(self, file_id: str, mime_type: str) -> Optional[str]:
        """Get content from a file based on its type"""
        try:
            cache_key = f"file_content_{file_id}"
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                return cached_result
            
            content = None
            
            if mime_type == 'application/vnd.google-apps.document':
                content = self._get_google_doc_content(file_id)
            elif mime_type == 'application/vnd.google-apps.spreadsheet':
                content = self._get_google_sheet_content(file_id)
            elif mime_type == 'application/vnd.google-apps.presentation':
                content = self._get_google_slides_content(file_id)
            elif mime_type == 'application/pdf':
                content = self._get_pdf_content(file_id)
            elif mime_type in ['text/plain', 'text/markdown']:
                content = self._get_text_content(file_id)
            elif mime_type in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword']:
                content = self._get_doc_content(file_id)
            
            if content:
                self._set_cache(cache_key, content)
            
            return content
            
        except Exception as e:
            logger.error(f"Error getting file content for {file_id}: {e}")
            return None
    
    def _get_google_doc_content(self, file_id: str) -> Optional[str]:
        """Get content from Google Doc"""
        try:
            document = self.docs_service.documents().get(documentId=file_id).execute()
            return self._extract_text_from_google_doc(document)
        except HttpError as e:
            logger.error(f"Error getting Google Doc content: {e}")
            return None
    
    def _extract_text_from_google_doc(self, document: Dict[str, Any]) -> str:
        """Extract text from Google Doc structure"""
        def extract_text_from_element(element):
            text = ""
            if 'textRun' in element:
                text += element['textRun']['content']
            elif 'pageBreak' in element:
                text += '\n\n--- Page Break ---\n\n'
            return text
        
        def extract_text_from_paragraph(paragraph):
            text = ""
            if 'elements' in paragraph:
                for element in paragraph['elements']:
                    text += extract_text_from_element(element)
            return text
        
        full_text = ""
        document_title = document.get('title', 'Untitled Document')
        full_text += f"Document: {document_title}\n\n"
        
        if 'body' in document and 'content' in document['body']:
            for content_element in document['body']['content']:
                if 'paragraph' in content_element:
                    paragraph_text = extract_text_from_paragraph(content_element['paragraph'])
                    full_text += paragraph_text
                elif 'table' in content_element:
                    table = content_element['table']
                    for row in table.get('tableRows', []):
                        row_text = ""
                        for cell in row.get('tableCells', []):
                            cell_text = ""
                            for cell_content in cell.get('content', []):
                                if 'paragraph' in cell_content:
                                    cell_text += extract_text_from_paragraph(cell_content['paragraph'])
                            row_text += cell_text + " | "
                        full_text += row_text.rstrip(" | ") + "\n"
                    full_text += "\n"
        
        return full_text.strip()
    
    def _get_google_sheet_content(self, file_id: str) -> Optional[str]:
        """Get content from Google Sheet"""
        try:
            sheet = self.sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
            title = sheet.get('properties', {}).get('title', 'Untitled Sheet')
            
            content = f"Spreadsheet: {title}\n\n"
            
            # Get all sheets
            sheets = sheet.get('sheets', [])
            
            for sheet_info in sheets:
                sheet_title = sheet_info.get('properties', {}).get('title', 'Untitled')
                content += f"Sheet: {sheet_title}\n"
                
                # Get sheet data
                range_name = f"'{sheet_title}'"
                result = self.sheets_service.spreadsheets().values().get(
                    spreadsheetId=file_id,
                    range=range_name
                ).execute()
                
                values = result.get('values', [])
                
                for row in values:
                    content += " | ".join(str(cell) for cell in row) + "\n"
                
                content += "\n"
            
            return content
            
        except HttpError as e:
            logger.error(f"Error getting Google Sheet content: {e}")
            return None
    
    def _get_google_slides_content(self, file_id: str) -> Optional[str]:
        """Get content from Google Slides"""
        try:
            # For slides, we'll export as text
            request = self.drive_service.files().export_media(
                fileId=file_id,
                mimeType='text/plain'
            )
            
            file_io = io.BytesIO()
            downloader = MediaIoBaseDownload(file_io, request)
            done = False
            
            while done is False:
                status, done = downloader.next_chunk()
            
            content = file_io.getvalue().decode('utf-8')
            return content
            
        except HttpError as e:
            logger.error(f"Error getting Google Slides content: {e}")
            return None
    
    def _get_pdf_content(self, file_id: str) -> Optional[str]:
        """Get content from PDF file"""
        try:
            # For PDFs, we'll try to export as text if possible
            request = self.drive_service.files().export_media(
                fileId=file_id,
                mimeType='text/plain'
            )
            
            file_io = io.BytesIO()
            downloader = MediaIoBaseDownload(file_io, request)
            done = False
            
            while done is False:
                status, done = downloader.next_chunk()
            
            content = file_io.getvalue().decode('utf-8')
            return content
            
        except HttpError as e:
            logger.warning(f"Cannot extract text from PDF {file_id}: {e}")
            return None
    
    def _get_text_content(self, file_id: str) -> Optional[str]:
        """Get content from text file"""
        try:
            request = self.drive_service.files().get_media(fileId=file_id)
            
            file_io = io.BytesIO()
            downloader = MediaIoBaseDownload(file_io, request)
            done = False
            
            while done is False:
                status, done = downloader.next_chunk()
            
            content = file_io.getvalue().decode('utf-8')
            return content
            
        except HttpError as e:
            logger.error(f"Error getting text content: {e}")
            return None
    
    def _get_doc_content(self, file_id: str) -> Optional[str]:
        """Get content from Word document"""
        try:
            # Export as text
            request = self.drive_service.files().export_media(
                fileId=file_id,
                mimeType='text/plain'
            )
            
            file_io = io.BytesIO()
            downloader = MediaIoBaseDownload(file_io, request)
            done = False
            
            while done is False:
                status, done = downloader.next_chunk()
            
            content = file_io.getvalue().decode('utf-8')
            return content
            
        except HttpError as e:
            logger.error(f"Error getting Word document content: {e}")
            return None
    
    def fetch_all_documents(self, folder_ids: List[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch all accessible documents from Google Drive"""
        try:
            logger.info("Fetching all documents from Google Drive...")
            
            if force_refresh:
                self.cache.clear()
            
            documents = []
            
            # If specific folder IDs are provided, search within those
            if folder_ids:
                for folder_id in folder_ids:
                    files = self.list_files(folder_id=folder_id)
                    documents.extend(self._process_files(files))
            else:
                # Get all supported files
                files = self.list_files()
                documents.extend(self._process_files(files))
            
            # Also check configured document IDs from environment
            legacy_doc_ids = config.faq_document_ids + config.meeting_notes_document_ids
            for doc_id in legacy_doc_ids:
                if doc_id not in [d['document_id'] for d in documents]:
                    try:
                        # Try to get this document
                        file_info = self.drive_service.files().get(
                            fileId=doc_id,
                            fields="id, name, mimeType, parents, modifiedTime"
                        ).execute()
                        
                        content = self.get_file_content(doc_id, file_info['mimeType'])
                        if content:
                            doc_type = 'faq' if doc_id in config.faq_document_ids else 'meeting_notes'
                            documents.append({
                                'document_id': doc_id,
                                'title': file_info.get('name', 'Untitled'),
                                'content': content,
                                'type': doc_type,
                                'mime_type': file_info['mimeType'],
                                'modified_time': file_info.get('modifiedTime'),
                                'source': 'legacy_config'
                            })
                    except Exception as e:
                        logger.warning(f"Could not fetch legacy document {doc_id}: {e}")
            
            logger.info(f"Successfully fetched {len(documents)} documents from Google Drive")
            return documents
            
        except Exception as e:
            logger.error(f"Error fetching documents: {e}")
            return []
    
    def _process_files(self, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process a list of files and extract content"""
        documents = []
        
        for file_info in files:
            file_id = file_info['id']
            file_name = file_info['name']
            mime_type = file_info['mimeType']
            
            # Get file content
            content = self.get_file_content(file_id, mime_type)
            
            if content:
                # Determine document type based on name/content
                doc_type = self._determine_document_type(file_name, content)
                
                documents.append({
                    'document_id': file_id,
                    'title': file_name,
                    'content': content,
                    'type': doc_type,
                    'mime_type': mime_type,
                    'modified_time': file_info.get('modifiedTime'),
                    'source': 'google_drive'
                })
        
        return documents
    
    def _determine_document_type(self, file_name: str, content: str) -> str:
        """Determine document type based on filename and content"""
        file_name_lower = file_name.lower()
        content_lower = content.lower()
        
        # Check for FAQ indicators
        faq_indicators = ['faq', 'frequently asked', 'questions', 'q&a', 'help']
        if any(indicator in file_name_lower for indicator in faq_indicators):
            return 'faq'
        
        # Check for meeting notes indicators
        meeting_indicators = ['meeting', 'notes', 'minutes', 'agenda', 'standup', 'retrospective']
        if any(indicator in file_name_lower for indicator in meeting_indicators):
            return 'meeting_notes'
        
        # Check content for FAQ patterns
        if re.search(r'(^|\n)\s*Q\s*[:?]|question\s*[:?]', content_lower):
            return 'faq'
        
        # Check content for meeting patterns
        if re.search(r'(agenda|action items|decisions|attendees|meeting)', content_lower):
            return 'meeting_notes'
        
        # Default to general
        return 'general'
    
    def test_connection(self) -> bool:
        """Test the Google Drive connection"""
        try:
            # Try to get user info
            about = self.drive_service.about().get(fields="user").execute()
            user_email = about.get('user', {}).get('emailAddress', 'Unknown')
            logger.info(f"Connected to Google Drive as: {user_email}")
            return True
        except Exception as e:
            logger.error(f"Google Drive connection test failed: {e}")
            return False
    
    def get_drive_info(self) -> Dict[str, Any]:
        """Get information about the connected Google Drive"""
        try:
            about = self.drive_service.about().get(fields="user,storageQuota").execute()
            return {
                'user_email': about.get('user', {}).get('emailAddress'),
                'storage_quota': about.get('storageQuota', {}),
                'connection_status': 'connected'
            }
        except Exception as e:
            logger.error(f"Error getting drive info: {e}")
            return {'connection_status': 'error', 'error': str(e)} 