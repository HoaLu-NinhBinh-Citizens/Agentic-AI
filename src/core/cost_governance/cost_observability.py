"""Cost Observability - metrics: cost_per_session, model_tier_usage, cache_hit_rate.

Provides cost observability and reporting.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CostMetrics:
    """Cost metrics snapshot."""

    timestamp: int
    total_cost: float = 0.0
    total_tokens: int = 0
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    model_usage: dict[str, int] = field(default_factory=dict)
    session_costs: dict[str, float] = field(default_factory=dict)

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0

    @property
    def avg_cost_per_request(self) -> float:
        """Calculate average cost per request."""
        return self.total_cost / self.total_requests if self.total_requests > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "total_cost": self.total_cost,
            "total_tokens": self.total_tokens,
            "total_requests": self.total_requests,
            "cache_hit_rate": self.cache_hit_rate,
            "avg_cost_per_request": self.avg_cost_per_request,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "model_usage": self.model_usage,
            "session_costs": self.session_costs,
        }


class CostObserver:
    """Observes and reports cost metrics.

    Features:
    - Cost per session tracking
    - Model tier usage
    - Cache hit rate
    - Cost aggregations
    """

    def __init__(self) -> None:
        """Initialize cost observer."""
        self._total_cost = 0.0
        self._total_tokens = 0
        self._total_requests = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._model_usage: dict[str, int] = {}
        self._session_costs: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def record_cost(
        self,
        session_id: str,
        cost: float,
        tokens: int,
        model_name: str | None = None,
    ) -> None:
        """Record a cost event.

        Args:
            session_id: Session identifier.
            cost: Cost amount.
            tokens: Number of tokens.
            model_name: Model used.
        """
        async with self._lock:
            self._total_cost += cost
            self._total_tokens += tokens
            self._total_requests += 1

            self._session_costs[session_id] = self._session_costs.get(session_id, 0.0) + cost

            if model_name:
                self._model_usage[model_name] = self._model_usage.get(model_name, 0) + 1

            logger.debug(
                "Cost recorded: session=%s cost=%.6f tokens=%d total=%.4f",
                session_id,
                cost,
                tokens,
                self._total_cost,
            )

    async def record_cache_hit(self) -> None:
        """Record a cache hit."""
        async with self._lock:
            self._cache_hits += 1

    async def record_cache_miss(self) -> None:
        """Record a cache miss."""
        async with self._lock:
            self._cache_misses += 1

    async def get_metrics(self) -> CostMetrics:
        """Get current cost metrics.

        Returns:
            CostMetrics with current values.
        """
        async with self._lock:
            return CostMetrics(
                timestamp=int(datetime.now().timestamp()),
                total_cost=self._total_cost,
                total_tokens=self._total_tokens,
                total_requests=self._total_requests,
                cache_hits=self._cache_hits,
                cache_misses=self._cache_misses,
                model_usage=self._model_usage.copy(),
                session_costs=self._session_costs.copy(),
            )

    async def get_session_cost(self, session_id: str) -> float:
        """Get total cost for a session.

        Args:
            session_id: Session identifier.

        Returns:
            Total cost for session.
        """
        async with self._lock:
            return self._session_costs.get(session_id, 0.0)

    async def get_model_usage(self) -> dict[str, int]:
        """Get model usage counts.

        Returns:
            Dictionary of model name to usage count.
        """
        async with self._lock:
            return self._model_usage.copy()

    async def get_top_sessions(self, limit: int = 10) -> list[tuple[str, float]]:
        """Get top N sessions by cost.

        Args:
            limit: Number of sessions to return.

        Returns:
            List of (session_id, cost) tuples.
        """
        async with self._lock:
            sorted_sessions = sorted(
                self._session_costs.items(),
                key=lambda x: x[1],
                reverse=True,
            )
            return sorted_sessions[:limit]

    async def reset(self) -> None:
        """Reset all metrics."""
        async with self._lock:
            self._total_cost = 0.0
            self._total_tokens = 0
            self._total_requests = 0
            self._cache_hits = 0
            self._cache_misses = 0
            self._model_usage.clear()
            self._session_costs.clear()
            logger.info("Cost metrics reset")

    async def get_stats(self) -> dict[str, Any]:
        """Get cost observer statistics.

        Returns:
            Statistics dictionary.
        """
        metrics = await self.get_metrics()
        top_sessions = await self.get_top_sessions(5)

        return {
            "total_cost": metrics.total_cost,
            "total_tokens": metrics.total_tokens,
            "total_requests": metrics.total_requests,
            "cache_hit_rate": metrics.cache_hit_rate,
            "avg_cost_per_request": metrics.avg_cost_per_request,
            "model_usage": metrics.model_usage,
            "top_sessions": [{"session_id": s[0], "cost": s[1]} for s in top_sessions],
            "session_count": len(self._session_costs),
        }
