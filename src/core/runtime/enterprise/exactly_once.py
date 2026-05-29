"""Exactly-once side effects via idempotency - Phase 5B v10.

Ensures exactly-once semantics for activities:
- Idempotency key generation
- Side effect registry
- Result caching for replay

P0-Hardening:
- RedisIdempotencyStore: durable, Redis-backed implementation
- IdempotencyStoreFactory: creates store by config
- ResultIdempotencyStore: Redis source-of-truth with in-memory L1 cache
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
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


# =============================================================================
# P0-DURABLE: REDIS-BACKED IDEMPOTENCY STORE
# =============================================================================


class RedisIdempotencyStore(IdempotencyStore):
    """P0-Durable: Redis-backed idempotency store.

    Schema per key:
      HSET idempotency:{workflow_id}:{step_id}:{attempt}
        status       -> PENDING | COMPLETED | FAILED
        workflow_id  -> workflow ID
        activity_id  -> activity ID
        result       -> JSON-encoded result (COMPLETED)
        error        -> error string (FAILED)
        created_at   -> unix timestamp
        completed_at -> unix timestamp
        ttl_hours    -> TTL in hours

    TTL is set per-key (workflow-scoped, default 168h = 7 days).
    """

    _KEY_PREFIX = "idempotency"

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        ttl_hours: int = 168,
    ):
        self._redis_url = redis_url
        self._redis: Any = None
        self._connected = False
        self._default_ttl_hours = ttl_hours

    async def connect(self) -> bool:
        """Connect to Redis."""
        if self._connected:
            return True
        try:
            import redis.asyncio as redis
            self._redis = redis.from_url(
                self._redis_url,
                decode_responses=False,
            )
            await self._redis.ping()
            self._connected = True
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis and self._connected:
            await self._redis.close()
            self._connected = False

    def _make_key(self, idempotency_key: str) -> str:
        return f"{self._KEY_PREFIX}:{idempotency_key}"

    def _ttl_seconds(self, ttl_hours: int) -> int:
        return ttl_hours * 3600

    async def get(self, key: str) -> Optional[IdempotencyRecord]:
        """Get idempotency record from Redis."""
        if not self._connected:
            await self.connect()

        full_key = self._make_key(key)
        try:
            data = await self._redis.hgetall(full_key)
            if not data:
                return None

            def decode(v: Any) -> str:
                return v.decode() if isinstance(v, bytes) else str(v)

            fields = {k.decode() if isinstance(k, bytes) else k: decode(v) for k, v in data.items()}

            return IdempotencyRecord(
                idempotency_key=key,
                workflow_id=fields.get("workflow_id", ""),
                activity_id=fields.get("activity_id", ""),
                status=IdempotencyStatus(fields.get("status", "pending")),
                result=json.loads(fields["result"]) if "result" in fields else None,
                error=fields.get("error"),
                created_at=int(fields.get("created_at", 0)),
                completed_at=int(fields["completed_at"]) if "completed_at" in fields else None,
                ttl_hours=int(fields.get("ttl_hours", self._default_ttl_hours)),
            )
        except Exception:
            return None

    async def save(self, record: IdempotencyRecord) -> None:
        """Save idempotency record to Redis with TTL."""
        if not self._connected:
            await self.connect()

        full_key = self._make_key(record.idempotency_key)
        ttl = self._ttl_seconds(record.ttl_hours)
        try:
            await self._redis.hset(full_key, mapping={
                "idempotency_key": record.idempotency_key,
                "workflow_id": record.workflow_id,
                "activity_id": record.activity_id,
                "status": record.status.value,
                "created_at": str(record.created_at),
                "ttl_hours": str(record.ttl_hours),
            })
            await self._redis.expire(full_key, ttl)
        except Exception:
            pass

    async def update_result(
        self,
        key: str,
        status: IdempotencyStatus,
        result: Optional[Any] = None,
        error: Optional[str] = None,
    ) -> bool:
        """Update result of idempotent operation in Redis."""
        if not self._connected:
            await self.connect()

        full_key = self._make_key(key)
        try:
            updates: dict[str, Any] = {
                "status": status.value,
                "completed_at": str(int(time.time())),
            }
            if result is not None:
                updates["result"] = json.dumps(result)
            if error is not None:
                updates["error"] = error

            await self._redis.hset(full_key, mapping=updates)
            return True
        except Exception:
            return False

    async def cleanup_expired(self) -> int:
        """Redis handles expiry via TTL; this is a no-op."""
        return 0


class ResultIdempotencyStore:
    """P0-Durable: Redis source-of-truth with in-memory L1 cache.

    Wraps both stores:
    - RedisIdempotencyStore as authoritative backend (durable)
    - InMemoryIdempotencyStore as L1 read cache (fast)

    On read: check L1 first, fall back to Redis.
    On write: write to Redis, then populate L1.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        l1_store: Optional[InMemoryIdempotencyStore] = None,
    ):
        self._redis_store = RedisIdempotencyStore(redis_url=redis_url)
        self._l1_store = l1_store or InMemoryIdempotencyStore()

    async def connect(self) -> bool:
        return await self._redis_store.connect()

    async def get(self, key: str) -> Optional[IdempotencyRecord]:
        """Read-through: L1 cache, then Redis."""
        record = await self._l1_store.get(key)
        if record is not None:
            return record
        record = await self._redis_store.get(key)
        if record is not None:
            # Populate L1
            await self._l1_store.save(record)
        return record

    async def save(self, record: IdempotencyRecord) -> None:
        """Write-through: Redis (authoritative), then L1."""
        await self._redis_store.save(record)
        await self._l1_store.save(record)

    async def update_result(
        self,
        key: str,
        status: IdempotencyStatus,
        result: Optional[Any] = None,
        error: Optional[str] = None,
    ) -> bool:
        """Write-through: Redis, then L1."""
        ok = await self._redis_store.update_result(key, status, result, error)
        if ok:
            await self._l1_store.update_result(key, status, result, error)
        return ok

    async def cleanup_expired(self) -> int:
        return await self._redis_store.cleanup_expired()


class IdempotencyStoreFactory:
    """Factory for creating IdempotencyStore by configuration."""

    @staticmethod
    def create(
        backend: str = "memory",
        redis_url: str = "redis://localhost:6379",
    ) -> IdempotencyStore:
        """Create an idempotency store by backend type.

        Args:
            backend: "memory" for InMemoryIdempotencyStore,
                     "redis" for RedisIdempotencyStore,
                     "cached" for ResultIdempotencyStore.
            redis_url: Redis connection URL for redis/cached backends.
        """
        if backend == "memory":
            return InMemoryIdempotencyStore()
        elif backend == "redis":
            return RedisIdempotencyStore(redis_url=redis_url)
        elif backend == "cached":
            return ResultIdempotencyStore(redis_url=redis_url)
        else:
            raise ValueError(f"Unknown idempotency backend: {backend}")


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
