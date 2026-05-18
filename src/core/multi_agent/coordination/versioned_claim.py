"""
Versioned Task Claim with Self-Healing.

Provides:
- Version tokens to prevent duplicate claims
- Self-healing queue without race conditions
- Atomic claim operations
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ClaimStatus(str, Enum):
    """Task claim status."""
    PENDING = "pending"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class TaskClaim:
    """Task claim record."""
    task_id: str
    worker_id: str
    version: int
    status: ClaimStatus
    claimed_at: datetime
    expires_at: datetime
    last_renewed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClaimResult:
    """Result of a claim operation."""
    success: bool
    version: Optional[int]
    claim: Optional[TaskClaim]
    reason: str


@dataclass
class ClaimConflict:
    """Record of a claim conflict."""
    task_id: str
    expected_version: int
    actual_version: int
    conflicting_worker: str
    timestamp: datetime


class VersionedTaskStore:
    """In-memory versioned task store."""
    
    def __init__(self):
        self._claims: Dict[str, TaskClaim] = {}
        self._versions: Dict[str, int] = {}  # task_id -> version
        self._conflicts: List[ClaimConflict] = []
        self._lock = asyncio.Lock()
    
    async def get_version(self, task_id: str) -> int:
        """Get current version for task."""
        return self._versions.get(task_id, 0)
    
    async def increment_version(self, task_id: str) -> int:
        """Atomically increment version."""
        async with self._lock:
            current = self._versions.get(task_id, 0)
            new_version = current + 1
            self._versions[task_id] = new_version
            return new_version
    
    async def set_claim(self, claim: TaskClaim) -> None:
        """Set claim."""
        self._claims[claim.task_id] = claim
    
    async def get_claim(self, task_id: str) -> Optional[TaskClaim]:
        """Get claim."""
        return self._claims.get(task_id)
    
    async def delete_claim(self, task_id: str) -> None:
        """Delete claim."""
        self._claims.pop(task_id, None)
    
    async def add_conflict(self, conflict: ClaimConflict) -> None:
        """Add conflict record."""
        self._conflicts.append(conflict)
        if len(self._conflicts) > 1000:
            self._conflicts = self._conflicts[-500:]


class VersionedTaskClaim:
    """
    Versioned task claim with self-healing.
    
    Features:
    - Version tokens to prevent duplicate claims
    - Atomic claim operations
    - Self-healing when worker fails
    - Conflict detection
    
    Guarantees:
    - No two workers can claim same task version
    - Failed claims automatically become available
    - Conflicts are detected and recorded
    """
    
    def __init__(
        self,
        claim_ttl_seconds: float = 300.0,
        renewal_interval_seconds: float = 30.0,
        max_renewals: int = 10,
    ):
        self.claim_ttl = claim_ttl_seconds
        self.renewal_interval = renewal_interval_seconds
        self.max_renewals = max_renewals
        
        self._store = VersionedTaskStore()
        self._expiry_queue: List[str] = []  # task_ids pending expiry
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
        # Conflict callbacks
        self._conflict_callbacks: List[callable] = []
    
    def register_conflict_callback(
        self,
        callback: callable,
    ) -> None:
        """Register callback for conflict events."""
        self._conflict_callbacks.append(callback)
    
    async def claim(
        self,
        task_id: str,
        worker_id: str,
        expected_version: Optional[int] = None,
    ) -> ClaimResult:
        """
        Attempt to claim a task.
        
        Args:
            task_id: Task ID
            worker_id: Worker attempting claim
            expected_version: Expected version (for atomic compare-and-swap)
            
        Returns:
            ClaimResult with success status and version
        """
        async with self._lock:
            # Get current state
            current_version = await self._store.get_version(task_id)
            existing_claim = await self._store.get_claim(task_id)
            
            # Check if version matches
            if expected_version is not None and current_version != expected_version:
                # Version conflict
                conflict = ClaimConflict(
                    task_id=task_id,
                    expected_version=expected_version,
                    actual_version=current_version,
                    conflicting_worker=existing_claim.worker_id if existing_claim else "unknown",
                    timestamp=datetime.now(),
                )
                await self._store.add_conflict(conflict)
                
                # Notify callbacks
                for cb in self._conflict_callbacks:
                    try:
                        cb(conflict)
                    except Exception as e:
                        logger.error(f"Conflict callback error: {e}")
                
                return ClaimResult(
                    success=False,
                    version=current_version,
                    claim=None,
                    reason="VERSION_MISMATCH",
                )
            
            # Check if task is already claimed
            if existing_claim:
                if existing_claim.status == ClaimStatus.CLAIMED:
                    # Check if claim expired
                    if datetime.now() > existing_claim.expires_at:
                        # Claim expired, allow new claim
                        pass
                    else:
                        # Claim still valid
                        conflict = ClaimConflict(
                            task_id=task_id,
                            expected_version=expected_version or current_version,
                            actual_version=current_version,
                            conflicting_worker=existing_claim.worker_id,
                            timestamp=datetime.now(),
                        )
                        await self._store.add_conflict(conflict)
                        
                        return ClaimResult(
                            success=False,
                            version=current_version,
                            claim=existing_claim,
                            reason="ALREADY_CLAIMED",
                        )
            
            # Claim the task
            new_version = await self._store.increment_version(task_id)
            
            claim = TaskClaim(
                task_id=task_id,
                worker_id=worker_id,
                version=new_version,
                status=ClaimStatus.CLAIMED,
                claimed_at=datetime.now(),
                expires_at=datetime.now().timestamp() + self.claim_ttl,
            )
            
            await self._store.set_claim(claim)
            
            logger.info(f"Worker {worker_id} claimed task {task_id} v{new_version}")
            
            return ClaimResult(
                success=True,
                version=new_version,
                claim=claim,
                reason="CLAIMED",
            )
    
    async def renew(
        self,
        task_id: str,
        worker_id: str,
        version: int,
    ) -> ClaimResult:
        """
        Renew an existing claim.
        
        Only the worker that claimed the task can renew it.
        """
        async with self._lock:
            existing = await self._store.get_claim(task_id)
            
            if not existing:
                return ClaimResult(
                    success=False,
                    version=None,
                    claim=None,
                    reason="NO_CLAIM",
                )
            
            # Check ownership
            if existing.worker_id != worker_id:
                return ClaimResult(
                    success=False,
                    version=existing.version,
                    claim=existing,
                    reason="NOT_OWNER",
                )
            
            # Check version
            if existing.version != version:
                return ClaimResult(
                    success=False,
                    version=existing.version,
                    claim=existing,
                    reason="VERSION_MISMATCH",
                )
            
            # Renew claim
            existing.last_renewed_at = datetime.now()
            existing.expires_at = datetime.now().timestamp() + self.claim_ttl
            
            return ClaimResult(
                success=True,
                version=existing.version,
                claim=existing,
                reason="RENEWED",
            )
    
    async def complete(
        self,
        task_id: str,
        worker_id: str,
        version: int,
    ) -> ClaimResult:
        """
        Mark task as completed.
        
        Only the worker that claimed the task can complete it.
        """
        async with self._lock:
            existing = await self._store.get_claim(task_id)
            
            if not existing:
                return ClaimResult(
                    success=False,
                    version=None,
                    claim=None,
                    reason="NO_CLAIM",
                )
            
            # Check ownership and version
            if existing.worker_id != worker_id:
                return ClaimResult(
                    success=False,
                    version=existing.version,
                    claim=existing,
                    reason="NOT_OWNER",
                )
            
            if existing.version != version:
                return ClaimResult(
                    success=False,
                    version=existing.version,
                    claim=existing,
                    reason="VERSION_MISMATCH",
                )
            
            # Complete claim
            existing.status = ClaimStatus.COMPLETED
            await self._store.delete_claim(task_id)
            
            logger.info(f"Worker {worker_id} completed task {task_id} v{version}")
            
            return ClaimResult(
                success=True,
                version=version,
                claim=existing,
                reason="COMPLETED",
            )
    
    async def release(
        self,
        task_id: str,
        worker_id: str,
    ) -> ClaimResult:
        """Release a claim (voluntary)."""
        async with self._lock:
            existing = await self._store.get_claim(task_id)
            
            if not existing:
                return ClaimResult(
                    success=False,
                    version=None,
                    claim=None,
                    reason="NO_CLAIM",
                )
            
            if existing.worker_id != worker_id:
                return ClaimResult(
                    success=False,
                    version=existing.version,
                    claim=existing,
                    reason="NOT_OWNER",
                )
            
            existing.status = ClaimStatus.CANCELLED
            await self._store.delete_claim(task_id)
            
            return ClaimResult(
                success=True,
                version=existing.version,
                claim=existing,
                reason="RELEASED",
            )
    
    async def start(self) -> None:
        """Start expiry monitoring."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._expiry_loop())
        logger.info("Versioned task claim started")
    
    async def stop(self) -> None:
        """Stop expiry monitoring."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Versioned task claim stopped")
    
    async def _expiry_loop(self) -> None:
        """Background expiry checking loop."""
        while self._running:
            try:
                await asyncio.sleep(self.renewal_interval)
                await self._check_expiries()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Expiry loop error: {e}")
    
    async def _check_expiries(self) -> None:
        """Check and expire stale claims."""
        async with self._lock:
            now = datetime.now()
            expired = []
            
            for task_id, claim in list(self._store._claims.items()):
                if claim.expires_at < now.timestamp():
                    expired.append(task_id)
            
            for task_id in expired:
                claim = self._store._claims.get(task_id)
                if claim:
                    claim.status = ClaimStatus.EXPIRED
                    self._store._claims.pop(task_id, None)
                    logger.info(f"Task {task_id} claim expired, self-healing")
    
    async def get_claim(self, task_id: str) -> Optional[TaskClaim]:
        """Get claim status."""
        return await self._store.get_claim(task_id)
    
    async def get_conflicts(self, limit: int = 100) -> List[ClaimConflict]:
        """Get recent conflicts."""
        return self._store._conflicts[-limit:]
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get claim metrics."""
        async with self._lock:
            total_claims = len(self._store._claims)
            active = sum(
                1 for c in self._store._claims.values()
                if c.status == ClaimStatus.CLAIMED
            )
            
            return {
                "total_claims": total_claims,
                "active_claims": active,
                "total_conflicts": len(self._store._conflicts),
                "recent_conflicts": len(self._store._conflicts[-10:]),
            }
