"""Exactly-once side effects via idempotency - Phase 5B v10.

Ensures exactly-once semantics for activities:
- Idempotency key generation
- Side effect registry
- Result caching for replay
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional, Callable
from enum import Enum


class IdempotencyStatus(Enum):
    """Status of an idempotency record."""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IdempotencyRecord:
    """Record of an idempotent operation."""
    idempotency_key: str
    workflow_id: str
    activity_id: str
    status: IdempotencyStatus
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: int = field(default_factory=lambda: int(time.time()))
    completed_at: Optional[int] = None
    ttl_hours: int = 168


class IdempotencyStore:
    """Store interface for idempotency records."""
    
    async def get(self, key: str) -> Optional[IdempotencyRecord]:
        """Get idempotency record by key."""
        raise NotImplementedError
    
    async def save(self, record: IdempotencyRecord) -> None:
        """Save idempotency record."""
        raise NotImplementedError
    
    async def update_result(
        self,
        key: str,
        status: IdempotencyStatus,
        result: Optional[Any] = None,
        error: Optional[str] = None,
    ) -> bool:
        """Update result of idempotent operation."""
        raise NotImplementedError
    
    async def cleanup_expired(self) -> int:
        """Clean up expired records."""
        raise NotImplementedError


class InMemoryIdempotencyStore(IdempotencyStore):
    """In-memory implementation of idempotency store."""
    
    def __init__(self):
        self._records: dict[str, IdempotencyRecord] = {}
    
    async def get(self, key: str) -> Optional[IdempotencyRecord]:
        return self._records.get(key)
    
    async def save(self, record: IdempotencyRecord) -> None:
        self._records[record.idempotency_key] = record
    
    async def update_result(
        self,
        key: str,
        status: IdempotencyStatus,
        result: Optional[Any] = None,
        error: Optional[str] = None,
    ) -> bool:
        record = self._records.get(key)
        if not record:
            return False
        
        record.status = status
        record.result = result
        record.error = error
        record.completed_at = int(time.time())
        return True
    
    async def cleanup_expired(self) -> int:
        now = int(time.time())
        expired = []
        
        for key, record in self._records.items():
            age_hours = (now - record.created_at) / 3600
            if age_hours > record.ttl_hours:
                expired.append(key)
        
        for key in expired:
            del self._records[key]
        
        return len(expired)


class IdempotencyKeyGenerator:
    """Generates idempotency keys for activities.
    
    Key format: {workflow_id}:{step_id}:{attempt}
    Hash ensures consistent key generation.
    """
    
    @staticmethod
    def generate(
        workflow_id: str,
        step_id: str,
        attempt: int = 1,
    ) -> str:
        """Generate idempotency key.
        
        Args:
            workflow_id: Workflow identifier
            step_id: Step/activity identifier
            attempt: Attempt number
            
        Returns:
            Idempotency key string
        """
        return f"{workflow_id}:{step_id}:{attempt}"
    
    @staticmethod
    def parse(key: str) -> tuple[str, str, int]:
        """Parse idempotency key.
        
        Args:
            key: Idempotency key
            
        Returns:
            Tuple of (workflow_id, step_id, attempt)
        """
        parts = key.split(":")
        if len(parts) != 3:
            raise ValueError(f"Invalid idempotency key: {key}")
        
        return parts[0], parts[1], int(parts[2])


class SideEffectRegistry:
    """Registry for side effects to ensure exactly-once semantics.
    
    Records side effects and their results, returning cached
    results during replay.
    """
    
    def __init__(self, store: IdempotencyStore):
        self._store = store
    
    async def check_executed(
        self,
        idempotency_key: str,
    ) -> tuple[bool, Optional[Any], Optional[str]]:
        """Check if side effect was already executed.
        
        Args:
            idempotency_key: Unique key for the side effect
            
        Returns:
            Tuple of (was_executed, result, error)
        """
        record = await self._store.get(idempotency_key)
        
        if record is None:
            return False, None, None
        
        if record.status == IdempotencyStatus.COMPLETED:
            return True, record.result, None
        
        if record.status == IdempotencyStatus.FAILED:
            return True, None, record.error
        
        return False, None, None
    
    async def register_execution(
        self,
        idempotency_key: str,
        workflow_id: str,
        activity_id: str,
    ) -> None:
        """Register that execution is starting.
        
        Args:
            idempotency_key: Unique key for the side effect
            workflow_id: Workflow identifier
            activity_id: Activity identifier
        """
        record = IdempotencyRecord(
            idempotency_key=idempotency_key,
            workflow_id=workflow_id,
            activity_id=activity_id,
            status=IdempotencyStatus.PENDING,
        )
        await self._store.save(record)
    
    async def record_success(
        self,
        idempotency_key: str,
        result: Any,
    ) -> None:
        """Record successful execution.
        
        Args:
            idempotency_key: Unique key for the side effect
            result: Execution result
        """
        await self._store.update_result(
            idempotency_key,
            IdempotencyStatus.COMPLETED,
            result=result,
        )
    
    async def record_failure(
        self,
        idempotency_key: str,
        error: str,
    ) -> None:
        """Record failed execution.
        
        Args:
            idempotency_key: Unique key for the side effect
            error: Error message
        """
        await self._store.update_result(
            idempotency_key,
            IdempotencyStatus.FAILED,
            error=error,
        )


class ExactlyOnceActivityExecutor:
    """Executor that ensures exactly-once activity execution.
    
    Wraps activity execution with idempotency checks:
    1. Check if already executed (return cached result)
    2. Register execution
    3. Execute activity
    4. Record result
    """
    
    def __init__(
        self,
        registry: SideEffectRegistry,
        key_generator: Optional[IdempotencyKeyGenerator] = None,
    ):
        self._registry = registry
        self._key_generator = key_generator or IdempotencyKeyGenerator()
    
    async def execute(
        self,
        activity_fn: Callable,
        workflow_id: str,
        step_id: str,
        input: dict,
        attempt: int = 1,
    ) -> Any:
        """Execute activity with exactly-once guarantee.
        
        Args:
            activity_fn: Activity function to execute
            workflow_id: Workflow identifier
            step_id: Step identifier
            input: Activity input
            attempt: Attempt number
            
        Returns:
            Activity result
        """
        key = self._key_generator.generate(workflow_id, step_id, attempt)
        
        was_executed, cached_result, cached_error = await self._registry.check_executed(key)
        
        if was_executed:
            if cached_error:
                raise Exception(cached_error)
            return cached_result
        
        await self._registry.register_execution(key, workflow_id, f"{step_id}_{attempt}")
        
        try:
            result = await activity_fn(input)
            await self._registry.record_success(key, result)
            return result
        except Exception as e:
            await self._registry.record_failure(key, str(e))
            raise
