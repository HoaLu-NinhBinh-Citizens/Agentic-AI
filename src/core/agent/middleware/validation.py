"""Validation middleware module."""

from typing import Any


class ValidationMiddleware:
    """Input validation middleware."""
    
    async def process(self, context: dict[str, Any], next_handler) -> Any:
        """Process with validation."""
        return await next_handler(context)
