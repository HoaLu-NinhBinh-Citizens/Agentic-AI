"""Tool Cache - Main facade integrating all cache components.

Production-grade tool cache with Kafka-level rigor.

FIX W-007: Added args validation to prevent cache key collision.
FIX W-010: Load shedding already activated in start().
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

from src.infrastructure.cache.tool.adaptive_ttl import AdaptiveTTLConfig, AdaptiveTTLEngine
from src.infrastructure.cache.tool.load_shedding import LoadSheddingConfig, LoadSheddingController
from src.infrastructure.cache.tool.lru_store import LRUConfig, LRUStore, PinManager
from src.infrastructure.cache.tool.metrics import MetricsConfig, MetricsEngine
from src.infrastructure.cache.tool.normalizer import KeyGenerator, StrictNormalizer
from src.infrastructure.cache.tool.persistence import PersistenceConfig, PersistentStore
from src.infrastructure.cache.tool.rate_limiter import RateLimitConfig, ToolRateLimiter
from src.infrastructure.cache.tool.reconciliation import ReconciliationConfig, ReconciliationEngine
from src.infrastructure.cache.tool.single_flight import SingleFlightConfig, SingleFlightCoordinator
from src.infrastructure.cache.tool.state_machine import StateManager
from src.infrastructure.cache.tool.swr_engine import SWRConfig, SWREngine
from src.infrastructure.cache.tool.threshold_engine import ThresholdConfig, AdaptiveThresholdEngine
from src.infrastructure.cache.tool.types import CacheEntry, CacheResponse, KeyState
from src.infrastructure.cache.tool.validation import PoisonValidationEngine, ValidationConfig
from src.infrastructure.cache.tool.warmup import WarmupConfig, WarmUpManager, WarmupEntry
from src.infrastructure.cache.tool.write_back import WriteBackConfig, WriteBackQueue

logger = logging.getLogger(__name__)


@dataclass
class ToolCacheConfig:
    """Configuration for ToolCache."""

    max_entries: int = 1000
    max_memory_bytes: int = 100 * 1024 * 1024
    default_ttl_seconds: float = 300.0
    enable_persistence: bool = False
    enable_metrics: bool = True
    enable_warmup: bool = True
    enable_args_validation: bool = True  # W-007: Validate args are JSON-serializable


class ToolCache:
    """Production-grade Tool Cache.

    Integrates all cache components:
    - KeyStateMachine (linearizable per-key FSM)
    - StrictNormalizer (lossless canonicalization)
    - KeyGenerator (versioned SHA256)
    - SingleFlightCoordinator (bounded, cancellable)
    - SWREngine (state-driven, no duplicate refresh)
    - ToolRateLimiter (global + per-tool + per-key fairness)
    - AdaptiveThresholdEngine (time-decayed EMA + percentile)
    - LoadSheddingController (DEGRADED lifecycle)
    - LRUStore (byte+entry bounded, lock-free read)
    - PinManager (dual constraint + priority eviction)
    - AdaptiveTTLEngine (time-aware EMA bounded)
    - PoisonValidationEngine (Pydantic or strict schema)
    - WarmUpManager (atomic init-only)
    - PersistentStore (append-only async log)
    - WriteBackQueue (non-blocking, drop/spill only)
    - MetricsEngine (lock-free counters + sampling)
    - ReconciliationEngine (vector-clock resolver)

    Core Principle:
    Cache is a non-authoritative optimization layer, not a correctness dependency.
    - Cache failure = fallback to tool execution
    - Cache corruption = automatic bypass (self-healing)
    - Cache unavailability = system continues normally
    """

    def __init__(self, config: ToolCacheConfig | None = None) -> None:
        self.config = config or ToolCacheConfig()

        self._normalizer = StrictNormalizer()
        self._key_generator = KeyGenerator(self._normalizer)
        self._state_manager = StateManager()

        self._single_flight = SingleFlightCoordinator(
            SingleFlightConfig()
        )
        self._rate_limiter = ToolRateLimiter(RateLimitConfig())

        self._lru_store = LRUStore(LRUConfig(
            max_entries=self.config.max_entries,
            max_memory_bytes=self.config.max_memory_bytes,
        ))
        self._pin_manager = PinManager(self._lru_store)

        self._swr_engine = SWREngine(
            state_manager=self._state_manager,
            single_flight=self._single_flight,
            config=SWRConfig(),
        )

        self._threshold_engine = AdaptiveThresholdEngine(ThresholdConfig())
        self._load_shedding = LoadSheddingController(
            state_manager=self._state_manager,
            threshold_engine=self._threshold_engine,
            config=LoadSheddingConfig(),
        )

        self._validation = PoisonValidationEngine(ValidationConfig())

        self._persistence = PersistentStore(PersistenceConfig()) if self.config.enable_persistence else None
        self._write_back = WriteBackQueue(WriteBackConfig()) if self.config.enable_persistence else None

        self._metrics = MetricsEngine(MetricsConfig()) if self.config.enable_metrics else None

        self._warmup = WarmUpManager(
            store=self._lru_store,
            state_manager=self._state_manager,
            config=WarmupConfig(),
        )

        self._reconciliation = ReconciliationEngine(ReconciliationConfig())

        self._ttl_engines: dict[str, AdaptiveTTLEngine] = {}

        self._running = False

    async def start(self) -> None:
        """Start the cache."""
        if self._running:
            return

        self._running = True

        if self._persistence:
            await self._persistence.start()

        if self._write_back:
            await self._write_back.start()

        if self._metrics:
            await self._metrics.start()

        await self._load_shedding.start()
        await self._swr_engine.start_refresh_worker()

        logger.info("ToolCache started")

    async def stop(self) -> None:
        """Stop the cache."""
        self._running = False

        await self._swr_engine.stop_refresh_worker()
        await self._load_shedding.stop()

        if self._metrics:
            await self._metrics.stop()

        if self._write_back:
            await self._write_back.stop()

        if self._persistence:
            await self._persistence.stop()

        logger.info("ToolCache stopped")

    def generate_key(
        self,
        tool: str,
        version: str,
        args: dict[str, Any],
    ) -> str:
        """Generate cache key.

        FIX W-007: Validates args are JSON-serializable to prevent key collision.

        Args:
            tool: Tool name
            version: Tool version
            args: Tool arguments

        Returns:
            Cache key (SHA256 hash)
            
        Raises:
            ValueError: If args contains non-serializable types.
        """
        # W-007: Validate args are JSON-serializable
        if self.config.enable_args_validation:
            try:
                json.dumps(args)
            except (TypeError, ValueError) as e:
                raise ValueError(
                    f"Args must be JSON-serializable for cache key generation: {e}"
                )
        
        return self._key_generator.generate(tool, version, args)

    async def get(
        self,
        key: str,
        tool: str,
    ) -> CacheResponse:
        """Get value from cache.

        Args:
            key: Cache key
            tool: Tool name

        Returns:
            CacheResponse with value and state
        """
        if self._load_shedding.is_degraded:
            self._metrics.record_miss() if self._metrics else None
            return CacheResponse.degraded("System degraded")

        entry = await self._lru_store.get(key)

        if entry is None:
            self._metrics.record_miss() if self._metrics else None
            return CacheResponse.miss("Key not found")

        state = await self._state_manager.get_state(key)

        if state == KeyState.FRESH:
            self._metrics.record_hit() if self._metrics else None
            return CacheResponse.hit(entry.value, entry.expires_at)

        if state == KeyState.STALE:
            self._metrics.record_hit() if self._metrics else None
            return CacheResponse.stale(entry.value, entry.expires_at, "TTL expired")

        if state == KeyState.REFRESHING:
            self._metrics.record_hit() if self._metrics else None
            return CacheResponse.stale(entry.value, entry.expires_at, "Refresh in progress")

        return CacheResponse.miss("Unknown state")

    async def set(
        self,
        key: str,
        value: Any,
        tool: str,
        ttl_seconds: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[bool, str | None]:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            tool: Tool name
            ttl_seconds: TTL in seconds
            metadata: Optional metadata

        Returns:
            (success, error_reason)
        """
        validation_result = self._validation.validate(tool, value)
        if not validation_result.valid:
            return (False, validation_result.message)

        ttl = ttl_seconds or self._get_ttl(tool)

        entry = CacheEntry(
            key=key,
            value=value,
            state=KeyState.FRESH,
            created_at=time.time(),
            expires_at=time.time() + ttl,
            metadata=metadata or {},
        )

        entry = self._reconciliation.attach_clock(entry)

        success = await self._lru_store.set(key, entry)
        if success:
            await self._state_manager.transition(key, "set", KeyState.FRESH)

            if self._write_back:
                await self._write_back.enqueue(key, entry)

            if self._persistence:
                await self._persistence.append("SET", key, value, {
                    "state": entry.state.name,
                    "expires_at": entry.expires_at,
                })

        return (success, None)

    async def delete(self, key: str) -> bool:
        """Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if deleted
        """
        deleted = await self._lru_store.delete(key)
        if deleted:
            await self._state_manager.transition(key, "delete", KeyState.MISS)

            if self._persistence:
                await self._persistence.append("DELETE", key, None, {})

        return deleted

    async def refresh(
        self,
        key: str,
        tool: str,
        fn: Callable[..., Coroutine[Any, Any, Any]],
    ) -> CacheResponse:
        """Refresh a cache entry.

        Args:
            key: Cache key
            tool: Tool name
            fn: Async function to get new value

        Returns:
            CacheResponse with new value
        """
        if self._load_shedding.should_reject_new_work():
            return CacheResponse.degraded("System overloaded")

        try:
            acquired = await self._single_flight.acquire(key, tool)
            if acquired is not None:
                return await acquired

            try:
                value = await fn()

                ttl = self._get_ttl(tool)
                success, reason = await self.set(key, value, tool, ttl)

                if success:
                    await self._state_manager.transition(key, "refresh_success", KeyState.FRESH)
                    self._metrics.record_refresh() if self._metrics else None
                    return CacheResponse.hit(value, time.time() + ttl)
                else:
                    await self._state_manager.transition(key, "refresh_failure", KeyState.STALE)
                    return CacheResponse.stale(None, 0, reason)

            finally:
                await self._single_flight.release(key)

        except Exception as e:
            logger.error(f"Refresh error for key {key}: {e}")
            await self._state_manager.transition(key, "refresh_error", KeyState.STALE)
            self._metrics.record_failure() if self._metrics else None
            return CacheResponse.stale(None, 0, str(e))

    def pin(self, key: str) -> bool:
        """Pin an entry (prevents eviction).

        Args:
            key: Cache key

        Returns:
            True if pinned
        """
        return asyncio.run(self._pin_manager.pin(key))

    def unpin(self, key: str) -> bool:
        """Unpin an entry.

        Args:
            key: Cache key

        Returns:
            True if unpinned
        """
        return asyncio.run(self._pin_manager.unpin(key))

    async def warmup(
        self,
        entries: list[WarmupEntry],
    ) -> dict[str, Any]:
        """Execute warmup with entries.

        Args:
            entries: Entries to preload

        Returns:
            Warmup result
        """
        self._warmup.add_entries(entries)
        return await self._warmup.execute()

    def _get_ttl(self, tool: str) -> float:
        """Get TTL for tool.

        Args:
            tool: Tool name

        Returns:
            TTL in seconds
        """
        if tool not in self._ttl_engines:
            self._ttl_engines[tool] = AdaptiveTTLEngine(
                tool,
                AdaptiveTTLConfig(base_ttl_seconds=self.config.default_ttl_seconds),
            )

        return self._ttl_engines[tool].get_ttl(tool)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        stats = {
            "lru_store": self._lru_store.get_stats(),
            "pin_manager": self._pin_manager.get_stats(),
            "single_flight": self._single_flight.get_stats(),
            "rate_limiter": self._rate_limiter.get_stats(),
            "load_shedding": self._load_shedding.get_stats(),
            "swr_engine": self._swr_engine.get_stats(),
        }

        if self._metrics:
            stats["metrics"] = self._metrics.get_stats()

        if self._persistence:
            stats["persistence"] = self._persistence.get_stats()

        if self._write_back:
            stats["write_back"] = self._write_back.get_stats()

        stats["warmup"] = self._warmup.get_stats()
        stats["reconciliation"] = self._reconciliation.get_stats()

        return stats

    async def clear(self) -> None:
        """Clear all cache entries."""
        await self._lru_store.clear()
        logger.info("Cache cleared")
