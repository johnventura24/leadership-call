from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging
import json
from datetime import datetime, timedelta
import os
import asyncio
from contextlib import asynccontextmanager
import uvicorn

from config import config
from google_drive_client import GoogleDriveClient
from document_processor import DocumentProcessor
from knowledge_base import KnowledgeBase
from qa_system import QASystem

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic models for API
class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000, description="The question to ask")
    max_context_items: int = Field(default=5, ge=1, le=20, description="Maximum number of context items to retrieve")
    include_sources: bool = Field(default=True, description="Whether to include source information")

class QuestionResponse(BaseModel):
    answer: str
    confidence: float
    sources: List[Dict[str, Any]]
    question: str
    timestamp: str
    processing_time: float

class DocumentSyncRequest(BaseModel):
    force_refresh: bool = Field(default=False, description="Force refresh of all documents")
    folder_ids: Optional[List[str]] = Field(default=None, description="Specific folder IDs to sync")

class DocumentSyncResponse(BaseModel):
    success: bool
    documents_processed: int
    chunks_created: int
    processing_time: float
    message: str

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    components: Dict[str, str]

class StatsResponse(BaseModel):
    knowledge_base_stats: Dict[str, Any]
    system_info: Dict[str, Any]
    uptime: str

# Global variables
knowledge_base = None
qa_system = None
google_drive_client = None
app_start_time = datetime.now()

# Security
security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Verify API token"""
    expected_token = os.getenv("API_TOKEN")
    if not expected_token:
        raise HTTPException(status_code=500, detail="API token not configured")
    
    if credentials.credentials != expected_token:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    
    return credentials

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    logger.info("Starting Leadership Knowledge Base API...")
    await initialize_system()
    
    # Optionally load documents on startup
    if os.getenv("LOAD_DOCS_ON_STARTUP", "false").lower() == "true":
        logger.info("Loading documents on startup...")
        await load_documents_background()
    
    logger.info("API is ready!")
    yield
    
    # Shutdown
    logger.info("Shutting down API...")

# Create FastAPI app
app = FastAPI(
    title="Leadership Knowledge Base API",
    description="AI-powered knowledge base agent for accessing Google Drive documents",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def initialize_system():
    """Initialize the knowledge base system"""
    global knowledge_base, qa_system, google_drive_client
    
    try:
        logger.info("Initializing system components...")
        
        # Initialize Google Drive client
        google_drive_client = GoogleDriveClient()
        
        # Initialize knowledge base
        knowledge_base = KnowledgeBase()
        
        # Initialize QA system
        qa_system = QASystem(knowledge_base)
        
        logger.info("System initialization completed successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize system: {e}")
        raise

async def load_documents_background():
    """Load documents in the background"""
    try:
        logger.info("Starting background document loading...")
        
        # Fetch documents from Google Drive
        documents = google_drive_client.fetch_all_documents()
        
        if not documents:
            logger.warning("No documents found in Google Drive")
            return
        
        # Process documents
        processor = DocumentProcessor()
        processed_chunks = processor.process_all_documents(documents)
        
        # Update knowledge base
        knowledge_base.update_documents(processed_chunks)
        
        logger.info(f"Successfully loaded {len(documents)} documents ({len(processed_chunks)} chunks)")
        
    except Exception as e:
        logger.error(f"Background document loading failed: {e}")

@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint"""
    return {
        "message": "Leadership Knowledge Base API",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/docs"
    }

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    try:
        # Check system components
        components = {
            "knowledge_base": "healthy" if knowledge_base else "unavailable",
            "qa_system": "healthy" if qa_system else "unavailable",
            "google_drive": "healthy" if google_drive_client else "unavailable",
        }
        
        # Test knowledge base connection
        if knowledge_base:
            try:
                stats = knowledge_base.get_collection_stats()
                if stats.get('total_documents', 0) > 0:
                    components["knowledge_base"] = "healthy"
                else:
                    components["knowledge_base"] = "no_data"
            except Exception as e:
                components["knowledge_base"] = f"error: {str(e)}"
        
        overall_status = "healthy" if all(status == "healthy" for status in components.values()) else "degraded"
        
        return HealthResponse(
            status=overall_status,
            timestamp=datetime.now().isoformat(),
            version="1.0.0",
            components=components
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail="Health check failed")

@app.post("/ask", response_model=QuestionResponse)
async def ask_question(
    request: QuestionRequest,
    credentials: HTTPAuthorizationCredentials = Depends(verify_token)
):
    """Ask a question to the knowledge base"""
    start_time = datetime.now()
    
    try:
        if not qa_system:
            raise HTTPException(status_code=503, detail="QA system not initialized")
        
        # Process the question
        answer_result = qa_system.answer_question(
            request.question,
            max_context_items=request.max_context_items
        )
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Format response
        response = QuestionResponse(
            answer=answer_result['answer'],
            confidence=answer_result['confidence'],
            sources=answer_result['sources'] if request.include_sources else [],
            question=request.question,
            timestamp=answer_result['timestamp'],
            processing_time=processing_time
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Question processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process question: {str(e)}")

@app.post("/sync", response_model=DocumentSyncResponse)
async def sync_documents(
    request: DocumentSyncRequest,
    background_tasks: BackgroundTasks,
    credentials: HTTPAuthorizationCredentials = Depends(verify_token)
):
    """Sync documents from Google Drive"""
    start_time = datetime.now()
    
    try:
        if not google_drive_client:
            raise HTTPException(status_code=503, detail="Google Drive client not initialized")
        
        # Fetch documents
        documents = google_drive_client.fetch_all_documents(
            folder_ids=request.folder_ids,
            force_refresh=request.force_refresh
        )
        
        if not documents:
            return DocumentSyncResponse(
                success=True,
                documents_processed=0,
                chunks_created=0,
                processing_time=(datetime.now() - start_time).total_seconds(),
                message="No documents found to sync"
            )
        
        # Process documents
        processor = DocumentProcessor()
        processed_chunks = processor.process_all_documents(documents)
        
        # Update knowledge base
        knowledge_base.update_documents(processed_chunks)
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return DocumentSyncResponse(
            success=True,
            documents_processed=len(documents),
            chunks_created=len(processed_chunks),
            processing_time=processing_time,
            message=f"Successfully synced {len(documents)} documents"
        )
        
    except Exception as e:
        logger.error(f"Document sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Document sync failed: {str(e)}")

@app.get("/stats", response_model=StatsResponse)
async def get_stats(credentials: HTTPAuthorizationCredentials = Depends(verify_token)):
    """Get system statistics"""
    try:
        # Knowledge base stats
        kb_stats = knowledge_base.get_collection_stats() if knowledge_base else {}
        
        # System info
        system_info = {
            "config_valid": config.validate_config(),
            "documents_loaded": kb_stats.get('total_documents', 0),
            "openai_model": config.qa_model,
            "embedding_model": config.embedding_model,
            "vector_store_path": config.vector_store_path
        }
        
        # Calculate uptime
        uptime = datetime.now() - app_start_time
        uptime_str = str(uptime).split('.')[0]  # Remove microseconds
        
        return StatsResponse(
            knowledge_base_stats=kb_stats,
            system_info=system_info,
            uptime=uptime_str
        )
        
    except Exception as e:
        logger.error(f"Stats retrieval failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")

@app.get("/search/faq")
async def search_faq(
    query: str,
    limit: int = 5,
    credentials: HTTPAuthorizationCredentials = Depends(verify_token)
):
    """Search FAQ documents"""
    try:
        if not qa_system:
            raise HTTPException(status_code=503, detail="QA system not initialized")
        
        suggestions = qa_system.get_faq_suggestions(query, limit)
        
        return {
            "query": query,
            "suggestions": suggestions,
            "count": len(suggestions)
        }
        
    except Exception as e:
        logger.error(f"FAQ search failed: {e}")
        raise HTTPException(status_code=500, detail="FAQ search failed")

@app.get("/search/meetings")
async def search_meetings(
    topic: str,
    limit: int = 5,
    credentials: HTTPAuthorizationCredentials = Depends(verify_token)
):
    """Search meeting notes"""
    try:
        if not qa_system:
            raise HTTPException(status_code=503, detail="QA system not initialized")
        
        topics = qa_system.search_meeting_topics(topic, limit)
        
        return {
            "topic": topic,
            "results": topics,
            "count": len(topics)
        }
        
    except Exception as e:
        logger.error(f"Meeting search failed: {e}")
        raise HTTPException(status_code=500, detail="Meeting search failed")

@app.post("/documents/refresh")
async def refresh_documents(
    background_tasks: BackgroundTasks,
    credentials: HTTPAuthorizationCredentials = Depends(verify_token)
):
    """Refresh all documents in the background"""
    try:
        # Start background task
        background_tasks.add_task(load_documents_background)
        
        return {
            "message": "Document refresh started in background",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Document refresh failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to start document refresh")

@app.get("/documents/list")
async def list_documents(credentials: HTTPAuthorizationCredentials = Depends(verify_token)):
    """List all documents in the knowledge base"""
    try:
        if not knowledge_base:
            raise HTTPException(status_code=503, detail="Knowledge base not initialized")
        
        # Get document metadata
        all_docs = knowledge_base.vector_store.get()
        
        # Extract unique documents
        documents = {}
        if all_docs and 'metadatas' in all_docs:
            for metadata in all_docs['metadatas']:
                if metadata:
                    doc_id = metadata.get('document_id')
                    if doc_id and doc_id not in documents:
                        documents[doc_id] = {
                            'id': doc_id,
                            'title': metadata.get('document_title', 'Untitled'),
                            'type': metadata.get('document_type', 'unknown'),
                            'added_at': metadata.get('added_at')
                        }
        
        return {
            "documents": list(documents.values()),
            "count": len(documents)
        }
        
    except Exception as e:
        logger.error(f"Document listing failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to list documents")

if __name__ == "__main__":
    # Run the server
    uvicorn.run(
        "api_service:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        log_level="info",
        reload=os.getenv("ENVIRONMENT", "production") == "development"
    ) 