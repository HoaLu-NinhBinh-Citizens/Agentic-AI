"""Retry policy stub."""

import asyncio
from typing import Any, Callable, TypeVar

T = TypeVar('T')


class RetryPolicy:
    """Retry policy for failed operations."""
    
    def __init__(self, max_attempts: int = 3, delay: float = 1.0):
        self.max_attempts = max_attempts
        self.delay = delay
    
    async def execute(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute with retry logic."""
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_attempts - 1:
                    await asyncio.sleep(self.delay * (attempt + 1))
        raise last_error
