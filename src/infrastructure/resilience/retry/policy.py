"""Retry policies: deterministic delay schedules for retry loops."""

from __future__ import annotations

import random
from dataclasses import dataclass

# Jitter below 1.0 keeps the deterministic exponential lower bound testable
# while still de-synchronizing concurrent retries (thundering herd).
DEFAULT_MAX_DELAY_SECONDS = 30.0


@dataclass
class ExponentialBackoff:
    """Exponential backoff schedule: base_delay * 2^attempt, capped.

    get_delay() is deterministic; pass jitter=True to add up to +50%
    random spread on top of the deterministic floor.
    """

    max_retries: int = 3
    base_delay: float = 0.1
    max_delay: float = DEFAULT_MAX_DELAY_SECONDS
    jitter: bool = False

    def get_delay(self, attempt: int) -> float:
        """Delay before retry `attempt` (0-indexed)."""
        delay = min(self.base_delay * (2**attempt), self.max_delay)
        if self.jitter:
            delay += delay * 0.5 * random.random()
        return delay

    def should_retry(self, attempt: int) -> bool:
        return attempt < self.max_retries
