# AI_support Dockerfile
# Multi-stage build for smaller production image

FROM python:3.12-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY AI_support/requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

# Copy application code
COPY AI_support /app/AI_support

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Create data directory
RUN mkdir -p /data/rag_index /data/memory

# Expose API port
EXPOSE 8766

# Default command: run API server
CMD ["python", "-m", "AI_support.app.api_server"]

# Alternative commands:
# Run CLI: docker run ai-support python -m AI_support.app.embedded_agent
# Run tests: docker run ai-support python -m pytest AI_support/tests
