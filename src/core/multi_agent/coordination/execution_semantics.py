"""
Formal Execution Semantics for Distributed Systems.

Defines formal guarantees:
- internal_state = EXACTLY_ONCE
- external_effects = IDEMPOTENT_REQUIRED

This addresses the fundamental limitation that true end-to-end exactly-once
is impossible in distributed systems with external side effects.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import secrets

logger = logging.getLogger(__name__)


class ExecutionSemantics(str, Enum):
    """
    Formal execution semantics.
    
    Internal state: EXACTLY_ONCE - State is updated exactly once
    External effects: IDEMPOTENT_REQUIRED - External calls must be idempotent
    """
    EXACTLY_ONCE_INTERNAL = "exactly_once_internal"
    AT_LEAST_ONCE = "at_least_once"
    AT_MOST_ONCE = "at_most_once"
    IDEMPOTENT = "idempotent"


@dataclass
class ExecutionContext:
    """Context for a single execution attempt."""
    execution_id: str
    task_id: str
    idempotency_key: str
    semantics: ExecutionSemantics
    started_at: datetime
    attempt: int = 1
    lease_token: Optional[str] = None
    lineage: List[str] = field(default_factory=list)  # Execution lineage


@dataclass
class IdempotencyRecord:
    """Record for idempotency tracking."""
    idempotency_key: str
    execution_id: str
    status: str  # pending, completed, failed
    created_at: datetime
    result_hash: Optional[str] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    external_calls: List[str] = field(default_factory=list)


class IdempotencyKeyManager:
    """
    Manages idempotency keys for external effects.
    
    Key insight: External side effects (API calls, payments, etc.) cannot be
    made exactly-once. They can only be made idempotent.
    
    Strategy:
    1. Generate deterministic idempotency key from execution context
    2. Check if key was already processed
    3. If yes, return cached result
    4. If no, execute and cache result
    5. External systems must respect idempotency keys
    """
    
    def __init__(
        self,
        ttl_seconds: float = 86400 * 7,  # 7 days
        max_results: int = 100000,
    ):
        self.ttl = ttl_seconds
        self.max_results = max_results
        
        self._records: Dict[str, IdempotencyRecord] = {}
        self._lock = asyncio.Lock()
    
    async def generate_key(
        self,
        task_id: str,
        action: str,
        params: Dict[str, Any],
    ) -> str:
        """
        Generate deterministic idempotency key.
        
        Key is deterministic so same input always produces same key.
        """
        # Sort params for deterministic output
        sorted_params = sorted(params.items())
        param_str = "|".join(f"{k}={v}" for k, v in sorted_params)
        
        raw = f"{task_id}:{action}:{param_str}"
        key_hash = hashlib.sha256(raw.encode()).hexdigest()[:32]
        
        return f"idempotent_{action}_{key_hash}"
    
    async def check_and_reserve(
        self,
        idempotency_key: str,
        execution_id: str,
    ) -> tuple[bool, Optional[IdempotencyRecord]]:
        """
        Check if key exists and reserve for execution.
        
        Returns (should_execute, existing_record)
        """
        async with self._lock:
            if idempotency_key in self._records:
                record = self._records[idempotency_key]
                
                if record.status == "completed":
                    # Already executed successfully
                    return False, record
                elif record.status == "pending":
                    # Another execution in progress
                    return False, None
                else:
                    # Failed, allow retry
                    record.execution_id = execution_id
                    record.retry_count += 1
                    return True, record
            
            # New execution
            record = IdempotencyRecord(
                idempotency_key=idempotency_key,
                execution_id=execution_id,
                status="pending",
                created_at=datetime.now(),
            )
            self._records[idempotency_key] = record
            return True, None
    
    async def mark_completed(
        self,
        idempotency_key: str,
        result: Any,
        external_calls: Optional[List[str]] = None,
    ) -> None:
        """Mark execution as completed."""
        async with self._lock:
            if idempotency_key in self._records:
                record = self._records[idempotency_key]
                record.status = "completed"
                record.completed_at = datetime.now()
                record.result_hash = hashlib.sha256(
                    str(result).encode()
                ).hexdigest()
                if external_calls:
                    record.external_calls = external_calls
    
    async def mark_failed(
        self,
        idempotency_key: str,
        error: str,
    ) -> None:
        """Mark execution as failed."""
        async with self._lock:
            if idempotency_key in self._records:
                record = self._records[idempotency_key]
                record.status = f"failed: {error}"


class GlobalExecutionLease:
    """
    Global execution lease to prevent ghost execution.
    
    Addresses the classic problem:
    - Worker A starts execution
    - Region A times out (but execution still running)
    - Worker B picks up task (ghost execution)
    - Both A and B complete -> duplicated effect
    
    Solution: Global lease that must be held for execution to proceed.
    """
    
    def __init__(
        self,
        lease_ttl_seconds: float = 60.0,
        heartbeat_interval: float = 5.0,
    ):
        self.lease_ttl = lease_ttl_seconds
        self.heartbeat_interval = heartbeat_interval
        
        self._leases: Dict[str, Dict[str, Any]] = {}  # task_id -> lease info
        self._lock = asyncio.Lock()
        self._running_tasks: Dict[str, asyncio.Task] = {}
    
    async def acquire(
        self,
        task_id: str,
        worker_id: str,
        execution_id: str,
    ) -> tuple[bool, Optional[str]]:
        """
        Attempt to acquire execution lease.
        
        Returns (acquired, lease_token)
        """
        async with self._lock:
            now = datetime.now()
            
            # Check existing lease
            if task_id in self._leases:
                lease = self._leases[task_id]
                expires_at = lease["expires_at"]
                
                # Lease still valid
                if now.timestamp() < expires_at:
                    # Check if same worker (allow renewal)
                    if lease["worker_id"] == worker_id:
                        # Extend lease
                        lease["expires_at"] = now.timestamp() + self.lease_ttl
                        lease["execution_id"] = execution_id
                        return True, lease["token"]
                    else:
                        # Different worker, cannot acquire
                        return False, None
                else:
                    # Lease expired, can acquire
                    pass
            
            # Acquire new lease
            token = secrets.token_hex(32)
            self._leases[task_id] = {
                "worker_id": worker_id,
                "execution_id": execution_id,
                "token": token,
                "acquired_at": now,
                "expires_at": now.timestamp() + self.lease_ttl,
                "last_heartbeat": now,
            }
            
            return True, token
    
    async def release(
        self,
        task_id: str,
        worker_id: str,
        token: str,
    ) -> bool:
        """Release execution lease."""
        async with self._lock:
            if task_id not in self._leases:
                return True
            
            lease = self._leases[task_id]
            
            # Verify ownership
            if lease["worker_id"] != worker_id:
                return False
            if lease["token"] != token:
                return False
            
            del self._leases[task_id]
            return True
    
    async def validate(
        self,
        task_id: str,
        worker_id: str,
        token: str,
    ) -> tuple[bool, str]:
        """
        Validate lease is still valid.
        
        Returns (valid, reason)
        """
        async with self._lock:
            if task_id not in self._leases:
                return False, "NO_LEASE"
            
            lease = self._leases[task_id]
            now = datetime.now()
            
            # Check expiration
            if now.timestamp() > lease["expires_at"]:
                return False, "LEASE_EXPIRED"
            
            # Check ownership
            if lease["worker_id"] != worker_id:
                return False, "WRONG_WORKER"
            
            if lease["token"] != token:
                return False, "INVALID_TOKEN"
            
            return True, "VALID"
    
    async def heartbeat(
        self,
        task_id: str,
        worker_id: str,
        token: str,
    ) -> bool:
        """Renew lease via heartbeat."""
        async with self._lock:
            valid, _ = await self.validate(task_id, worker_id, token)
            if not valid:
                return False
            
            self._leases[task_id]["last_heartbeat"] = datetime.now()
            self._leases[task_id]["expires_at"] = (
                datetime.now().timestamp() + self.lease_ttl
            )
            return True
    
    async def revoke(
        self,
        task_id: str,
        reason: str = "MANUAL_REVOCATION",
    ) -> bool:
        """Revoke lease (admin action)."""
        async with self._lock:
            if task_id in self._leases:
                lease = self._leases.pop(task_id)
                logger.warning(f"Lease revoked for {task_id}: {reason}")
                return True
            return False


class ExecutionOwnershipRegistry:
    """
    Registry tracking which execution owns each task.
    
    Provides global view of task ownership for preventing conflicts.
    """
    
    def __init__(self):
        self._ownership: Dict[str, Dict[str, Any]] = {}
        self._history: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
    
    async def claim(
        self,
        task_id: str,
        execution_id: str,
        worker_id: str,
        region: str,
        lease_token: str,
    ) -> tuple[bool, Optional[Dict[str, Any]]]:
        """
        Claim ownership of task.
        
        Returns (claimed, previous_owner)
        """
        async with self._lock:
            now = datetime.now()
            
            # Check existing ownership
            if task_id in self._ownership:
                current = self._ownership[task_id]
                
                # Same execution - allow
                if current["execution_id"] == execution_id:
                    return True, None
                
                # Different execution - check if expired
                if now.timestamp() < current["expires_at"]:
                    # Still owned
                    return False, current
                
                # Expired - record handover
                self._history.append({
                    "task_id": task_id,
                    "from_execution": current["execution_id"],
                    "from_worker": current["worker_id"],
                    "to_execution": execution_id,
                    "to_worker": worker_id,
                    "timestamp": now,
                    "reason": "LEASE_EXPIRED",
                })
            
            # Claim ownership
            self._ownership[task_id] = {
                "execution_id": execution_id,
                "worker_id": worker_id,
                "region": region,
                "lease_token": lease_token,
                "claimed_at": now,
                "expires_at": now.timestamp() + 300,  # 5 minutes
            }
            
            return True, None
    
    async def release(
        self,
        task_id: str,
        execution_id: str,
    ) -> bool:
        """Release ownership."""
        async with self._lock:
            if task_id not in self._ownership:
                return True
            
            current = self._ownership[task_id]
            if current["execution_id"] != execution_id:
                return False
            
            del self._ownership[task_id]
            return True
    
    async def get_owner(
        self,
        task_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get current owner."""
        async with self._lock:
            return self._ownership.get(task_id)
    
    async def get_ownership_history(
        self,
        task_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get ownership history for task."""
        async with self._lock:
            return [
                h for h in self._history
                if h["task_id"] == task_id
            ][-limit:]


class FormalExecutionEngine:
    """
    Formal execution engine with proper semantics.
    
    Guarantees:
    - Internal state: EXACTLY_ONCE
    - External effects: IDEMPOTENT_REQUIRED
    
    This is the formal layer that coordinates:
    - Idempotency key management
    - Execution lease
    - Ownership registry
    """
    
    def __init__(
        self,
        idempotency_manager: Optional[IdempotencyKeyManager] = None,
        execution_lease: Optional[GlobalExecutionLease] = None,
        ownership_registry: Optional[ExecutionOwnershipRegistry] = None,
    ):
        self.idempotency = idempotency_manager or IdempotencyKeyManager()
        self.lease = execution_lease or GlobalExecutionLease()
        self.ownership = ownership_registry or ExecutionOwnershipRegistry()
    
    async def execute_with_semantics(
        self,
        task_id: str,
        action: str,
        params: Dict[str, Any],
        worker_id: str,
        region: str,
        external_effect_handler: Callable,
    ) -> tuple[bool, Any, str]:
        """
        Execute with formal semantics.
        
        Flow:
        1. Generate idempotency key
        2. Check idempotency (may return cached result)
        3. Acquire global execution lease
        4. Claim ownership
        5. Execute (with idempotent external calls)
        6. Release ownership and lease
        
        Returns (executed, result, status)
        """
        import uuid
        
        execution_id = str(uuid.uuid4())
        
        # Step 1: Generate idempotency key
        idempotency_key = await self.idempotency.generate_key(
            task_id, action, params
        )
        
        # Step 2: Check idempotency
        should_execute, existing = await self.idempotency.check_and_reserve(
            idempotency_key, execution_id
        )
        
        if not should_execute and existing:
            if existing.status == "completed":
                return False, None, "IDEMPOTENT_HIT"
            else:
                return False, None, "CONCURRENT_EXECUTION"
        
        # Step 3: Acquire execution lease
        acquired, lease_token = await self.lease.acquire(
            task_id, worker_id, execution_id
        )
        
        if not acquired:
            await self.idempotency.mark_failed(
                idempotency_key, "LEASE_CONFLICT"
            )
            return False, None, "LEASE_CONFLICT"
        
        try:
            # Step 4: Claim ownership
            claimed, prev_owner = await self.ownership.claim(
                task_id, execution_id, worker_id, region, lease_token
            )
            
            if not claimed:
                await self.idempotency.mark_failed(
                    idempotency_key, "OWNERSHIP_CONFLICT"
                )
                return False, None, "OWNERSHIP_CONFLICT"
            
            # Step 5: Execute with external effects
            result = await external_effect_handler(
                idempotency_key=idempotency_key,
                params=params,
            )
            
            # Step 6: Mark completed
            await self.idempotency.mark_completed(
                idempotency_key, result
            )
            
            return True, result, "COMPLETED"
            
        except Exception as e:
            await self.idempotency.mark_failed(idempotency_key, str(e))
            return False, None, f"EXECUTION_ERROR: {e}"
            
        finally:
            # Always release resources
            await self.ownership.release(task_id, execution_id)
            await self.lease.release(task_id, worker_id, lease_token)
