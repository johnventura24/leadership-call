import os
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv
import json
import logging

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class Config:
    """Configuration management for the Leadership Knowledge Base Agent"""
    
    def __init__(self):
        # Environment
        self.environment = os.getenv('ENVIRONMENT', 'development')
        self.is_production = self.environment == 'production'
        
        # OpenAI Configuration
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.embedding_model = os.getenv('EMBEDDING_MODEL', 'text-embedding-ada-002')
        self.qa_model = os.getenv('QA_MODEL', 'gpt-3.5-turbo')
        self.max_tokens = int(os.getenv('MAX_TOKENS', '1000'))
        self.temperature = float(os.getenv('TEMPERATURE', '0.7'))
        
        # Google Configuration
        self.google_credentials_path = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
        self.google_token_path = os.getenv('GOOGLE_TOKEN_PATH', 'token.json')
        
        # Handle Google credentials from environment (for cloud deployment)
        google_creds_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
        if google_creds_json and not os.path.exists(self.google_credentials_path):
            try:
                # Decode if base64 encoded
                import base64
                try:
                    decoded = base64.b64decode(google_creds_json).decode('utf-8')
                    google_creds_json = decoded
                except:
                    pass
                
                # Write credentials to file
                with open(self.google_credentials_path, 'w') as f:
                    if google_creds_json.startswith('{'):
                        f.write(google_creds_json)
                    else:
                        f.write(json.dumps(json.loads(google_creds_json), indent=2))
                
                logger.info("Google credentials written from environment variable")
            except Exception as e:
                logger.error(f"Error writing Google credentials: {e}")
        
        # Document Configuration (legacy support)
        self.faq_document_ids = self._parse_document_ids(os.getenv('FAQ_DOCUMENT_IDS', ''))
        self.meeting_notes_document_ids = self._parse_document_ids(os.getenv('MEETING_NOTES_DOCUMENT_IDS', ''))
        
        # Vector Store Configuration
        self.vector_store_path = os.getenv('VECTOR_STORE_PATH', './vector_store')
        self.collection_name = os.getenv('COLLECTION_NAME', 'leadership_knowledge_base')
        
        # Text Processing Configuration
        self.chunk_size = int(os.getenv('CHUNK_SIZE', '1000'))
        self.chunk_overlap = int(os.getenv('CHUNK_OVERLAP', '200'))
        
        # API Configuration
        self.api_host = os.getenv('API_HOST', '0.0.0.0')
        self.api_port = int(os.getenv('PORT', '8000'))
        self.api_token = os.getenv('API_TOKEN')
        
        # Database Configuration (for cloud deployment)
        self.database_url = os.getenv('DATABASE_URL')
        self.redis_url = os.getenv('REDIS_URL')
        
        # Slack Configuration
        self.slack_bot_token = os.getenv('SLACK_BOT_TOKEN')
        self.slack_signing_secret = os.getenv('SLACK_SIGNING_SECRET')
        self.slack_app_token = os.getenv('SLACK_APP_TOKEN')
        
        # Cloud Configuration
        self.aws_region = os.getenv('AWS_REGION', 'us-east-1')
        self.ecr_repository = os.getenv('ECR_REPOSITORY')
        
        # Logging Configuration
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.log_format = os.getenv('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # Performance Configuration
        self.max_concurrent_requests = int(os.getenv('MAX_CONCURRENT_REQUESTS', '10'))
        self.request_timeout = int(os.getenv('REQUEST_TIMEOUT', '30'))
        self.cache_ttl = int(os.getenv('CACHE_TTL', '3600'))  # 1 hour
        
        # Feature Flags
        self.load_docs_on_startup = os.getenv('LOAD_DOCS_ON_STARTUP', 'false').lower() == 'true'
        self.enable_metrics = os.getenv('ENABLE_METRICS', 'false').lower() == 'true'
        self.enable_tracing = os.getenv('ENABLE_TRACING', 'false').lower() == 'true'
        
        # Security Configuration
        self.cors_origins = self._parse_cors_origins(os.getenv('CORS_ORIGINS', '*'))
        self.rate_limit_per_minute = int(os.getenv('RATE_LIMIT_PER_MINUTE', '60'))
        
        # Ensure required directories exist
        self._ensure_directories()
    
    def _parse_document_ids(self, ids_string: str) -> List[str]:
        """Parse comma-separated document IDs"""
        if not ids_string:
            return []
        return [id.strip() for id in ids_string.split(',') if id.strip()]
    
    def _parse_cors_origins(self, origins_string: str) -> List[str]:
        """Parse CORS origins"""
        if origins_string == '*':
            return ['*']
        return [origin.strip() for origin in origins_string.split(',') if origin.strip()]
    
    def _ensure_directories(self):
        """Ensure required directories exist"""
        directories = [
            self.vector_store_path,
            'logs'
        ]
        
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
    
    def validate_config(self) -> dict:
        """Validate configuration and return validation results"""
        results = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        # Required configurations
        if not self.openai_api_key:
            results['errors'].append('OpenAI API key is required')
            results['valid'] = False
        
        if not os.path.exists(self.google_credentials_path):
            results['errors'].append(f'Google credentials file not found at {self.google_credentials_path}')
            results['valid'] = False
        
        if self.is_production and not self.api_token:
            results['errors'].append('API token is required for production environment')
            results['valid'] = False
        
        # Optional configurations with warnings
        if not self.database_url and self.is_production:
            results['warnings'].append('Database URL not configured for production')
        
        if not self.redis_url and self.is_production:
            results['warnings'].append('Redis URL not configured for production')
        
        # Slack configuration validation
        if self.slack_bot_token and not self.slack_signing_secret:
            results['warnings'].append('Slack bot token provided but signing secret is missing')
        
        # Performance warnings
        if self.chunk_size > 2000:
            results['warnings'].append('Large chunk size may impact performance')
        
        if self.max_tokens > 2000:
            results['warnings'].append('Large max_tokens may increase costs')
        
        return results
    
    def get_database_config(self) -> dict:
        """Get database configuration"""
        if not self.database_url:
            return {}
        
        # Parse database URL
        from urllib.parse import urlparse
        parsed = urlparse(self.database_url)
        
        return {
            'host': parsed.hostname,
            'port': parsed.port,
            'database': parsed.path.lstrip('/'),
            'username': parsed.username,
            'password': parsed.password,
            'url': self.database_url
        }
    
    def get_redis_config(self) -> dict:
        """Get Redis configuration"""
        if not self.redis_url:
            return {}
        
        # Parse Redis URL
        from urllib.parse import urlparse
        parsed = urlparse(self.redis_url)
        
        return {
            'host': parsed.hostname,
            'port': parsed.port or 6379,
            'db': int(parsed.path.lstrip('/')) if parsed.path else 0,
            'password': parsed.password,
            'url': self.redis_url
        }
    
    def get_logging_config(self) -> dict:
        """Get logging configuration"""
        return {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'detailed': {
                    'format': self.log_format
                },
                'simple': {
                    'format': '%(levelname)s - %(message)s'
                }
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'level': self.log_level,
                    'formatter': 'detailed',
                    'stream': 'ext://sys.stdout'
                },
                'file': {
                    'class': 'logging.FileHandler',
                    'level': self.log_level,
                    'formatter': 'detailed',
                    'filename': 'logs/application.log',
                    'mode': 'a'
                }
            },
            'loggers': {
                '': {
                    'handlers': ['console', 'file'],
                    'level': self.log_level,
                    'propagate': False
                }
            }
        }
    
    def get_security_headers(self) -> dict:
        """Get security headers for HTTP responses"""
        return {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'Content-Security-Policy': "default-src 'self'",
            'Referrer-Policy': 'strict-origin-when-cross-origin'
        }
    
    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled"""
        feature_flags = {
            'metrics': self.enable_metrics,
            'tracing': self.enable_tracing,
            'slack': bool(self.slack_bot_token),
            'database': bool(self.database_url),
            'redis': bool(self.redis_url)
        }
        return feature_flags.get(feature, False)
    
    def get_health_checks(self) -> dict:
        """Get health check configuration"""
        checks = {
            'openai': {
                'enabled': bool(self.openai_api_key),
                'required': True
            },
            'google_drive': {
                'enabled': os.path.exists(self.google_credentials_path),
                'required': True
            },
            'vector_store': {
                'enabled': os.path.exists(self.vector_store_path),
                'required': True
            },
            'database': {
                'enabled': bool(self.database_url),
                'required': self.is_production
            },
            'redis': {
                'enabled': bool(self.redis_url),
                'required': False
            }
        }
        return checks
    
    def to_dict(self) -> dict:
        """Convert configuration to dictionary (excluding sensitive data)"""
        return {
            'environment': self.environment,
            'embedding_model': self.embedding_model,
            'qa_model': self.qa_model,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
            'chunk_size': self.chunk_size,
            'chunk_overlap': self.chunk_overlap,
            'vector_store_path': self.vector_store_path,
            'collection_name': self.collection_name,
            'api_host': self.api_host,
            'api_port': self.api_port,
            'log_level': self.log_level,
            'load_docs_on_startup': self.load_docs_on_startup,
            'enable_metrics': self.enable_metrics,
            'enable_tracing': self.enable_tracing,
            'cors_origins': self.cors_origins,
            'rate_limit_per_minute': self.rate_limit_per_minute,
            'max_concurrent_requests': self.max_concurrent_requests,
            'request_timeout': self.request_timeout,
            'cache_ttl': self.cache_ttl
        }

# Create global config instance
config = Config() 