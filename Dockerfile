FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Prevent Python from writing .pyc files to disk and disable stdout buffering
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies needed for compiling some Python extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files
COPY requirements.txt .

# Install dependencies into system Python
RUN uv pip install --system --no-cache -r requirements.txt

# Copy application source code
COPY . .

# Create volume mount points
RUN mkdir -p /app/database /app/logs /app/vector_store

# Command to run application
CMD ["python", "main.py"]
