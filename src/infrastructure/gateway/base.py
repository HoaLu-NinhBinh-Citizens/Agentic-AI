"""Gateway base stub."""

from typing import Any, Callable


class GatewayBase:
    """Base class for API gateways."""
    
    def __init__(self):
        self._middlewares: list[Callable] = []
    
    def add_middleware(self, middleware: Callable) -> None:
        """Add a middleware."""
        self._middlewares.append(middleware)
    
    async def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle incoming request."""
        return {"status": "ok"}
