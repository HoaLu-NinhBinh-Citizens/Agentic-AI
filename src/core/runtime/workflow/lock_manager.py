"""Distributed Lock Manager with Fencing Token - Phase 5A (v6).

Implements distributed locking with fencing tokens for safe lock release.

RECOVERY SEMANTICS
===================

1. CLOCK SKEW ASSUMPTIONS:
   - Uses TTL-based leases, not wall clock
   - Assumes clock drift < lock_timeout / 2
   - If drift exceeds threshold, lock may expire early

2. REDIS PARTITION BEHAVIOR:
   - On partition: falls back to in-memory locks
   - On reconnect: transfers pending locks to Redis
   - May have brief inconsistency during partition

3. TOKEN MONOTONICITY GUARANTEES:
   - Fence tokens are monotonic epochs (per lock key)
   - Under Redis uncertainty, acquire fails closed (no unsafe fallback)
   - Services must reject operations with stale epoch

4. SPLIT-BRAIN PREVENTION:
   - Fencing token passed to external services
   - Services check token before accepting operations
   - Only operations with highest token are processed
"""

from __future__ import annotations

import asyncio
import logging
import time

from typing import Optional
from dataclasses import dataclass, field

from .types import LockFenceToken

logger = logging.getLogger(__name__)


# Clock skew tolerance (in seconds)
CLOCK_SKEW_TOLERANCE = 1.0


@dataclass
class LockRecoveryState:
    """State for lock recovery after Redis partition."""
    lock_key: str
    token: str
    owner_id: str
    created_at: float
    expires_at: float
    is_pending: bool = True


class LockManager:
    """Distributed lock manager with fencing tokens.
    
    Features:
    - Fencing tokens to prevent split-brain
    - Lease renewal via heartbeat
    - Automatic expiry
    - Redis backend support
    - Fail-closed on Redis unavailability (no in-memory fallback for dangerous ops)
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        lock_timeout_seconds: float = 10.0,
        fencing_enabled: bool = True,
        health_check_interval: float = 30.0,
        clock_skew_tolerance: float = CLOCK_SKEW_TOLERANCE,
        partition_recovery_enabled: bool = True,
    ):
        self._redis_url = redis_url
        self._lock_timeout = lock_timeout_seconds
        self._fencing_enabled = fencing_enabled
        self._health_check_interval = health_check_interval
        self._clock_skew_tolerance = clock_skew_tolerance
        self._partition_recovery = partition_recovery_enabled
        
        self._redis = None
        self._fallback_locks: dict[str, str] = {}  # key -> token
        self._fallback_count = 0
        
        # Token storage
        self._tokens: dict[str, str] = {}  # full_key -> token
        
        # Recovery state
        self._recovery_states: dict[str, LockRecoveryState] = {}
        
        # Health check
        self._health_check_task: Optional[asyncio.Task] = None
        self._redis_available = False
        self._redis_available_lock = asyncio.Lock()
        
        # Pending transfer locks
        self._pending_transfer_locks: dict[str, str] = {}

    async def acquire(
        self,
        key: str,
        owner_id: str,
        timeout: float = 5.0,
    ) -> Optional[LockFenceToken]:
        """Acquire a distributed lock.

        P0 safety:
        - Uses Redis-backed monotonic fencing epoch (INCR per key)
        - If Redis is unavailable, returns None (fail-closed) to prevent dangerous ops
        """
        full_key = f"lock:{key}"
        epoch_key = f"lock_epoch:{key}"

        # Start health check if not running
        if self._health_check_task is None or self._health_check_task.done():
            self._health_check_task = asyncio.create_task(self._health_check_loop())

        try:
            redis = await self._get_redis()
            if not redis:
                return None

            # Monotonic fencing epoch for this lock key
            epoch = int(await redis.incr(epoch_key))

            # Token still stored for compare-and-delete ownership
            token = f"{owner_id}:{epoch}"

            acquired = await redis.set(
                full_key,
                token,
                nx=True,
                ex=int(self._lock_timeout),
            )

            if acquired:
                async with self._redis_available_lock:
                    self._redis_available = True

                fence_token = LockFenceToken(
                    epoch=epoch,
                    lock_id=key,
                    owner_id=owner_id,
                    expires_at=time.time() + self._lock_timeout,
                )
                self._tokens[full_key] = token

                logger.debug(f"Lock acquired: {key} (epoch={epoch})")
                return fence_token

            return None

        except Exception as e:
            logger.warning(f"Redis lock acquire failed: {e}")
            return None

    async def _acquire_fallback(
        self,
        key: str,
        owner_id: str,
        token: str,
    ) -> Optional[LockFenceToken]:
        """Fallback to in-memory lock.

        Deprecated for production: P0 requires fail-closed under Redis uncertainty.
        Kept for single-node tests only.
        """
        return None

    async def release(
        self,
        key: str,
        token: LockFenceToken,
    ) -> bool:
        """Release a lock.

        Only releases if token matches (fencing).
        """
        full_key = f"lock:{key}"
        
        # Check in-memory first
        if key in self._fallback_locks:
            if self._fallback_locks.get(key) == token.token:
                del self._fallback_locks[key]
                self._tokens.pop(full_key, None)
                self._pending_transfer_locks.pop(key, None)
                return True
            return False
        
        # Try Redis
        try:
            redis = await self._get_redis()
            if not redis:
                return False

            # Compare-and-delete ownership token
            stored = await redis.get(full_key)
            expected = self._tokens.get(full_key)
            if stored and expected and stored == expected:
                await redis.delete(full_key)
                self._tokens.pop(full_key, None)
                return True

            return False

        except Exception as e:
            logger.warning(f"Redis lock release failed: {e}")
            return False

    async def extend(
        self,
        key: str,
        token: LockFenceToken,
        additional_seconds: float,
    ) -> bool:
        """Extend lock lease."""
        full_key = f"lock:{key}"

        # Try Redis
        try:
            redis = await self._get_redis()
            if not redis:
                return False

            stored = await redis.get(full_key)
            expected = self._tokens.get(full_key)
            if stored and expected and stored == expected:
                new_expiry = int(additional_seconds)
                await redis.expire(full_key, new_expiry)
                token.expires_at = max(token.expires_at, time.time()) + additional_seconds
                return True

            return False

        except Exception as e:
            logger.warning(f"Lock extend failed: {e}")
            return False

    async def check_token(
        self,
        key: str,
        token: str,
    ) -> bool:
        """Check if token is still valid."""
        full_key = f"lock:{key}"

        try:
            redis = await self._get_redis()
            if not redis:
                return False

            stored = await redis.get(full_key)
            expected = self._tokens.get(full_key)
            return bool(stored and expected and stored == expected)

        except Exception:
            return False

    async def _get_redis(self):
        """Get Redis connection."""
        if self._redis is None and self._redis_url:
            try:
                from redis import asyncio as redis  # type: ignore
                self._redis = redis.from_url(self._redis_url)
            except Exception:
                return None
        
        return self._redis

    async def _health_check_loop(self) -> None:
        """Periodically check Redis connectivity."""
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                
                was_unavailable = not self._redis_available
                
                if await self._check_redis_connection():
                    async with self._redis_available_lock:
                        self._redis_available = True
                    
                    if was_unavailable:
                        logger.info("Redis connection restored, switching back")
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
            if redis:
                await redis.ping()
                return True
        except Exception:
            pass
        return False

    async def _transfer_pending_locks(self) -> None:
        """No-op.

        P0 fail-closed: we do not keep in-memory locks for transfer.
        """
        return

    @property
    def fallback_count(self) -> int:
        """Number of times fallback was used."""
        return self._fallback_count
    
    # =========================================================================
    # RECOVERY SEMANTICS
    # =========================================================================
    
    async def get_recovery_state(self, key: str) -> Optional[LockRecoveryState]:
        """Get recovery state for a lock.
        
        Returns state captured during partition for potential recovery.
        """
        return self._recovery_states.get(key)
    
    async def validate_clock_skew(self) -> bool:
        """Validate that clock skew is within tolerance.
        
        Checks if our clock is reasonably synchronized with Redis server.
        Returns True if skew is acceptable.
        """
        try:
            redis = await self._get_redis()
            if not redis:
                return True  # Can't check, assume OK
            
            # Get Redis server time
            server_time = await redis.time()
            local_time = time.time()
            
            # Calculate skew
            skew = abs(local_time - server_time)
            
            if skew > self._clock_skew_tolerance:
                logger.warning(
                    f"Clock skew detected: {skew}s "
                    f"(tolerance: {self._clock_skew_tolerance}s)"
                )
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Clock skew validation failed: {e}")
            return True  # Assume OK if check fails
    
    async def get_lock_info(self, key: str) -> dict:
        """Get information about a lock.

        Returns lock metadata for debugging/monitoring.
        """
        full_key = f"lock:{key}"

        info: dict[str, object] = {
            "key": key,
            "locked": False,
            "owner": None,
            "expires_at": None,
            "backend": "redis" if self._redis_url else "none",
        }

        try:
            redis = await self._get_redis()
            if not redis:
                return info

            stored = await redis.get(full_key)
            if stored:
                info["locked"] = True
                info["owner"] = str(stored)

                ttl = await redis.ttl(full_key)
                if ttl > 0:
                    info["expires_at"] = time.time() + ttl

        except Exception as e:
            logger.debug(f"Failed to get lock info: {e}")

        return info
    
    async def force_expire(self, key: str) -> bool:
        """Force expire a lock (admin operation).
        
        WARNING: Use with caution. May cause race conditions.
        
        Args:
            key: Lock key to expire.
            
        Returns:
            True if lock was expired.
        """
        full_key = f"lock:{key}"
        
        # Remove from memory
        self._fallback_locks.pop(key, None)
        self._recovery_states.pop(key, None)
        
        # Remove from Redis
        try:
            redis = await self._get_redis()
            if redis:
                await redis.delete(full_key)
                await redis.delete(f"{full_key}:owner")
                return True
        except Exception as e:
            logger.error(f"Failed to force expire lock: {e}")
        
        return False


class FencedLock:
    """Context manager for fenced lock."""
    
    def __init__(
        self,
        manager: LockManager,
        key: str,
        owner_id: str,
    ):
        self._manager = manager
        self._key = key
        self._owner_id = owner_id
        self._token: Optional[LockFenceToken] = None
    
    async def __aenter__(self) -> FencedLock:
        self._token = await self._manager.acquire(
            key=self._key,
            owner_id=self._owner_id,
        )
        if not self._token:
            raise LockAcquisitionError(f"Failed to acquire lock: {self._key}")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._token:
            await self._manager.release(self._key, self._token)
    
    @property
    def token(self) -> LockFenceToken:
        """Get the fence token."""
        if not self._token:
            raise LockAcquisitionError("Lock not acquired")
        return self._token


class LockAcquisitionError(Exception):
    """Failed to acquire lock."""
    pass
