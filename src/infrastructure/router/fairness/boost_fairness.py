"""Fairness boost budget calculator.

Distributes boost budget fairly across intents with per-intent caps.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.infrastructure.router.types import BoostFairnessConfig

logger = logging.getLogger(__name__)


class FairnessBoostCalculator:
    """
    Calculates boost with fairness constraints.
    
    Ensures:
    - No intent exceeds per_intent_weight_cap of global budget
    - Every intent gets at least min_share_per_intent
    - No intent is starved
    """

    def __init__(self, config: BoostFairnessConfig):
        self._config = config
        self._intent_usage: dict[str, float] = {}
        self._usage_reset_time = time.time()
        self._lock = asyncio.Lock()

    async def calculate_boost(
        self,
        intent: str,
        base_score: float,
        max_intent_boost: float,
    ) -> float:
        """
        Calculate fair boost for intent.
        
        Args:
            intent: Intent path
            base_score: Base score to add boost to
            max_intent_boost: Maximum boost for this intent
            
        Returns:
            Base score with fair boost applied
        """
        if not self._config.enabled:
            return base_score + max_intent_boost

        await self._reset_if_needed()
        await self._lock.acquire()

        try:
            current_usage = self._intent_usage.get(intent, 0.0)

            max_this_intent = (
                self._config.global_boost_per_second * self._config.per_intent_weight_cap
            )

            if current_usage >= max_this_intent:
                logger.debug(f"Intent {intent} exhausted boost budget")
                return base_score

            available = max_this_intent - current_usage

            effective_boost = min(max_intent_boost, available)

            min_boost = max_intent_boost * self._config.min_share_per_intent
            effective_boost = max(effective_boost, min_boost)

            self._intent_usage[intent] = current_usage + effective_boost

            return base_score + effective_boost

        finally:
            self._lock.release()

    async def _reset_if_needed(self) -> None:
        """Reset usage counters every second."""
        now = time.time()
        if now - self._usage_reset_time >= 1.0:
            async with self._lock:
                if now - self._usage_reset_time >= 1.0:
                    self._intent_usage.clear()
                    self._usage_reset_time = now

    async def get_usage_stats(self) -> dict[str, dict]:
        """Get usage statistics for all intents."""
        await self._reset_if_needed()
        async with self._lock:
            max_per_intent = (
                self._config.global_boost_per_second * self._config.per_intent_weight_cap
            )
            return {
                intent: {
                    "usage": usage,
                    "max_allowed": max_per_intent,
                    "remaining": max(0, max_per_intent - usage),
                }
                for intent, usage in self._intent_usage.items()
            }

    def get_config(self) -> BoostFairnessConfig:
        """Get fairness configuration."""
        return self._config
