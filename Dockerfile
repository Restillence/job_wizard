FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Playwright dependencies for Crawl4AI
RUN python -m playwright install --with-deps chromium

# Copy application code
COPY src/ src/

# Create necessary directories for local stateless storage
RUN mkdir -p uploads/resumes uploads/cover_letters

# Expose port
EXPOSE 8000

# Start server
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
