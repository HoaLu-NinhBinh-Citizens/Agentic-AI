"""Retry gateway stub."""

import asyncio
from typing import Any, Callable, TypeVar

T = TypeVar('T')


class RetryGateway:
    """Retry mechanism for gateway calls."""
    
    def __init__(self, max_attempts: int = 3, delay: float = 1.0):
        self._max = max_attempts
        self._delay = delay
    
    async def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Call with retry."""
        last_error: Exception | None = None
        for attempt in range(self._max):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self._max - 1:
                    await asyncio.sleep(self._delay * (attempt + 1))
        raise last_error
