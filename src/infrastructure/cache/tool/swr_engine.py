"""Stale-While-Revalidate (SWR) Engine.

State-driven refresh logic with anti-dogpile protection.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from src.infrastructure.cache.tool.single_flight import SingleFlightCoordinator
from src.infrastructure.cache.tool.state_machine import StateManager
from src.infrastructure.cache.tool.types import CacheEntry, CacheResponse, KeyState

logger = logging.getLogger(__name__)


@dataclass
class SWRConfig:
    """Configuration for SWR behavior."""

    early_refresh_threshold: float = 0.9
    early_refresh_probability: float = 0.1
    max_concurrent_refreshes: int = 10
    refresh_timeout_seconds: float = 30.0
    enable_early_refresh: bool = True


@dataclass
class SWRDecision:
    """Decision from SWR engine."""

    action: Literal["RETURN_FRESH", "RETURN_STALE", "TRIGGER_REFRESH", "LOAD"]
    response: CacheResponse
    should_refresh: bool
    refresh_key: Optional[str] = None


@dataclass
class RefreshRequest:
    """Request for async refresh."""

    key: str
    tool: str
    entry: CacheEntry
    priority: int = 0
    created_at: float = field(default_factory=time.time)
    attempts: int = 0


class SWREngine:
    """Stale-While-Revalidate engine.

    Rules:
    | State   | Behavior                                      |
    |---------|----------------------------------------------|
    | FRESH   | Return immediately                           |
    | STALE   | Return stale, trigger exactly 1 refresh/key  |
    | REFRESHING | No duplicate refresh allowed            |

    Anti-dogpile: if now > 0.9 * expires_at, refresh_probability = 10%
    """

    def __init__(
        self,
        state_manager: StateManager,
        single_flight: SingleFlightCoordinator,
        config: SWRConfig | None = None,
    ) -> None:
        self.state_manager = state_manager
        self.single_flight = single_flight
        self.config = config or SWRConfig()

        self._refresh_queue: asyncio.PriorityQueue[tuple[int, RefreshRequest]] = (
            asyncio.PriorityQueue()
        )
        self._active_refreshes: dict[str, RefreshRequest] = {}
        self._lock = asyncio.Lock()
        self._refresh_worker_task: Optional[asyncio.Task] = None

    async def decide(
        self,
        key: str,
        entry: Optional[CacheEntry],
    ) -> SWRDecision:
        """Decide action based on entry state.

        Args:
            key: Cache key
            entry: Current cache entry (may be None for MISS)

        Returns:
            SWRDecision with action and response
        """
        if entry is None:
            return SWRDecision(
                action="LOAD",
                response=CacheResponse.miss("Key not in cache"),
                should_refresh=False,
            )

        now = time.time()
        state = await self.state_manager.get_state(key)

        expires_at = entry.expires_at or float("inf")
        time_to_expiry = expires_at - now
        ttl = entry.expires_at - entry.created_at if entry.expires_at else 0

        if state == KeyState.FRESH:
            return self._decide_fresh(key, entry, now, time_to_expiry, ttl)

        if state == KeyState.STALE:
            return await self._decide_stale(key, entry, now)

        if state == KeyState.REFRESHING:
            return self._decide_refreshing(key, entry)

        if state == KeyState.DEGRADED:
            return SWRDecision(
                action="RETURN_STALE",
                response=CacheResponse.degraded(
                    "System degraded, using stale data",
                    entry.value,
                ),
                should_refresh=False,
            )

        if state == KeyState.LOADING:
            return SWRDecision(
                action="RETURN_STALE",
                response=CacheResponse.miss("Still loading"),
                should_refresh=False,
            )

        return SWRDecision(
            action="LOAD",
            response=CacheResponse.miss(f"Unknown state: {state}"),
            should_refresh=False,
        )

    def _decide_fresh(
        self,
        key: str,
        entry: CacheEntry,
        now: float,
        time_to_expiry: float,
        ttl: float,
    ) -> SWRDecision:
        """Decide action for FRESH state."""
        entry.record_hit()

        if self.config.enable_early_refresh and ttl > 0:
            refresh_boundary = ttl * (1 - self.config.early_refresh_threshold)
            if time_to_expiry <= refresh_boundary:
                if self._should_early_refresh():
                    return SWRDecision(
                        action="TRIGGER_REFRESH",
                        response=CacheResponse.stale(
                            entry.value,
                            entry.expires_at,
                            "Early refresh triggered",
                        ),
                        should_refresh=True,
                        refresh_key=key,
                    )

        return SWRDecision(
            action="RETURN_FRESH",
            response=CacheResponse.hit(entry.value, entry.expires_at),
            should_refresh=False,
        )

    async def _decide_stale(
        self,
        key: str,
        entry: CacheEntry,
        now: float,
    ) -> SWRDecision:
        """Decide action for STALE state."""
        entry.record_hit()

        if self.single_flight.is_in_flight(key):
            return SWRDecision(
                action="RETURN_STALE",
                response=CacheResponse.stale(
                    entry.value,
                    entry.expires_at,
                    "Refresh already in progress",
                ),
                should_refresh=False,
            )

        return SWRDecision(
            action="TRIGGER_REFRESH",
            response=CacheResponse.stale(
                entry.value,
                entry.expires_at,
                "Stale data, triggering refresh",
            ),
            should_refresh=True,
            refresh_key=key,
        )

    def _decide_refreshing(
        self,
        key: str,
        entry: CacheEntry,
    ) -> SWRDecision:
        """Decide action for REFRESHING state."""
        entry.record_hit()

        return SWRDecision(
            action="RETURN_STALE",
            response=CacheResponse.stale(
                entry.value,
                entry.expires_at,
                "Refresh in progress, returning stale",
            ),
            should_refresh=False,
        )

    def _should_early_refresh(self) -> bool:
        """Determine if early refresh should happen."""
        return (
            self.config.enable_early_refresh
            and self._random() < self.config.early_refresh_probability
        )

    def _random(self) -> float:
        """Generate random float [0, 1)."""
        import random
        return random.random()

    async def start_refresh_worker(self) -> None:
        """Start background refresh worker."""
        if self._refresh_worker_task is None or self._refresh_worker_task.done():
            self._refresh_worker_task = asyncio.create_task(self._refresh_worker())

    async def stop_refresh_worker(self) -> None:
        """Stop background refresh worker."""
        if self._refresh_worker_task:
            self._refresh_worker_task.cancel()
            try:
                await self._refresh_worker_task
            except asyncio.CancelledError:
                pass
            self._refresh_worker_task = None

    async def queue_refresh(
        self,
        key: str,
        tool: str,
        entry: CacheEntry,
        priority: int = 0,
    ) -> None:
        """Queue a refresh request.

        Args:
            key: Cache key
            tool: Tool name
            entry: Current entry
            priority: Higher = more urgent
        """
        request = RefreshRequest(
            key=key,
            tool=tool,
            entry=entry,
            priority=priority,
        )

        await self._refresh_queue.put((~priority, request))
        logger.debug(f"Queued refresh for key {key} with priority {priority}")

    async def _refresh_worker(self) -> None:
        """Background worker that processes refresh queue."""
        while True:
            try:
                _, request = await asyncio.wait_for(
                    self._refresh_queue.get(),
                    timeout=1.0,
                )

                if len(self._active_refreshes) >= self.config.max_concurrent_refreshes:
                    await self._refresh_queue.put((~request.priority, request))
                    await asyncio.sleep(0.1)
                    continue

                asyncio.create_task(self._do_refresh(request))

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Refresh worker error: {e}")

    async def _do_refresh(self, request: RefreshRequest) -> None:
        """Execute a single refresh."""
        key = request.key
        self._active_refreshes[key] = request

        try:
            await self.state_manager.transition(key, "refresh_start", KeyState.REFRESHING)
        except Exception as e:
            logger.warning(f"Failed to transition to REFRESHING: {e}")
        finally:
            self._active_refreshes.pop(key, None)

    def get_stats(self) -> dict[str, Any]:
        """Get SWR statistics."""
        return {
            "queue_size": self._refresh_queue.qsize(),
            "active_refreshes": len(self._active_refreshes),
            "max_concurrent_refreshes": self.config.max_concurrent_refreshes,
        }
