"""Lifecycle manager for intent lifecycle management.

Manages intent disable/restore with TTL and health-based auto-recovery.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.infrastructure.router.types import IntentLifecycle, LifecycleConfig, IntentLifecycleState

logger = logging.getLogger(__name__)


class LifecycleManager:
    """
    Manages intent lifecycle with rollback-safe behavior.
    
    Features:
    - Disable intent with TTL for auto-recovery
    - Auto-restore based on health metrics
    - Exponential backoff for repeated disables
    """

    def __init__(
        self,
        storage: LifecycleStorage,
        config: LifecycleConfig,
        health_monitor: "HealthMonitor",
    ):
        self._storage = storage
        self._config = config
        self._health_monitor = health_monitor
        self._lifecycle_cache: dict[str, IntentLifecycle] = {}
        self._cache_ttl = 60
        self._lock = asyncio.Lock()

    async def get_intent_state(self, intent_path: str) -> IntentLifecycle:
        """
        Get current lifecycle state for intent.
        
        Checks cache first, then loads from storage.
        """
        cached = self._lifecycle_cache.get(intent_path)
        if cached and time.time() - (cached.disabled_at or 0) < self._cache_ttl:
            if not cached.should_auto_restore:
                return cached

        lifecycle = await self._storage.load_lifecycle(intent_path)

        if lifecycle.should_auto_restore:
            await self._attempt_restore(lifecycle)

        self._lifecycle_cache[intent_path] = lifecycle
        return lifecycle

    async def disable_intent(
        self,
        intent_path: str,
        reason: str,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """
        Disable intent with TTL for auto-recovery.
        
        Args:
            intent_path: Intent to disable
            reason: Reason for disabling
            ttl_seconds: TTL in seconds (default from config)
        """
        ttl = ttl_seconds or self._config.disable_ttl_seconds

        await self._storage.save_lifecycle(intent_path, {
            "state": "disabled",
            "disabled_at": time.time(),
            "disable_ttl_seconds": ttl,
            "auto_restore_after": time.time() + ttl,
        })

        self._lifecycle_cache.pop(intent_path, None)

        logger.warning(
            f"Intent {intent_path} disabled: {reason}, TTL={ttl}s"
        )

    async def enable_intent(self, intent_path: str) -> None:
        """Manually enable intent (cancel any pending disable)."""
        await self._storage.save_lifecycle(intent_path, {
            "state": "active",
            "disabled_at": None,
            "disable_ttl_seconds": self._config.disable_ttl_seconds,
            "auto_restore_after": None,
        })

        self._lifecycle_cache.pop(intent_path, None)
        logger.info(f"Intent {intent_path} enabled")

    async def _attempt_restore(self, lifecycle: IntentLifecycle) -> None:
        """
        Attempt to restore disabled intent based on health.
        """
        if not self._config.auto_restore_if_health_recovers:
            return

        success_rate = await self._health_monitor.get_success_rate(
            lifecycle.intent_path,
            window_hours=float(self._config.restore_observation_window_hours),
        )

        if success_rate >= self._config.restore_success_rate_threshold:
            await self._restore_intent(lifecycle, success_rate)
        else:
            new_ttl = int(lifecycle.disable_ttl_seconds * 0.5)
            new_ttl = max(new_ttl, 3600)

            await self.disable_intent(
                lifecycle.intent_path,
                reason=f"Health not recovered: rate={success_rate:.2f}",
                ttl_seconds=new_ttl,
            )

    async def _restore_intent(
        self,
        lifecycle: IntentLifecycle,
        success_rate: float,
    ) -> None:
        """Restore intent to active state."""
        await self._storage.save_lifecycle(lifecycle.intent_path, {
            "state": "active",
            "disabled_at": None,
            "disable_ttl_seconds": self._config.disable_ttl_seconds,
            "auto_restore_after": None,
            "health_check_start": time.time(),
        })

        self._lifecycle_cache.pop(lifecycle.intent_path, None)

        logger.info(
            f"Intent {lifecycle.intent_path} auto-restored: "
            f"success_rate={success_rate:.2f}"
        )

    async def check_post_restore_health(self, intent_path: str) -> None:
        """
        Monitor health after restore. Disable if still unhealthy.
        """
        lifecycle = await self.get_intent_state(intent_path)

        if lifecycle.state.value != "restored":
            return

        if lifecycle.health_check_start is None:
            return

        window_elapsed = time.time() - lifecycle.health_check_start >= 3600

        if window_elapsed:
            success_rate = await self._health_monitor.get_success_rate(
                intent_path,
                window_hours=1,
            )

            if success_rate < self._config.restore_success_rate_threshold:
                await self.disable_intent(
                    intent_path,
                    reason=f"Post-restore health check failed: rate={success_rate:.2f}",
                    ttl_seconds=lifecycle.disable_ttl_seconds // 2,
                )
            else:
                await self._mark_fully_active(intent_path)

    async def _mark_fully_active(self, intent_path: str) -> None:
        """Mark intent as fully active after successful health check."""
        await self._storage.save_lifecycle(intent_path, {
            "state": "active",
            "health_check_start": None,
        })
        self._lifecycle_cache.pop(intent_path, None)

    async def get_available_intents(
        self,
        all_intents: list[str],
    ) -> list[str]:
        """
        Get list of available intents, filtering out disabled ones.
        
        Args:
            all_intents: List of all configured intents
            
        Returns:
            List of available intents
        """
        available = []
        for intent in all_intents:
            lifecycle = await self.get_intent_state(intent)
            if lifecycle.is_available:
                available.append(intent)
        return available


class LifecycleStorage:
    """
    Storage interface for intent lifecycle data.
    
    Implement this to integrate with your database.
    """

    async def load_lifecycle(self, intent_path: str) -> "IntentLifecycle":
        """Load lifecycle state from storage."""
        from src.infrastructure.router.types import IntentLifecycle, IntentLifecycleState

        return IntentLifecycle(intent_path=intent_path)

    async def save_lifecycle(self, intent_path: str, data: dict) -> None:
        """Save lifecycle state to storage."""
        raise NotImplementedError


class InMemoryLifecycleStorage(LifecycleStorage):
    """In-memory implementation for testing."""

    def __init__(self):
        self._data: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def load_lifecycle(self, intent_path: str) -> "IntentLifecycle":
        from src.infrastructure.router.types import IntentLifecycle, IntentLifecycleState

        async with self._lock:
            data = self._data.get(intent_path, {})
            return IntentLifecycle(
                intent_path=intent_path,
                state=IntentLifecycleState(data.get("state", "active")),
                disabled_at=data.get("disabled_at"),
                disable_ttl_seconds=data.get("disable_ttl_seconds", 86400),
                auto_restore_after=data.get("auto_restore_after"),
                health_check_start=data.get("health_check_start"),
            )

    async def save_lifecycle(self, intent_path: str, data: dict) -> None:
        async with self._lock:
            if intent_path in self._data:
                self._data[intent_path].update(data)
            else:
                self._data[intent_path] = data
