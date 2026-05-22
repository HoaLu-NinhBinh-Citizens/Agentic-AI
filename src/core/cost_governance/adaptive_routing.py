"""Adaptive Routing - route to cheapest model meeting quality threshold.

Routes requests to appropriate LLM models based on quality requirements and cost.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    """Model tier levels."""

    FAST = "fast"
    BALANCED = "balanced"
    ACCURATE = "accurate"


class RoutingPolicy(str, Enum):
    """Routing policies."""

    CHEAPEST = "cheapest"
    QUALITY_FIRST = "quality_first"
    ROUND_ROBIN = "round_robin"
    ADAPTIVE = "adaptive"


@dataclass
class ModelInfo:
    """Information about a model."""

    name: str
    tier: ModelTier
    cost_per_token: float
    quality_score: float
    latency_ms: float
    max_tokens: int
    capabilities: list[str] = field(default_factory=list)


@dataclass
class RoutingDecision:
    """Result of a routing decision."""

    model_name: str
    tier: ModelTier
    reason: str
    estimated_cost: float
    estimated_latency_ms: float


class AdaptiveRouter:
    """Routes requests to appropriate models based on requirements.

    Features:
    - Route to cheapest model meeting quality threshold
    - Tier-based routing (fast/balanced/accurate)
    - Quality-aware routing
    - Cost optimization
    """

    def __init__(
        self,
        policy: RoutingPolicy = RoutingPolicy.QUALITY_FIRST,
        quality_threshold: float = 0.7,
    ) -> None:
        """Initialize adaptive router.

        Args:
            policy: Routing policy.
            quality_threshold: Minimum quality threshold (0-1).
        """
        self._policy = policy
        self._quality_threshold = quality_threshold
        self._models: dict[str, ModelInfo] = {}
        self._tier_counters: dict[ModelTier, int] = {
            ModelTier.FAST: 0,
            ModelTier.BALANCED: 0,
            ModelTier.ACCURATE: 0,
        }
        self._lock = asyncio.Lock()

    def register_model(self, model: ModelInfo) -> None:
        """Register a model.

        Args:
            model: Model information.
        """
        self._models[model.name] = model
        logger.info("Model registered: name=%s tier=%s cost=%.6f", model.name, model.tier.value, model.cost_per_token)

    def get_model(self, name: str) -> ModelInfo | None:
        """Get model by name.

        Args:
            name: Model name.

        Returns:
            ModelInfo or None if not found.
        """
        return self._models.get(name)

    def get_models_by_tier(self, tier: ModelTier) -> list[ModelInfo]:
        """Get all models of a tier.

        Args:
            tier: Model tier.

        Returns:
            List of models.
        """
        return [m for m in self._models.values() if m.tier == tier]

    async def route(
        self,
        required_tier: ModelTier | None = None,
        min_quality: float | None = None,
        max_cost: float | None = None,
        max_latency_ms: float | None = None,
        required_capabilities: list[str] | None = None,
    ) -> RoutingDecision:
        """Route to an appropriate model.

        Args:
            required_tier: Required tier (optional).
            min_quality: Minimum quality score (0-1).
            max_cost: Maximum cost per token.
            max_latency_ms: Maximum latency in milliseconds.
            required_capabilities: Required model capabilities.

        Returns:
            RoutingDecision with selected model.
        """
        async with self._lock:
            candidates = self._filter_candidates(
                required_tier=required_tier,
                min_quality=min_quality,
                max_cost=max_cost,
                max_latency_ms=max_latency_ms,
                required_capabilities=required_capabilities,
            )

            if not candidates:
                return RoutingDecision(
                    model_name="",
                    tier=ModelTier.BALANCED,
                    reason="No model matches requirements",
                    estimated_cost=0.0,
                    estimated_latency_ms=0.0,
                )

            if self._policy == RoutingPolicy.CHEAPEST:
                model = min(candidates, key=lambda m: m.cost_per_token)
                reason = "cheapest model meeting requirements"
            elif self._policy == RoutingPolicy.QUALITY_FIRST:
                model = max(candidates, key=lambda m: m.quality_score)
                reason = "highest quality model meeting requirements"
            elif self._policy == RoutingPolicy.ROUND_ROBIN:
                model = self._round_robin_select(candidates)
                reason = "round-robin selection"
            else:
                model = candidates[0]
                reason = "first matching model"

            logger.debug(
                "Routing decision: model=%s tier=%s reason=%s",
                model.name,
                model.tier.value,
                reason,
            )

            return RoutingDecision(
                model_name=model.name,
                tier=model.tier,
                reason=reason,
                estimated_cost=model.cost_per_token,
                estimated_latency_ms=model.latency_ms,
            )

    def _filter_candidates(
        self,
        required_tier: ModelTier | None,
        min_quality: float | None,
        max_cost: float | None,
        max_latency_ms: float | None,
        required_capabilities: list[str] | None,
    ) -> list[ModelInfo]:
        """Filter models by requirements."""
        candidates = list(self._models.values())

        if required_tier:
            candidates = [m for m in candidates if m.tier == required_tier]

        effective_quality = min_quality if min_quality is not None else self._quality_threshold
        candidates = [m for m in candidates if m.quality_score >= effective_quality]

        if max_cost is not None:
            candidates = [m for m in candidates if m.cost_per_token <= max_cost]

        if max_latency_ms is not None:
            candidates = [m for m in candidates if m.latency_ms <= max_latency_ms]

        if required_capabilities:
            candidates = [
                m for m in candidates
                if all(cap in m.capabilities for cap in required_capabilities)
            ]

        return candidates

    def _round_robin_select(self, candidates: list[ModelInfo]) -> ModelInfo:
        """Select model using round-robin."""
        if not candidates:
            return candidates[0]

        tier = candidates[0].tier
        counter = self._tier_counters[tier]
        index = counter % len(candidates)
        self._tier_counters[tier] = counter + 1

        return candidates[index]

    def get_stats(self) -> dict[str, Any]:
        """Get router statistics.

        Returns:
            Statistics dictionary.
        """
        return {
            "policy": self._policy.value,
            "quality_threshold": self._quality_threshold,
            "models_registered": len(self._models),
            "by_tier": {
                tier.value: len(self.get_models_by_tier(tier))
                for tier in ModelTier
            },
        }
