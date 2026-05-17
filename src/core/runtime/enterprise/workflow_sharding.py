"""Workflow sharding and partitioning - Phase 5B v10.

Implements workflow sharding for horizontal scaling:
- ConsistentHashRing: Consistent hashing for shard assignment
- WorkflowPartitioner: Partitions workflows across shards
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Shard:
    """A database or processing shard."""
    shard_id: str
    node_id: str
    tenant_ids: list[str] = field(default_factory=list)
    workflow_count: int = 0
    is_active: bool = True


@dataclass
class PartitionKey:
    """Key for workflow partitioning."""
    tenant_id: str
    shard_id: str
    
    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.shard_id}"
    
    @classmethod
    def from_string(cls, key: str) -> PartitionKey:
        """Parse a partition key string."""
        parts = key.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid partition key: {key}")
        return cls(parts[0], parts[1])


class ConsistentHashRing:
    """Consistent hash ring for shard assignment.
    
    Provides:
    - Consistent hashing for even distribution
    - Minimal redistribution when nodes join/leave
    - Virtual nodes for better load balancing
    """
    
    def __init__(
        self,
        num_virtual_nodes: int = 100,
    ):
        self._num_virtual = num_virtual_nodes
        self._ring: dict[int, str] = {}
        self._sorted_keys: list[int] = []
        self._shards: dict[str, Shard] = {}
    
    def add_shard(self, shard: Shard) -> None:
        """Add a shard to the ring.
        
        Args:
            shard: Shard to add
        """
        self._shards[shard.shard_id] = shard
        
        for i in range(self._num_virtual):
            key = self._hash(f"{shard.shard_id}:vn{i}")
            self._ring[key] = shard.shard_id
        
        self._sorted_keys = sorted(self._ring.keys())
    
    def remove_shard(self, shard_id: str) -> None:
        """Remove a shard from the ring.
        
        Args:
            shard_id: Shard to remove
        """
        if shard_id not in self._shards:
            return
        
        del self._shards[shard_id]
        
        keys_to_remove = [
            k for k, v in self._ring.items()
            if v == shard_id
        ]
        for key in keys_to_remove:
            del self._ring[key]
        
        self._sorted_keys = sorted(self._ring.keys())
    
    def get_shard(self, key: str) -> Optional[Shard]:
        """Get the shard for a given key.
        
        Args:
            key: Key to hash
            
        Returns:
            Shard that owns the key, or None if ring is empty
        """
        if not self._sorted_keys:
            return None
        
        hash_value = self._hash(key)
        
        for ring_key in self._sorted_keys:
            if ring_key >= hash_value:
                shard_id = self._ring[ring_key]
                return self._shards.get(shard_id)
        
        first_key = self._sorted_keys[0]
        shard_id = self._ring[first_key]
        return self._shards.get(shard_id)
    
    def get_shard_id(self, key: str) -> Optional[str]:
        """Get the shard ID for a given key.
        
        Args:
            key: Key to hash
            
        Returns:
            Shard ID that owns the key
        """
        shard = self.get_shard(key)
        return shard.shard_id if shard else None
    
    def _hash(self, key: str) -> int:
        """Hash a key to a position on the ring."""
        return int(hashlib.sha256(key.encode()).hexdigest()[:16], 16)
    
    def get_all_shards(self) -> list[Shard]:
        """Get all shards in the ring."""
        return list(self._shards.values())
    
    def get_shard_count(self) -> int:
        """Get number of physical shards."""
        return len(self._shards)
    
    def rebalance(self) -> dict[str, list[str]]:
        """Calculate rebalancing plan when adding/removing shards.
        
        Returns:
            Dict mapping shard_id to list of keys to move
        """
        moves = {shard_id: [] for shard_id in self._shards}
        
        for shard_id in self._shards:
            moves[shard_id] = []
        
        return moves


class WorkflowPartitioner:
    """Partitions workflows across database shards.
    
    Uses consistent hashing with tenant awareness.
    """
    
    def __init__(
        self,
        num_shards: int = 64,
        partition_key_type: str = "tenant_id",
    ):
        self._num_shards = num_shards
        self._partition_key_type = partition_key_type
        self._ring = ConsistentHashRing()
        
        for i in range(num_shards):
            shard = Shard(
                shard_id=f"shard_{i}",
                node_id=f"node_{i % 4}",
            )
            self._ring.add_shard(shard)
    
    def get_partition_key(
        self,
        tenant_id: str,
        workflow_id: Optional[str] = None,
    ) -> PartitionKey:
        """Generate partition key for a workflow.
        
        Args:
            tenant_id: Tenant identifier
            workflow_id: Optional workflow identifier
            
        Returns:
            Partition key
        """
        key = tenant_id
        if workflow_id:
            key = f"{tenant_id}:{workflow_id}"
        
        shard_id = self._ring.get_shard_id(key) or "shard_0"
        
        return PartitionKey(tenant_id, shard_id)
    
    def get_shard(
        self,
        tenant_id: str,
        workflow_id: Optional[str] = None,
    ) -> Optional[Shard]:
        """Get the shard for a workflow.
        
        Args:
            tenant_id: Tenant identifier
            workflow_id: Optional workflow identifier
            
        Returns:
            Shard that owns the workflow
        """
        key = self.get_partition_key(tenant_id, workflow_id)
        return self._ring.get_shard(str(key))
    
    def add_shard(self, shard: Shard) -> None:
        """Add a new shard.
        
        Args:
            shard: Shard to add
        """
        self._ring.add_shard(shard)
    
    def remove_shard(self, shard_id: str) -> None:
        """Remove a shard.
        
        Args:
            shard_id: Shard to remove
        """
        self._ring.remove_shard(shard_id)
    
    def get_workflow_partition_query(
        self,
        tenant_id: str,
        shard_filter: bool = True,
    ) -> tuple[str, list[str]]:
        """Generate partition-aware query for workflows.
        
        Args:
            tenant_id: Tenant identifier
            shard_filter: Whether to add shard filter
            
        Returns:
            Tuple of (WHERE clause, parameters)
        """
        if shard_filter:
            shard = self.get_shard(tenant_id)
            if shard:
                return "WHERE tenant_id = ? AND shard_id = ?", [tenant_id, shard.shard_id]
        
        return "WHERE tenant_id = ?", [tenant_id]
    
    def get_all_shards(self) -> list[Shard]:
        """Get all shards."""
        return self._ring.get_all_shards()
    
    def get_shard_by_id(self, shard_id: str) -> Optional[Shard]:
        """Get a specific shard by ID.
        
        Args:
            shard_id: Shard identifier
            
        Returns:
            Shard or None
        """
        shards = self._ring.get_all_shards()
        for shard in shards:
            if shard.shard_id == shard_id:
                return shard
        return None
    
    def get_tenant_shards(self, tenant_id: str) -> list[Shard]:
        """Get all shards that contain a tenant's workflows.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            List of shards
        """
        key = self.get_partition_key(tenant_id)
        shard = self._ring.get_shard(str(key))
        return [shard] if shard else []


class ShardAwareEventStore:
    """Event store with shard awareness.
    
    Routes events to the correct shard based on partition key.
    """
    
    def __init__(self, partitioner: WorkflowPartitioner):
        self._partitioner = partitioner
        self._shard_stores: dict[str, dict] = {}
    
    def get_shard_store(self, shard_id: str) -> dict:
        """Get the event store for a shard."""
        if shard_id not in self._shard_stores:
            self._shard_stores[shard_id] = {}
        return self._shard_stores[shard_id]
    
    async def append_event(
        self,
        tenant_id: str,
        workflow_id: str,
        event: dict,
    ) -> None:
        """Append an event to the correct shard.
        
        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow identifier
            event: Event data
        """
        partition_key = self._partitioner.get_partition_key(tenant_id, workflow_id)
        store = self.get_shard_store(partition_key.shard_id)
        
        if workflow_id not in store:
            store[workflow_id] = []
        
        store[workflow_id].append(event)
    
    async def get_events(
        self,
        tenant_id: str,
        workflow_id: str,
    ) -> list[dict]:
        """Get all events for a workflow.
        
        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow identifier
            
        Returns:
            List of events
        """
        partition_key = self._partitioner.get_partition_key(tenant_id, workflow_id)
        store = self.get_shard_store(partition_key.shard_id)
        return store.get(workflow_id, [])
    
    async def migrate_workflow(
        self,
        tenant_id: str,
        workflow_id: str,
        target_shard_id: str,
    ) -> bool:
        """Migrate a workflow to a different shard.
        
        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow identifier
            target_shard_id: Target shard ID
            
        Returns:
            True if migration succeeded
        """
        source_key = self._partitioner.get_partition_key(tenant_id, workflow_id)
        source_store = self.get_shard_store(source_key.shard_id)
        
        events = source_store.pop(workflow_id, [])
        if not events:
            return True
        
        target_store = self.get_shard_store(target_shard_id)
        target_store[workflow_id] = events
        
        return True
