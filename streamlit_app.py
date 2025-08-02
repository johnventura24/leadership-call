import streamlit as st
import logging
from typing import Dict, Any, List
import json
from datetime import datetime
import os
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from config import config
from google_docs_client import GoogleDocsClient
from document_processor import DocumentProcessor
from knowledge_base import KnowledgeBase
from qa_system import QASystem

# Page configuration
st.set_page_config(
    page_title="Leadership Knowledge Base Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    
    .question-box {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
    }
    
    .answer-box {
        background-color: #ffffff;
        border-left: 4px solid #1f77b4;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }
    
    .source-box {
        background-color: #f8f9fa;
        border-radius: 5px;
        padding: 0.5rem;
        margin: 0.5rem 0;
        font-size: 0.9rem;
    }
    
    .confidence-high { color: #28a745; }
    .confidence-medium { color: #ffc107; }
    .confidence-low { color: #dc3545; }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'conversation_history' not in st.session_state:
    st.session_state.conversation_history = []

if 'knowledge_base' not in st.session_state:
    st.session_state.knowledge_base = None

if 'qa_system' not in st.session_state:
    st.session_state.qa_system = None

if 'initialized' not in st.session_state:
    st.session_state.initialized = False

def initialize_system():
    """Initialize the knowledge base system"""
    try:
        with st.spinner("Initializing knowledge base system..."):
            # Validate configuration
            if not config.validate_config():
                st.error("Configuration validation failed. Please check your environment variables.")
                return False
            
            # Initialize knowledge base
            knowledge_base = KnowledgeBase()
            
            # Initialize QA system
            qa_system = QASystem(knowledge_base)
            
            # Store in session state
            st.session_state.knowledge_base = knowledge_base
            st.session_state.qa_system = qa_system
            st.session_state.initialized = True
            
            return True
            
    except Exception as e:
        st.error(f"Failed to initialize system: {str(e)}")
        logger.error(f"System initialization failed: {e}")
        return False

def load_documents():
    """Load documents from Google Docs"""
    try:
        with st.spinner("Loading documents from Google Docs..."):
            # Initialize Google Docs client
            docs_client = GoogleDocsClient()
            
            # Test connection
            if not docs_client.test_connection():
                st.error("Failed to connect to Google Docs. Please check your credentials.")
                return False
            
            # Fetch documents
            documents = docs_client.fetch_all_documents()
            
            if not documents:
                st.warning("No documents found. Please check your document IDs.")
                return False
            
            # Process documents
            processor = DocumentProcessor()
            processed_chunks = processor.process_all_documents(documents)
            
            # Update knowledge base
            st.session_state.knowledge_base.update_documents(processed_chunks)
            
            st.success(f"Successfully loaded {len(documents)} documents ({len(processed_chunks)} chunks)")
            
            # Show statistics
            stats = processor.get_chunk_statistics(processed_chunks)
            st.info(f"Total chunks: {stats['total_chunks']}, Average tokens per chunk: {stats['average_tokens_per_chunk']:.1f}")
            
            return True
            
    except Exception as e:
        st.error(f"Failed to load documents: {str(e)}")
        logger.error(f"Document loading failed: {e}")
        return False

def display_answer(answer_result: Dict[str, Any]):
    """Display the answer with sources and confidence"""
    question = answer_result.get('question', '')
    answer = answer_result.get('answer', '')
    sources = answer_result.get('sources', [])
    confidence = answer_result.get('confidence', 0.0)
    
    # Display question
    st.markdown(f'<div class="question-box"><strong>Question:</strong> {question}</div>', unsafe_allow_html=True)
    
    # Display answer
    st.markdown(f'<div class="answer-box"><strong>Answer:</strong><br>{answer}</div>', unsafe_allow_html=True)
    
    # Display confidence
    confidence_color = "confidence-high" if confidence > 0.7 else "confidence-medium" if confidence > 0.4 else "confidence-low"
    st.markdown(f'<p class="{confidence_color}"><strong>Confidence:</strong> {confidence:.2f}</p>', unsafe_allow_html=True)
    
    # Display sources
    if sources:
        st.markdown("**Sources:**")
        for i, source in enumerate(sources, 1):
            doc_type = source.get('document_type', 'Unknown')
            doc_title = source.get('document_title', 'Untitled')
            section_type = source.get('section_type', 'general')
            relevance = source.get('relevance_score', 0.0)
            
            source_text = f"{i}. **{doc_type.upper()}**: {doc_title} ({section_type.replace('_', ' ').title()}) - Relevance: {relevance:.3f}"
            
            if source.get('faq_question'):
                source_text += f"<br>FAQ: {source['faq_question']}"
            
            st.markdown(f'<div class="source-box">{source_text}</div>', unsafe_allow_html=True)

def main():
    """Main application function"""
    
    # Header
    st.markdown('<h1 class="main-header">🤖 Leadership Knowledge Base Agent</h1>', unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.header("📋 System Configuration")
        
        # Configuration info
        with st.expander("📊 Configuration Status"):
            config_info = config.get_config_info()
            st.json(config_info)
        
        # System initialization
        if not st.session_state.initialized:
            if st.button("🚀 Initialize System"):
                if initialize_system():
                    st.success("System initialized successfully!")
                    st.rerun()
        else:
            st.success("✅ System initialized")
        
        # Document loading
        if st.session_state.initialized:
            if st.button("📚 Load Documents"):
                if load_documents():
                    st.rerun()
        
        # Knowledge base statistics
        if st.session_state.knowledge_base:
            with st.expander("📈 Knowledge Base Stats"):
                stats = st.session_state.knowledge_base.get_collection_stats()
                st.json(stats)
        
        # Clear conversation
        if st.button("🧹 Clear Conversation"):
            st.session_state.conversation_history = []
            st.rerun()
    
    # Main content area
    if not st.session_state.initialized:
        st.info("👈 Please initialize the system using the sidebar")
        return
    
    if not st.session_state.knowledge_base:
        st.warning("Knowledge base not loaded. Please load documents first.")
        return
    
    # Question input
    st.header("❓ Ask a Question")
    
    # Question input methods
    input_method = st.radio("Choose input method:", ["Type Question", "Select from FAQ Suggestions"])
    
    if input_method == "Type Question":
        question = st.text_input("Enter your question:", placeholder="e.g., What is our remote work policy?")
        
    else:  # FAQ Suggestions
        search_term = st.text_input("Search FAQs:", placeholder="e.g., remote work")
        question = None
        
        if search_term:
            suggestions = st.session_state.qa_system.get_faq_suggestions(search_term, 5)
            
            if suggestions:
                st.write("**FAQ Suggestions:**")
                for i, suggestion in enumerate(suggestions):
                    if st.button(f"Q: {suggestion['question']}", key=f"faq_{i}"):
                        question = suggestion['question']
            else:
                st.info("No FAQ suggestions found for this search term.")
    
    # Answer question
    if question:
        with st.spinner("Searching knowledge base..."):
            answer_result = st.session_state.qa_system.answer_question(question)
            
            # Display answer
            display_answer(answer_result)
            
            # Add to conversation history
            st.session_state.conversation_history.append({
                'question': question,
                'answer': answer_result['answer'],
                'timestamp': answer_result['timestamp'],
                'sources': answer_result['sources'],
                'confidence': answer_result['confidence']
            })
    
    # Advanced features
    st.header("🔍 Advanced Features")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📋 Meeting Topics Search")
        meeting_topic = st.text_input("Search meeting topics:", placeholder="e.g., budget planning")
        
        if meeting_topic:
            topics = st.session_state.qa_system.search_meeting_topics(meeting_topic, 5)
            
            if topics:
                for topic in topics:
                    st.markdown(f"""
                    **{topic['document_title']}**
                    - Section: {topic['section_title']}
                    - Relevance: {topic['relevance_score']:.3f}
                    
                    {topic['content'][:200]}...
                    """)
            else:
                st.info("No meeting topics found.")
    
    with col2:
        st.subheader("📊 Answer Quality Check")
        if st.session_state.conversation_history:
            last_answer = st.session_state.conversation_history[-1]
            quality_metrics = st.session_state.qa_system.validate_answer_quality(last_answer)
            
            st.metric("Overall Quality", f"{quality_metrics['overall_quality']:.2f}")
            st.metric("Quality Level", quality_metrics['quality_level'])
            st.metric("Sources Used", len(last_answer['sources']))
            st.metric("Confidence", f"{last_answer['confidence']:.2f}")
    
    # Conversation history
    if st.session_state.conversation_history:
        st.header("💬 Conversation History")
        
        for i, entry in enumerate(reversed(st.session_state.conversation_history[-5:])):
            with st.expander(f"Q: {entry['question'][:50]}..." if len(entry['question']) > 50 else f"Q: {entry['question']}"):
                st.write(f"**Question:** {entry['question']}")
                st.write(f"**Answer:** {entry['answer']}")
                st.write(f"**Confidence:** {entry['confidence']:.2f}")
                st.write(f"**Timestamp:** {entry['timestamp']}")
                
                if entry['sources']:
                    st.write("**Sources:**")
                    for source in entry['sources']:
                        st.write(f"- {source['document_type'].upper()}: {source['document_title']}")
    
    # Export conversation
    if st.session_state.conversation_history:
        st.header("📤 Export Conversation")
        
        if st.button("Export as JSON"):
            export_data = {
                'conversation_history': st.session_state.conversation_history,
                'export_timestamp': datetime.now().isoformat()
            }
            
            st.download_button(
                label="Download Conversation",
                data=json.dumps(export_data, indent=2),
                file_name=f"conversation_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )

if __name__ == "__main__":
    main() 