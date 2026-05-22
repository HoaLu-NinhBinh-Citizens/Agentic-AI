"""Inference Policy - cache strategy, model tiering.

Manages inference policies for cost optimization.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CacheStrategy(str, Enum):
    """Cache strategies."""

    DISABLED = "disabled"
    LRU = "lru"
    TTL = "ttl"
    SEMANTIC = "semantic"


@dataclass
class TierConfig:
    """Configuration for a model tier."""

    tier_name: str
    max_retries: int = 3
    timeout_seconds: float = 60.0
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600


@dataclass
class InferencePolicy:
    """Inference policy configuration."""

    default_tier: str = "balanced"
    cache_strategy: CacheStrategy = CacheStrategy.LRU
    cache_ttl_seconds: int = 3600
    max_context_length: int = 128000
    temperature: float = 0.7
    top_p: float = 0.9
    tiers: dict[str, TierConfig] = field(default_factory=dict)

    def get_tier_config(self, tier: str) -> TierConfig:
        """Get tier configuration."""
        return self.tiers.get(tier, TierConfig(tier_name=tier))


class InferencePolicyManager:
    """Manages inference policies for different scenarios.

    Features:
    - Cache strategy configuration
    - Model tiering
    - Timeout and retry policies
    """

    def __init__(self, default_policy: InferencePolicy | None = None) -> None:
        """Initialize inference policy manager.

        Args:
            default_policy: Default inference policy.
        """
        self._default_policy = default_policy or InferencePolicy()
        self._policies: dict[str, InferencePolicy] = {}
        self._lock = asyncio.Lock()

    async def get_policy(self, name: str | None = None) -> InferencePolicy:
        """Get policy by name or default.

        Args:
            name: Policy name.

        Returns:
            Inference policy.
        """
        if name and name in self._policies:
            return self._policies[name]
        return self._default_policy

    async def register_policy(self, name: str, policy: InferencePolicy) -> None:
        """Register a named policy.

        Args:
            name: Policy name.
            policy: Inference policy.
        """
        async with self._lock:
            self._policies[name] = policy
            logger.info("Inference policy registered: name=%s", name)

    async def get_cache_strategy(self, name: str | None = None) -> CacheStrategy:
        """Get cache strategy for policy.

        Args:
            name: Policy name.

        Returns:
            Cache strategy.
        """
        policy = await self.get_policy(name)
        return policy.cache_strategy

    async def get_tier_config(self, tier: str, policy_name: str | None = None) -> TierConfig:
        """Get tier configuration.

        Args:
            tier: Tier name.
            policy_name: Policy name.

        Returns:
            Tier configuration.
        """
        policy = await self.get_policy(policy_name)
        return policy.get_tier_config(tier)

    async def get_stats(self) -> dict[str, Any]:
        """Get policy manager statistics.

        Returns:
            Statistics dictionary.
        """
        return {
            "default_policy": self._default_policy.default_tier,
            "cache_strategy": self._default_policy.cache_strategy.value,
            "registered_policies": len(self._policies),
        }
