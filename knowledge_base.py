import os
import logging
from typing import List, Dict, Any, Optional, Tuple
import chromadb
from chromadb.config import Settings
from langchain.schema import Document
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Chroma
import numpy as np
from datetime import datetime

from config import config

logger = logging.getLogger(__name__)

class KnowledgeBase:
    """Vector-based knowledge base for document storage and retrieval"""
    
    def __init__(self):
        self.embeddings = OpenAIEmbeddings(
            openai_api_key=config.openai_api_key,
            model=config.embedding_model
        )
        
        self.vector_store = None
        self.collection_name = "leadership_kb"
        self.persist_directory = config.vector_store_path
        
        # Initialize ChromaDB
        self._initialize_vector_store()
    
    def _initialize_vector_store(self):
        """Initialize the vector store"""
        try:
            # Create persist directory if it doesn't exist
            os.makedirs(self.persist_directory, exist_ok=True)
            
            # Initialize Chroma vector store
            self.vector_store = Chroma(
                collection_name=self.collection_name,
                embedding_function=self.embeddings,
                persist_directory=self.persist_directory
            )
            
            logger.info(f"Vector store initialized at {self.persist_directory}")
            
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            raise
    
    def add_documents(self, documents: List[Document], batch_size: int = 100):
        """Add documents to the knowledge base"""
        if not documents:
            logger.warning("No documents to add to knowledge base")
            return
        
        logger.info(f"Adding {len(documents)} documents to knowledge base")
        
        # Process documents in batches to avoid memory issues
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            
            try:
                # Add timestamp to metadata
                for doc in batch:
                    doc.metadata['added_at'] = datetime.now().isoformat()
                
                # Add documents to vector store
                self.vector_store.add_documents(batch)
                
                logger.info(f"Added batch {i//batch_size + 1}/{(len(documents)-1)//batch_size + 1}")
                
            except Exception as e:
                logger.error(f"Failed to add batch {i//batch_size + 1}: {e}")
                raise
        
        # Persist the vector store
        self.vector_store.persist()
        logger.info("Knowledge base updated and persisted")
    
    def search_similar(self, query: str, k: int = 5, filter_dict: Optional[Dict[str, Any]] = None) -> List[Tuple[Document, float]]:
        """Search for similar documents"""
        try:
            # Perform similarity search with scores
            results = self.vector_store.similarity_search_with_score(
                query,
                k=k,
                filter=filter_dict
            )
            
            logger.info(f"Found {len(results)} similar documents for query: {query[:50]}...")
            return results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def search_by_document_type(self, query: str, document_type: str, k: int = 5) -> List[Tuple[Document, float]]:
        """Search within a specific document type"""
        filter_dict = {"document_type": document_type}
        return self.search_similar(query, k, filter_dict)
    
    def search_faqs(self, query: str, k: int = 5) -> List[Tuple[Document, float]]:
        """Search specifically in FAQ documents"""
        return self.search_by_document_type(query, "faq", k)
    
    def search_meeting_notes(self, query: str, k: int = 5) -> List[Tuple[Document, float]]:
        """Search specifically in meeting notes"""
        return self.search_by_document_type(query, "meeting_notes", k)
    
    def get_relevant_context(self, query: str, max_chunks: int = 5, relevance_threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Get relevant context for a query with filtering"""
        # First, search in FAQs (higher priority)
        faq_results = self.search_faqs(query, max_chunks // 2 + 1)
        
        # Then, search in meeting notes
        meeting_results = self.search_meeting_notes(query, max_chunks // 2 + 1)
        
        # Combine and sort by relevance
        all_results = faq_results + meeting_results
        all_results.sort(key=lambda x: x[1])  # Sort by score (lower is better)
        
        # Filter by relevance threshold and format results
        relevant_context = []
        for doc, score in all_results[:max_chunks]:
            if score <= relevance_threshold:
                context_item = {
                    'content': doc.page_content,
                    'metadata': doc.metadata,
                    'relevance_score': score,
                    'document_type': doc.metadata.get('document_type'),
                    'document_title': doc.metadata.get('document_title'),
                    'section_type': doc.metadata.get('section_type')
                }
                
                # Add FAQ-specific information
                if doc.metadata.get('section_type') == 'faq':
                    context_item['question'] = doc.metadata.get('question')
                    context_item['answer'] = doc.metadata.get('answer')
                
                relevant_context.append(context_item)
        
        logger.info(f"Retrieved {len(relevant_context)} relevant context items")
        return relevant_context
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the knowledge base"""
        try:
            # Get collection info
            collection = self.vector_store._collection
            count = collection.count()
            
            # Get all documents to analyze metadata
            all_docs = self.vector_store.get()
            
            # Analyze document types
            doc_types = {}
            section_types = {}
            
            if all_docs and 'metadatas' in all_docs:
                for metadata in all_docs['metadatas']:
                    if metadata:
                        doc_type = metadata.get('document_type', 'unknown')
                        section_type = metadata.get('section_type', 'unknown')
                        
                        doc_types[doc_type] = doc_types.get(doc_type, 0) + 1
                        section_types[section_type] = section_types.get(section_type, 0) + 1
            
            return {
                'total_documents': count,
                'document_types': doc_types,
                'section_types': section_types,
                'collection_name': self.collection_name,
                'persist_directory': self.persist_directory
            }
            
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {}
    
    def clear_knowledge_base(self):
        """Clear all documents from the knowledge base"""
        try:
            # Delete the collection
            self.vector_store.delete_collection()
            
            # Reinitialize
            self._initialize_vector_store()
            
            logger.info("Knowledge base cleared and reinitialized")
            
        except Exception as e:
            logger.error(f"Failed to clear knowledge base: {e}")
            raise
    
    def update_documents(self, documents: List[Document]):
        """Update the knowledge base with new documents (replaces existing)"""
        logger.info("Updating knowledge base with new documents")
        
        # Clear existing documents
        self.clear_knowledge_base()
        
        # Add new documents
        self.add_documents(documents)
        
        logger.info("Knowledge base updated successfully")
    
    def search_by_metadata(self, metadata_filter: Dict[str, Any], k: int = 10) -> List[Document]:
        """Search documents by metadata criteria"""
        try:
            results = self.vector_store.get(
                where=metadata_filter,
                limit=k
            )
            
            documents = []
            if results and 'documents' in results and 'metadatas' in results:
                for i, doc_content in enumerate(results['documents']):
                    metadata = results['metadatas'][i] if i < len(results['metadatas']) else {}
                    documents.append(Document(
                        page_content=doc_content,
                        metadata=metadata
                    ))
            
            return documents
            
        except Exception as e:
            logger.error(f"Metadata search failed: {e}")
            return []
    
    def get_document_by_id(self, document_id: str) -> List[Document]:
        """Get all chunks for a specific document"""
        return self.search_by_metadata({"document_id": document_id})
    
    def backup_knowledge_base(self, backup_path: str):
        """Create a backup of the knowledge base"""
        try:
            import shutil
            shutil.copytree(self.persist_directory, backup_path)
            logger.info(f"Knowledge base backed up to {backup_path}")
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            raise
    
    def restore_knowledge_base(self, backup_path: str):
        """Restore knowledge base from backup"""
        try:
            import shutil
            if os.path.exists(self.persist_directory):
                shutil.rmtree(self.persist_directory)
            shutil.copytree(backup_path, self.persist_directory)
            
            # Reinitialize vector store
            self._initialize_vector_store()
            
            logger.info(f"Knowledge base restored from {backup_path}")
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            raise 