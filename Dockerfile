FROM python:3.11-alpine

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    && rm -rf /var/cache/apk/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY pyircbot.py .
COPY config.py .

# Create data directory for persistent logs
RUN mkdir -p /app/data

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Use Python directly as the entrypoint
ENTRYPOINT ["python", "pyircbot.py"] 