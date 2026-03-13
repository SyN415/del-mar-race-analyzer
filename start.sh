#!/bin/bash

# Production startup script for Del Mar Race Analyzer
set -e

echo "🚀 Starting Del Mar Race Analyzer..."

# Set environment variables for production
export ENVIRONMENT=${ENVIRONMENT:-production}
export PORT=${PORT:-8000}
export LOG_LEVEL=${LOG_LEVEL:-info}

# Create necessary directories
mkdir -p data
mkdir -p logs

# Check if Playwright browsers are installed
if [ ! -d "/opt/render/project/.cache/ms-playwright" ] && [ ! -d "$HOME/.cache/ms-playwright" ]; then
    echo "🌐 Installing Playwright browsers..."
    python -m playwright install chromium || echo "⚠️  Warning: Could not install Playwright browsers"
fi

# Start the application
echo "🎯 Starting application on port $PORT..."
if [ "$ENVIRONMENT" = "production" ]; then
    # Use a single-process Uvicorn server on Render to avoid Gunicorn worker boot stalls
    exec python -m uvicorn app:app --host 0.0.0.0 --port "$PORT" --log-level "$LOG_LEVEL"
else
    # Use Uvicorn for development
    exec python app.py
fi
