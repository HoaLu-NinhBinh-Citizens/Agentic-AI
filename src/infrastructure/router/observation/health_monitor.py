"""Health monitor for intent health tracking."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.infrastructure.router.types import IntentLifecycle

logger = logging.getLogger(__name__)


@dataclass
class HealthRecord:
    """Health record for an intent."""

    intent_path: str
    success: bool
    latency_ms: float
    timestamp: float = field(default_factory=time.time)


class HealthMonitor:
    """
    Monitors intent health based on execution results.
    
    Tracks success rates and latency for health-based decisions.
    """

    def __init__(
        self,
        window_size: int = 100,
        success_rate_threshold: float = 0.7,
    ):
        self._window_size = window_size
        self._success_rate_threshold = success_rate_threshold
        self._records: dict[str, deque[HealthRecord]] = {}
        self._lock = asyncio.Lock()

    async def record(
        self,
        intent: str,
        success: bool,
        latency_ms: float,
    ) -> None:
        """
        Record execution result for intent.
        
        Args:
            intent: Intent path
            success: Whether execution succeeded
            latency_ms: Execution latency in milliseconds
        """
        async with self._lock:
            if intent not in self._records:
                self._records[intent] = deque(maxlen=self._window_size)

            self._records[intent].append(
                HealthRecord(
                    intent_path=intent,
                    success=success,
                    latency_ms=latency_ms,
                )
            )

    async def get_success_rate(
        self,
        intent: str,
        window_hours: float = 1.0,
    ) -> float:
        """
        Get success rate for intent.
        
        Args:
            intent: Intent path
            window_hours: Time window in hours (default 1)
            
        Returns:
            Success rate between 0 and 1
        """
        async with self._lock:
            if intent not in self._records:
                return 1.0  # Default to healthy if no data

            cutoff = time.time() - (window_hours * 3600)
            recent = [r for r in self._records[intent] if r.timestamp >= cutoff]

            if not recent:
                return 1.0

            successes = sum(1 for r in recent if r.success)
            return successes / len(recent)

    async def get_latency_stats(
        self,
        intent: str,
        window_hours: float = 1.0,
    ) -> dict[str, float]:
        """
        Get latency statistics for intent.
        
        Returns:
            Dict with p50, p95, p99 latency
        """
        async with self._lock:
            if intent not in self._records:
                return {"p50": 0.0, "p95": 0.0, "p99": 0.0}

            cutoff = time.time() - (window_hours * 3600)
            recent = [r for r in self._records[intent] if r.timestamp >= cutoff]

            if not recent:
                return {"p50": 0.0, "p95": 0.0, "p99": 0.0}

            latencies = sorted(r.latency_ms for r in recent)
            n = len(latencies)

            return {
                "p50": latencies[int(n * 0.5)],
                "p95": latencies[int(n * 0.95)] if n > 1 else latencies[0],
                "p99": latencies[int(n * 0.99)] if n > 1 else latencies[0],
            }

    async def is_healthy(
        self,
        intent: str,
        threshold: Optional[float] = None,
    ) -> bool:
        """
        Check if intent is healthy based on success rate.
        
        Args:
            intent: Intent path
            threshold: Success rate threshold (default from config)
            
        Returns:
            True if intent is healthy
        """
        threshold = threshold or self._success_rate_threshold
        rate = await self.get_success_rate(intent)
        return rate >= threshold

    async def get_health_summary(self) -> dict[str, dict]:
        """Get health summary for all intents."""
        async with self._lock:
            summary = {}
            for intent in self._records:
                rate = await self.get_success_rate(intent)
                stats = await self.get_latency_stats(intent)
                summary[intent] = {
                    "success_rate": rate,
                    "is_healthy": rate >= self._success_rate_threshold,
                    "sample_count": len(self._records[intent]),
                    "latency": stats,
                }
            return summary
