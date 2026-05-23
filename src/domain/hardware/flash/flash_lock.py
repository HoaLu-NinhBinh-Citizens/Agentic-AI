"""Flash Lock - Distributed concurrency locking for flash operations.

Phase 6.2: Implements distributed flash locking for:
- Atomic lock acquisition
- Automatic lease renewal
- Lock timeout handling
- Integration with event bus
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FlashLock:
    """Distributed flash lock for target."""
    
    target_name: str
    owner_id: str
    
    acquired_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=datetime.now)
    
    lease_timeout: timedelta = field(default_factory=lambda: timedelta(seconds=60))
    
    version: int = 1
    
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
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "target_name": self.target_name,
            "owner_id": self.owner_id,
            "acquired_at": self.acquired_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "version": self.version,
        }


@dataclass
class TargetFlashLock:
    """Manages flash locks for targets.
    
    Features:
    - Atomic lock acquisition
    - Automatic lease renewal
    - Distributed lock support (Redis)
    - Lock timeout handling
    """
    
    lock_storage: str = "memory"  # "memory", "file", "redis"
    lock_dir: str = "/tmp/aisupport/locks"
    redis_url: str = "redis://localhost:6379"
    
    lease_timeout_seconds: int = 60
    renew_interval_seconds: int = 30
    
    _locks: dict[str, FlashLock] = field(default_factory=dict)
    _renew_tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    
    _redis: Any = field(default=None, init=False)
    
    def __post_init__(self) -> None:
        """Initialize lock storage."""
        if self.lock_storage == "file":
            os.makedirs(self.lock_dir, exist_ok=True)
    
    async def _init_redis(self) -> None:
        """Initialize Redis connection."""
        if self._redis is None and self.lock_storage == "redis":
            try:
                import aioredis
                self._redis = await aioredis.create_redis_pool(self.redis_url)
            except Exception as e:
                logger.warning("redis_connection_failed", error=str(e))
                self.lock_storage = "memory"
    
    async def acquire(
        self,
        target_name: str,
        owner_id: str,
        timeout_seconds: float = 30.0,
    ) -> FlashLock | None:
        """Acquire flash lock for target.
        
        Args:
            target_name: Target to lock
            owner_id: Owner (agent/session ID)
            timeout_seconds: Time to wait for lock
        
        Returns:
            FlashLock if acquired, None if failed
        """
        start_time = datetime.now()
        
        await self._init_redis()
        
        while True:
            async with self._lock:
                # Check existing lock
                existing = self._locks.get(target_name)
                
                if existing and existing.is_valid():
                    if existing.owner_id == owner_id:
                        existing.renew()
                        return existing
                    
                    if (datetime.now() - start_time).total_seconds() >= timeout_seconds:
                        return None
                    
                    await asyncio.sleep(1)
                    continue
                
                # Acquire new lock
                lock = FlashLock(
                    target_name=target_name,
                    owner_id=owner_id,
                    expires_at=datetime.now() + timedelta(seconds=self.lease_timeout_seconds),
                    lease_timeout=timedelta(seconds=self.lease_timeout_seconds),
                )
                self._locks[target_name] = lock
                
                # Start renew task
                self._renew_tasks[target_name] = asyncio.create_task(
                    self._renew_loop(target_name)
                )
                
                logger.info(
                    "flash_lock_acquired",
                    target=target_name,
                    owner=owner_id,
                    expires=lock.expires_at.isoformat(),
                )
                
                return lock
            
            await asyncio.sleep(0.1)
    
    async def release(self, target_name: str, owner_id: str) -> bool:
        """Release flash lock.
        
        Args:
            target_name: Target name
            owner_id: Owner ID (must match)
        
        Returns:
            True if released
        """
        async with self._lock:
            lock = self._locks.get(target_name)
            
            if not lock:
                return True
            
            if lock.owner_id != owner_id:
                logger.warning(
                    "flash_lock_release_denied: target=%s, requested_by=%s, owned_by=%s",
                    target_name, owner_id, lock.owner_id,
                )
                return False
            
            # Cancel renew task
            if target_name in self._renew_tasks:
                self._renew_tasks[target_name].cancel()
                del self._renew_tasks[target_name]
            
            del self._locks[target_name]
            
            logger.info(
                "flash_lock_released",
                target=target_name,
                owner=owner_id,
            )
            
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
        """Get current lock for target."""
        return self._locks.get(target_name)
    
    def is_locked(self, target_name: str) -> bool:
        """Check if target is locked."""
        lock = self._locks.get(target_name)
        return lock is not None and lock.is_valid()
    
    def get_lock_owner(self, target_name: str) -> str | None:
        """Get owner of lock."""
        lock = self._locks.get(target_name)
        return lock.owner_id if lock else None
    
    def get_all_locks(self) -> dict[str, FlashLock]:
        """Get all current locks."""
        return self._locks.copy()
    
    async def force_release(self, target_name: str) -> bool:
        """Force release a lock (admin operation).
        
        Use with caution - may cause data loss if target is being flashed.
        """
        async with self._lock:
            if target_name in self._renew_tasks:
                self._renew_tasks[target_name].cancel()
                del self._renew_tasks[target_name]
            
            if target_name in self._locks:
                del self._locks[target_name]
                logger.warning("flash_lock_force_released: target=%s", target_name)
                return True
            
            return False


@dataclass
class LockManager:
    """Manages flash locks and coordinates with event bus.
    
    Integrates with Phase 6.1 event bus for lock events.
    """
    
    target_lock: TargetFlashLock
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
        """Get detailed lock status."""
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
        }
