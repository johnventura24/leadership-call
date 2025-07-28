import os
import logging
from typing import Dict, Any, List, Optional
import json
from datetime import datetime
import re
import threading
import time

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config import config
from google_docs_client import GoogleDocsClient
from document_processor import DocumentProcessor
from knowledge_base import KnowledgeBase
from qa_system import QASystem

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SlackKnowledgeBot:
    """Slack bot for the Leadership Knowledge Base Agent"""
    
    def __init__(self):
        # Validate Slack configuration
        if not config.validate_slack_config():
            raise ValueError("Slack configuration is invalid. Please check your environment variables.")
        
        # Initialize Slack app
        self.app = App(token=config.slack_bot_token)
        
        # Initialize knowledge base system
        self.knowledge_base = None
        self.qa_system = None
        self.is_initialized = False
        
        # Bot settings
        self.bot_user_id = None
        self.bot_mention_pattern = None
        
        # Initialize the system
        self._initialize_system()
        
        # Set up event handlers
        self._setup_event_handlers()
        
        # Get bot info
        self._get_bot_info()
    
    def _initialize_system(self):
        """Initialize the knowledge base system"""
        try:
            logger.info("Initializing knowledge base system...")
            
            # Initialize knowledge base
            self.knowledge_base = KnowledgeBase()
            
            # Initialize QA system
            self.qa_system = QASystem(self.knowledge_base)
            
            self.is_initialized = True
            logger.info("Knowledge base system initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize knowledge base system: {e}")
            raise
    
    def _get_bot_info(self):
        """Get bot information for mention detection"""
        try:
            client = WebClient(token=config.slack_bot_token)
            response = client.auth_test()
            self.bot_user_id = response['user_id']
            self.bot_mention_pattern = re.compile(f'<@{self.bot_user_id}>')
            logger.info(f"Bot user ID: {self.bot_user_id}")
            
        except SlackApiError as e:
            logger.error(f"Failed to get bot info: {e}")
    
    def _setup_event_handlers(self):
        """Set up Slack event handlers"""
        
        # Handle app mentions
        @self.app.event("app_mention")
        def handle_app_mention(event, say, client):
            self._handle_question(event, say, client, is_mention=True)
        
        # Handle direct messages
        @self.app.event("message")
        def handle_message(event, say, client):
            # Only handle direct messages (not in channels)
            if event.get("channel_type") == "im":
                self._handle_question(event, say, client, is_mention=False)
        
        # Handle slash commands
        @self.app.command("/ask-kb")
        def handle_ask_command(ack, command, client):
            ack()
            self._handle_slash_command(command, client)
        
        # Handle help command
        @self.app.command("/kb-help")
        def handle_help_command(ack, command, client):
            ack()
            self._handle_help_command(command, client)
        
        # Handle stats command
        @self.app.command("/kb-stats")
        def handle_stats_command(ack, command, client):
            ack()
            self._handle_stats_command(command, client)
    
    def _handle_question(self, event, say, client, is_mention=False):
        """Handle questions from mentions or direct messages"""
        try:
            # Get the question text
            text = event.get("text", "")
            user_id = event.get("user")
            channel_id = event.get("channel")
            
            # Remove bot mention if present
            if self.bot_mention_pattern and is_mention:
                text = self.bot_mention_pattern.sub("", text).strip()
            
            if not text:
                say("Hi! I'm the Leadership Knowledge Base Agent. Ask me any question about our FAQs or meeting notes!")
                return
            
            # Check if system is initialized
            if not self.is_initialized:
                say("⚠️ The knowledge base system is not initialized. Please contact your administrator.")
                return
            
            # Send typing indicator
            try:
                client.chat_postMessage(
                    channel=channel_id,
                    text="🤔 Searching knowledge base...",
                    thread_ts=event.get("ts")
                )
            except:
                pass
            
            # Process the question
            answer_result = self.qa_system.answer_question(text)
            
            # Format the response
            response = self._format_answer_response(answer_result)
            
            # Send the response
            say(response)
            
        except Exception as e:
            logger.error(f"Error handling question: {e}")
            say(f"😞 Sorry, I encountered an error while processing your question: {str(e)}")
    
    def _handle_slash_command(self, command, client):
        """Handle /ask-kb slash command"""
        try:
            question = command.get("text", "").strip()
            channel_id = command.get("channel_id")
            user_id = command.get("user_id")
            
            if not question:
                client.chat_postMessage(
                    channel=channel_id,
                    text="Please provide a question after the command. Example: `/ask-kb What is our remote work policy?`"
                )
                return
            
            # Check if system is initialized
            if not self.is_initialized:
                client.chat_postMessage(
                    channel=channel_id,
                    text="⚠️ The knowledge base system is not initialized. Please contact your administrator."
                )
                return
            
            # Process the question
            answer_result = self.qa_system.answer_question(question)
            
            # Format the response
            response = self._format_answer_response(answer_result)
            
            # Send the response
            client.chat_postMessage(
                channel=channel_id,
                text=response
            )
            
        except Exception as e:
            logger.error(f"Error handling slash command: {e}")
            client.chat_postMessage(
                channel=command.get("channel_id"),
                text=f"😞 Sorry, I encountered an error: {str(e)}"
            )
    
    def _handle_help_command(self, command, client):
        """Handle help command"""
        help_text = """
🤖 **Leadership Knowledge Base Agent Help**

**How to ask questions:**
• Mention me in a channel: `@KnowledgeBot What is our remote work policy?`
• Send me a direct message: `What is our remote work policy?`
• Use slash command: `/ask-kb What is our remote work policy?`

**Available commands:**
• `/ask-kb <question>` - Ask a question
• `/kb-help` - Show this help message
• `/kb-stats` - Show knowledge base statistics

**What I can help with:**
• FAQ questions and answers
• Meeting notes and decisions
• Leadership team information
• Company policies and procedures

**Tips for better answers:**
• Be specific in your questions
• Use keywords from your documents
• Ask one question at a time

Need help? Contact your administrator.
"""
        
        client.chat_postMessage(
            channel=command.get("channel_id"),
            text=help_text
        )
    
    def _handle_stats_command(self, command, client):
        """Handle stats command"""
        try:
            if not self.is_initialized:
                client.chat_postMessage(
                    channel=command.get("channel_id"),
                    text="⚠️ The knowledge base system is not initialized."
                )
                return
            
            # Get knowledge base statistics
            stats = self.knowledge_base.get_collection_stats()
            
            stats_text = f"""
📊 **Knowledge Base Statistics**

**Documents:** {stats.get('total_documents', 0)}
**Document Types:** {', '.join(f"{k}: {v}" for k, v in stats.get('document_types', {}).items())}
**Section Types:** {', '.join(f"{k}: {v}" for k, v in stats.get('section_types', {}).items())}

**System Status:** ✅ Online and ready
**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            
            client.chat_postMessage(
                channel=command.get("channel_id"),
                text=stats_text
            )
            
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            client.chat_postMessage(
                channel=command.get("channel_id"),
                text=f"😞 Sorry, I couldn't retrieve statistics: {str(e)}"
            )
    
    def _format_answer_response(self, answer_result: Dict[str, Any]) -> str:
        """Format the answer result for Slack"""
        question = answer_result.get('question', '')
        answer = answer_result.get('answer', '')
        sources = answer_result.get('sources', [])
        confidence = answer_result.get('confidence', 0.0)
        
        # Format confidence indicator
        if confidence > 0.8:
            confidence_emoji = "🟢"
        elif confidence > 0.6:
            confidence_emoji = "🟡"
        else:
            confidence_emoji = "🔴"
        
        # Start building the response
        response = f"**Question:** {question}\n\n"
        response += f"**Answer:** {answer}\n\n"
        response += f"**Confidence:** {confidence_emoji} {confidence:.2f}\n\n"
        
        # Add sources if available
        if sources:
            response += "**Sources:**\n"
            for i, source in enumerate(sources[:3], 1):  # Limit to 3 sources for readability
                doc_type = source.get('document_type', 'Unknown')
                doc_title = source.get('document_title', 'Untitled')
                section_type = source.get('section_type', 'general')
                
                response += f"{i}. {doc_type.upper()}: {doc_title} ({section_type.replace('_', ' ').title()})\n"
                
                # Add FAQ question if available
                if source.get('faq_question'):
                    response += f"   FAQ: {source['faq_question']}\n"
            
            if len(sources) > 3:
                response += f"   ... and {len(sources) - 3} more sources\n"
        
        return response
    
    def load_documents(self):
        """Load documents from Google Docs"""
        try:
            logger.info("Loading documents from Google Docs...")
            
            # Initialize Google Docs client
            docs_client = GoogleDocsClient()
            
            # Test connection
            if not docs_client.test_connection():
                logger.error("Failed to connect to Google Docs")
                return False
            
            # Fetch documents
            documents = docs_client.fetch_all_documents()
            
            if not documents:
                logger.warning("No documents found")
                return False
            
            # Process documents
            processor = DocumentProcessor()
            processed_chunks = processor.process_all_documents(documents)
            
            # Update knowledge base
            self.knowledge_base.update_documents(processed_chunks)
            
            logger.info(f"Successfully loaded {len(documents)} documents ({len(processed_chunks)} chunks)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load documents: {e}")
            return False
    
    def start(self):
        """Start the Slack bot"""
        try:
            logger.info("Starting Slack bot...")
            
            # Create socket mode handler
            handler = SocketModeHandler(self.app, config.slack_app_token)
            
            logger.info("Slack bot is running! 🚀")
            
            # Start the bot
            handler.start()
            
        except Exception as e:
            logger.error(f"Failed to start Slack bot: {e}")
            raise
    
    def stop(self):
        """Stop the Slack bot"""
        logger.info("Stopping Slack bot...")
        # The handler will be stopped automatically when the process terminates

def main():
    """Main function to run the Slack bot"""
    try:
        # Create and start the bot
        bot = SlackKnowledgeBot()
        
        # Optionally load documents on startup
        if os.getenv("LOAD_DOCS_ON_STARTUP", "false").lower() == "true":
            logger.info("Loading documents on startup...")
            bot.load_documents()
        
        # Start the bot
        bot.start()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot failed to start: {e}")
        raise

if __name__ == "__main__":
    main() 