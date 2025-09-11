FROM python:3.11-slim

# Set environment variables for Playwright and Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies in smaller chunks to avoid timeouts
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    libglib2.0-0 \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libgtk-3-0 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Install additional dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxrandr2 \
    libxcomposite1 \
    libxi6 \
    libxcursor1 \
    libxtst6 \
    libxdamage1 \
    libxfixes3 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set working directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies with timeout handling
RUN pip install --no-cache-dir --upgrade pip --timeout 300
RUN pip install --no-cache-dir -r requirements.txt --timeout 300

# Install Playwright (without browsers first to save time)
RUN pip install --no-cache-dir playwright --timeout 300

# Install Playwright browsers with retry logic and timeout
RUN python -m playwright install-deps || echo "Warning: Some deps failed to install"
RUN timeout 600 python -m playwright install chromium || \
    (echo "First attempt failed, retrying..." && \
     timeout 600 python -m playwright install chromium) || \
    echo "Warning: Browser installation failed, will try at runtime"

# Copy application code
COPY . .

# Create necessary directories with proper permissions
RUN mkdir -p /app/data /app/logs /app/.cache && \
    chmod 755 /app/data /app/logs /app/.cache

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app

# Try to set browser permissions if they exist
RUN if [ -d "/ms-playwright" ]; then chown -R app:app /ms-playwright; fi

USER app

# Expose port (Render will set $PORT)
EXPOSE 8000

# Health check with proper port handling
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Start the application with proper port handling
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]