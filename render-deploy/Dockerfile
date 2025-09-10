FROM python:3.11-slim

# Set environment variables for Playwright and Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0

# Install system dependencies for Playwright browser automation
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    procps \
    curl \
    xvfb \
    libglib2.0-0 \
    libnss3-dev \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libdbus-glib-1-2 \
    libgtk-3-0 \
    libgdk-pixbuf2.0-0 \
    libxss1 \
    libgconf-2-4 \
    libgbm1 \
    libasound2 \
    libxrandr2 \
    libxcomposite1 \
    libxi6 \
    libxcursor1 \
    libxtst6 \
    libxdamage1 \
    libxfixes3 \
    libwayland-client0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libnspr4 \
    libnss3 \
    fonts-liberation \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set working directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers with system dependencies
# This ensures browsers are installed in the Docker image, not at runtime
RUN python -m playwright install chromium --with-deps

# Verify Playwright installation
RUN python -m playwright install-deps && \
    python -c "from playwright.sync_api import sync_playwright; print('Playwright installation verified')"

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/data /app/logs /app/.cache

# Create non-root user for security but ensure proper permissions
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app && \
    chown -R app:app /ms-playwright
USER app

# Expose port (Render will set $PORT)
EXPOSE 8000

# Health check with proper port handling
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Start the application with proper port handling
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]