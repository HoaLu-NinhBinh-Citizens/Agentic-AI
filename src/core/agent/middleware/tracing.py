"""Tracing middleware module."""

from typing import Any


class TracingMiddleware:
    """Tracing middleware."""
    
    async def process(self, context: dict[str, Any], next_handler) -> Any:
        """Process with tracing."""
        return await next_handler(context)
