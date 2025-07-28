# Leadership Knowledge Base Agent

A comprehensive AI-powered knowledge base agent that can access and understand content from your Google Drive, answer questions, and integrate with various platforms including Slack. The agent can be deployed locally or in the cloud (AWS/Digital Ocean) and provides REST API endpoints for integration.

## Features

- **Google Drive Integration**: Automatically reads and processes documents from Google Drive including:
  - Google Docs, Sheets, and Slides
  - PDF files
  - Text and Markdown files
  - Word documents
- **AI-Powered Q&A**: Uses OpenAI's GPT models for intelligent question answering
- **Semantic Search**: Vector-based search using OpenAI embeddings and ChromaDB
- **Multiple Interfaces**: 
  - REST API for programmatic access
  - Slack bot integration
  - Web interface (Streamlit)
  - Command-line interface
- **Cloud Deployment**: Ready for AWS and Digital Ocean deployment
- **Authentication**: Secure API access with token-based authentication
- **Monitoring**: Health checks, logging, and performance metrics

## Architecture

```
Google Drive ←→ AI Agent ←→ Vector Database
     ↓              ↓              ↓
  Documents    Question/Answer   Knowledge Base
     ↓              ↓              ↓
API Endpoints ←→ Slack Bot ←→ Web Interface
```

## Quick Start

### Local Development

1. **Clone and Setup**
   ```bash
   git clone <repository-url>
   cd leadership-knowledge-base
   pip install -r requirements.txt
   ```

2. **Configure Environment**
   ```bash
   cp environment_example.txt .env
   # Edit .env with your configuration
   ```

3. **Setup Google Drive Access**
   - Create a Google Cloud Project
   - Enable Google Drive API and Google Docs API
   - Create service account credentials
   - Download credentials.json

4. **Run Locally**
   ```bash
   # API Server
   python api_service.py
   
   # Slack Bot
   python run_slack_bot.py
   
   # Web Interface
   streamlit run streamlit_app.py
   ```

### Cloud Deployment

Choose your preferred cloud platform:

- **AWS**: Complete infrastructure with ECS, RDS, and ElastiCache
- **Digital Ocean**: Simplified deployment with App Platform

## Cloud Deployment Guide

### AWS Deployment

The AWS deployment creates a complete production infrastructure:

- **ECS Fargate**: Containerized application hosting
- **Application Load Balancer**: High availability and SSL termination
- **RDS PostgreSQL**: Managed database for persistent storage
- **ElastiCache Redis**: In-memory caching layer
- **VPC with Public/Private Subnets**: Secure network architecture
- **AWS Secrets Manager**: Secure credential storage

#### Prerequisites

```bash
# Install required tools
aws configure  # Configure AWS credentials
terraform --version  # Install Terraform
docker --version  # Install Docker
```

#### Environment Variables

```bash
export OPENAI_API_KEY="your-openai-api-key"
export API_TOKEN="your-secure-api-token"
# Ensure credentials.json is in project root
```

#### Deploy to AWS

```bash
# One-command deployment
./deploy.sh

# Manual steps
./deploy.sh deploy    # Full deployment
./deploy.sh update    # Update application only
./deploy.sh destroy   # Remove all resources
```

#### Deployment Output

```
=== DEPLOYMENT INFORMATION ===
Application: leadership-kb-agent
Region: us-east-1
Load Balancer DNS: leadership-kb-agent-alb-1234567890.us-east-1.elb.amazonaws.com
API URL: http://leadership-kb-agent-alb-1234567890.us-east-1.elb.amazonaws.com
Health Check: http://leadership-kb-agent-alb-1234567890.us-east-1.elb.amazonaws.com/health
API Documentation: http://leadership-kb-agent-alb-1234567890.us-east-1.elb.amazonaws.com/docs
```

### Digital Ocean Deployment

The Digital Ocean deployment uses App Platform for simplified hosting:

- **App Platform**: Managed container hosting
- **Managed PostgreSQL**: Database service
- **Managed Redis**: Caching service
- **Container Registry**: Private Docker registry
- **Automatic SSL**: Built-in SSL certificates

#### Prerequisites

```bash
# Install doctl (Digital Ocean CLI)
snap install doctl  # Linux
brew install doctl  # macOS

# Authenticate
doctl auth init
```

#### Deploy to Digital Ocean

```bash
# Make script executable
chmod +x deploy-digitalocean.sh

# Deploy
./deploy-digitalocean.sh

# Available commands
./deploy-digitalocean.sh deploy    # Full deployment
./deploy-digitalocean.sh update    # Update application
./deploy-digitalocean.sh destroy   # Remove all resources
```

## API Reference

### Authentication

All API endpoints require authentication using Bearer tokens:

```bash
curl -H "Authorization: Bearer YOUR_API_TOKEN" \
     https://your-api-url.com/endpoint
```

### Core Endpoints

#### Health Check
```bash
GET /health
```

#### Ask Question
```bash
POST /ask
Content-Type: application/json

{
  "question": "What is our remote work policy?",
  "max_context_items": 5,
  "include_sources": true
}
```

#### Sync Documents
```bash
POST /sync
Content-Type: application/json

{
  "force_refresh": true,
  "folder_ids": ["folder-id-1", "folder-id-2"]
}
```

#### Search FAQ
```bash
GET /search/faq?query=remote%20work&limit=5
```

#### Get Statistics
```bash
GET /stats
```

### Response Format

```json
{
  "answer": "Based on the documentation...",
  "confidence": 0.95,
  "sources": [
    {
      "document_id": "doc-123",
      "title": "Remote Work Policy",
      "chunk_text": "...",
      "relevance_score": 0.89
    }
  ],
  "question": "What is our remote work policy?",
  "timestamp": "2024-01-15T10:30:00Z",
  "processing_time": 1.23
}
```

## Configuration

### Environment Variables

Create a `.env` file with the following variables:

```bash
# Required
OPENAI_API_KEY=your-openai-api-key
API_TOKEN=your-secure-api-token

# Google Drive
GOOGLE_CREDENTIALS_PATH=credentials.json
GOOGLE_TOKEN_PATH=token.json

# Database (Cloud deployment)
DATABASE_URL=postgresql://user:pass@host:5432/db
REDIS_URL=redis://host:6379/0

# API Configuration
PORT=8000
ENVIRONMENT=production

# Performance
MAX_TOKENS=1000
TEMPERATURE=0.7
CHUNK_SIZE=1000
CHUNK_OVERLAP=200

# Features
LOAD_DOCS_ON_STARTUP=true
ENABLE_METRICS=true
CORS_ORIGINS=*
RATE_LIMIT_PER_MINUTE=60
```

### Google Cloud Setup

1. **Create Google Cloud Project**
   - Go to Google Cloud Console
   - Create a new project
   - Enable Google Drive API and Google Docs API

2. **Create Service Account**
   - Navigate to IAM & Admin → Service Accounts
   - Create a new service account
   - Download the JSON credentials file as `credentials.json`

3. **Grant Permissions**
   - Share your Google Drive folders with the service account email
   - Or use domain-wide delegation for organization access

### Security Best Practices

1. **API Token**: Use a strong, randomly generated token
2. **CORS**: Configure specific origins instead of "*" for production
3. **Rate Limiting**: Adjust based on your usage patterns
4. **Database**: Use SSL connections for database access
5. **Secrets**: Store sensitive data in environment variables or cloud secrets

## Monitoring and Troubleshooting

### Health Monitoring

```bash
# Check application health
curl https://your-api-url.com/health

# Expected response
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "version": "1.0.0",
  "components": {
    "knowledge_base": "healthy",
    "qa_system": "healthy",
    "google_drive": "healthy"
  }
}
```

### Logging

- Application logs: `logs/application.log`
- Cloud logs: Available in respective cloud platforms
- Structured logging with JSON format in production

### Common Issues

1. **Google Drive Authentication**
   ```bash
   # Check credentials file
   ls -la credentials.json
   
   # Test authentication
   python -c "from google_drive_client import GoogleDriveClient; client = GoogleDriveClient(); print(client.test_connection())"
   ```

2. **Vector Store Issues**
   ```bash
   # Reset vector store
   rm -rf vector_store/
   
   # Rebuild from documents
   curl -X POST -H "Authorization: Bearer YOUR_TOKEN" \
        -d '{"force_refresh": true}' \
        https://your-api-url.com/sync
   ```

3. **Memory Issues**
   ```bash
   # Reduce chunk size
   export CHUNK_SIZE=500
   export CHUNK_OVERLAP=100
   ```

## Advanced Features

### Custom Document Processing

Extend the document processor to handle additional file types:

```python
# document_processor.py
def process_custom_format(self, content: str) -> List[Dict]:
    # Custom processing logic
    pass
```

### Webhook Integration

Set up webhooks to automatically sync documents:

```bash
# Google Drive webhook
POST /webhook/google-drive
```

### Batch Processing

Process large document sets efficiently:

```bash
# Batch sync specific folders
curl -X POST -H "Authorization: Bearer YOUR_TOKEN" \
     -d '{"folder_ids": ["folder1", "folder2"], "force_refresh": true}' \
     https://your-api-url.com/sync
```

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run tests
pytest tests/

# With coverage
pytest --cov=. tests/
```

### Code Quality

```bash
# Format code
black .

# Lint code
flake8 .

# Type checking
mypy .
```

### Docker Development

```bash
# Build image
docker build -t leadership-kb-agent .

# Run container
docker run -p 8000:8000 --env-file .env leadership-kb-agent

# Docker Compose
docker-compose up -d
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- Check the troubleshooting section
- Review the API documentation
- Open an issue on GitHub

---

**Note**: This agent is designed for internal use with your organization's Google Drive. Ensure you have proper permissions and follow your organization's data governance policies. 