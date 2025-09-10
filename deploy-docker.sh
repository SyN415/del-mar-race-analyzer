#!/bin/bash

# Docker Deployment Script for Del Mar Race Analyzer
# This script helps deploy the application using Docker on Render.com

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "\n${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}\n"
}

# Main deployment function
main() {
    print_header "🐳 Del Mar Race Analyzer - Docker Deployment"
    
    print_status "Starting Docker deployment preparation..."
    
    # Check if we're in the right directory
    if [ ! -f "app.py" ]; then
        print_error "app.py not found. Please run this script from the project root directory."
        exit 1
    fi
    
    # Check if render-deploy directory exists
    if [ ! -d "render-deploy" ]; then
        print_error "render-deploy directory not found. Please ensure the Docker configuration exists."
        exit 1
    fi
    
    # Verify Docker configuration files
    print_status "Verifying Docker configuration files..."
    
    if [ ! -f "render-deploy/Dockerfile" ]; then
        print_error "render-deploy/Dockerfile not found."
        exit 1
    fi
    
    if [ ! -f "render-deploy/render.yaml" ]; then
        print_error "render-deploy/render.yaml not found."
        exit 1
    fi
    
    print_success "Docker configuration files verified."
    
    # Test Docker build locally (optional)
    read -p "Do you want to test the Docker build locally? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        test_docker_build
    fi
    
    # Display deployment instructions
    print_deployment_instructions
    
    # Offer to open Render.com dashboard
    read -p "Do you want to open Render.com dashboard? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if command -v open >/dev/null 2>&1; then
            open "https://dashboard.render.com"
        elif command -v xdg-open >/dev/null 2>&1; then
            xdg-open "https://dashboard.render.com"
        else
            print_status "Please open https://dashboard.render.com manually."
        fi
    fi
    
    print_success "Docker deployment preparation complete!"
}

# Function to test Docker build locally
test_docker_build() {
    print_header "🧪 Testing Docker Build Locally"
    
    if ! command -v docker &> /dev/null; then
        print_warning "Docker not found. Skipping local build test."
        return
    fi
    
    print_status "Building Docker image locally..."
    
    # Build the Docker image
    if docker build -f render-deploy/Dockerfile -t del-mar-analyzer:test .; then
        print_success "Docker build completed successfully!"
        
        # Test if the image can start
        print_status "Testing if the container can start..."
        if timeout 30 docker run --rm -p 8000:8000 -e PORT=8000 del-mar-analyzer:test &
        then
            sleep 5
            if curl -f http://localhost:8000/health >/dev/null 2>&1; then
                print_success "Container started successfully and health check passed!"
            else
                print_warning "Container started but health check failed. This might be normal for local testing."
            fi
            # Stop the container
            docker stop $(docker ps -q --filter ancestor=del-mar-analyzer:test) >/dev/null 2>&1 || true
        else
            print_warning "Container test completed. Check logs if there were issues."
        fi
        
        # Clean up test image
        docker rmi del-mar-analyzer:test >/dev/null 2>&1 || true
    else
        print_error "Docker build failed. Please check the Dockerfile and try again."
        exit 1
    fi
}

# Function to display deployment instructions
print_deployment_instructions() {
    print_header "📋 Render.com Deployment Instructions"
    
    echo "Follow these steps to deploy using Docker on Render.com:"
    echo
    echo "1. 🌐 Go to your Render.com Dashboard:"
    echo "   https://dashboard.render.com"
    echo
    echo "2. ➕ Create a new Web Service (or update existing):"
    echo "   - Click 'New +' → 'Web Service'"
    echo "   - Connect your GitHub repository"
    echo
    echo "3. ⚙️  Configure the service:"
    echo "   - Name: del-mar-analyzer-docker"
    echo "   - Runtime: Docker"
    echo "   - Dockerfile Path: render-deploy/Dockerfile"
    echo "   - Docker Context: ./"
    echo "   - Auto-Deploy: false (recommended)"
    echo
    echo "4. 🔧 Set Environment Variables:"
    echo "   ENVIRONMENT=production"
    echo "   OPENROUTER_API_KEY=your_api_key_here"
    echo "   SCRAPER_USER_AGENT=Mozilla/5.0 (compatible; DelMar-Analyzer/1.0)"
    echo "   SCRAPER_HEADLESS=true"
    echo "   SCRAPER_TIMEOUT=45"
    echo "   LOG_LEVEL=INFO"
    echo "   DEBUG=false"
    echo "   PLAYWRIGHT_BROWSERS_PATH=/ms-playwright"
    echo "   PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0"
    echo
    echo "5. 💾 Configure Persistent Disk (optional):"
    echo "   - Name: del-mar-data"
    echo "   - Mount Path: /app/data"
    echo "   - Size: 1GB"
    echo
    echo "6. 🚀 Deploy:"
    echo "   - Click 'Create Web Service'"
    echo "   - Monitor build logs for Playwright installation"
    echo "   - Verify health check at /health endpoint"
    echo
    echo "7. ✅ Verify Deployment:"
    echo "   - Check that build completes without errors"
    echo "   - Ensure Playwright browsers install during build"
    echo "   - Test scraping functionality"
    echo
    
    print_warning "Important: Make sure to set your OPENROUTER_API_KEY in the environment variables!"
    print_status "For detailed troubleshooting, see DOCKER_DEPLOYMENT_GUIDE.md"
}

# Run main function
main "$@"
