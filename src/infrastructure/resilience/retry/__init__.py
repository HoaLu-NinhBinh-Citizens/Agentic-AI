"""Retry module."""

import asyncio
from typing import Any, TypeVar, Callable

T = TypeVar('T')


async def retry(func: Callable[..., T], attempts: int = 3) -> T:
    """Retry a function."""
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            return await func()
        except Exception as e:
            last_error = e
            await asyncio.sleep(1)
    raise last_error
