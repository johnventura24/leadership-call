#!/usr/bin/env python3
"""
Slack Bot Deployment Script
This script runs the Leadership Knowledge Base Agent in Slack
"""

import os
import sys
import logging
import argparse
from datetime import datetime
import signal
import time

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import config
from slack_bot import SlackKnowledgeBot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('slack_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def validate_environment():
    """Validate that all required environment variables are set"""
    logger.info("Validating environment configuration...")
    
    # Check basic configuration
    if not config.validate_config():
        logger.error("Basic configuration validation failed")
        logger.error("Please ensure the following are set:")
        logger.error("1. OPENAI_API_KEY environment variable")
        logger.error("2. Google credentials file (credentials.json)")
        logger.error("3. At least one document ID in FAQ_DOCUMENT_IDS or MEETING_NOTES_DOCUMENT_IDS")
        return False
    
    # Check Slack configuration
    if not config.validate_slack_config():
        logger.error("Slack configuration validation failed")
        logger.error("Please ensure the following are set:")
        logger.error("1. SLACK_BOT_TOKEN")
        logger.error("2. SLACK_SIGNING_SECRET")
        logger.error("3. SLACK_APP_TOKEN")
        return False
    
    logger.info("Environment validation passed")
    return True

def check_dependencies():
    """Check if all required dependencies are installed"""
    logger.info("Checking dependencies...")
    
    try:
        import slack_bolt
        import slack_sdk
        import openai
        import chromadb
        import langchain
        logger.info("All dependencies are available")
        return True
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        logger.error("Please run: pip install -r requirements.txt")
        return False

def setup_signal_handlers(bot):
    """Set up signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        bot.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

def main():
    """Main function to run the Slack bot"""
    parser = argparse.ArgumentParser(description="Leadership Knowledge Base Slack Bot")
    parser.add_argument("--load-docs", action="store_true", help="Load documents on startup")
    parser.add_argument("--validate-only", action="store_true", help="Only validate configuration")
    parser.add_argument("--log-level", default="INFO", help="Log level (DEBUG, INFO, WARNING, ERROR)")
    
    args = parser.parse_args()
    
    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level.upper()))
    
    # Validate environment
    if not validate_environment():
        sys.exit(1)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    if args.validate_only:
        logger.info("Configuration validation completed successfully!")
        sys.exit(0)
    
    # Initialize the bot
    try:
        logger.info("Initializing Slack bot...")
        bot = SlackKnowledgeBot()
        
        # Set up signal handlers
        setup_signal_handlers(bot)
        
        # Load documents if requested
        if args.load_docs:
            logger.info("Loading documents from Google Docs...")
            if bot.load_documents():
                logger.info("Documents loaded successfully")
            else:
                logger.warning("Failed to load documents, but continuing anyway")
        
        # Start the bot
        logger.info("Starting Slack bot...")
        logger.info("Bot is now running! Press Ctrl+C to stop.")
        
        bot.start()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot failed to start: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 