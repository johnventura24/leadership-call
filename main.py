#!/usr/bin/env python3
"""
Leadership Knowledge Base Agent
Main application file for running the knowledge base system
"""

import logging
import argparse
import sys
from typing import List, Dict, Any
import json
from datetime import datetime

from config import config
from google_docs_client import GoogleDocsClient
from document_processor import DocumentProcessor
from knowledge_base import KnowledgeBase
from qa_system import QASystem

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def validate_setup():
    """Validate that the system is properly configured"""
    logger.info("Validating system configuration...")
    
    if not config.validate_config():
        logger.error("Configuration validation failed")
        logger.error("Please ensure the following are set:")
        logger.error("1. OPENAI_API_KEY environment variable")
        logger.error("2. Google credentials file (credentials.json)")
        logger.error("3. At least one document ID in FAQ_DOCUMENT_IDS or MEETING_NOTES_DOCUMENT_IDS")
        return False
    
    logger.info("Configuration validation passed")
    return True

def initialize_system():
    """Initialize all system components"""
    logger.info("Initializing knowledge base system...")
    
    try:
        # Initialize knowledge base
        knowledge_base = KnowledgeBase()
        
        # Initialize QA system
        qa_system = QASystem(knowledge_base)
        
        logger.info("System initialized successfully")
        return knowledge_base, qa_system
        
    except Exception as e:
        logger.error(f"Failed to initialize system: {e}")
        raise

def load_documents_from_google_docs():
    """Load and process documents from Google Docs"""
    logger.info("Loading documents from Google Docs...")
    
    try:
        # Initialize Google Docs client
        docs_client = GoogleDocsClient()
        
        # Test connection
        if not docs_client.test_connection():
            logger.error("Failed to connect to Google Docs")
            return None
        
        # Fetch documents
        documents = docs_client.fetch_all_documents()
        
        if not documents:
            logger.warning("No documents found")
            return None
        
        # Process documents
        processor = DocumentProcessor()
        processed_chunks = processor.process_all_documents(documents)
        
        # Print statistics
        stats = processor.get_chunk_statistics(processed_chunks)
        logger.info(f"Processed {len(documents)} documents into {stats['total_chunks']} chunks")
        logger.info(f"Average tokens per chunk: {stats['average_tokens_per_chunk']:.1f}")
        
        return processed_chunks
        
    except Exception as e:
        logger.error(f"Failed to load documents: {e}")
        raise

def update_knowledge_base(knowledge_base: KnowledgeBase, processed_chunks: List):
    """Update the knowledge base with processed document chunks"""
    logger.info("Updating knowledge base...")
    
    try:
        knowledge_base.update_documents(processed_chunks)
        
        # Get and display statistics
        stats = knowledge_base.get_collection_stats()
        logger.info(f"Knowledge base updated with {stats['total_documents']} document chunks")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to update knowledge base: {e}")
        raise

def interactive_qa_session(qa_system: QASystem):
    """Run an interactive Q&A session"""
    logger.info("Starting interactive Q&A session...")
    print("\n" + "="*50)
    print("Leadership Knowledge Base Agent")
    print("Type 'quit' to exit, 'help' for commands")
    print("="*50)
    
    conversation_history = []
    
    while True:
        try:
            # Get user input
            question = input("\nEnter your question: ").strip()
            
            if not question:
                continue
                
            if question.lower() == 'quit':
                break
                
            if question.lower() == 'help':
                print("\nAvailable commands:")
                print("- quit: Exit the program")
                print("- help: Show this help message")
                print("- stats: Show knowledge base statistics")
                print("- faq <search_term>: Search for FAQ suggestions")
                print("- meeting <topic>: Search meeting notes for a topic")
                print("- export: Export conversation history")
                continue
            
            if question.lower().startswith('stats'):
                stats = qa_system.knowledge_base.get_collection_stats()
                print(f"\nKnowledge Base Statistics:")
                print(json.dumps(stats, indent=2))
                continue
            
            if question.lower().startswith('faq '):
                search_term = question[4:].strip()
                suggestions = qa_system.get_faq_suggestions(search_term, 5)
                
                if suggestions:
                    print(f"\nFAQ Suggestions for '{search_term}':")
                    for i, suggestion in enumerate(suggestions, 1):
                        print(f"{i}. Q: {suggestion['question']}")
                        print(f"   A: {suggestion['answer'][:100]}...")
                        print(f"   (Relevance: {suggestion['relevance_score']:.3f})")
                        print()
                else:
                    print("No FAQ suggestions found.")
                continue
            
            if question.lower().startswith('meeting '):
                topic = question[8:].strip()
                topics = qa_system.search_meeting_topics(topic, 5)
                
                if topics:
                    print(f"\nMeeting Topics for '{topic}':")
                    for i, topic_info in enumerate(topics, 1):
                        print(f"{i}. {topic_info['document_title']}")
                        print(f"   Section: {topic_info['section_title']}")
                        print(f"   Content: {topic_info['content'][:150]}...")
                        print(f"   (Relevance: {topic_info['relevance_score']:.3f})")
                        print()
                else:
                    print("No meeting topics found.")
                continue
            
            if question.lower() == 'export':
                if conversation_history:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"conversation_export_{timestamp}.json"
                    
                    export_data = {
                        'conversation_history': conversation_history,
                        'export_timestamp': datetime.now().isoformat()
                    }
                    
                    with open(filename, 'w') as f:
                        json.dump(export_data, f, indent=2)
                    
                    print(f"\nConversation exported to {filename}")
                else:
                    print("No conversation history to export.")
                continue
            
            # Process the question
            print("\nSearching knowledge base...")
            answer_result = qa_system.answer_question(question)
            
            # Display the answer
            print(f"\nQuestion: {question}")
            print(f"Answer: {answer_result['answer']}")
            print(f"Confidence: {answer_result['confidence']:.2f}")
            
            # Display sources
            if answer_result['sources']:
                print("\nSources:")
                for i, source in enumerate(answer_result['sources'], 1):
                    doc_type = source['document_type']
                    doc_title = source['document_title']
                    section_type = source['section_type']
                    relevance = source['relevance_score']
                    
                    print(f"{i}. {doc_type.upper()}: {doc_title} ({section_type.replace('_', ' ').title()})")
                    print(f"   Relevance: {relevance:.3f}")
                    
                    if source.get('faq_question'):
                        print(f"   FAQ: {source['faq_question']}")
            
            # Add to conversation history
            conversation_history.append({
                'question': question,
                'answer': answer_result['answer'],
                'timestamp': answer_result['timestamp'],
                'sources': answer_result['sources'],
                'confidence': answer_result['confidence']
            })
            
        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
        except Exception as e:
            logger.error(f"Error processing question: {e}")
            print(f"Error: {e}")
    
    print("\nGoodbye!")

def main():
    """Main application function"""
    parser = argparse.ArgumentParser(description="Leadership Knowledge Base Agent")
    parser.add_argument("--load-docs", action="store_true", help="Load documents from Google Docs")
    parser.add_argument("--interactive", action="store_true", help="Start interactive Q&A session")
    parser.add_argument("--question", type=str, help="Ask a single question")
    parser.add_argument("--validate", action="store_true", help="Validate configuration only")
    parser.add_argument("--stats", action="store_true", help="Show knowledge base statistics")
    
    args = parser.parse_args()
    
    # Validate configuration
    if not validate_setup():
        sys.exit(1)
    
    if args.validate:
        print("Configuration validation passed!")
        sys.exit(0)
    
    # Initialize system
    try:
        knowledge_base, qa_system = initialize_system()
    except Exception as e:
        logger.error(f"Failed to initialize system: {e}")
        sys.exit(1)
    
    # Load documents if requested
    if args.load_docs:
        try:
            processed_chunks = load_documents_from_google_docs()
            if processed_chunks:
                update_knowledge_base(knowledge_base, processed_chunks)
            else:
                logger.warning("No documents were loaded")
        except Exception as e:
            logger.error(f"Failed to load documents: {e}")
            sys.exit(1)
    
    # Show statistics if requested
    if args.stats:
        stats = knowledge_base.get_collection_stats()
        print("\nKnowledge Base Statistics:")
        print(json.dumps(stats, indent=2))
        return
    
    # Handle single question
    if args.question:
        try:
            answer_result = qa_system.answer_question(args.question)
            
            print(f"\nQuestion: {args.question}")
            print(f"Answer: {answer_result['answer']}")
            print(f"Confidence: {answer_result['confidence']:.2f}")
            
            if answer_result['sources']:
                print("\nSources:")
                for i, source in enumerate(answer_result['sources'], 1):
                    print(f"{i}. {source['document_type'].upper()}: {source['document_title']}")
        except Exception as e:
            logger.error(f"Failed to answer question: {e}")
            sys.exit(1)
        return
    
    # Start interactive session
    if args.interactive:
        interactive_qa_session(qa_system)
        return
    
    # If no specific action, show help
    parser.print_help()

if __name__ == "__main__":
    main() 