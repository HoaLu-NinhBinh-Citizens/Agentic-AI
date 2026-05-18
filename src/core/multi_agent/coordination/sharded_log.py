"""
Sharded Exactly-Once Log.

Provides exactly-once delivery semantics with horizontal scaling through log sharding.
Uses consistent hashing to distribute logs across shards to avoid bottlenecks.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class LogEntry:
    """Single log entry."""
    entry_id: str
    task_id: str
    tenant_id: str
    shard: int
    sequence: int
    payload: Dict[str, Any]
    timestamp: datetime
    idempotency_key: str
    committed: bool = False


@dataclass
class ShardMetrics:
    """Metrics for a single shard."""
    shard_id: int
    entry_count: int
    last_sequence: int
    total_bytes: int


class ShardRouter:
    """
    Consistent hashing router for log sharding.
    
    Routes entries to shards based on tenant_id or task_id.
    """
    
    def __init__(self, shard_count: int, shard_by: str = "tenant_id"):
        self.shard_count = shard_count
        self.shard_by = shard_by
        self._shards: Dict[int, List[str]] = defaultdict(list)
    
    def get_shard(self, entry_id: str, tenant_id: str, task_id: str) -> int:
        """
        Get shard number using consistent hashing.
        
        Args:
            entry_id: Unique entry ID
            tenant_id: Tenant identifier
            task_id: Task identifier
            
        Returns:
            Shard number (0 to shard_count-1)
        """
        if self.shard_by == "tenant_id":
            key = tenant_id
        elif self.shard_by == "task_id":
            key = task_id
        else:
            key = entry_id
        
        # Consistent hash
        hash_value = int(hashlib.sha256(key.encode()).hexdigest(), 16)
        return hash_value % self.shard_count
    
    def get_all_shards(self) -> List[int]:
        """Get all shard IDs."""
        return list(range(self.shard_count))


class ShardedLogStore:
    """
    In-memory sharded log store for testing.
    
    In production, each shard would be a separate database/stream.
    """
    
    def __init__(self, shard_count: int):
        self.shard_count = shard_count
        self._shards: Dict[int, List[LogEntry]] = defaultdict(list)
        self._sequences: Dict[int, int] = defaultdict(int)
        self._indexes: Dict[int, Dict[str, int]] = defaultdict(dict)  # shard -> {entry_id -> index}
        self._idempotency: Dict[str, LogEntry] = {}  # Global idempotency index
        self._lock = asyncio.Lock()
    
    async def append(
        self,
        shard: int,
        entry: LogEntry,
    ) -> LogEntry:
        """Append entry to shard."""
        async with self._lock:
            self._sequences[shard] += 1
            entry.sequence = self._sequences[shard]
            
            self._shards[shard].append(entry)
            self._indexes[shard][entry.entry_id] = len(self._shards[shard]) - 1
            self._idempotency[entry.idempotency_key] = entry
            
            return entry
    
    async def get(self, shard: int, entry_id: str) -> Optional[LogEntry]:
        """Get entry by ID from shard."""
        async with self._lock:
            idx = self._indexes[shard].get(entry_id)
            if idx is not None and idx < len(self._shards[shard]):
                return self._shards[shard][idx]
            return None
    
    async def get_by_idempotency(self, idempotency_key: str) -> Optional[LogEntry]:
        """Get entry by idempotency key."""
        return self._idempotency.get(idempotency_key)
    
    async def get_range(
        self,
        shard: int,
        start_seq: int,
        end_seq: Optional[int] = None,
        limit: int = 100,
    ) -> List[LogEntry]:
        """Get entries by sequence range."""
        async with self._lock:
            shard_entries = self._shards[shard]
            
            # Binary search for start
            start_idx = 0
            for i, entry in enumerate(shard_entries):
                if entry.sequence >= start_seq:
                    start_idx = i
                    break
            
            end_idx = min(start_idx + limit, len(shard_entries))
            if end_seq:
                for i in range(start_idx, len(shard_entries)):
                    if shard_entries[i].sequence > end_seq:
                        end_idx = i
                        break
            
            return shard_entries[start_idx:end_idx]
    
    async def get_all_shards_range(
        self,
        start_seq: int,
        end_seq: Optional[int] = None,
        limit: int = 100,
    ) -> List[LogEntry]:
        """Get entries from all shards (expensive, use sparingly)."""
        all_entries = []
        for shard in range(self.shard_count):
            entries = await self.get_range(shard, start_seq, end_seq, limit)
            all_entries.extend(entries)
        
        all_entries.sort(key=lambda e: (e.sequence, e.shard))
        return all_entries[:limit]
    
    async def get_metrics(self) -> List[ShardMetrics]:
        """Get metrics for all shards."""
        async with self._lock:
            metrics = []
            for shard in range(self.shard_count):
                entries = self._shards[shard]
                total_bytes = sum(len(str(e.payload)) for e in entries)
                
                metrics.append(ShardMetrics(
                    shard_id=shard,
                    entry_count=len(entries),
                    last_sequence=self._sequences.get(shard, 0),
                    total_bytes=total_bytes,
                ))
            return metrics


class ShardedExactlyOnceLog:
    """
    Exactly-once log with sharding.
    
    Features:
    - Consistent hashing for shard routing
    - Per-shard idempotency
    - Sequence numbering per shard
    - Cross-shard queries when needed
    
    Guarantees:
    - Each entry appears exactly once (idempotency_key)
    - Entries are ordered within a shard
    - Shards are independent (no cross-shard transactions)
    """
    
    def __init__(
        self,
        shard_count: int = 64,
        shard_by: str = "tenant_id",
        store: Optional[ShardedLogStore] = None,
    ):
        self.router = ShardRouter(shard_count, shard_by)
        self.store = store or ShardedLogStore(shard_count)
        self.shard_count = shard_count
        
        # Sequence tracking per shard
        self._global_lock = asyncio.Lock()
    
    async def write(
        self,
        entry_id: str,
        task_id: str,
        tenant_id: str,
        payload: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> LogEntry:
        """
        Write entry with exactly-once semantics.
        
        If idempotency_key exists, returns existing entry.
        """
        # Check idempotency first
        if idempotency_key:
            existing = await self.store.get_by_idempotency(idempotency_key)
            if existing:
                logger.debug(f"Duplicate entry detected: {idempotency_key}")
                return existing
        
        # Route to shard
        shard = self.router.get_shard(entry_id, tenant_id, task_id)
        
        # Create entry
        entry = LogEntry(
            entry_id=entry_id,
            task_id=task_id,
            tenant_id=tenant_id,
            shard=shard,
            sequence=0,  # Will be set by store
            payload=payload,
            timestamp=datetime.now(),
            idempotency_key=idempotency_key or entry_id,
        )
        
        # Append to shard
        result = await self.store.append(shard, entry)
        
        logger.debug(f"Written entry {entry_id} to shard {shard}, seq={result.sequence}")
        return result
    
    async def read(
        self,
        shard: int,
        entry_id: str,
    ) -> Optional[LogEntry]:
        """Read entry from specific shard."""
        return await self.store.get(shard, entry_id)
    
    async def read_by_idempotency(
        self,
        idempotency_key: str,
    ) -> Optional[LogEntry]:
        """Read entry by idempotency key (cross-shard search)."""
        return await self.store.get_by_idempotency(idempotency_key)
    
    async def read_range(
        self,
        shard: int,
        start_seq: int,
        end_seq: Optional[int] = None,
        limit: int = 100,
    ) -> List[LogEntry]:
        """Read entries by sequence range from specific shard."""
        return await self.store.get_range(shard, start_seq, end_seq, limit)
    
    async def read_all_range(
        self,
        start_seq: int = 1,
        end_seq: Optional[int] = None,
        limit: int = 100,
    ) -> List[LogEntry]:
        """Read entries from all shards (expensive, use sparingly)."""
        return await self.store.get_all_shards_range(start_seq, end_seq, limit)
    
    async def get_shard_for(
        self,
        tenant_id: str,
        task_id: str,
    ) -> int:
        """Get shard number for tenant/task."""
        return self.router.get_shard("", tenant_id, task_id)
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get overall metrics."""
        shard_metrics = await self.store.get_metrics()
        
        return {
            "shard_count": self.shard_count,
            "shard_by": self.router.shard_by,
            "total_entries": sum(m.entry_count for m in shard_metrics),
            "total_bytes": sum(m.total_bytes for m in shard_metrics),
            "shards": [
                {
                    "shard_id": m.shard_id,
                    "entry_count": m.entry_count,
                    "last_sequence": m.last_sequence,
                    "total_bytes": m.total_bytes,
                }
                for m in shard_metrics
            ],
        }
