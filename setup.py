"""Setup configuration for AI_support package (src/ layout)."""
from setuptools import setup, find_packages

setup(
    name="AI_support",
    version="0.1.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.10",
    install_requires=[
        "aiohttp>=3.12.0",
        "fastapi>=0.135.0",
        "uvicorn>=0.35.0",
        "pydantic>=2.11.0",
        "pydantic-settings>=2.10.0",
        "chromadb>=1.0.0",
        "openai>=2.31.0",
        "anthropic>=0.40.0",
        "ollama>=0.5.0",
        "langchain>=0.3.0",
        "langgraph>=0.2.0",
        "structlog>=25.0.0",
        "opentelemetry-api>=1.35.0",
        "opentelemetry-sdk>=1.35.0",
        "httpx>=0.28.0",
        "python-dotenv>=1.1.0",
        "rich>=14.0.0",
        "typer>=0.16.0",
        "websockets>=15.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=9.0.0",
            "pytest-asyncio>=1.3.0",
            "ruff>=0.9.0",
            "mypy>=1.0.0",
        ],
        "server": ["uvicorn[standard]>=0.35.0", "websockets>=15.0.0"],
        "dashboard": ["streamlit>=1.47.0"],
    },
)
