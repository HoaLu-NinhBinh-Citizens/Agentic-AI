"""Server middleware module."""

from typing import Any, Callable


async def middleware(handler: Callable, request: dict[str, Any]) -> Any:
    """Process middleware."""
    return await handler(request)
