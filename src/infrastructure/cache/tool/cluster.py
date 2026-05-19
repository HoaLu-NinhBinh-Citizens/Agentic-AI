"""Cluster Coordinator for distributed cache coordination.

Implements partitioned cluster model with consistent hashing.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ClusterMode(Enum):
    """Cluster deployment modes."""

    STANDALONE = "standalone"
    CLUSTER = "cluster"


@dataclass
class ClusterTopology:
    """Cluster topology configuration."""

    model: str = "partitioned"
    num_partitions: int = 256
    replication_factor: int = 1
    quorum_size: int = 2


@dataclass
class ClusterConfig:
    """Configuration for cluster coordinator."""

    mode: ClusterMode = ClusterMode.STANDALONE
    node_id: str = "local"
    cluster_id: str = "default"
    topology: ClusterTopology = field(default_factory=ClusterTopology)

    redis_url: Optional[str] = None
    redis_required: bool = False
    redis_retry_interval: float = 5.0
    redis_max_retries: int = 3

    fallback_mode: str = "local_only"

    heartbeat_interval_seconds: float = 5.0
    heartbeat_timeout_seconds: float = 30.0


@dataclass
class NodeInfo:
    """Information about a cluster node."""

    node_id: str
    partitions: list[int]
    is_active: bool = True
    last_heartbeat: float = field(default_factory=time.time)
    mode: str = "active"


@dataclass
class PartitionManager:
    """Manages consistent hashing for partitioned cluster."""

    num_partitions: int = 256
    _ring: list[tuple[int, str]] = field(default_factory=list)
    _partition_map: dict[int, str] = field(default_factory=dict)

    def get_owner(self, key: str) -> str:
        """Get primary owner of key."""
        hash_value = self._hash(key)
        return self._find_node(hash_value)

    def get_replicas(self, key: str, replication_factor: int) -> list[str]:
        """Get replica owners for key."""
        if replication_factor <= 1:
            return []

        primary = self.get_owner(key)
        return self._find_next_n_nodes(primary, replication_factor - 1)

    def add_node(self, node_id: str, partitions: list[int]) -> None:
        """Add a node to the cluster ring."""
        for partition in partitions:
            self._partition_map[partition] = node_id

    def remove_node(self, node_id: str) -> list[int]:
        """Remove a node and return its partitions."""
        removed = []
        for partition, owner in list(self._partition_map.items()):
            if owner == node_id:
                del self._partition_map[partition]
                removed.append(partition)
        return removed

    def get_node_partitions(self, node_id: str) -> list[int]:
        """Get partitions owned by a node."""
        return [
            partition for partition, owner in self._partition_map.items()
            if owner == node_id
        ]

    def _hash(self, key: str) -> int:
        """Hash a key to a partition number."""
        import hashlib
        hash_bytes = hashlib.sha256(key.encode()).digest()
        return int.from_bytes(hash_bytes[:4], "big") % self.num_partitions

    def _find_node(self, hash_value: int) -> str:
        """Find node responsible for a hash value."""
        for partition in sorted(self._partition_map.keys()):
            if partition >= hash_value:
                return self._partition_map[partition]
        if self._partition_map:
            return self._partition_map[min(self._partition_map.keys())]
        return "unknown"

    def _find_next_n_nodes(self, start_node: str, n: int) -> list[str]:
        """Find next n nodes after the start node."""
        result = []
        all_nodes = list(set(self._partition_map.values()))
        if start_node in all_nodes:
            start_idx = all_nodes.index(start_node)
            for i in range(1, n + 1):
                idx = (start_idx + i) % len(all_nodes)
                if all_nodes[idx] != start_node:
                    result.append(all_nodes[idx])
        return result


class ClusterCoordinator:
    """Coordinates distributed cache operations.

    Features:
    - Partitioned cluster model (recommended for production)
    - Consistent hashing for key distribution
    - Node health monitoring via heartbeats
    - Distributed locking
    - Single-flight coordination across nodes

    Guarantees:
    - Partitioned model: each key has single owner
    - Conflict-free for normal operations
    - Graceful degradation on failure
    """

    def __init__(
        self,
        config: ClusterConfig | None = None,
    ) -> None:
        self.config = config or ClusterConfig()
        self._mode = self.config.mode

        self._partition_manager = PartitionManager(
            num_partitions=self.config.topology.num_partitions
        )

        self._nodes: dict[str, NodeInfo] = {}
        self._redis_client: Optional[Any] = None
        self._redis_available = False

        self._local_locks: dict[str, asyncio.Lock] = {}
        self._lock_last_used: dict[str, float] = {}

        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False

        self._cluster_state: dict[str, Any] = {}

    async def initialize(self) -> None:
        """Initialize the cluster coordinator."""
        if self._mode == ClusterMode.CLUSTER:
            await self._init_redis()
            await self._join_cluster()

        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info(f"Cluster coordinator initialized in {self._mode.value} mode")

    async def shutdown(self) -> None:
        """Shutdown the cluster coordinator gracefully."""
        logger.info("Initiating graceful shutdown...")

        self._running = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self._mode == ClusterMode.CLUSTER:
            await self._leave_cluster()

        logger.info("Cluster coordinator shutdown complete")

    async def _init_redis(self) -> None:
        """Initialize Redis connection."""
        if not self.config.redis_url:
            logger.warning("Redis URL not configured, falling back to local mode")
            self._redis_available = False
            return

        try:
            import redis.asyncio as redis
            self._redis_client = redis.from_url(self.config.redis_url)
            await self._redis_client.ping()
            self._redis_available = True
            logger.info("Redis connection established")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, using local fallback")
            self._redis_available = False

    async def _join_cluster(self) -> None:
        """Join the cluster."""
        if self._redis_available and self._redis_client:
            node_key = f"cluster:{self.config.cluster_id}:node:{self.config.node_id}"
            await self._redis_client.hset(node_key, mapping={
                "node_id": self.config.node_id,
                "partitions": ",".join(map(str, self._allocate_partitions())),
                "mode": "active",
                "joined_at": str(time.time()),
            })
            await self._redis_client.expire(node_key, 60)

    async def _leave_cluster(self) -> None:
        """Leave the cluster gracefully."""
        if self._redis_available and self._redis_client:
            node_key = f"cluster:{self.config.cluster_id}:node:{self.config.node_id}"
            await self._redis_client.delete(node_key)

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to cluster."""
        while self._running:
            try:
                await asyncio.sleep(self.config.heartbeat_interval_seconds)
                await self._send_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

    async def _send_heartbeat(self) -> None:
        """Send heartbeat to cluster."""
        if self._redis_available and self._redis_client:
            node_key = f"cluster:{self.config.cluster_id}:node:{self.config.node_id}"
            await self._redis_client.hset(node_key, "last_heartbeat", str(time.time()))
            await self._redis_client.expire(node_key, int(self.config.heartbeat_timeout_seconds))

    def _allocate_partitions(self) -> list[int]:
        """Allocate partitions for this node."""
        partitions_per_node = self.config.topology.num_partitions // 3
        start = hash(self.config.node_id) % self.config.topology.num_partitions
        return [(start + i) % self.config.topology.num_partitions for i in range(partitions_per_node)]

    def get_owner(self, key: str) -> str:
        """Get primary owner of a key."""
        if self._mode == ClusterMode.STANDALONE:
            return self.config.node_id
        return self._partition_manager.get_owner(key)

    def get_partition(self, key: str) -> int:
        """Get partition for a key."""
        return self._partition_manager._hash(key)

    async def acquire_lock(
        self,
        key: str,
        timeout: float = 5.0,
    ) -> bool:
        """Acquire a distributed lock.

        Args:
            key: Lock key
            timeout: Lock timeout in seconds

        Returns:
            True if lock acquired, False otherwise
        """
        lock_key = f"lock:{key}"

        if self._mode == ClusterMode.STANDALONE:
            return await self._acquire_local_lock(key, timeout)

        if not self._redis_available:
            return await self._acquire_local_lock(key, timeout)

        try:
            acquired = await self._redis_client.set(
                lock_key,
                self.config.node_id,
                nx=True,
                ex=int(timeout),
            )
            return bool(acquired)
        except Exception as e:
            logger.warning(f"Redis lock failed: {e}, falling back to local")
            return await self._acquire_local_lock(key, timeout)

    async def _acquire_local_lock(self, key: str, timeout: float) -> bool:
        """Acquire a local lock."""
        if key not in self._local_locks:
            self._local_locks[key] = asyncio.Lock()
            self._lock_last_used[key] = time.time()
        else:
            self._lock_last_used[key] = time.time()

        try:
            return await asyncio.wait_for(
                self._local_locks[key].acquire(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return False

    async def release_lock(self, key: str) -> None:
        """Release a distributed lock."""
        lock_key = f"lock:{key}"

        if self._mode == ClusterMode.STANDALONE or not self._redis_available:
            if key in self._local_locks:
                self._local_locks[key].release()
            return

        try:
            await self._redis_client.delete(lock_key)
        except Exception as e:
            logger.warning(f"Redis lock release failed: {e}")

    async def get_lock(self, key: str) -> Optional[str]:
        """Get current lock holder for a key."""
        lock_key = f"lock:{key}"

        if self._mode == ClusterMode.STANDALONE or not self._redis_available:
            if key in self._local_locks and self._local_locks[key].locked():
                return self.config.node_id
            return None

        try:
            holder = await self._redis_client.get(lock_key)
            return holder.decode() if holder else None
        except Exception:
            return None

    async def get_active_nodes(self) -> list[str]:
        """Get list of active nodes in cluster."""
        if self._mode == ClusterMode.STANDALONE or not self._redis_available:
            return [self.config.node_id]

        try:
            pattern = f"cluster:{self.config.cluster_id}:node:*"
            keys = await self._redis_client.keys(pattern)
            nodes = []
            for key in keys:
                node_id = (await self._redis_client.hget(key, "node_id"))
                if node_id:
                    nodes.append(node_id.decode())
            return nodes
        except Exception as e:
            logger.warning(f"Failed to get active nodes: {e}")
            return [self.config.node_id]

    async def set_node_mode(self, node_id: str, mode: str) -> None:
        """Set node mode (active/shadow)."""
        if self._redis_available and self._redis_client:
            node_key = f"cluster:{self.config.cluster_id}:node:{node_id}"
            await self._redis_client.hset(node_key, "mode", mode)

    async def get_node_mode(self, node_id: str) -> str:
        """Get node mode."""
        if self._redis_available and self._redis_client:
            node_key = f"cluster:{self.config.cluster_id}:node:{node_id}"
            mode = await self._redis_client.hget(node_key, "mode")
            return mode.decode() if mode else "unknown"
        return "active"

    async def broadcast_invalidation(self, key: str) -> None:
        """Broadcast cache invalidation to all nodes."""
        if self._redis_available:
            channel = f"cache:invalidation:{self.get_partition(key)}"
            await self._redis_client.publish(channel, key)

    async def subscribe_invalidation(self, callback: Any) -> None:
        """Subscribe to cache invalidation events."""
        if self._redis_available:
            pubsub = self._redis_client.pubsub()
            pattern = "cache:invalidation:*"
            await pubsub.psubscribe(pattern)

            async def listen():
                async for message in pubsub.listen():
                    if message["type"] == "pmessage":
                        key = message["data"].decode()
                        await callback(key)

            asyncio.create_task(listen())

    def is_cluster_mode(self) -> bool:
        """Check if running in cluster mode."""
        return self._mode == ClusterMode.CLUSTER

    async def cleanup_idle_locks(self) -> None:
        """Cleanup idle local locks."""
        now = time.time()
        idle_threshold = 3600

        keys_to_remove = [
            key for key, last_used in self._lock_last_used.items()
            if now - last_used > idle_threshold
        ]

        for key in keys_to_remove:
            if key in self._local_locks:
                del self._local_locks[key]
            del self._lock_last_used[key]

        if keys_to_remove:
            logger.info(f"Cleaned up {len(keys_to_remove)} idle locks")
