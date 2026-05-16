"""Dispatcher stub."""

from typing import Any, Callable


class Dispatcher:
    """Task dispatcher for routing work."""
    
    async def dispatch(self, task: dict[str, Any], handler: Callable) -> Any:
        """Dispatch task to handler."""
        return await handler(task)
