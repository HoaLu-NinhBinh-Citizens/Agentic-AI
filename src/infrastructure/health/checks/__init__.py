"""Health checks module."""

from typing import Any


class HealthCheck:
    """Base health check."""
    
    name: str = "health_check"
    
    async def check(self) -> dict[str, Any]:
        """Perform check."""
        return {"status": "healthy"}


class LLMHealthCheck(HealthCheck):
    """LLM provider health check."""
    name = "llm"
    
    async def check(self) -> dict[str, Any]:
        return {"status": "healthy", "provider": "openai"}


class MemoryHealthCheck(HealthCheck):
    """Memory health check."""
    name = "memory"
    
    async def check(self) -> dict[str, Any]:
        import psutil
        return {"status": "healthy", "usage_percent": psutil.virtual_memory().percent}
