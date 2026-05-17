"""Main compression engine with strategy registry and compression operations."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import TYPE_CHECKING, Literal, Optional

from .config import CompressionConfig
from .types import (
    CompressionMetadata,
    CompressionResult,
    CompressionStats,
    MemoryItem,
    CacheItem,
    OriginalBlob,
)
from .strategies.base import (
    CompressionStrategy,
    StrategyNotFoundError,
    DecompressionError,
)
from .cache import DecompressionCache
from .decompression import Decompressor
from .strategies.truncation import TruncationCompressor
from .strategies.extractive import ExtractiveSummarizer
from .strategies.keyvalue import KeyValueCompactor
from .strategies.adaptive import AdaptivePruner

if TYPE_CHECKING:
    from ...embeddings.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class DistributedLock:
    """Distributed lock interface for multi-instance coordination.
    
    Implementations:
    - RedisDistributedLock (for production)
    - InMemoryDistributedLock (for single instance)
    """
    
    async def acquire(self, key: str, timeout: float = 5.0) -> bool:
        """Acquire a distributed lock."""
        raise NotImplementedError()
    
    async def release(self, key: str) -> None:
        """Release a distributed lock."""
        raise NotImplementedError()
    
    async def is_locked(self, key: str) -> bool:
        """Check if a key is locked."""
        raise NotImplementedError()


class InMemoryDistributedLock(DistributedLock):
    """In-memory lock for single instance (no-op for multi-instance)."""
    
    def __init__(self):
        self._locks: set[str] = set()
        self._lock = asyncio.Lock()
    
    async def acquire(self, key: str, timeout: float = 5.0) -> bool:
        async with self._lock:
            if key not in self._locks:
                self._locks.add(key)
                return True
            return False
    
    async def release(self, key: str) -> None:
        async with self._lock:
            self._locks.discard(key)
    
    async def is_locked(self, key: str) -> bool:
        return key in self._locks


class RedisDistributedLock(DistributedLock):
    """Redis-based distributed lock for multi-instance production deployments.
    
    Phase 4E: Issues #2-4 - Token ownership + heartbeat renewal.
    
    Uses Redis SET NX EX for atomic lock acquisition with expiration.
    Token ownership prevents split-brain: only the owner can release.
    Background heartbeat renews locks before expiration.
    
    Args:
        redis_url: Redis connection URL (e.g., redis://localhost:6379)
        prefix: Key prefix for lock keys (default: "compression_lock:")
        timeout: Lock expiration timeout in seconds
        heartbeat_interval: Interval for lock renewal (default: timeout / 3)
        fallback_to_inmemory: If True, fall back to in-memory lock when Redis fails.
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        prefix: str = "compression_lock:",
        timeout: float = 30.0,
        heartbeat_interval: float = 10.0,
        fallback_to_inmemory: bool = True,
        health_check_interval: float = 30.0,
    ):
        import uuid
        
        self._redis_url = redis_url
        self._prefix = prefix
        self._timeout = timeout
        self._heartbeat_interval = heartbeat_interval
        self._fallback = fallback_to_inmemory
        self._health_check_interval = health_check_interval
        
        self._redis = None
        self._local_lock = asyncio.Lock()
        self._in_memory_locks: dict[str, str] = {}  # key -> token
        self._fallback_count = 0
        
        # Token storage for safe release
        self._tokens: dict[str, str] = {}  # full_key -> token
        
        # Heartbeat task
        self._heartbeat_task: asyncio.Task | None = None
        self._active_locks: set[str] = set()
        self._heartbeat_lock = asyncio.Lock()
        
        # Health check task for Redis recovery
        self._health_check_task: asyncio.Task | None = None
        self._redis_available = False
        self._redis_available_lock = asyncio.Lock()
        
        # Track locks acquired while in fallback mode (need transfer when Redis recovers)
        self._pending_transfer_locks: dict[str, str] = {}  # key -> token
    
    async def _get_redis(self):
        """Lazy initialization of Redis client."""
        if self._redis is None:
            try:
                import redis.asyncio as redis
                self._redis = redis.from_url(self._redis_url)
            except ImportError:
                raise ImportError(
                    "redis package required for RedisDistributedLock. "
                    "Install with: pip install redis"
                )
        return self._redis
    
    async def acquire(self, key: str, timeout: float = 5.0) -> bool:
        """Acquire distributed lock with token ownership (Phase 4E: Issue #3).
        
        Token ownership prevents split-brain:
        1. Generate unique UUID token
        2. SET key token NX EX timeout
        3. Store token locally for safe release
        """
        import uuid
        
        full_key = f"{self._prefix}{key}"
        token = str(uuid.uuid4())
        lock_timeout = int(max(timeout, self._timeout))
        
        # Start health check if not running
        if self._health_check_task is None or self._health_check_task.done():
            self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        try:
            redis = await self._get_redis()
            
            # SET key token NX EX timeout
            acquired = await redis.set(
                full_key,
                token,
                nx=True,
                ex=lock_timeout
            )
            
            if acquired:
                # Mark Redis as available
                async with self._redis_available_lock:
                    self._redis_available = True
                
                # Store token for safe release
                self._tokens[full_key] = token
                
                # Track for heartbeat
                async with self._heartbeat_lock:
                    self._active_locks.add(full_key)
                
                # Start heartbeat if not running
                if self._heartbeat_task is None or self._heartbeat_task.done():
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                
                return True
            
            return False
        except Exception as e:
            logger.warning(f"Redis lock acquire failed for {key}: {e}")
            
            # Fallback to in-memory lock
            if self._fallback:
                return await self._acquire_fallback(key, token)
            return False
    
    async def _acquire_fallback(self, key: str, token: str) -> bool:
        """Fallback to in-memory lock."""
        self._fallback_count += 1
        if self._fallback_count == 1:
            logger.warning(
                f"Redis unavailable, falling back to in-memory lock. "
                f"Multi-instance safety NOT guaranteed. "
                f"Will auto-recover when Redis is back."
            )
        
        full_key = f"{self._prefix}{key}"
        
        async with self._local_lock:
            if key not in self._in_memory_locks:
                self._in_memory_locks[key] = token
                self._tokens[full_key] = token
                # Track for later transfer to Redis
                self._pending_transfer_locks[key] = token
                return True
        return False
    
    async def release(self, key: str) -> bool:
        """Release lock only if we own it (Phase 4E: Issue #3).
        
        Uses compare-and-delete to prevent releasing another worker's lock:
        - Only delete if stored token matches our token
        """
        import uuid
        
        full_key = f"{self._prefix}{key}"
        
        # Check in-memory first
        if key in self._in_memory_locks:
            async with self._local_lock:
                if key in self._in_memory_locks:
                    del self._in_memory_locks[key]
                    self._tokens.pop(full_key, None)
                    async with self._heartbeat_lock:
                        self._active_locks.discard(full_key)
                    return True
        
        # Check Redis with token ownership
        try:
            redis = await self._get_redis()
            token = self._tokens.get(full_key)
            
            if not token:
                return False  # We don't own this lock
            
            # Lua script for atomic compare-and-delete
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            result = await redis.eval(lua_script, 1, full_key, token)
            
            self._tokens.pop(full_key, None)
            async with self._heartbeat_lock:
                self._active_locks.discard(full_key)
            
            return result > 0
        except Exception as e:
            logger.warning(f"Redis lock release failed for {key}: {e}")
            return False
    
    async def _heartbeat_loop(self) -> None:
        """Renew locks before they expire (Phase 4E: Issue #4)."""
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                
                async with self._heartbeat_lock:
                    locks = list(self._active_locks)
                
                for full_key in locks:
                    await self._renew_lock(full_key)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    async def _renew_lock(self, full_key: str) -> None:
        """Renew lock expiration using PEXPIRE."""
        try:
            redis = await self._get_redis()
            token = self._tokens.get(full_key)
            
            if not token:
                return
            
            # Only renew if we still own it
            stored = await redis.get(full_key)
            if stored == token:
                new_expiry = int(self._timeout * 1000)  # ms
                await redis.pexpire(full_key, new_expiry)
        except Exception as e:
            logger.warning(f"Lock renewal failed for {full_key}: {e}")
    
    async def _health_check_loop(self) -> None:
        """Periodically check Redis connectivity and recover from fallback mode.
        
        When Redis is down, we fall back to in-memory locks. Once Redis recovers,
        we detect this and switch back, transferring any pending locks.
        """
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                
                was_unavailable = not self._redis_available
                
                if await self._check_redis_connection():
                    async with self._redis_available_lock:
                        self._redis_available = True
                    
                    # Redis recovered!
                    if was_unavailable:
                        logger.info("Redis connection restored, switching back from fallback mode")
                        await self._transfer_pending_locks()
                else:
                    async with self._redis_available_lock:
                        self._redis_available = False
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")
    
    async def _check_redis_connection(self) -> bool:
        """Check if Redis is reachable."""
        try:
            redis = await self._get_redis()
            await redis.ping()
            return True
        except Exception:
            return False
    
    async def _transfer_pending_locks(self) -> None:
        """Transfer in-memory locks to Redis when it recovers."""
        if not self._pending_transfer_locks:
            return
        
        logger.info(f"Transferring {len(self._pending_transfer_locks)} locks to Redis")
        
        transferred = 0
        failed = 0
        
        for key, token in list(self._pending_transfer_locks.items()):
            try:
                full_key = f"{self._prefix}{key}"
                redis = await self._get_redis()
                
                # Try to acquire in Redis (may fail if another instance grabbed it)
                acquired = await redis.set(full_key, token, nx=True, ex=int(self._timeout))
                
                if acquired:
                    transferred += 1
                    # Update tracking
                    self._tokens[full_key] = token
                    async with self._heartbeat_lock:
                        self._active_locks.add(full_key)
                    # Remove from pending
                    del self._pending_transfer_locks[key]
                else:
                    failed += 1
                    logger.warning(f"Lock {key} was taken by another instance")
                    
            except Exception as e:
                failed += 1
                logger.error(f"Failed to transfer lock {key}: {e}")
        
        logger.info(f"Lock transfer complete: {transferred} transferred, {failed} failed")
        
        # Start heartbeat if we have active locks
        if self._active_locks and (self._heartbeat_task is None or self._heartbeat_task.done()):
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    
    async def is_locked(self, key: str) -> bool:
        """Check if key is locked."""
        try:
            redis = await self._get_redis()
            full_key = f"{self._prefix}{key}"
            return await redis.exists(full_key) > 0
        except Exception:
            if self._fallback:
                return key in self._in_memory_locks
            return False
    
    @property
    def fallback_count(self) -> int:
        """Get number of times fallback to in-memory lock was used."""
        return self._fallback_count


class CircuitBreaker:
    """Circuit breaker for external services (embedding, etc.).
    
    States:
    - CLOSED: Normal operation
    - OPEN: Failing, reject requests immediately
    - HALF_OPEN: Testing recovery
    """
    
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
        half_open_requests: int = 3,
    ):
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout_seconds
        self._half_open_requests = half_open_requests
        
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._state = self.CLOSED
        self._half_open_successes = 0
    
    @property
    def state(self) -> str:
        """Get current circuit state."""
        if self._state == self.OPEN:
            # Check if recovery timeout has passed
            if self._last_failure_time:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self._recovery_timeout:
                    self._state = self.HALF_OPEN
                    self._half_open_successes = 0
        return self._state
    
    def is_available(self) -> bool:
        """Check if requests can be made."""
        return self.state != self.OPEN
    
    def record_success(self) -> None:
        """Record a successful request."""
        if self._state == self.HALF_OPEN:
            self._half_open_successes += 1
            if self._half_open_successes >= self._half_open_requests:
                self._state = self.CLOSED
                self._failure_count = 0
        elif self._state == self.CLOSED:
            self._failure_count = max(0, self._failure_count - 1)
    
    def record_failure(self) -> None:
        """Record a failed request."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        if self._state == self.HALF_OPEN:
            self._state = self.OPEN
        elif self._failure_count >= self._failure_threshold:
            self._state = self.OPEN


class CompressionDebtCalculator:
    """Calculate compression debt metrics."""
    
    def __init__(self):
        self._estimated_savings = 0.0
        self._pending_items = 0
        self._last_calculated = time.time()
    
    def update(self, uncompressed_bytes: int, compressed_bytes: int) -> None:
        """Update debt based on compression."""
        self._estimated_savings += (uncompressed_bytes - compressed_bytes)
        self._pending_items += 1
        self._last_calculated = time.time()
    
    def get_metrics(self) -> dict:
        """Get compression debt metrics."""
        return {
            "estimated_savings_bytes": self._estimated_savings,
            "pending_compressions": self._pending_items,
            "last_calculated": self._last_calculated,
            "estimated_savings_mb": round(self._estimated_savings / (1024 * 1024), 2),
        }
    
    def reset(self) -> None:
        """Reset debt counters."""
        self._estimated_savings = 0.0
        self._pending_items = 0


class AtomicCompression:
    """Phase 4E: Issue #1 - Atomic save_blob + compress operations.
    
    Ensures data consistency by wrapping save_original_blob and update_compressed_item
    in a database transaction. If either fails, both are rolled back.
    """
    
    def __init__(self, engine: "CompressionEngine"):
        self._engine = engine
    
    async def compress_atomic(
        self,
        item: MemoryItem | CacheItem,
        item_id: str,
        item_type: Literal["memory", "cache"],
        compressed_content: str,
        metadata: CompressionMetadata,
        original_hash: str,
    ) -> bool:
        """Atomically save original blob and compress item.
        
        Uses SAVEPOINT to ensure atomicity:
        1. SAVEPOINT
        2. Save original blob
        3. Update compressed item
        4. RELEASE SAVEPOINT
        
        On failure: ROLLBACK TO SAVEPOINT
        """
        if not self._engine._db:
            return False
        
        savepoint_name = f"compress_{item_id[:8]}_{int(time.time() * 1000)}"
        
        try:
            # Begin transaction
            await self._engine._db.execute(f"SAVEPOINT {savepoint_name}")
            
            # Step 1: Save original blob for fallback
            blob_saved = await self._save_original_blob_atomic(
                item_id=item_id,
                item_type=item_type,
                content=item.content,
                content_hash=original_hash,
            )
            
            if not blob_saved:
                await self._engine._db.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                return False
            
            # Step 2: Update compressed item
            success = await self._update_compressed_item_atomic(
                item=item,
                item_id=item_id,
                item_type=item_type,
                compressed_content=compressed_content,
                metadata=metadata,
            )
            
            if not success:
                await self._engine._db.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                return False
            
            # Commit the savepoint
            await self._engine._db.execute(f"RELEASE SAVEPOINT {savepoint_name}")
            
            # Invalidate cache
            self._engine._invalidate_cache(item_id, item_type)
            
            return True
            
        except Exception as e:
            logger.error(f"Atomic compression failed for {item_id}: {e}")
            try:
                await self._engine._db.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            except Exception:
                pass
            return False
    
    async def _save_original_blob_atomic(
        self,
        item_id: str,
        item_type: str,
        content: str,
        content_hash: str,
    ) -> bool:
        """Insert original blob with deduplication check (Phase 4E: Issue #14)."""
        if not self._engine._db:
            return False
        
        try:
            # Check if blob already exists for this item+hash
            existing = await self._engine._db.query(
                """
                SELECT id, reference_count FROM original_blobs 
                WHERE item_id = ? AND content_hash = ?
                """,
                (item_id, content_hash),
            )
            
            if existing:
                # Increment reference count instead of inserting duplicate
                await self._engine._db.execute(
                    """
                    UPDATE original_blobs 
                    SET reference_count = reference_count + 1
                    WHERE id = ?
                    """,
                    (existing["id"],),
                )
                return True
            
            # Insert new blob
            await self._engine._db.execute(
                """
                INSERT INTO original_blobs 
                (item_id, content, content_hash, item_type, compressed_at, reference_count)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (item_id, content, content_hash, item_type, int(time.time())),
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to save original blob: {e}")
            return False
    
    async def _update_compressed_item_atomic(
        self,
        item: MemoryItem | CacheItem,
        item_id: str,
        item_type: str,
        compressed_content: str,
        metadata: CompressionMetadata,
    ) -> bool:
        """Update item with compressed content."""
        if not self._engine._db:
            return False
        
        table = "memory" if item_type == "memory" else "tool_cache"
        new_version = item.version + 1
        
        try:
            result = await self._engine._db.execute(
                f"""
                UPDATE {table}
                SET content = ?,
                    compressed = TRUE,
                    compression_type = ?,
                    compression_metadata = ?,
                    original_length = COALESCE(original_length, LENGTH(?)),
                    compressed_length = LENGTH(?),
                    semantic_similarity = ?,
                    last_compressed_at = ?,
                    last_updated = ?,
                    compression_attempt_count = 0,
                    version = ?
                WHERE id = ? AND version = ?
                """,
                (
                    compressed_content,
                    metadata.strategy,
                    metadata.to_json(),
                    compressed_content,  # For original_length calculation
                    compressed_content,
                    metadata.semantic_similarity or 0.85,
                    int(time.time()),
                    int(time.time()),
                    new_version,
                    item_id,
                    item.version,
                ),
            )
            return result > 0
        except Exception as e:
            logger.warning(f"Failed to update compressed item: {e}")
            return False


class CompressionRatioGuard:
    """Phase 4E: Issue #15 - Reject compression if ratio is not beneficial."""
    
    def __init__(
        self,
        min_ratio: float = 0.95,
        absolute_min_savings: int = 100,
    ):
        self._min_ratio = min_ratio
        self._absolute_min_savings = absolute_min_savings
    
    def should_accept(
        self,
        original_length: int,
        compressed_length: int,
    ) -> tuple[bool, str]:
        """Check if compression result is acceptable."""
        if original_length == 0:
            return False, "original_length is zero"
        
        ratio = compressed_length / original_length
        savings = original_length - compressed_length
        
        # Check ratio
        if ratio >= self._min_ratio:
            if savings < self._absolute_min_savings:
                return False, f"Ratio {ratio:.2%} >= {self._min_ratio:.0%}, savings {savings}B < {self._absolute_min_savings}B"
        
        # Check absolute savings
        if savings < self._absolute_min_savings:
            return False, f"Only saves {savings}B, minimum {self._absolute_min_savings}B required"
        
        return True, "OK"


class CompressionEngine:
    """Main compression engine with strategy registry.
    
    Phase 4E Updates:
    - Issue #1: Atomic transactions (AtomicCompression)
    - Issue #9: Similarity validation sampling
    - Issue #15: Compression ratio guard
    - Issue #19: Correlation IDs support
    """
    
    def __init__(
        self,
        db: "DatabaseAdapter | None" = None,
        config: CompressionConfig | None = None,
        embedding_service: "EmbeddingService | None" = None,
        distributed_lock: "DistributedLock | None" = None,
    ):
        self._db = db
        self._config = config or CompressionConfig()
        self._embedding_service = embedding_service
        self._distributed_lock = distributed_lock
        
        self._strategies: dict[str, CompressionStrategy] = {}
        self._decompression_cache: DecompressionCache | None = None
        self._decompressor: Decompressor | None = None
        self._worker_task = None
        self._shutdown = False
        
        self._stats = CompressionStats()
        self._last_error: str | None = None
        
        # Phase 4E: Issue #1 - Atomic compression
        self._atomic = AtomicCompression(self)
        
        # Phase 4E: Issue #15 - Ratio guard
        self._ratio_guard = CompressionRatioGuard(
            min_ratio=self._config.quality.min_compression_ratio,
            absolute_min_savings=self._config.quality.absolute_min_savings_bytes,
        )
        
        # Circuit breaker for embedding service
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=self._config.circuit_breaker.failure_threshold,
            recovery_timeout_seconds=self._config.circuit_breaker.recovery_timeout_seconds,
            half_open_requests=self._config.circuit_breaker.half_open_requests,
        )
        
        # Compression debt calculator
        self._debt_calculator = CompressionDebtCalculator()
        
        self._initialize_default_strategies()
    
    def _initialize_default_strategies(self) -> None:
        """Initialize default compression strategies."""
        self._strategies["truncation"] = TruncationCompressor(
            config=self._config.strategies.truncation
        )
        
        self._strategies["extractive"] = ExtractiveSummarizer(
            embedding_service=self._embedding_service,
            config=self._config.strategies.extractive,
        )
        
        self._strategies["kv_compact"] = KeyValueCompactor(
            config=self._config.strategies.kv_compact
        )
        
        self._strategies["adaptive_prune"] = AdaptivePruner(
            config=self._config.strategies.adaptive_prune
        )
        
        if self._config.decompression_cache.enabled:
            self._decompression_cache = DecompressionCache(
                maxsize=self._config.decompression_cache.maxsize,
                ttl_seconds=self._config.decompression_cache.ttl_seconds,
            )
    
    @property
    def stats(self) -> CompressionStats:
        """Get compression statistics."""
        return self._stats
    
    @property
    def last_error(self) -> str | None:
        """Get last error message."""
        return self._last_error
    
    async def register_strategy(
        self, name: str, strategy: CompressionStrategy
    ) -> None:
        """Register a compression strategy.
        
        Args:
            name: Strategy name.
            strategy: Strategy instance.
        """
        self._strategies[name] = strategy
    
    def get_strategy(self, name: str) -> CompressionStrategy:
        """Get a registered strategy.
        
        Args:
            name: Strategy name.
            
        Returns:
            Strategy instance.
            
        Raises:
            StrategyNotFoundError: If strategy not found.
        """
        if name not in self._strategies:
            raise StrategyNotFoundError(name)
        return self._strategies[name]
    
    async def compress_item(
        self,
        item_id: str,
        item_type: Literal["memory", "cache"],
        strategy: str | None = None,
    ) -> bool:
        """Compress a single item.
        
        Phase 4E Updates:
        - Issue #1: Uses atomic compression for save_blob + compress
        - Issue #9: Similarity validation sampling
        - Issue #15: Compression ratio guard
        
        Args:
            item_id: Item ID.
            item_type: Item type (memory or cache).
            strategy: Optional strategy override.
            
        Returns:
            True if compression successful.
        """
        start_time = time.time()
        self._last_error = None
        
        item = await self._get_item(item_id, item_type)
        if not item:
            self._last_error = "ITEM_NOT_FOUND"
            return False
        
        # Handle oversized items
        item_size_mb = len(item.content) / (1024 * 1024)
        if item_size_mb > self._config.limits.max_item_size_mb:
            if self._config.limits.large_item_strategy == "truncate":
                max_chars = int(self._config.limits.max_item_size_mb * 1024 * 1024)
                
                stripped = item.content.strip()
                is_structured = (
                    stripped.startswith('{') or 
                    stripped.startswith('[') or 
                    stripped.startswith('<')
                )
                if is_structured:
                    logger.warning(
                        f"Large item {item_id} truncated in-place. "
                        f"Content may be structurally invalid (JSON/XML detected)."
                    )
                
                item.content = item.content[:max_chars]
            else:
                self._last_error = f"ITEM_TOO_LARGE:{item_size_mb:.2f}MB"
                self._stats.items_skipped_flag += 1
                return False
        
        if not self._can_compress(item):
            if item.no_compress:
                self._last_error = "NO_COMPRESS_FLAG"
            elif item.compressed:
                self._last_error = "ALREADY_COMPRESSED"
            elif item.deleted:
                self._last_error = "ALREADY_DELETED"
            self._stats.items_skipped_flag += 1
            return False
        
        age_threshold = self._config.worker.min_age_days * 86400
        age = time.time() - item.last_updated
        if age < age_threshold:
            self._last_error = "TOO_YOUNG"
            self._stats.items_skipped_age += 1
            return False
        
        strategy_name = strategy or self._config.strategies.default
        strategy_impl = self._strategies.get(strategy_name)
        if not strategy_impl:
            self._last_error = f"STRATEGY_NOT_FOUND:{strategy_name}"
            return False
        
        try:
            compressed_content, metadata = await strategy_impl.compress(item.content)
            
            original_length = len(item.content)
            compressed_length = len(compressed_content)
            
            # Phase 4E: Issue #15 - Compression ratio guard
            should_accept, reason = self._ratio_guard.should_accept(
                original_length=original_length,
                compressed_length=compressed_length,
            )
            
            if not should_accept:
                logger.info(f"Skipping {item_id}: {reason}")
                self._last_error = f"RATIO_REJECTED:{reason}"
                return False
            
            # Phase 4E: Issue #9 - Similarity validation with sampling
            if self._config.quality.validate_before_commit:
                similarity = await self._validate_similarity_sampled(
                    item.content, compressed_content, item_id, metadata
                )
                metadata.semantic_similarity = similarity
                
                if similarity < self._config.quality.min_similarity:
                    item.compression_attempt_count += 1
                    self._last_error = f"LOW_SIMILARITY:{similarity:.3f}"
                    
                    if item.compression_attempt_count >= self._config.worker.max_attempts:
                        await self._set_no_compress(item_id, item_type)
                        self._last_error = "MAX_ATTEMPTS_REACHED"
                    
                    self._stats.items_failed += 1
                    return False
            
            # Phase 4E: Issue #1 - Atomic compression
            original_hash = hashlib.sha256(item.content.encode()).hexdigest()
            
            success = await self._atomic.compress_atomic(
                item=item,
                item_id=item_id,
                item_type=item_type,
                compressed_content=compressed_content,
                metadata=metadata,
                original_hash=original_hash,
            )
            
            if not success:
                self._last_error = "ATOMIC_FAILED"
                self._stats.items_failed += 1
                return False
            
            self._stats.items_compressed += 1
            ratio = original_length / compressed_length if compressed_length > 0 else 1.0
            self._stats.update_compression(ratio, metadata.semantic_similarity)
            
            self._debt_calculator.update(original_length, compressed_length)
            
            latency_ms = (time.time() - start_time) * 1000
            self._stats.update_worker_latency(latency_ms)
            
            return True
            
        except Exception as e:
            logger.error(f"Compression failed for {item_id}: {e}")
            self._last_error = f"ERROR:{str(e)}"
            self._stats.items_failed += 1
            return False
    
    async def _validate_similarity_sampled(
        self,
        original: str,
        compressed: str,
        item_id: str,
        metadata: CompressionMetadata,
    ) -> float:
        """Phase 4E: Issue #9 - Validate similarity with sampling.
        
        Only validates a percentage of items to reduce embedding API calls.
        Always validates items with suspicious compression ratio or metadata.
        """
        import random
        
        quality_config = self._config.quality
        
        # Check if we should validate
        should_validate = (
            # Always validate if sampling is 100%
            quality_config.validation_sampling_rate >= 1.0 or
            # Always validate if high compression ratio (suspicious)
            (quality_config.validate_always_if_ratio_below and 
             len(compressed) < len(original) * quality_config.validate_always_if_ratio_below) or
            # Random sampling based on rate
            random.random() < quality_config.validation_sampling_rate or
            # Validate if metadata has errors
            (quality_config.validate_always_if_suspicious and metadata.error)
        )
        
        if not should_validate:
            # Skip embedding, use estimated similarity
            return metadata.semantic_similarity or 0.85
        
        # Do full embedding validation
        return await self._validate_similarity(original, compressed)
    
    def _can_compress(self, item: MemoryItem | CacheItem) -> bool:
        """Check if an item can be compressed."""
        if item.no_compress:
            # Fix #11: Check no_compress_until TTL
            if item.no_compress_until and time.time() < item.no_compress_until:
                return False
            # If no_compress_until is None or expired, check config retry setting
            if self._config.no_compress.retry_after_hours > 0:
                retry_after = item.last_updated + (self._config.no_compress.retry_after_hours * 3600)
                if time.time() < retry_after:
                    return False
            return True
        return (
            not item.compressed
            and not item.deleted
        )
    
    async def _get_item(
        self, item_id: str, item_type: Literal["memory", "cache"]
    ) -> MemoryItem | CacheItem | None:
        """Get item from database."""
        if not self._db:
            return None
        
        table = "memory" if item_type == "memory" else "tool_cache"
        
        try:
            row = await self._db.query(
                f"SELECT * FROM {table} WHERE id = ?",
                (item_id,),
            )
            if not row:
                return None
            
            if item_type == "memory":
                return MemoryItem.from_dict(row)
            else:
                return CacheItem.from_dict(row)
        except Exception as e:
            logger.error(f"Failed to get item {item_id}: {e}")
            return None
    
    async def _update_item_with_lock(
        self,
        item: MemoryItem | CacheItem,
        item_id: str,
        item_type: Literal["memory", "cache"],
        expected_version: int,
        compressed_content: str,
        strategy_name: str,
        metadata: CompressionMetadata,
        original_length: int,
        compressed_length: int,
    ) -> bool:
        """Update item with optimistic lock."""
        if not self._db:
            return False
        
        table = "memory" if item_type == "memory" else "tool_cache"
        new_version = expected_version + 1
        
        try:
            # Fix #4: Auto-save original to original_blobs before compress
            original_hash = hashlib.sha256(item.content.encode()).hexdigest()
            await self._save_original_blob(
                item_id=item_id,
                item_type=item_type,
                content=item.content,
                content_hash=original_hash,
            )
            
            result = await self._db.execute(
                f"""
                UPDATE {table}
                SET content = ?,
                    compressed = true,
                    compression_type = ?,
                    compression_metadata = ?,
                    original_length = ?,
                    compressed_length = ?,
                    semantic_similarity = ?,
                    version = ?,
                    last_compressed_at = ?,
                    last_updated = ?,
                    compression_attempt_count = 0
                WHERE id = ? AND version = ?
                """,
                (
                    compressed_content,
                    strategy_name,
                    metadata.to_json(),
                    original_length,
                    compressed_length,
                    metadata.semantic_similarity,
                    new_version,
                    int(time.time()),
                    int(time.time()),
                    item_id,
                    expected_version,
                ),
            )
            return result > 0
        except Exception as e:
            logger.error(f"Failed to update item {item_id}: {e}")
            return False
    
    async def _validate_similarity(
        self, original: str, compressed: str
    ) -> float:
        """Validate semantic similarity between original and compressed.
        
        Uses character overlap as a proxy for semantic similarity.
        In production, this would use embedding comparison.
        """
        if self._embedding_service is None:
            overlap = self._calculate_overlap(original, compressed)
            return max(0.0, min(1.0, overlap))
        
        try:
            emb_orig = await self._embedding_service.embed(original)
            emb_comp = await self._embedding_service.embed(compressed)
            
            if not emb_orig or not emb_comp:
                return self._calculate_overlap(original, compressed)
            
            similarity = self._cosine_similarity(emb_orig, emb_comp)
            return float(similarity)
        except Exception:
            return self._calculate_overlap(original, compressed)
    
    def _calculate_overlap(self, original: str, compressed: str) -> float:
        """Calculate character overlap as similarity proxy."""
        if not original or not compressed:
            return 0.0
        
        original_set = set(original.lower())
        compressed_set = set(compressed.lower())
        
        if not original_set:
            return 0.0
        
        overlap = len(original_set & compressed_set) / len(original_set)
        return overlap
    
    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(a) != len(b) or not a:
            return 0.0
        
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot / (norm_a * norm_b)
    
    async def _set_no_compress(
        self, item_id: str, item_type: Literal["memory", "cache"]
    ) -> None:
        """Mark item as not compressible."""
        if not self._db:
            return
        
        table = "memory" if item_type == "memory" else "tool_cache"
        
        await self._db.execute(
            f"UPDATE {table} SET no_compress = true WHERE id = ?",
            (item_id,),
        )
    
    async def decompress_item(
        self,
        item_id: str,
        item_type: Literal["memory", "cache"],
    ) -> str | None:
        """Decompress an item with LRU cache.
        
        Args:
            item_id: Item ID.
            item_type: Item type.
            
        Returns:
            Decompressed content, or None if failed.
        """
        cache_key = f"{item_type}:{item_id}"
        
        if self._decompression_cache:
            cached = self._decompression_cache.get(cache_key)
            if cached is not None:
                return cached
        
        item = await self._get_item(item_id, item_type)
        if not item or not item.compressed:
            return None
        
        try:
            if item.compression_metadata is None:
                return item.content
            
            decompressor = self._decompressor or self._create_decompressor()
            
            content = await decompressor.decompress(
                item_id=item_id,
                item_type=item_type,
                content=item.content,
                metadata=item.compression_metadata,
            )
            
            if self._decompression_cache and content:
                self._decompression_cache.set(cache_key, content)
            
            return content
            
        except Exception as e:
            logger.error(f"Decompression failed for {item_id}: {e}")
            return await self._fallback_decompress(item_id, item_type)
    
    def _create_decompressor(self) -> Decompressor:
        """Create a decompressor instance."""
        self._decompressor = Decompressor(
            engine=self,
            cache=self._decompression_cache,
        )
        
        for name, strategy in self._strategies.items():
            self._decompressor.register_strategy(name, strategy)
        
        return self._decompressor
    
    async def _fallback_decompress(
        self, item_id: str, item_type: Literal["memory", "cache"]
    ) -> str | None:
        """Fallback to original_blobs table."""
        if not self._db:
            return None
        
        try:
            row = await self._db.query(
                "SELECT content FROM original_blobs WHERE item_id = ? ORDER BY created_at DESC LIMIT 1",
                (item_id,),
            )
            if row and row.get("content"):
                cache_key = f"{item_type}:{item_id}"
                if self._decompression_cache:
                    self._decompression_cache.set(cache_key, row["content"])
                return row["content"]
        except Exception as e:
            logger.error(f"Fallback decompression failed for {item_id}: {e}")
        
        return None
    
    async def _save_original_blob(
        self,
        item_id: str,
        item_type: Literal["memory", "cache"],
        content: str,
        content_hash: str,
    ) -> bool:
        """Save original content to original_blobs before compression (Fix #4).
        
        Args:
            item_id: Item ID.
            item_type: Item type.
            content: Original content.
            content_hash: SHA256 hash of content.
            
        Returns:
            True if saved successfully.
        """
        if not self._db:
            return False
        
        try:
            await self._db.execute(
                """
                INSERT OR REPLACE INTO original_blobs
                (item_id, content, content_hash, item_type, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (item_id, content, content_hash, item_type, int(time.time())),
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to save original blob for {item_id}: {e}")
            return False
    
    async def mark_no_compress(
        self, item_id: str, item_type: Literal["memory", "cache"]
    ) -> None:
        """Mark item as not compressible.
        
        Args:
            item_id: Item ID.
            item_type: Item type.
        """
        if not self._db:
            return
        
        table = "memory" if item_type == "memory" else "tool_cache"
        
        await self._db.execute(
            f"UPDATE {table} SET no_compress = true WHERE id = ?",
            (item_id,),
        )
        
        self._invalidate_cache(item_id, item_type)
    
    async def report_compression_issue(
        self, item_id: str, item_type: Literal["memory", "cache"], reason: str,
        disable_hours: int | None = None
    ) -> bool:
        """Handle agent feedback - rollback and mark no_compress.
        
        Args:
            item_id: Item ID.
            item_type: Item type.
            reason: Reason for reporting.
            disable_hours: Hours to disable compression. Uses config default if None.
            
        Returns:
            True if rollback successful.
        """
        if not self._config.feedback.rollback_and_mark_no_compress:
            return False
        
        item = await self._get_item(item_id, item_type)
        if not item:
            return False
        
        original = await self._fallback_decompress(item_id, item_type)
        if not original:
            logger.error(f"Cannot rollback item {item_id}: no original found")
            return False
        
        table = "memory" if item_type == "memory" else "tool_cache"
        
        # Calculate no_compress_until timestamp
        hours = disable_hours if disable_hours is not None else self._config.no_compress.disable_hours
        no_compress_until = int(time.time() + hours * 3600) if hours > 0 else 0
        
        await self._db.execute(
            f"""
            UPDATE {table}
            SET content = ?,
                compressed = false,
                no_compress = true,
                no_compress_until = ?,
                version = version + 1,
                last_updated = ?
            WHERE id = ?
            """,
            (original, no_compress_until, int(time.time()), item_id),
        )
        
        self._invalidate_cache(item_id, item_type)
        
        logger.info(f"Rolled back compression for {item_id}: {reason} (disabled for {hours}h)")
        return True
    
    def _invalidate_cache(
        self, item_id: str, item_type: Literal["memory", "cache"]
    ) -> None:
        """Invalidate decompression cache entry."""
        if self._decompression_cache:
            cache_key = f"{item_type}:{item_id}"
            self._decompression_cache.invalidate(cache_key)
    
    async def compress_batch(
        self,
        item_type: Literal["memory", "cache"],
        strategy: str | None = None,
        limit: int = 50,
    ) -> int:
        """Compress a batch of items.
        
        Args:
            item_type: Item type.
            strategy: Strategy to use.
            limit: Maximum items to compress.
            
        Returns:
            Number of items compressed.
        """
        if not self._db:
            return 0
        
        table = "memory" if item_type == "memory" else "tool_cache"
        cutoff_time = int(time.time() - self._config.worker.min_age_days * 86400)
        
        rows = await self._db.query_many(
            f"""
            SELECT id FROM {table}
            WHERE compressed = false
              AND no_compress = false
              AND deleted = false
              AND last_updated < ?
            ORDER BY last_updated ASC
            LIMIT ?
            """,
            (cutoff_time, limit),
        )
        
        count = 0
        for row in rows:
            success = await self.compress_item(row["id"], item_type, strategy)
            if success:
                count += 1
        
        return count
    
    async def get_stats(self) -> dict:
        """Get compression statistics.
        
        Returns:
            Statistics dictionary.
        """
        stats = self._stats.to_dict()
        
        if self._decompression_cache:
            cache_stats = self._decompression_cache.get_stats()
            stats["decompression_cache"] = cache_stats
        
        # Fix #15: Include compression debt metrics
        stats["compression_debt"] = self._debt_calculator.get_metrics()
        
        # Fix #5: Include circuit breaker status
        stats["circuit_breaker"] = {
            "state": self._circuit_breaker.state,
            "is_available": self._circuit_breaker.is_available(),
        }
        
        return stats
    
    async def shutdown(self) -> None:
        """Shutdown the compression engine."""
        self._shutdown = True
        if self._worker_task:
            self._worker_task.cancel()


class DatabaseAdapter:
    """Simple database adapter for compression operations."""
    
    def __init__(self, connection=None):
        self._conn = connection
    
    async def query(
        self, query: str, params: tuple = ()
    ) -> dict | None:
        """Execute a query and return one row."""
        raise NotImplementedError("Subclass must implement query")
    
    async def query_many(
        self, query: str, params: tuple = ()
    ) -> list[dict]:
        """Execute a query and return all rows."""
        raise NotImplementedError("Subclass must implement query_many")
    
    async def execute(self, query: str, params: tuple = ()) -> int:
        """Execute a statement and return affected rows."""
        raise NotImplementedError("Subclass must implement execute")
