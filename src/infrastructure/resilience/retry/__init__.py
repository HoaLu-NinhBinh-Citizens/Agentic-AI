"""Retry module with exponential backoff and jitter."""

import asyncio
from typing import Callable, TypeVar

from .policy import ExponentialBackoff

T = TypeVar('T')


async def retry(
    func: Callable[..., T],
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
) -> T:
    """Retry an async callable with exponential backoff + jitter.

    Sleeps base_delay * 2^attempt (+ up to 50% jitter, capped at max_delay)
    between attempts. No sleep after the final failed attempt.
    """
    policy = ExponentialBackoff(
        max_retries=attempts, base_delay=base_delay, max_delay=max_delay, jitter=True
    )
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return await func()
        except Exception as e:
            last_error = e
            if attempt < attempts - 1:
                await asyncio.sleep(policy.get_delay(attempt))
    raise last_error


__all__ = ["retry", "ExponentialBackoff"]
