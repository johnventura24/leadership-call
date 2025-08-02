import re
import logging
from typing import List, Dict, Any, Optional
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
import tiktoken

from config import config

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """Process and chunk documents for the knowledge base"""
    
    def __init__(self):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""]
        )
        
        # Initialize tokenizer for token counting
        try:
            self.tokenizer = tiktoken.encoding_for_model("gpt-3.5-turbo")
        except:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize text content"""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove empty lines
        text = re.sub(r'\n\s*\n', '\n', text)
        
        # Remove special characters that might interfere with processing
        text = re.sub(r'[^\w\s\-.,!?():"\'/@#$%&*+=\[\]{}|\\`~<>]', '', text)
        
        # Normalize quotes
        text = re.sub(r'[""]', '"', text)
        text = re.sub(r'['']', "'", text)
        
        return text.strip()
    
    def extract_sections(self, text: str, document_type: str) -> List[Dict[str, Any]]:
        """Extract logical sections from document text"""
        sections = []
        
        if document_type == 'faq':
            sections = self._extract_faq_sections(text)
        elif document_type == 'meeting_notes':
            sections = self._extract_meeting_sections(text)
        else:
            # Default processing for unknown types
            sections = [{'content': text, 'section_type': 'general', 'title': 'Content'}]
        
        return sections
    
    def _extract_faq_sections(self, text: str) -> List[Dict[str, Any]]:
        """Extract FAQ question-answer pairs"""
        sections = []
        
        # Pattern to match FAQ questions (lines that end with ?)
        faq_pattern = r'(?:^|\n)(.+\?)\s*\n(.*?)(?=\n.*\?|\n\n|\Z)'
        
        matches = re.findall(faq_pattern, text, re.MULTILINE | re.DOTALL)
        
        for question, answer in matches:
            question = question.strip()
            answer = answer.strip()
            
            if question and answer:
                sections.append({
                    'content': f"Q: {question}\nA: {answer}",
                    'section_type': 'faq',
                    'title': question,
                    'question': question,
                    'answer': answer
                })
        
        # If no FAQs found, try alternative patterns
        if not sections:
            # Look for Q: A: patterns
            qa_pattern = r'(?:^|\n)(?:Q:|Question:)\s*(.+?)\n(?:A:|Answer:)\s*(.*?)(?=\n(?:Q:|Question:)|\n\n|\Z)'
            matches = re.findall(qa_pattern, text, re.MULTILINE | re.DOTALL)
            
            for question, answer in matches:
                question = question.strip()
                answer = answer.strip()
                
                if question and answer:
                    sections.append({
                        'content': f"Q: {question}\nA: {answer}",
                        'section_type': 'faq',
                        'title': question,
                        'question': question,
                        'answer': answer
                    })
        
        # If still no sections, treat as general content
        if not sections:
            sections = [{'content': text, 'section_type': 'general', 'title': 'FAQ Content'}]
        
        return sections
    
    def _extract_meeting_sections(self, text: str) -> List[Dict[str, Any]]:
        """Extract meeting notes sections"""
        sections = []
        
        # Common meeting section headers
        section_patterns = [
            r'(?:^|\n)((?:agenda|topics?|discussion|action items?|decisions?|notes?|summary).*?):\s*\n(.*?)(?=\n(?:agenda|topics?|discussion|action items?|decisions?|notes?|summary)|\n\n|\Z)',
            r'(?:^|\n)(\d+\.\s*.+?)\n(.*?)(?=\n\d+\.|\n\n|\Z)',
            r'(?:^|\n)(#{1,3}\s*.+?)\n(.*?)(?=\n#{1,3}|\n\n|\Z)'
        ]
        
        for pattern in section_patterns:
            matches = re.findall(pattern, text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
            
            for title, content in matches:
                title = title.strip()
                content = content.strip()
                
                if title and content:
                    sections.append({
                        'content': f"{title}\n{content}",
                        'section_type': 'meeting_section',
                        'title': title
                    })
        
        # If no structured sections found, try to split by common markers
        if not sections:
            # Split by bullet points or numbered lists
            bullet_pattern = r'(?:^|\n)((?:[-*•]\s*.+?)(?:\n[-*•].*)*)'
            matches = re.findall(bullet_pattern, text, re.MULTILINE)
            
            for match in matches:
                content = match.strip()
                if content:
                    sections.append({
                        'content': content,
                        'section_type': 'meeting_bullet',
                        'title': content.split('\n')[0][:50] + '...'
                    })
        
        # If still no sections, treat as general content
        if not sections:
            sections = [{'content': text, 'section_type': 'general', 'title': 'Meeting Notes'}]
        
        return sections
    
    def process_document(self, document: Dict[str, Any]) -> List[Document]:
        """Process a single document into chunks"""
        content = document.get('content', '')
        doc_type = document.get('type', 'general')
        title = document.get('title', 'Untitled')
        doc_id = document.get('document_id', '')
        
        # Clean the text
        cleaned_content = self.clean_text(content)
        
        # Extract sections
        sections = self.extract_sections(cleaned_content, doc_type)
        
        # Create chunks from sections
        chunks = []
        
        for section in sections:
            section_content = section['content']
            section_title = section['title']
            section_type = section['section_type']
            
            # Split section into smaller chunks if needed
            section_chunks = self.text_splitter.split_text(section_content)
            
            for i, chunk_text in enumerate(section_chunks):
                # Create metadata for the chunk
                metadata = {
                    'document_id': doc_id,
                    'document_title': title,
                    'document_type': doc_type,
                    'section_title': section_title,
                    'section_type': section_type,
                    'chunk_index': i,
                    'total_chunks': len(section_chunks),
                    'token_count': len(self.tokenizer.encode(chunk_text))
                }
                
                # Add FAQ-specific metadata
                if section_type == 'faq' and 'question' in section:
                    metadata['question'] = section['question']
                    metadata['answer'] = section['answer']
                
                chunks.append(Document(
                    page_content=chunk_text,
                    metadata=metadata
                ))
        
        logger.info(f"Processed document '{title}' into {len(chunks)} chunks")
        return chunks
    
    def process_all_documents(self, documents: List[Dict[str, Any]]) -> List[Document]:
        """Process all documents into chunks"""
        all_chunks = []
        
        for document in documents:
            doc_chunks = self.process_document(document)
            all_chunks.extend(doc_chunks)
        
        logger.info(f"Processed {len(documents)} documents into {len(all_chunks)} total chunks")
        return all_chunks
    
    def get_chunk_statistics(self, chunks: List[Document]) -> Dict[str, Any]:
        """Get statistics about the processed chunks"""
        total_chunks = len(chunks)
        total_tokens = sum(chunk.metadata.get('token_count', 0) for chunk in chunks)
        
        doc_types = {}
        section_types = {}
        
        for chunk in chunks:
            doc_type = chunk.metadata.get('document_type', 'unknown')
            section_type = chunk.metadata.get('section_type', 'unknown')
            
            doc_types[doc_type] = doc_types.get(doc_type, 0) + 1
            section_types[section_type] = section_types.get(section_type, 0) + 1
        
        return {
            'total_chunks': total_chunks,
            'total_tokens': total_tokens,
            'average_tokens_per_chunk': total_tokens / total_chunks if total_chunks > 0 else 0,
            'document_types': doc_types,
            'section_types': section_types
        } 