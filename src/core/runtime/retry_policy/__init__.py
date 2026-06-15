"""Retry policy with exponential backoff and jitter.

Note: the production tool-execution path uses its own richer policies
(``src/infrastructure/tool_execution/retry.py`` and
``src/core/execution/cancellation.py``). This module is the lightweight,
general-purpose policy; it now adds capped exponential backoff plus jitter so
concurrent retriers do not synchronize ("thundering herd").

This package ``__init__`` is the importable target for
``src.core.runtime.retry_policy``. A sibling ``retry_policy.py`` module exists
but is shadowed by this package and is therefore unreachable.
"""

import asyncio
import random
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class RetryPolicy:
    """Retry policy for failed operations.

    Args:
        max_attempts: Total attempts before giving up.
        delay: Base delay (seconds) for the first backoff.
        backoff_factor: Multiplier applied per attempt (exponential growth).
        max_delay: Upper bound on the delay before jitter is added.
        jitter_factor: Fraction of the computed delay added as random jitter,
            in ``[0, jitter_factor * delay]``. ``0.0`` disables jitter
            (deterministic, useful in tests).
    """

    def __init__(
        self,
        max_attempts: int = 3,
        delay: float = 1.0,
        backoff_factor: float = 2.0,
        max_delay: float = 30.0,
        jitter_factor: float = 0.1,
    ):
        self.max_attempts = max_attempts
        self.delay = delay
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay
        self.jitter_factor = jitter_factor

    def compute_delay(self, attempt: int) -> float:
        """Delay before the retry that follows a failed ``attempt`` (0-based).

        Capped exponential backoff plus optional jitter.
        """
        base = self.delay * (self.backoff_factor ** attempt)
        capped = min(base, self.max_delay)
        if self.jitter_factor > 0:
            capped += random.uniform(0, self.jitter_factor * capped)
        return capped

    async def execute(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute ``func`` with retries on exception."""
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_attempts - 1:
                    await asyncio.sleep(self.compute_delay(attempt))
        raise last_error


__all__ = ["RetryPolicy"]
