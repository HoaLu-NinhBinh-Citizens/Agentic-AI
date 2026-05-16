"""Timeout module."""

import asyncio
from typing import Any, TypeVar

T = TypeVar('T')


async def with_timeout(coro: Any, timeout: float) -> T:
    """Execute with timeout."""
    return await asyncio.wait_for(coro, timeout=timeout)
