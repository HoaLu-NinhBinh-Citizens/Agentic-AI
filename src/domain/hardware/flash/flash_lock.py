"""Flash Lock - Distributed concurrency locking for flash operations.

Phase 6.2: Implements distributed flash locking for:
- Atomic lock acquisition
- Automatic lease renewal
- Lock timeout handling
- Integration with event bus
- Fencing token for flash operations (P0-C)

P0-C Requirements:
- NO silent Redis→Memory fallback (fail-fast)
- Fencing token enforced at probe adapter boundary
- Token validated on EVERY write operation
- Token logged to operation ledger
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# DETERMINISTIC TOKEN ID (P0-A alignment)
# =============================================================================


def deterministic_fence_token(lock_id: str, sequence: int) -> str:
    """Generate deterministic fence token ID.
    
    P0-A: Uses MD5 hash instead of random UUID for deterministic replay.
    """
    base = f"{lock_id}:fence:{sequence}"
    digest = hashlib.md5(base.encode()).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


@dataclass
class FlashFenceToken:
    """Fencing token for flash operations.
    
    CRITICAL: This token MUST be validated at EVERY flash operation
    (erase, write, verify) to prevent split-brain scenarios where
    stale operations overwrite newer data.
    
    P0-C: Token uses deterministic ID for replay correctness.
    
    The token contains:
    - A monotonically increasing sequence number
    - The target being operated on
    - The transaction that owns this token
    - Timestamp for staleness detection
    
    Usage pattern:
    1. Acquire lock -> receive FenceToken with seq=N
    2. Before EVERY flash operation (erase/write/verify):
       - Check token.seq >= N, reject if lower
       - Pass token to operation
    3. On operation failure, token becomes invalid
    """
    sequence: int = 0  # Monotonically increasing
    lock_id: str = ""  # Target lock ID
    transaction_id: str = ""  # Owning transaction
    owner_id: str = ""  # Owner (agent/session)
    
    # P0-C: Deterministic token ID (derived from lock_id + sequence)
    token: str = ""
    
    # Validity
    issued_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(seconds=60))
    is_revoked: bool = False
    
    # Version tracking
    version: int = 1  # Incremented on each operation
    
    def __post_init__(self) -> None:
        """Generate deterministic token ID if not provided."""
        if not self.token and self.lock_id and self.sequence >= 0:
            self.token = deterministic_fence_token(self.lock_id, self.sequence)
    
    def is_valid(self) -> bool:
        """Check if token is still valid for operations."""
        if self.is_revoked:
            return False
        if datetime.now() > self.expires_at:
            return False
        return True
    
    def validate_for_operation(self, operation_name: str) -> tuple[bool, str]:
        """Validate token is valid for a specific operation.
        
        Args:
            operation_name: Name of the operation (erase, write, verify)
            
        Returns:
            (is_valid, error_message)
        """
        if self.is_revoked:
            return False, f"Token {self.token[:8] if self.token else 'N/A'}... is revoked"
        
        if datetime.now() > self.expires_at:
            return False, f"Token {self.token[:8] if self.token else 'N/A'}... has expired"
        
        return True, ""
    
    def advance_version(self) -> None:
        """Advance token version after successful operation."""
        self.version += 1
    
    def revoke(self) -> None:
        """Revoke this token, preventing further operations."""
        self.is_revoked = True
        logger.info(
            "fence_token_revoked",
            token=self.token[:8] if self.token else "N/A",
            lock_id=self.lock_id,
            transaction_id=self.transaction_id,
            final_version=self.version,
        )


@dataclass
class FlashLock:
    """Distributed flash lock for target."""
    
    target_name: str
    owner_id: str
    
    acquired_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=datetime.now)
    
    lease_timeout: timedelta = field(default_factory=lambda: timedelta(seconds=60))
    
    version: int = 1
    
    # Fencing token sequence (for token generation)
    fence_sequence: int = 0
    
    def is_valid(self) -> bool:
        """Check if lock is still valid."""
        return datetime.now() < self.expires_at
    
    def renew(self, extend_by: timedelta | None = None) -> bool:
        """Renew the lock."""
        if not self.is_valid():
            return False
        
        duration = extend_by or self.lease_timeout
        self.expires_at = datetime.now() + duration
        self.version += 1
        return True
    
    def issue_fence_token(
        self,
        transaction_id: str,
        owner_id: str,
    ) -> FlashFenceToken:
        """Issue a new fencing token for flash operations.
        
        CRITICAL: Every flash operation MUST validate this token
        before proceeding.
        
        Args:
            transaction_id: The flash transaction ID
            owner_id: Owner (agent/session)
            
        Returns:
            FlashFenceToken for this operation
        """
        self.fence_sequence += 1
        
        token = FlashFenceToken(
            sequence=self.fence_sequence,
            lock_id=self.target_name,
            transaction_id=transaction_id,
            owner_id=owner_id,
            expires_at=self.expires_at,
        )
        
        logger.debug(
            "fence_token_issued",
            token=token.token[:8],
            sequence=token.sequence,
            lock_id=self.target_name,
            transaction_id=transaction_id,
        )
        
        return token
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "target_name": self.target_name,
            "owner_id": self.owner_id,
            "acquired_at": self.acquired_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "version": self.version,
            "fence_sequence": self.fence_sequence,
        }


@dataclass
class FenceValidationError(Exception):
    """Raised when fence token validation fails."""
    
    operation: str
    token_sequence: int
    required_sequence: int
    reason: str
    
    def __str__(self) -> str:
        return (
            f"Fence validation failed for {self.operation}: "
            f"token_seq={self.token_sequence}, required>={self.required_sequence}, "
            f"reason={self.reason}"
        )


@dataclass
class TargetFlashLock:
    """Manages flash locks for targets.

    Features:
    - Atomic lock acquisition
    - Automatic lease renewal
    - Distributed lock support (Redis)
    - Lock timeout handling
    - Fencing tokens for split-brain prevention (P0-C)

    P0-C CRITICAL:
    - Default fail_if_redis_unavailable=True for production safety
    - Silent memory fallback is ONLY allowed for single-node testing
    - ALL flash operations MUST validate fence token

    P0-Hardening:
    - Redis is authoritative storage when lock_storage="redis"
    - Lua scripts for atomic acquire/release (same pattern as distributed_locking.py)
    - OperationLedger is optionally Redis-backed
    - Stale lock recovery on startup
    """

    lock_storage: str = "memory"  # "memory", "file", "redis"
    lock_dir: str = "/tmp/aisupport/locks"
    redis_url: str = "redis://localhost:6379"

    # P0-C: CRITICAL - Default to True for production safety
    # Set to False ONLY for single-node testing with in-memory locks
    fail_if_redis_unavailable: bool = True

    lease_timeout_seconds: int = 60
    renew_interval_seconds: int = 30

    _locks: dict[str, FlashLock] = field(default_factory=dict)
    _renew_tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    _redis: Any = field(default=None, init=False)
    _redis_connected: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """Initialize lock storage and recover stale locks."""
        if self.lock_storage == "file":
            os.makedirs(self.lock_dir, exist_ok=True)

        # P0-C: Log warning if using memory storage (for visibility)
        if self.lock_storage == "memory" and not self.fail_if_redis_unavailable:
            logger.warning(
                "P0-C WARNING: Using memory storage with fail_if_redis_unavailable=False. "
                "This is ONLY safe for single-node testing. "
                "DO NOT use in production distributed deployments."
            )

        # P0-Hardening: Schedule stale lock recovery
        asyncio.create_task(self._startup_recovery())

    async def _startup_recovery(self) -> None:
        """P0-Hardening: Recover stale locks on startup.
        
        Called automatically after initialization to clean up any
        expired locks left behind by crashed processes.
        """
        if self.lock_storage != "redis":
            return
            
        try:
            await self._init_redis()
            recovered = await self._recover_stale_locks()
            if recovered > 0:
                logger.info("startup_stale_lock_recovery: recovered=%d", recovered)
        except Exception as e:
            logger.warning("startup_recovery_skipped: error=%s", str(e))

    # ---- Redis key helpers ----

    def _redis_key(self, target_name: str) -> str:
        return f"aisupport:flash_lock:{target_name}"

    def _redis_fence_key(self, target_name: str) -> str:
        return f"aisupport:flash_lock:{target_name}:fence"

    async def _init_redis(self) -> None:
        """Initialize Redis connection.

        CRITICAL: In production, silent fallback to memory is DANGEROUS
        because it breaks distributed lock guarantees. Set fail_if_redis_unavailable
        to True for production deployments.
        """
        if self._redis is None and self.lock_storage == "redis":
            try:
                import aioredis
                self._redis = await aioredis.create_redis_pool(self.redis_url)
                self._redis_connected = True
            except Exception as e:
                logger.error(
                    "redis_connection_failed: error=%s, fail_mode=%s",
                    str(e), self.fail_if_redis_unavailable,
                )
                if self.fail_if_redis_unavailable:
                    raise RuntimeError(
                        f"Failed to connect to Redis at {self.redis_url}. "
                        f"Cannot use memory fallback in distributed mode. "
                        f"Set fail_if_redis_unavailable=False only for single-node testing."
                    )
                else:
                    logger.warning(
                        "Using memory fallback for distributed locks - "
                        "THIS IS UNSAFE FOR PRODUCTION"
                    )
                    self.lock_storage = "memory"

    async def _recover_stale_locks(self) -> int:
        """P0-Hardening: Scan Redis for expired locks and auto-release.

        Called on startup to clean up stale locks left behind by crashed processes.
        Uses SCAN to iterate through keys safely in production.
        Returns the number of locks recovered.
        """
        if self._redis is None or not self._redis_connected:
            return 0

        recovered = 0
        prefix = "aisupport:flash_lock:"
        cursor = 0

        try:
            while True:
                # SCAN returns (cursor, keys)
                cursor, keys = await self._redis.scan(cursor, match=f"{prefix}*", count=100)
                for key in keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    # Skip fence keys
                    if ":fence" in key_str:
                        continue
                    try:
                        lock_data = await self._redis.hgetall(key_str)
                        if lock_data:
                            expires_at_str = lock_data.get(b"expires_at", lock_data.get("expires_at"))
                            if expires_at_str:
                                expires_at = float(
                                    expires_at_str.decode() if isinstance(expires_at_str, bytes) else expires_at_str
                                )
                                import time as _time
                                if expires_at < _time.time():
                                    await self._redis.delete(key_str)
                                    fence_key = key_str + ":fence"
                                    await self._redis.delete(fence_key)
                                    logger.info(
                                        "recovered_stale_lock: target=%s",
                                        key_str.replace(prefix, ""),
                                    )
                                    recovered += 1
                    except Exception:
                        pass
                if cursor == 0:
                    break
        except Exception:
            pass
        return recovered
    
    async def acquire(
        self,
        target_name: str,
        owner_id: str,
        timeout_seconds: float = 30.0,
    ) -> FlashLock | None:
        """Acquire flash lock for target.

        When lock_storage="redis": uses Lua-script atomic acquire against
        Redis (source of truth). In-memory dict is L1 cache only.

        Args:
            target_name: Target to lock
            owner_id: Owner (agent/session ID)
            timeout_seconds: Time to wait for lock

        Returns:
            FlashLock if acquired, None if failed
        """
        await self._init_redis()

        # P0-Hardening: Redis is authoritative backend
        if self._redis is not None and self._redis_connected:
            return await self._acquire_redis(target_name, owner_id, timeout_seconds)

        # Fallback to in-memory (single-node only)
        return await self._acquire_memory(target_name, owner_id, timeout_seconds)

    async def _acquire_redis(
        self,
        target_name: str,
        owner_id: str,
        timeout_seconds: float,
    ) -> FlashLock | None:
        """P0-Hardening: Redis-atomic lock acquisition via Lua script.

        Atomically: checks if lock is free or expired, then acquires.
        """
        import time as _time

        deadline = _time.time() + timeout_seconds
        redis_key = self._redis_key(target_name)
        fence_key = self._redis_fence_key(target_name)
        lease_s = self.lease_timeout_seconds

        lua_acquire = """
        local lock_key = KEYS[1]
        local fence_key = KEYS[2]
        local owner_id = ARGV[1]
        local lease_s = tonumber(ARGV[2])
        local fence_seq = tonumber(ARGV[3])
        local fence_token = ARGV[4]
        local expires_at = tonumber(ARGV[5])
        local now = tonumber(ARGV[6])

        local current_owner = redis.call('HGET', lock_key, 'owner_id')
        if current_owner == false then
            redis.call('HMSET', lock_key,
                'owner_id', owner_id,
                'lease_s', lease_s,
                'fence_seq', fence_seq,
                'fence_token', fence_token,
                'expires_at', expires_at)
            redis.call('EXPIRE', lock_key, lease_s + 10)
            redis.call('SET', fence_key, fence_seq, 'EX', lease_s + 10)
            return 1
        elseif current_owner == owner_id then
            redis.call('HMSET', lock_key,
                'lease_s', lease_s,
                'fence_seq', fence_seq,
                'fence_token', fence_token,
                'expires_at', expires_at)
            redis.call('EXPIRE', lock_key, lease_s + 10)
            redis.call('SET', fence_key, fence_seq, 'EX', lease_s + 10)
            return 1
        else
            local stored_exp = redis.call('HGET', lock_key, 'expires_at')
            if stored_exp == false or tonumber(stored_exp) <= now then
                redis.call('HMSET', lock_key,
                    'owner_id', owner_id,
                    'lease_s', lease_s,
                    'fence_seq', fence_seq,
                    'fence_token', fence_token,
                    'expires_at', expires_at)
                redis.call('EXPIRE', lock_key, lease_s + 10)
                redis.call('SET', fence_key, fence_seq, 'EX', lease_s + 10)
                return 1
            end
            return 0
        end
        """

        while _time.time() < deadline:
            fence_seq = int(_time.time() * 1000)
            token = deterministic_fence_token(target_name, fence_seq)
            expires_at = _time.time() + lease_s

            try:
                result = await self._redis.eval(
                    lua_acquire, 2, redis_key, fence_key,
                    owner_id, str(lease_s), str(fence_seq),
                    token, str(expires_at), str(_time.time()),
                )
                if result:
                    lock = FlashLock(
                        target_name=target_name,
                        owner_id=owner_id,
                        fence_sequence=fence_seq,
                    )
                    async with self._lock:
                        self._locks[target_name] = lock
                    logger.info(
                        "flash_lock_acquired_redis: target=%s owner=%s",
                        target_name, owner_id,
                    )
                    return lock
            except Exception as e:
                logger.error("flash_lock_redis_error: target=%s error=%s", target_name, str(e))
                return None

            await asyncio.sleep(0.1)

        return None

    async def _acquire_memory(
        self,
        target_name: str,
        owner_id: str,
        timeout_seconds: float,
    ) -> FlashLock | None:
        """In-memory lock acquisition (single-node only)."""
        import time as _time

        start_time = _time.time()
        while True:
            async with self._lock:
                existing = self._locks.get(target_name)
                if existing and existing.is_valid():
                    if existing.owner_id == owner_id:
                        existing.renew()
                        return existing
                    if _time.time() - start_time >= timeout_seconds:
                        return None
                    await asyncio.sleep(1)
                    continue

                lock = FlashLock(
                    target_name=target_name,
                    owner_id=owner_id,
                    expires_at=datetime.now() + timedelta(seconds=self.lease_timeout_seconds),
                    lease_timeout=timedelta(seconds=self.lease_timeout_seconds),
                )
                self._locks[target_name] = lock
                self._renew_tasks[target_name] = asyncio.create_task(
                    self._renew_loop(target_name)
                )
                logger.info(
                    "flash_lock_acquired_memory: target=%s owner=%s",
                    target_name, owner_id,
                )
                return lock

    async def release(self, target_name: str, owner_id: str) -> bool:
        """Release flash lock.

        Args:
            target_name: Target name
            owner_id: Owner ID (must match)

        Returns:
            True if released
        """
        if self._redis is not None and self._redis_connected:
            return await self._release_redis(target_name, owner_id)
        return await self._release_memory(target_name, owner_id)

    async def _release_redis(self, target_name: str, owner_id: str) -> bool:
        """P0-Hardening: Redis-atomic lock release via Lua script."""
        redis_key = self._redis_key(target_name)
        fence_key = self._redis_fence_key(target_name)

        lua_release = """
        local current = redis.call('HGET', KEYS[1], 'owner_id')
        if current == ARGV[1] then
            redis.call('DEL', KEYS[1])
            redis.call('DEL', KEYS[2])
            return 1
        end
        return 0
        """

        try:
            result = await self._redis.eval(lua_release, 2, redis_key, fence_key, owner_id)
            if result:
                async with self._lock:
                    if target_name in self._renew_tasks:
                        self._renew_tasks[target_name].cancel()
                        try:
                            await self._renew_tasks[target_name]
                        except asyncio.CancelledError:
                            pass
                        del self._renew_tasks[target_name]
                    self._locks.pop(target_name, None)
                logger.info("flash_lock_released_redis: target=%s owner=%s", target_name, owner_id)
                return True
            return False
        except Exception as e:
            logger.error("flash_lock_release_redis_error: target=%s error=%s", target_name, str(e))
            return False

    async def _release_memory(self, target_name: str, owner_id: str) -> bool:
        """In-memory lock release (single-node only)."""
        async with self._lock:
            lock = self._locks.get(target_name)
            if not lock:
                return True
            if lock.owner_id != owner_id:
                logger.warning(
                    "flash_lock_release_denied: target=%s requested_by=%s owned_by=%s",
                    target_name, owner_id, lock.owner_id,
                )
                return False
            if target_name in self._renew_tasks:
                self._renew_tasks[target_name].cancel()
                del self._renew_tasks[target_name]
            del self._locks[target_name]
            logger.info("flash_lock_released_memory: target=%s owner=%s", target_name, owner_id)
            return True
    
    async def _renew_loop(self, target_name: str) -> None:
        """Background task to renew lock."""
        while True:
            try:
                await asyncio.sleep(self.renew_interval_seconds)
                
                async with self._lock:
                    lock = self._locks.get(target_name)
                    if not lock or not lock.is_valid():
                        break
                    
                    lock.renew()
                    
                    logger.debug(
                        "flash_lock_renewed",
                        target=target_name,
                        expires=lock.expires_at.isoformat(),
                    )
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("flash_lock_renew_error", error=str(e))
    
    async def extend(
        self,
        target_name: str,
        owner_id: str,
        additional_seconds: int = 60,
    ) -> bool:
        """Extend lock timeout.
        
        Args:
            target_name: Target name
            owner_id: Owner ID
            additional_seconds: Seconds to add
        
        Returns:
            True if extended
        """
        async with self._lock:
            lock = self._locks.get(target_name)
            
            if not lock or lock.owner_id != owner_id:
                return False
            
            lock.renew(timedelta(seconds=additional_seconds))
            return True
    
    def get_lock(self, target_name: str) -> FlashLock | None:
        """Get current lock for target (L1 cache + Redis sync).

        When Redis is available, syncs from Redis (authoritative) to local cache.
        """
        # L1 cache hit
        lock = self._locks.get(target_name)
        if lock:
            return lock

        # P0-Hardening: Sync from Redis (authoritative) if available
        if self._redis is not None and self._redis_connected:
            return self._sync_lock_from_redis(target_name)

        return None

    def _sync_lock_from_redis(self, target_name: str) -> FlashLock | None:
        """P0-Hardening: Sync lock state from Redis to local cache.

        Redis is the authoritative source; in-memory is L1 cache only.
        """
        redis_key = self._redis_key(target_name)
        fence_key = self._redis_fence_key(target_name)

        try:
            import time as _time

            lock_data = self._redis.hgetall(redis_key)
            if not lock_data:
                return None

            owner_id = (
                lock_data[b"owner_id"].decode()
                if isinstance(lock_data.get(b"owner_id"), bytes)
                else lock_data.get("owner_id", "")
            )
            fence_seq = int(
                lock_data[b"fence_seq"].decode()
                if isinstance(lock_data.get(b"fence_seq"), bytes)
                else lock_data.get("fence_seq", 0)
            )
            expires_at_str = (
                lock_data[b"expires_at"].decode()
                if isinstance(lock_data.get(b"expires_at"), bytes)
                else lock_data.get("expires_at", "0")
            )
            expires_at = datetime.fromtimestamp(float(expires_at_str))

            lock = FlashLock(
                target_name=target_name,
                owner_id=owner_id,
                fence_sequence=fence_seq,
                expires_at=expires_at,
            )

            # Update L1 cache
            self._locks[target_name] = lock
            return lock

        except Exception as e:
            logger.warning("sync_lock_from_redis_failed: target=%s error=%s", target_name, str(e))
            return None

    async def _sync_lock_from_redis_async(self, target_name: str) -> FlashLock | None:
        """P0-Hardening: Async version of sync_lock_from_redis."""
        return self._sync_lock_from_redis(target_name)

    def is_locked(self, target_name: str) -> bool:
        """Check if target is locked."""
        # L1 cache check first
        lock = self._locks.get(target_name)
        if lock and lock.is_valid():
            return True

        # P0-Hardening: Check Redis if available
        if self._redis is not None and self._redis_connected:
            redis_key = self._redis_key(target_name)
            try:
                import time as _time

                expires_at_str = self._redis.hget(redis_key, "expires_at")
                if expires_at_str:
                    expires_at = float(
                        expires_at_str.decode() if isinstance(expires_at_str, bytes) else expires_at_str
                    )
                    return expires_at > _time.time()
            except Exception:
                pass

        return False

    def get_lock_owner(self, target_name: str) -> str | None:
        """Get owner of lock."""
        # L1 cache check first
        lock = self._locks.get(target_name)
        if lock and lock.is_valid():
            return lock.owner_id

        # P0-Hardening: Check Redis if available
        if self._redis is not None and self._redis_connected:
            redis_key = self._redis_key(target_name)
            try:
                owner = self._redis.hget(redis_key, "owner_id")
                if owner:
                    return owner.decode() if isinstance(owner, bytes) else owner
            except Exception:
                pass

        return None
    
    def get_all_locks(self) -> dict[str, FlashLock]:
        """Get all current locks.

        When Redis is available, syncs from Redis (authoritative) to local cache.
        """
        if self._redis is not None and self._redis_connected:
            self._sync_all_locks_from_redis()
        return self._locks.copy()

    def _sync_all_locks_from_redis(self) -> int:
        """P0-Hardening: Sync all locks from Redis to local cache.

        Returns the number of locks synced.
        """
        synced = 0
        prefix = "aisupport:flash_lock:"

        try:
            cursor = 0
            while True:
                cursor, keys = self._redis.scan(cursor, match=f"{prefix}*", count=100)
                for key in keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    if ":fence" in key_str:
                        continue
                    # Extract target_name from key
                    target_name = key_str.replace(prefix, "")
                    if target_name and target_name not in self._locks:
                        if self._sync_lock_from_redis(target_name):
                            synced += 1
                if cursor == 0:
                    break
        except Exception:
            pass
        return synced
    
    async def force_release(self, target_name: str) -> bool:
        """Force release a lock (admin operation).

        Use with caution - may cause data loss if target is being flashed.
        """
        async with self._lock:
            if target_name in self._renew_tasks:
                self._renew_tasks[target_name].cancel()
                del self._renew_tasks[target_name]

            # P0-Hardening: Clear Redis authoritative state if connected
            if self._redis is not None and self._redis_connected:
                try:
                    redis_key = self._redis_key(target_name)
                    fence_key = self._redis_fence_key(target_name)
                    await self._redis.delete(redis_key)
                    await self._redis.delete(fence_key)
                except Exception:
                    pass

            if target_name in self._locks:
                del self._locks[target_name]
                logger.warning("flash_lock_force_released: target=%s", target_name)
                return True

            return False
    
    # =================================================================
    # FENCING TOKEN OPERATIONS (P0)
    # =================================================================
    
    async def issue_fence_token(
        self,
        target_name: str,
        owner_id: str,
        transaction_id: str,
    ) -> FlashFenceToken | None:
        """Issue a fencing token for flash operations.

        CRITICAL: Every flash operation (erase/write/verify) MUST
        validate this token before proceeding to prevent split-brain.

        Args:
            target_name: Target being locked
            owner_id: Owner (must match lock owner)
            transaction_id: Flash transaction ID

        Returns:
            FlashFenceToken if lock is held by owner, None otherwise
        """
        async with self._lock:
            lock = self._locks.get(target_name)

            # P0-Hardening: Sync from Redis if not in local cache
            if not lock and self._redis is not None and self._redis_connected:
                lock = await self._sync_lock_from_redis_async(target_name)

            if not lock:
                logger.warning(
                    "fence_token_issue_failed: no lock held",
                    target=target_name,
                )
                return None

            if not lock.is_valid():
                logger.warning(
                    "fence_token_issue_failed: lock expired",
                    target=target_name,
                )
                return None

            if lock.owner_id != owner_id:
                logger.warning(
                    "fence_token_issue_failed: owner mismatch",
                    target=target_name,
                    requested_by=owner_id,
                    owned_by=lock.owner_id,
                )
                return None

            return lock.issue_fence_token(transaction_id, owner_id)
    
    async def validate_fence_token(
        self,
        target_name: str,
        token: FlashFenceToken,
        operation_name: str,
    ) -> tuple[bool, str]:
        """Validate a fence token before flash operation.

        CRITICAL: Call this BEFORE every erase/write/verify operation.

        Args:
            target_name: Target being operated on
            token: Fence token to validate
            operation_name: Name of operation (erase, write, verify)

        Returns:
            (is_valid, error_message)
        """
        async with self._lock:
            lock = self._locks.get(target_name)

            # P0-Hardening: Sync from Redis if not in local cache
            if not lock and self._redis is not None and self._redis_connected:
                lock = await self._sync_lock_from_redis_async(target_name)

            # Check lock exists
            if not lock:
                return False, f"No lock held for {target_name}"
            
            # Check lock owner matches token owner
            if lock.owner_id != token.owner_id:
                return False, (
                    f"Token owner mismatch: token={token.owner_id}, "
                    f"lock={lock.owner_id}"
                )
            
            # Check token validity
            is_valid, reason = token.validate_for_operation(operation_name)
            if not is_valid:
                return False, reason
            
            # Check token sequence matches current lock sequence
            if token.sequence < lock.fence_sequence:
                return False, (
                    f"Stale fence token: token_seq={token.sequence}, "
                    f"current_seq={lock.fence_sequence}. "
                    f"Rejecting {operation_name} to prevent split-brain."
                )
            
            # Token is valid
            return True, ""
    
    async def revoke_fence_token(
        self,
        target_name: str,
        owner_id: str,
    ) -> bool:
        """Revoke the current fence token for a lock.

        Call this when a flash operation fails to prevent
        stale operations from proceeding.

        Args:
            target_name: Target name
            owner_id: Owner ID

        Returns:
            True if revoked
        """
        async with self._lock:
            lock = self._locks.get(target_name)

            # P0-Hardening: Sync from Redis if not in local cache
            if not lock and self._redis is not None and self._redis_connected:
                lock = await self._sync_lock_from_redis_async(target_name)

            if not lock or lock.owner_id != owner_id:
                return False

            # This effectively invalidates the current token
            # New tokens will have higher sequence
            lock.fence_sequence += 1

            logger.info(
                "fence_token_revoked",
                target=target_name,
                owner=owner_id,
                new_sequence=lock.fence_sequence,
            )

            return True
    
    def get_fence_state(self, target_name: str) -> dict[str, Any] | None:
        """Get current fence state for a target."""
        lock = self._locks.get(target_name)
        if not lock:
            return None
        
        return {
            "target_name": target_name,
            "owner_id": lock.owner_id,
            "is_valid": lock.is_valid(),
            "fence_sequence": lock.fence_sequence,
            "version": lock.version,
        }


# =============================================================================
# OPERATION LEDGER (P0-C)
# =============================================================================


@dataclass
class FlashOperationRecord:
    """Record of a flash operation for audit and split-brain prevention.
    
    P0-C: Every flash operation (erase/write/verify) MUST be logged
    to the operation ledger with its fence token for traceability.
    """
    target_name: str
    operation: str  # "erase", "write", "verify"
    fence_token: str
    fence_sequence: int
    
    # Operation details
    transaction_id: str
    sector_start: int = 0
    sector_count: int = 0
    address: int = 0
    length: int = 0
    
    # Status
    status: str = "pending"  # pending, running, completed, failed
    result: str = ""
    
    # Timing
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    duration_ms: float = 0
    
    # Owner
    owner_id: str = ""
    
    def mark_completed(self, result: str = "success") -> None:
        """Mark operation as completed."""
        self.status = "completed"
        self.result = result
        self.completed_at = datetime.now()
        self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000
    
    def mark_failed(self, error: str) -> None:
        """Mark operation as failed."""
        self.status = "failed"
        self.result = error
        self.completed_at = datetime.now()
        self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000


class OperationLedger:
    """Ledger for tracking all flash operations.

    P0-C: This is the source of truth for operation history.
    Used to detect stale operations and prevent split-brain.

    P0-Hardening: optionally backed by Redis for durability across restarts.

    Features:
    - Append-only operation log
    - Fence token tracking
    - Staleness detection
    - Audit trail
    - Optional Redis backend with TTL
    """

    def __init__(
        self,
        max_records: int = 10000,
        redis_url: str | None = None,
    ):
        self._records: list[FlashOperationRecord] = []
        self.max_records = max_records
        self._lock = asyncio.Lock()

        # P0-Hardening: optional Redis backing
        self._redis_url = redis_url
        self._redis: Any = None
        self._redis_connected = False

    async def _ensure_redis(self) -> bool:
        """Connect to Redis if configured."""
        if self._redis_url is None or self._redis_connected:
            return self._redis_connected
        try:
            import aioredis
            self._redis = await aioredis.create_redis_pool(self._redis_url)
            self._redis_connected = True
            return True
        except Exception:
            return False
    
    async def append(
        self,
        target_name: str,
        operation: str,
        fence_token: FlashFenceToken,
        **kwargs,
    ) -> FlashOperationRecord:
        """Append a new operation record.

        Args:
            target_name: Target being operated on
            operation: Operation type (erase, write, verify)
            fence_token: Fence token for this operation
            **kwargs: Additional operation details

        Returns:
            FlashOperationRecord
        """
        async with self._lock:
            record = FlashOperationRecord(
                target_name=target_name,
                operation=operation,
                fence_token=fence_token.token,
                fence_sequence=fence_token.sequence,
                transaction_id=fence_token.transaction_id,
                owner_id=fence_token.owner_id,
                **kwargs,
            )

            self._records.append(record)

            # Trim if over limit
            if len(self._records) > self.max_records:
                self._records = self._records[-self.max_records:]

            # P0-Hardening: persist to Redis if configured
            if await self._ensure_redis():
                await self._append_redis(record)

            return record

    async def _append_redis(self, record: FlashOperationRecord) -> None:
        """P0-Hardening: append record to Redis list with TTL."""
        import json as _json

        key = f"aisupport:ledger:{record.target_name}"
        try:
            data = _json.dumps({
                "target_name": record.target_name,
                "operation": record.operation,
                "fence_token": record.fence_token,
                "fence_sequence": record.fence_sequence,
                "transaction_id": record.transaction_id,
                "sector_start": record.sector_start,
                "sector_count": record.sector_count,
                "address": record.address,
                "length": record.length,
                "status": record.status,
                "result": record.result,
                "started_at": record.started_at.isoformat(),
                "completed_at": record.completed_at.isoformat() if record.completed_at else None,
                "duration_ms": record.duration_ms,
                "owner_id": record.owner_id,
            })
            # LPUSH to list, LTRIM to max_records
            await self._redis.lpush(key, data)
            await self._redis.ltrim(key, 0, self.max_records - 1)
            # 30-day TTL for Redis entries
            await self._redis.expire(key, 30 * 24 * 3600)
        except Exception:
            pass  # Redis append failures should not break operation
    
    async def get_latest_for_target(
        self,
        target_name: str,
        operation: str = None,
    ) -> list[FlashOperationRecord]:
        """Get latest operation records for a target."""
        async with self._lock:
            records = [
                r for r in self._records
                if r.target_name == target_name
                and (operation is None or r.operation == operation)
            ]
            return records[-100:]  # Last 100
    
    async def get_latest_sequence(
        self,
        target_name: str,
    ) -> int:
        """Get the latest fence sequence for a target."""
        async with self._lock:
            target_records = [
                r for r in self._records
                if r.target_name == target_name
            ]
            if not target_records:
                return 0
            return max(r.fence_sequence for r in target_records)
    
    async def validate_no_stale_operations(
        self,
        target_name: str,
        fence_sequence: int,
    ) -> tuple[bool, str]:
        """Check if there are any pending/stale operations with lower sequence.
        
        P0-C: This prevents split-brain by detecting if an operation
        with a lower fence sequence is still pending.
        
        Returns:
            (is_safe, error_message)
        """
        async with self._lock:
            # Check for pending operations with lower or equal sequence
            for record in self._records:
                if (record.target_name == target_name
                    and record.fence_sequence <= fence_sequence
                    and record.status == "pending"):
                    
                    return False, (
                        f"Found pending operation seq={record.fence_sequence} "
                        f"for {record.operation} on {target_name}. "
                        f"Current seq={fence_sequence}. "
                        f"Cannot proceed until pending operation completes."
                    )
            
            return True, ""


@dataclass
class LockManager:
    """Manages flash locks and coordinates with event bus.

    Integrates with Phase 6.1 event bus for lock events.

    CRITICAL: Uses fencing tokens to prevent split-brain scenarios.
    Every flash operation MUST:
    1. Acquire lock -> get fence token
    2. Validate token BEFORE every erase/write/verify
    3. Advance token version after successful operation
    4. Revoke token on failure

    P0-Hardening:
    - TargetFlashLock uses Redis as authoritative storage with Lua-script atomicity
    - OperationLedger optionally persists to Redis with TTL
    - Stale lock recovery on startup
    """
    event_bus: Any = None
    
    async def acquire_and_publish(
        self,
        target_name: str,
        owner_id: str,
        timeout_seconds: float = 30.0,
    ) -> FlashLock | None:
        """Acquire lock and publish event."""
        lock = await self.target_lock.acquire(target_name, owner_id, timeout_seconds)
        
        if lock and self.event_bus:
            from ..event import DomainEvent
            
            event = DomainEvent(
                event_type="flash.lock.acquired",
                source="lock_manager",
                data=lock.to_dict(),
            )
            await self.event_bus.publish(event)
        
        return lock
    
    async def acquire_with_fence_token(
        self,
        target_name: str,
        owner_id: str,
        transaction_id: str,
        timeout_seconds: float = 30.0,
    ) -> tuple[FlashLock | None, FlashFenceToken | None]:
        """Acquire lock and issue fence token atomically.
        
        This is the PREFERRED method for flash operations.
        
        Args:
            target_name: Target to lock
            owner_id: Owner (agent/session)
            transaction_id: Flash transaction ID
            timeout_seconds: Lock acquisition timeout
            
        Returns:
            (FlashLock, FlashFenceToken) if successful, (None, None) otherwise
        """
        lock = await self.acquire_and_publish(target_name, owner_id, timeout_seconds)
        
        if not lock:
            return None, None
        
        token = await self.target_lock.issue_fence_token(
            target_name=target_name,
            owner_id=owner_id,
            transaction_id=transaction_id,
        )
        
        if not token:
            # Lock acquired but token issue failed - release lock
            await self.target_lock.release(target_name, owner_id)
            return None, None
        
        return lock, token
    
    async def validate_and_execute(
        self,
        target_name: str,
        fence_token: FlashFenceToken,
        operation_name: str,
        operation_fn: callable,
    ) -> Any:
        """Validate fence token and execute operation atomically.
        
        This is the CRITICAL pattern for ALL flash operations:
        
        ```python
        # 1. Acquire lock and token
        lock, token = await manager.acquire_with_fence_token(
            target_name, owner_id, transaction_id
        )
        
        # 2. Execute with validation
        result = await manager.validate_and_execute(
            target_name, token, "write", write_fn
        )
        
        # 3. Advance token on success
        if result:
            await manager.advance_fence_token(target_name, owner_id)
        ```
        
        Args:
            target_name: Target being operated on
            fence_token: Token from acquire_with_fence_token
            operation_name: Name of operation (erase, write, verify)
            operation_fn: Async function to execute
            
        Returns:
            Operation result if valid, raises FenceValidationError otherwise
        """
        is_valid, reason = await self.target_lock.validate_fence_token(
            target_name=target_name,
            token=fence_token,
            operation_name=operation_name,
        )
        
        if not is_valid:
            raise FenceValidationError(
                operation=operation_name,
                token_sequence=fence_token.sequence,
                required_sequence=fence_token.sequence,
                reason=reason,
            )
        
        result = await operation_fn()
        
        # Advance token version on success
        fence_token.advance_version()
        
        return result
    
    async def advance_fence_token(
        self,
        target_name: str,
        owner_id: str,
    ) -> bool:
        """Advance fence token version after successful operation.
        
        Call this after each successful erase/write/verify.
        """
        return await self.target_lock.revoke_fence_token(target_name, owner_id)
    
    async def invalidate_fence_on_failure(
        self,
        target_name: str,
        owner_id: str,
    ) -> bool:
        """Invalidate fence tokens on operation failure.
        
        Call this when a flash operation fails to prevent
        stale operations from proceeding.
        """
        revoked = await self.target_lock.revoke_fence_token(target_name, owner_id)
        
        if revoked and self.event_bus:
            from ..event import DomainEvent
            
            event = DomainEvent(
                event_type="flash.fence_invalidated",
                source="lock_manager",
                data={
                    "target_name": target_name,
                    "owner_id": owner_id,
                },
            )
            await self.event_bus.publish(event)
        
        return revoked
    
    async def release_and_publish(
        self,
        target_name: str,
        owner_id: str,
    ) -> bool:
        """Release lock and publish event."""
        released = await self.target_lock.release(target_name, owner_id)
        
        if released and self.event_bus:
            from ..event import DomainEvent
            
            event = DomainEvent(
                event_type="flash.lock.released",
                source="lock_manager",
                data={
                    "target_name": target_name,
                    "owner_id": owner_id,
                },
            )
            await self.event_bus.publish(event)
        
        return released
    
    async def cleanup_expired_locks(self) -> int:
        """Clean up expired locks.
        
        Returns:
            Number of locks cleaned
        """
        cleaned = 0
        
        async with self.target_lock._lock:
            for target_name in list(self.target_lock._locks.keys()):
                lock = self.target_lock._locks.get(target_name)
                if lock and not lock.is_valid():
                    if target_name in self.target_lock._renew_tasks:
                        self.target_lock._renew_tasks[target_name].cancel()
                        del self.target_lock._renew_tasks[target_name]
                    
                    del self.target_lock._locks[target_name]
                    cleaned += 1
        
        if cleaned > 0:
            logger.info("expired_locks_cleaned", count=cleaned)
        
        return cleaned
    
    async def get_lock_status(self, target_name: str) -> dict[str, Any]:
        """Get detailed lock status including fence state."""
        lock = self.target_lock.get_lock(target_name)
        
        if not lock:
            return {
                "locked": False,
                "target_name": target_name,
            }
        
        return {
            "locked": True,
            "target_name": target_name,
            "owner_id": lock.owner_id,
            "acquired_at": lock.acquired_at.isoformat(),
            "expires_at": lock.expires_at.isoformat(),
            "remaining_seconds": max(0, (lock.expires_at - datetime.now()).total_seconds()),
            "is_valid": lock.is_valid(),
            "fence_state": self.target_lock.get_fence_state(target_name),
        }
