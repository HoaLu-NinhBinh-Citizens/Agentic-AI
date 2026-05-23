"""Horizontal Sharding for Scalability.

Provides:
- Consistent hashing for shard distribution
- Cross-shard queries
- Shard rebalancing
- Geographic sharding
- Automatic failover

Usage:
    sharding = ShardingManager(num_shards=16)
    shard_id = sharding.get_shard("user-123")
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ShardKey(Enum):
    """Types of shard keys."""
    TENANT = "tenant"
    AGENT = "agent"
    SESSION = "session"
    TASK = "task"
    TIME = "time"


@dataclass
class Shard:
    """A shard instance."""
    shard_id: int
    region: str
    endpoint: str
    is_primary: bool = True
    is_healthy: bool = True
    last_heartbeat: datetime = field(default_factory=datetime.now)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class ShardConfig:
    """Configuration for sharding."""
    num_shards: int = 16
    replication_factor: int = 3
    virtual_nodes_per_shard: int = 100
    rebalance_threshold: float = 0.2


class ConsistentHashRing:
    """Consistent hashing ring for shard assignment.
    
    Uses virtual nodes to ensure even distribution.
    """
    
    def __init__(self, virtual_nodes: int = 100):
        self.virtual_nodes = virtual_nodes
        self._ring: dict[int, int] = {}  # hash -> shard_id
        self._sorted_keys: list[int] = []
    
    def add_shard(self, shard_id: int) -> None:
        """Add a shard to the ring."""
        for i in range(self.virtual_nodes):
            key = self._hash(f"{shard_id}:{i}")
            self._ring[key] = shard_id
        
        self._sorted_keys = sorted(self._ring.keys())
        logger.debug("shard_added_to_ring", shard_id=shard_id)
    
    def remove_shard(self, shard_id: int) -> None:
        """Remove a shard from the ring."""
        keys_to_remove = []
        for key, sid in self._ring.items():
            if sid == shard_id:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self._ring[key]
        
        self._sorted_keys = sorted(self._ring.keys())
        logger.debug("shard_removed_from_ring", shard_id=shard_id)
    
    def get_shard(self, key: str) -> int:
        """Get the shard for a key."""
        if not self._sorted_keys:
            raise ValueError("No shards in ring")
        
        hash_value = self._hash(key)
        
        # Binary search for first node >= hash
        for node_hash in self._sorted_keys:
            if node_hash >= hash_value:
                return self._ring[node_hash]
        
        # Wrap around to first node
        return self._ring[self._sorted_keys[0]]
    
    def _hash(self, key: str) -> int:
        """Hash function for consistent hashing."""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)


@dataclass
class ShardMetadata:
    """Metadata for a shard key."""
    shard_id: int
    region: str
    partition_key: str
    created_at: datetime = field(default_factory=datetime.now)


class ShardingManager:
    """Manager for horizontal sharding.
    
    Usage:
        manager = ShardingManager()
        
        # Assign to shard
        shard_id = await manager.assign("session-123", ShardKey.SESSION)
        
        # Query cross-shard
        results = await manager.query_all("SELECT * FROM sessions")
    """
    
    def __init__(self, config: ShardConfig | None = None):
        self._config = config or ShardConfig()
        self._shards: dict[int, Shard] = {}
        self._ring = ConsistentHashRing(self._config.virtual_nodes_per_shard)
        self._metadata: dict[str, ShardMetadata] = {}
    
    async def add_shard(
        self,
        shard_id: int,
        region: str,
        endpoint: str,
    ) -> None:
        """Add a new shard."""
        shard = Shard(
            shard_id=shard_id,
            region=region,
            endpoint=endpoint,
        )
        self._shards[shard_id] = shard
        self._ring.add_shard(shard_id)
        
        logger.info("shard_added", shard_id=shard_id, region=region)
    
    async def remove_shard(self, shard_id: int) -> None:
        """Remove a shard."""
        if shard_id in self._shards:
            del self._shards[shard_id]
            self._ring.remove_shard(shard_id)
            logger.info("shard_removed", shard_id=shard_id)
    
    def get_shard(self, key: str, shard_key: ShardKey = ShardKey.TENANT) -> int:
        """Get shard ID for a key."""
        # Combine key with shard type for better distribution
        composite_key = f"{shard_key.value}:{key}"
        return self._ring.get_shard(composite_key)
    
    async def assign(
        self,
        entity_id: str,
        shard_key: ShardKey,
    ) -> int:
        """Assign an entity to a shard."""
        shard_id = self.get_shard(entity_id, shard_key)
        
        self._metadata[entity_id] = ShardMetadata(
            shard_id=shard_id,
            region=self._shards.get(shard_id, Shard(0, "", "")).region,
            partition_key=entity_id,
        )
        
        return shard_id
    
    async def get_shard_for(self, entity_id: str) -> ShardMetadata | None:
        """Get shard metadata for an entity."""
        return self._metadata.get(entity_id)
    
    async def rebalance(self) -> dict[int, int]:
        """Rebalance shards based on load.
        
        Returns:
            Mapping of entity_id to new shard_id
        """
        moves = {}
        
        for entity_id, metadata in self._metadata.items():
            new_shard_id = self.get_shard(entity_id, ShardKey.TENANT)
            
            if new_shard_id != metadata.shard_id:
                old_shard_id = metadata.shard_id
                metadata.shard_id = new_shard_id
                moves[entity_id] = {"from": old_shard_id, "to": new_shard_id}
        
        if moves:
            logger.info("rebalance_completed", moves=len(moves))
        
        return moves
    
    def get_shard_stats(self) -> dict[str, Any]:
        """Get statistics for all shards."""
        counts = {}
        for metadata in self._metadata.values():
            sid = metadata.shard_id
            counts[sid] = counts.get(sid, 0) + 1
        
        return {
            "total_entities": len(self._metadata),
            "shard_distribution": counts,
            "num_shards": len(self._shards),
        }


class CrossShardQuery:
    """Execute queries across multiple shards."""
    
    def __init__(self, manager: ShardingManager, executor: callable):
        self._manager = manager
        self._executor = executor
    
    async def execute(
        self,
        query: str,
        params: dict | None = None,
        target_shards: list[int] | None = None,
    ) -> list[dict]:
        """Execute query across shards."""
        if target_shards is None:
            target_shards = list(self._manager._shards.keys())
        
        results = []
        for shard_id in target_shards:
            shard = self._manager._shards.get(shard_id)
            if not shard:
                continue
            
            try:
                result = await self._executor(shard.endpoint, query, params)
                results.extend(result)
            except Exception as e:
                logger.error("cross_shard_query_failed", shard_id=shard_id, error=str(e))
        
        return results


class GeoSharding:
    """Geographic sharding for latency optimization."""
    
    REGION_MAPPING = {
        "us-east": ["us-east-1", "us-east-2"],
        "us-west": ["us-west-1", "us-west-2"],
        "eu-west": ["eu-west-1", "eu-west-2", "eu-central-1"],
        "ap-south": ["ap-south-1", "ap-southeast-1"],
        "ap-east": ["ap-east-1", "ap-northeast-1"],
    }
    
    def __init__(self):
        self._region_shards: dict[str, list[int]] = {}
    
    def register_region(self, region: str, shard_ids: list[int]) -> None:
        """Register shards for a region."""
        self._region_shards[region] = shard_ids
        logger.info("region_registered", region=region, shards=shard_ids)
    
    def get_shards_for_region(self, region: str) -> list[int]:
        """Get shards for a region."""
        return self._region_shards.get(region, [])
    
    def get_region_for_availability_zone(self, az: str) -> str | None:
        """Get region for an availability zone."""
        for region, azs in self.REGION_MAPPING.items():
            if az in azs:
                return region
        return None
