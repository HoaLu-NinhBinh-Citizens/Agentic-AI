FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install tree-sitter languages
RUN pip install tree-sitter tree-sitter-languages

# Copy application
COPY . .

# Install Python dependencies
RUN pip install -e .

# Install Ollama for local LLM (optional)
# RUN curl -fsSL https://ollama.com/install.sh | sh

# Create non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Run the FastAPI server (the primary product surface).
# Port 8080 matches the docker-compose ai-support port mapping.
ENV PORT=8080
CMD ["python", "-m", "uvicorn", "interfaces.server.main:app", "--host", "0.0.0.0", "--port", "8080"]

# Expose port for API
EXPOSE 8080

# Volume for persistent data
VOLUME ["/data"]
