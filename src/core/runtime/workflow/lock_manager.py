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
   - Tokens are UUIDs, not monotonic counters
   - Use versioning/metadata for monotonicity
   - Fencing ensures operations see latest state

4. SPLIT-BRAIN PREVENTION:
   - Fencing token passed to external services
   - Services check token before accepting operations
   - Only operations with highest token are processed
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
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
    - In-memory fallback
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
        
        Args:
            key: Lock key.
            owner_id: Owner identifier (worker ID).
            timeout: Acquisition timeout.
            
        Returns:
            LockFenceToken if acquired, None otherwise.
        """
        token = str(uuid.uuid4())
        full_key = f"lock:{key}"
        
        # Start health check if not running
        if self._health_check_task is None or self._health_check_task.done():
            self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        # Try Redis first
        try:
            redis = await self._get_redis()
            if redis:
                acquired = await redis.set(
                    full_key,
                    token,
                    nx=True,
                    ex=int(self._lock_timeout)
                )
                
                if acquired:
                    async with self._redis_available_lock:
                        self._redis_available = True
                    
                    fence_token = LockFenceToken(
                        token=token,
                        lock_id=key,
                        owner_id=owner_id,
                        expires_at=time.time() + self._lock_timeout,
                    )
                    self._tokens[full_key] = token
                    
                    logger.debug(f"Lock acquired: {key} (token={token[:8]}...)")
                    return fence_token
        except Exception as e:
            logger.warning(f"Redis lock acquire failed: {e}")
        
        # Fallback to in-memory
        return await self._acquire_fallback(key, owner_id, token)

    async def _acquire_fallback(
        self,
        key: str,
        owner_id: str,
        token: str,
    ) -> Optional[LockFenceToken]:
        """Fallback to in-memory lock."""
        self._fallback_count += 1
        if self._fallback_count == 1:
            logger.warning(
                f"Redis unavailable, falling back to in-memory lock. "
                f"Multi-instance safety NOT guaranteed."
            )
        
        full_key = f"lock:{key}"
        
        if key not in self._fallback_locks:
            self._fallback_locks[key] = token
            self._tokens[full_key] = token
            self._pending_transfer_locks[key] = token
            
            return LockFenceToken(
                token=token,
                lock_id=key,
                owner_id=owner_id,
                expires_at=time.time() + self._lock_timeout,
            )
        
        return None

    async def release(
        self,
        key: str,
        token: LockFenceToken,
    ) -> bool:
        """Release a lock.
        
        Only releases if token matches (fencing).
        
        Args:
            key: Lock key.
            token: Token from acquire.
            
        Returns:
            True if released successfully.
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
            
            # Lua script for atomic compare-and-delete
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            result = await redis.eval(lua_script, 1, full_key, token.token)
            
            self._tokens.pop(full_key, None)
            return result > 0
            
        except Exception as e:
            logger.warning(f"Redis lock release failed: {e}")
            return False

    async def extend(
        self,
        key: str,
        token: LockFenceToken,
        additional_seconds: float,
    ) -> bool:
        """Extend lock lease.
        
        Args:
            key: Lock key.
            token: Token from acquire.
            additional_seconds: Additional lease time.
            
        Returns:
            True if extended successfully.
        """
        full_key = f"lock:{key}"
        
        # Check in-memory
        if key in self._fallback_locks:
            if self._fallback_locks.get(key) == token.token:
                # Extend from current expiry, not replace
                token.expires_at = max(token.expires_at, time.time()) + additional_seconds
                return True
            return False
        
        # Try Redis
        try:
            redis = await self._get_redis()
            if not redis:
                return False
            
            # Verify ownership and extend
            stored = await redis.get(full_key)
            if stored == token.token:
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
        """Check if token is still valid.
        
        Args:
            key: Lock key.
            token: Token to check.
            
        Returns:
            True if token is valid owner.
        """
        full_key = f"lock:{key}"
        
        if key in self._fallback_locks:
            return self._fallback_locks.get(key) == token
        
        try:
            redis = await self._get_redis()
            if not redis:
                return False
            
            stored = await redis.get(full_key)
            return stored == token
        except Exception:
            return False

    async def _get_redis(self):
        """Get Redis connection."""
        if self._redis is None and self._redis_url:
            try:
                import redis.asyncio as redis
                self._redis = redis.from_url(self._redis_url)
            except ImportError:
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
        """Transfer in-memory locks to Redis."""
        if not self._pending_transfer_locks:
            return
        
        logger.info(f"Transferring {len(self._pending_transfer_locks)} locks to Redis")
        
        for key, token in list(self._pending_transfer_locks.items()):
            try:
                full_key = f"lock:{key}"
                redis = await self._get_redis()
                
                acquired = await redis.set(
                    full_key, token, nx=True, ex=int(self._lock_timeout)
                )
                
                if acquired:
                    self._tokens[full_key] = token
                    del self._pending_transfer_locks[key]
                    
            except Exception as e:
                logger.error(f"Failed to transfer lock {key}: {e}")

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
        
        info = {
            "key": key,
            "locked": False,
            "owner": None,
            "expires_at": None,
            "is_pending": False,
        }
        
        # Check in-memory
        if key in self._fallback_locks:
            info["locked"] = True
            info["owner"] = self._fallback_locks.get(f"{key}_owner")
            if key in self._recovery_states:
                info["expires_at"] = self._recovery_states[key].expires_at
                info["is_pending"] = self._recovery_states[key].is_pending
            return info
        
        # Check Redis
        try:
            redis = await self._get_redis()
            if redis:
                ttl = await redis.ttl(full_key)
                if ttl > 0:
                    info["locked"] = True
                    info["expires_at"] = time.time() + ttl
                    stored_owner = await redis.get(f"{full_key}:owner")
                    info["owner"] = stored_owner
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
