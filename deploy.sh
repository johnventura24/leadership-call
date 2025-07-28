#!/bin/bash

# Leadership Knowledge Base Agent - AWS Deployment Script

set -e

# Configuration
APP_NAME="leadership-kb-agent"
AWS_REGION="us-east-1"
ECR_REPO_NAME="$APP_NAME"
TERRAFORM_DIR="terraform"

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
    
    # Check if AWS CLI is installed
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed. Please install it first."
        exit 1
    fi
    
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install it first."
        exit 1
    fi
    
    # Check if Terraform is installed
    if ! command -v terraform &> /dev/null; then
        log_error "Terraform is not installed. Please install it first."
        exit 1
    fi
    
    # Check if AWS credentials are configured
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials are not configured. Please run 'aws configure' first."
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

create_ecr_repository() {
    log_info "Creating ECR repository..."
    
    # Check if repository exists
    if aws ecr describe-repositories --repository-names $ECR_REPO_NAME --region $AWS_REGION &> /dev/null; then
        log_warn "ECR repository $ECR_REPO_NAME already exists."
    else
        # Create repository
        aws ecr create-repository \
            --repository-name $ECR_REPO_NAME \
            --region $AWS_REGION \
            --image-scanning-configuration scanOnPush=true
        
        log_info "ECR repository created successfully!"
    fi
}

build_and_push_image() {
    log_info "Building and pushing Docker image..."
    
    # Get ECR login token
    aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $(aws sts get-caller-identity --query Account --output text).dkr.ecr.$AWS_REGION.amazonaws.com
    
    # Build image
    docker build -t $ECR_REPO_NAME .
    
    # Tag image
    ECR_URI=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:latest
    docker tag $ECR_REPO_NAME:latest $ECR_URI
    
    # Push image
    docker push $ECR_URI
    
    log_info "Docker image pushed successfully!"
    echo "ECR_URI=$ECR_URI" >> deployment.env
}

deploy_infrastructure() {
    log_info "Deploying infrastructure with Terraform..."
    
    cd $TERRAFORM_DIR
    
    # Initialize Terraform
    terraform init
    
    # Create terraform.tfvars file
    cat > terraform.tfvars << EOF
aws_region = "$AWS_REGION"
app_name = "$APP_NAME"
openai_api_key = "$OPENAI_API_KEY"
api_token = "$API_TOKEN"
google_credentials_json = $(cat ../credentials.json | jq -c .)
EOF
    
    # Plan deployment
    terraform plan -var-file=terraform.tfvars
    
    # Apply deployment
    terraform apply -var-file=terraform.tfvars -auto-approve
    
    # Get outputs
    LOAD_BALANCER_DNS=$(terraform output -raw load_balancer_dns)
    
    cd ..
    
    log_info "Infrastructure deployed successfully!"
    echo "LOAD_BALANCER_DNS=$LOAD_BALANCER_DNS" >> deployment.env
}

update_ecs_service() {
    log_info "Updating ECS service..."
    
    # Get the ECR URI from deployment.env
    source deployment.env
    
    # Update task definition with new image
    cd $TERRAFORM_DIR
    
    # Force service update
    terraform apply -var-file=terraform.tfvars -auto-approve -replace="aws_ecs_service.main"
    
    cd ..
    
    log_info "ECS service updated successfully!"
}

test_deployment() {
    log_info "Testing deployment..."
    
    source deployment.env
    
    # Wait for service to be stable
    sleep 30
    
    # Test health endpoint
    if curl -f "http://$LOAD_BALANCER_DNS/health" &> /dev/null; then
        log_info "Health check passed!"
    else
        log_error "Health check failed. Deployment may have issues."
        exit 1
    fi
    
    # Test API endpoint
    if curl -f "http://$LOAD_BALANCER_DNS/" &> /dev/null; then
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
    echo "Region: $AWS_REGION"
    echo "Load Balancer DNS: $LOAD_BALANCER_DNS"
    echo "API URL: http://$LOAD_BALANCER_DNS"
    echo "Health Check: http://$LOAD_BALANCER_DNS/health"
    echo "API Documentation: http://$LOAD_BALANCER_DNS/docs"
    echo ""
    echo "=== TESTING THE API ==="
    echo "1. Health check:"
    echo "   curl http://$LOAD_BALANCER_DNS/health"
    echo ""
    echo "2. Ask a question (replace YOUR_API_TOKEN):"
    echo "   curl -H \"Authorization: Bearer YOUR_API_TOKEN\" \\"
    echo "        -H \"Content-Type: application/json\" \\"
    echo "        -d '{\"question\": \"What is our remote work policy?\"}' \\"
    echo "        http://$LOAD_BALANCER_DNS/ask"
    echo ""
    echo "3. Sync documents:"
    echo "   curl -H \"Authorization: Bearer YOUR_API_TOKEN\" \\"
    echo "        -H \"Content-Type: application/json\" \\"
    echo "        -d '{\"force_refresh\": true}' \\"
    echo "        http://$LOAD_BALANCER_DNS/sync"
    echo ""
}

cleanup() {
    log_info "Cleaning up temporary files..."
    rm -f deployment.env
    rm -f $TERRAFORM_DIR/terraform.tfvars
}

# Main execution
main() {
    log_info "Starting deployment of Leadership Knowledge Base Agent..."
    
    check_prerequisites
    check_environment_variables
    create_ecr_repository
    build_and_push_image
    deploy_infrastructure
    update_ecs_service
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
        log_info "Destroying infrastructure..."
        cd $TERRAFORM_DIR
        terraform destroy -var-file=terraform.tfvars -auto-approve
        cd ..
        cleanup
        log_info "Infrastructure destroyed!"
        ;;
    update)
        log_info "Updating application..."
        build_and_push_image
        update_ecs_service
        test_deployment
        log_info "Application updated!"
        ;;
    *)
        echo "Usage: $0 {deploy|destroy|update}"
        echo "  deploy  - Deploy the complete infrastructure and application"
        echo "  destroy - Destroy all infrastructure"
        echo "  update  - Update the application with new code"
        exit 1
        ;;
esac 