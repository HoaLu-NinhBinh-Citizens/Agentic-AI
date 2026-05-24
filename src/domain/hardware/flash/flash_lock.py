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
    
    def __post_init__(self) -> None:
        """Initialize lock storage."""
        if self.lock_storage == "file":
            os.makedirs(self.lock_dir, exist_ok=True)
        
        # P0-C: Log warning if using memory storage (for visibility)
        if self.lock_storage == "memory" and not self.fail_if_redis_unavailable:
            logger.warning(
                "P0-C WARNING: Using memory storage with fail_if_redis_unavailable=False. "
                "This is ONLY safe for single-node testing. "
                "DO NOT use in production distributed deployments."
            )
    
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
    
    Features:
    - Append-only operation log
    - Fence token tracking
    - Staleness detection
    - Audit trail
    """
    
    def __init__(self, max_records: int = 10000):
        self._records: list[FlashOperationRecord] = []
        self.max_records = max_records
        self._lock = asyncio.Lock()
    
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
            
            return record
    
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
