"""Middleware base stub."""

from typing import Any, Callable
from functools import wraps


class MiddlewareBase:
    """Base class for middleware."""
    
    async def process(self, context: dict[str, Any], next_handler: Callable) -> Any:
        """Process request through middleware."""
        return await next_handler(context)
