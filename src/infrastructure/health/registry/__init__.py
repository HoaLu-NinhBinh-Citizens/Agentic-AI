"""Health registry stub."""

from typing import Any, Callable


class HealthRegistry:
    """Registry for health checks."""
    
    def __init__(self):
        self._checks: dict[str, Callable] = {}
    
    def register(self, name: str, check: Callable) -> None:
        """Register a health check."""
        self._checks[name] = check
    
    async def check_all(self) -> dict[str, Any]:
        """Run all health checks."""
        results = {}
        for name, check in self._checks.items():
            try:
                results[name] = {"status": "healthy", "result": await check()}
            except Exception as e:
                results[name] = {"status": "unhealthy", "error": str(e)}
        return results
