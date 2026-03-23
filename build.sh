#!/bin/bash

# Build script for Render.com deployment
set -e

echo "🚀 Starting TrackStarAI build..."

# Clear stale Python bytecode from previous builds
echo "🧹 Clearing stale bytecode caches..."
find . -name "*.pyc" -delete 2>/dev/null || true
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Upgrade pip
echo "📦 Upgrading pip..."
pip install --upgrade pip

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Set Playwright environment
export PLAYWRIGHT_BROWSERS_PATH="/opt/render/project/.cache/ms-playwright"

# Try to install Playwright browsers (may fail on Render.com)
echo "🌐 Installing Playwright browsers..."
if python -m playwright install chromium; then
    echo "✅ Playwright browsers installed successfully"
else
    echo "⚠️  Warning: Could not install Playwright browsers - will try at runtime"
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p data
mkdir -p logs
mkdir -p .cache

echo "✅ Build completed successfully!"
