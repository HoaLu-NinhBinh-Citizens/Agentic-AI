"""Embedding Budget - RAG cost control, rerank budget.

Manages embedding costs for RAG operations.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingCostConfig:
    """Configuration for embedding costs."""

    cost_per_1k_tokens: float = 0.0001
    max_batch_size: int = 100
    rerank_cost_per_1k: float = 0.01
    max_rerank_results: int = 20


@dataclass
class EmbeddingUsage:
    """Embedding usage statistics."""

    total_tokens: int = 0
    total_cost: float = 0.0
    embedding_calls: int = 0
    rerank_calls: int = 0
    rerank_cost: float = 0.0


class EmbeddingBudget:
    """Manages embedding budget for RAG operations.

    Features:
    - Token-based cost tracking
    - Batch size limits
    - Rerank budget
    - Usage reporting
    """

    def __init__(
        self,
        config: EmbeddingCostConfig | None = None,
        max_daily_tokens: int = 1000000,
    ) -> None:
        """Initialize embedding budget manager.

        Args:
            config: Embedding cost configuration.
            max_daily_tokens: Maximum tokens per day.
        """
        self._config = config or EmbeddingCostConfig()
        self._max_daily_tokens = max_daily_tokens
        self._usage = EmbeddingUsage()
        self._lock = asyncio.Lock()

    async def check_and_record(
        self,
        token_count: int,
        is_rerank: bool = False,
    ) -> tuple[bool, float]:
        """Check budget and record usage.

        Args:
            token_count: Number of tokens.
            is_rerank: Whether this is a rerank operation.

        Returns:
            Tuple of (allowed, estimated_cost).
        """
        async with self._lock:
            if is_rerank:
                cost = (token_count / 1000) * self._config.rerank_cost_per_1k
                self._usage.rerank_calls += 1
                self._usage.rerank_cost += cost
                self._usage.total_cost += cost
                return True, cost

            projected_tokens = self._usage.total_tokens + token_count
            if projected_tokens > self._max_daily_tokens:
                logger.warning(
                    "Embedding budget exceeded: projected=%d limit=%d",
                    projected_tokens,
                    self._max_daily_tokens,
                )
                return False, 0.0

            cost = (token_count / 1000) * self._config.cost_per_1k_tokens
            self._usage.embedding_calls += 1
            self._usage.total_tokens += token_count
            self._usage.total_cost += cost

            logger.debug(
                "Embedding recorded: tokens=%d cost=%.6f total=%.6f",
                token_count,
                cost,
                self._usage.total_cost,
            )

            return True, cost

    async def estimate_cost(self, token_count: int, is_rerank: bool = False) -> float:
        """Estimate cost without recording.

        Args:
            token_count: Number of tokens.
            is_rerank: Whether this is a rerank operation.

        Returns:
            Estimated cost.
        """
        if is_rerank:
            return (token_count / 1000) * self._config.rerank_cost_per_1k
        return (token_count / 1000) * self._config.cost_per_1k_tokens

    async def check_batch(self, batch_size: int) -> tuple[bool, str]:
        """Check if batch size is allowed.

        Args:
            batch_size: Requested batch size.

        Returns:
            Tuple of (allowed, reason).
        """
        if batch_size > self._config.max_batch_size:
            return False, f"Batch size {batch_size} exceeds max {self._config.max_batch_size}"
        return True, "Batch allowed"

    async def get_usage(self) -> EmbeddingUsage:
        """Get current usage statistics.

        Returns:
            EmbeddingUsage with current stats.
        """
        async with self._lock:
            return EmbeddingUsage(
                total_tokens=self._usage.total_tokens,
                total_cost=self._usage.total_cost,
                embedding_calls=self._usage.embedding_calls,
                rerank_calls=self._usage.rerank_calls,
                rerank_cost=self._usage.rerank_cost,
            )

    async def reset(self) -> None:
        """Reset usage counters."""
        async with self._lock:
            self._usage = EmbeddingUsage()
            logger.info("Embedding budget usage reset")

    async def get_stats(self) -> dict[str, Any]:
        """Get budget statistics.

        Returns:
            Statistics dictionary.
        """
        usage = await self.get_usage()
        return {
            "config": {
                "cost_per_1k_tokens": self._config.cost_per_1k_tokens,
                "max_batch_size": self._config.max_batch_size,
                "rerank_cost_per_1k": self._config.rerank_cost_per_1k,
                "max_rerank_results": self._config.max_rerank_results,
            },
            "usage": {
                "total_tokens": usage.total_tokens,
                "total_cost": usage.total_cost,
                "embedding_calls": usage.embedding_calls,
                "rerank_calls": usage.rerank_calls,
                "rerank_cost": usage.rerank_cost,
            },
            "limits": {
                "max_daily_tokens": self._max_daily_tokens,
                "tokens_remaining": max(0, self._max_daily_tokens - usage.total_tokens),
                "utilization_percent": (usage.total_tokens / self._max_daily_tokens * 100)
                if self._max_daily_tokens > 0
                else 0,
            },
        }
