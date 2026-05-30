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

# Default command
CMD ["python", "-m", "src.interfaces.cli.main", "review", "/workspace"]

# Expose port for API (if needed)
EXPOSE 8080

# Volume for persistent data
VOLUME ["/data"]
