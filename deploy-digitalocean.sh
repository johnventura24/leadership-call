#!/bin/bash

# Leadership Knowledge Base Agent - Digital Ocean Deployment Script

set -e

# Configuration
APP_NAME="leadership-kb-agent"
REGION="nyc3"
SPEC_FILE="digitalocean-spec.yaml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if doctl is installed
    if ! command -v doctl &> /dev/null; then
        log_error "doctl is not installed. Please install it first."
        echo "Install with: snap install doctl # or brew install doctl"
        exit 1
    fi
    
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install it first."
        exit 1
    fi
    
    # Check if doctl is authenticated
    if ! doctl auth list &> /dev/null; then
        log_error "doctl is not authenticated. Please run 'doctl auth init' first."
        exit 1
    fi
    
    log_info "Prerequisites check passed!"
}

check_environment_variables() {
    log_info "Checking environment variables..."
    
    if [ -z "$OPENAI_API_KEY" ]; then
        log_error "OPENAI_API_KEY environment variable is not set."
        exit 1
    fi
    
    if [ -z "$API_TOKEN" ]; then
        log_error "API_TOKEN environment variable is not set."
        exit 1
    fi
    
    if [ ! -f "credentials.json" ]; then
        log_error "credentials.json file not found. Please ensure Google Cloud credentials are available."
        exit 1
    fi
    
    log_info "Environment variables check passed!"
}

create_container_registry() {
    log_info "Creating Digital Ocean Container Registry..."
    
    # Check if registry exists
    if doctl registry get $APP_NAME &> /dev/null; then
        log_warn "Container registry $APP_NAME already exists."
    else
        # Create registry
        doctl registry create $APP_NAME --subscription-tier basic
        log_info "Container registry created successfully!"
    fi
}

build_and_push_image() {
    log_info "Building and pushing Docker image..."
    
    # Login to registry
    doctl registry login
    
    # Build image
    docker build -t $APP_NAME .
    
    # Tag image
    docker tag $APP_NAME:latest registry.digitalocean.com/$APP_NAME/$APP_NAME:latest
    
    # Push image
    docker push registry.digitalocean.com/$APP_NAME/$APP_NAME:latest
    
    log_info "Docker image pushed successfully!"
}

create_databases() {
    log_info "Creating managed databases..."
    
    # Create PostgreSQL database
    if doctl databases list | grep -q "$APP_NAME-db"; then
        log_warn "Database $APP_NAME-db already exists."
    else
        doctl databases create $APP_NAME-db \
            --engine postgres \
            --version 15 \
            --region $REGION \
            --size db-s-1vcpu-1gb \
            --num-nodes 1
        
        log_info "PostgreSQL database created successfully!"
    fi
    
    # Create Redis database
    if doctl databases list | grep -q "$APP_NAME-redis"; then
        log_warn "Redis database $APP_NAME-redis already exists."
    else
        doctl databases create $APP_NAME-redis \
            --engine redis \
            --version 7 \
            --region $REGION \
            --size db-s-1vcpu-1gb \
            --num-nodes 1
        
        log_info "Redis database created successfully!"
    fi
    
    # Wait for databases to be ready
    log_info "Waiting for databases to be ready..."
    sleep 60
}

get_database_info() {
    log_info "Getting database connection information..."
    
    # Get PostgreSQL connection info
    PG_CONNECTION=$(doctl databases connection $APP_NAME-db --format URI --no-header)
    
    # Get Redis connection info
    REDIS_CONNECTION=$(doctl databases connection $APP_NAME-redis --format URI --no-header)
    
    log_info "Database connection information retrieved!"
}

create_app_spec() {
    log_info "Creating App Platform specification..."
    
    # Get Google credentials as base64
    GOOGLE_CREDENTIALS_B64=$(cat credentials.json | base64 -w 0)
    
    cat > $SPEC_FILE << EOF
name: $APP_NAME
region: $REGION
services:
- name: api
  source_dir: /
  github:
    repo: your-github-repo
    branch: main
  run_command: python api_service.py
  environment_slug: python
  instance_count: 1
  instance_size_slug: basic-xxs
  http_port: 8000
  health_check:
    http_path: /health
    initial_delay_seconds: 60
    period_seconds: 10
    timeout_seconds: 5
    success_threshold: 1
    failure_threshold: 3
  envs:
  - key: OPENAI_API_KEY
    value: $OPENAI_API_KEY
    type: SECRET
  - key: API_TOKEN
    value: $API_TOKEN
    type: SECRET
  - key: GOOGLE_CREDENTIALS_JSON
    value: $GOOGLE_CREDENTIALS_B64
    type: SECRET
  - key: DATABASE_URL
    value: $PG_CONNECTION
    type: SECRET
  - key: REDIS_URL
    value: $REDIS_CONNECTION
    type: SECRET
  - key: ENVIRONMENT
    value: production
  - key: PORT
    value: "8000"
  - key: VECTOR_STORE_PATH
    value: /app/vector_store
  - key: EMBEDDING_MODEL
    value: text-embedding-ada-002
  - key: QA_MODEL
    value: gpt-3.5-turbo
  - key: MAX_TOKENS
    value: "1000"
  - key: TEMPERATURE
    value: "0.7"
  - key: CHUNK_SIZE
    value: "1000"
  - key: CHUNK_OVERLAP
    value: "200"
  - key: LOAD_DOCS_ON_STARTUP
    value: "true"
  - key: GOOGLE_CREDENTIALS_PATH
    value: /app/credentials.json
  - key: GOOGLE_TOKEN_PATH
    value: /app/token.json
EOF
    
    log_info "App specification created!"
}

deploy_app() {
    log_info "Deploying application to Digital Ocean App Platform..."
    
    # Deploy the app
    doctl apps create --spec $SPEC_FILE
    
    # Wait for deployment
    log_info "Waiting for deployment to complete..."
    sleep 120
    
    # Get app info
    APP_ID=$(doctl apps list --format ID --no-header | head -1)
    APP_URL=$(doctl apps get $APP_ID --format LiveURL --no-header)
    
    log_info "Application deployed successfully!"
    echo "APP_ID=$APP_ID" >> deployment.env
    echo "APP_URL=$APP_URL" >> deployment.env
}

test_deployment() {
    log_info "Testing deployment..."
    
    source deployment.env
    
    # Wait for service to be stable
    sleep 30
    
    # Test health endpoint
    if curl -f "$APP_URL/health" &> /dev/null; then
        log_info "Health check passed!"
    else
        log_error "Health check failed. Deployment may have issues."
        exit 1
    fi
    
    # Test API endpoint
    if curl -f "$APP_URL/" &> /dev/null; then
        log_info "API endpoint is accessible!"
    else
        log_error "API endpoint is not accessible."
        exit 1
    fi
    
    log_info "Deployment test passed!"
}

print_deployment_info() {
    log_info "Deployment completed successfully!"
    
    source deployment.env
    
    echo ""
    echo "=== DEPLOYMENT INFORMATION ==="
    echo "Application: $APP_NAME"
    echo "Region: $REGION"
    echo "App ID: $APP_ID"
    echo "App URL: $APP_URL"
    echo "Health Check: $APP_URL/health"
    echo "API Documentation: $APP_URL/docs"
    echo ""
    echo "=== TESTING THE API ==="
    echo "1. Health check:"
    echo "   curl $APP_URL/health"
    echo ""
    echo "2. Ask a question (replace YOUR_API_TOKEN):"
    echo "   curl -H \"Authorization: Bearer YOUR_API_TOKEN\" \\"
    echo "        -H \"Content-Type: application/json\" \\"
    echo "        -d '{\"question\": \"What is our remote work policy?\"}' \\"
    echo "        $APP_URL/ask"
    echo ""
    echo "3. Sync documents:"
    echo "   curl -H \"Authorization: Bearer YOUR_API_TOKEN\" \\"
    echo "        -H \"Content-Type: application/json\" \\"
    echo "        -d '{\"force_refresh\": true}' \\"
    echo "        $APP_URL/sync"
    echo ""
    echo "=== MANAGEMENT COMMANDS ==="
    echo "View logs: doctl apps logs $APP_ID"
    echo "View app details: doctl apps get $APP_ID"
    echo "Update app: doctl apps update $APP_ID --spec $SPEC_FILE"
    echo ""
}

cleanup() {
    log_info "Cleaning up temporary files..."
    rm -f deployment.env
    rm -f $SPEC_FILE
}

# Main execution
main() {
    log_info "Starting deployment of Leadership Knowledge Base Agent to Digital Ocean..."
    
    check_prerequisites
    check_environment_variables
    create_container_registry
    build_and_push_image
    create_databases
    get_database_info
    create_app_spec
    deploy_app
    test_deployment
    print_deployment_info
    
    log_info "Deployment completed successfully!"
}

# Handle script arguments
case "${1:-deploy}" in
    deploy)
        main
        ;;
    destroy)
        log_info "Destroying application and resources..."
        
        # Get app ID
        APP_ID=$(doctl apps list --format ID --no-header | head -1)
        
        # Delete app
        doctl apps delete $APP_ID --force
        
        # Delete databases
        doctl databases delete $APP_NAME-db --force
        doctl databases delete $APP_NAME-redis --force
        
        # Delete container registry
        doctl registry delete $APP_NAME --force
        
        cleanup
        log_info "All resources destroyed!"
        ;;
    update)
        log_info "Updating application..."
        
        # Get app ID
        APP_ID=$(doctl apps list --format ID --no-header | head -1)
        
        build_and_push_image
        get_database_info
        create_app_spec
        
        # Update app
        doctl apps update $APP_ID --spec $SPEC_FILE
        
        test_deployment
        log_info "Application updated!"
        ;;
    *)
        echo "Usage: $0 {deploy|destroy|update}"
        echo "  deploy  - Deploy the complete application and resources"
        echo "  destroy - Destroy all resources"
        echo "  update  - Update the application with new code"
        exit 1
        ;;
esac 