import os
import json
from typing import List, Dict, Any, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging

from config import config

logger = logging.getLogger(__name__)

class GoogleDocsClient:
    """Client for interacting with Google Docs API"""
    
    SCOPES = ['https://www.googleapis.com/auth/documents.readonly']
    
    def __init__(self):
        self.service = None
        self.credentials = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Docs API"""
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
        self.service = build('docs', 'v1', credentials=creds)
    
    def get_document_content(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get content from a Google Docs document"""
        try:
            document = self.service.documents().get(documentId=document_id).execute()
            return document
        except HttpError as e:
            logger.error(f"Error fetching document {document_id}: {e}")
            return None
    
    def extract_text_from_document(self, document: Dict[str, Any]) -> str:
        """Extract plain text from a Google Docs document structure"""
        def extract_text_from_element(element):
            """Recursively extract text from document elements"""
            text = ""
            
            if 'textRun' in element:
                text += element['textRun']['content']
            elif 'pageBreak' in element:
                text += '\n\n--- Page Break ---\n\n'
            
            return text
        
        def extract_text_from_paragraph(paragraph):
            """Extract text from a paragraph"""
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
                    # Handle table content
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
    
    def get_document_metadata(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a document"""
        try:
            document = self.service.documents().get(documentId=document_id).execute()
            return {
                'title': document.get('title', 'Untitled Document'),
                'document_id': document_id,
                'created_time': document.get('createdTime'),
                'modified_time': document.get('modifiedTime'),
                'revision_id': document.get('revisionId')
            }
        except HttpError as e:
            logger.error(f"Error fetching document metadata {document_id}: {e}")
            return None
    
    def fetch_all_documents(self) -> List[Dict[str, Any]]:
        """Fetch all configured documents with their content and metadata"""
        documents = []
        
        all_doc_ids = config.get_all_document_ids()
        
        for doc_id in all_doc_ids:
            logger.info(f"Fetching document: {doc_id}")
            
            # Get document content
            document = self.get_document_content(doc_id)
            if not document:
                logger.warning(f"Could not fetch document {doc_id}")
                continue
            
            # Extract text content
            text_content = self.extract_text_from_document(document)
            
            # Get metadata
            metadata = self.get_document_metadata(doc_id)
            
            # Determine document type
            doc_type = 'faq' if doc_id in config.faq_document_ids else 'meeting_notes'
            
            documents.append({
                'document_id': doc_id,
                'title': document.get('title', 'Untitled Document'),
                'content': text_content,
                'metadata': metadata,
                'type': doc_type
            })
        
        logger.info(f"Successfully fetched {len(documents)} documents")
        return documents
    
    def test_connection(self) -> bool:
        """Test the Google Docs API connection"""
        try:
            # Try to fetch a test document (first available document)
            all_doc_ids = config.get_all_document_ids()
            if not all_doc_ids:
                logger.warning("No document IDs configured")
                return False
            
            test_doc_id = all_doc_ids[0]
            document = self.get_document_content(test_doc_id)
            return document is not None
        except Exception as e:
            logger.error(f"Google Docs API connection test failed: {e}")
            return False 