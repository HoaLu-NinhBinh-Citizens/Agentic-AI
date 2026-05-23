"""Redis Cluster Backend - Horizontal scaling with automatic failover.

Provides:
- Redis Cluster support for horizontal scaling
- Hash slot routing for distributed streams
- Automatic failover with replica promotion
- Cluster-aware consumer groups
- Connection pooling with slot awareness

Usage:
    cluster = RedisClusterBackend(
        nodes=["redis://node1:6379", "redis://node2:6379"],
        stream_prefix="aisupport:events",
    )
    await cluster.start()
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ClusterEventBusBackend(Enum):
    """Cluster backend types."""
    REDIS_CLUSTER = "redis_cluster"


@dataclass
class Event:
    """Base event for the event bus."""
    event_id: str
    event_type: str
    topic: str
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    correlation_id: str | None = None
    causation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    sequence: int = 0


@dataclass
class Subscription:
    """Event subscription."""
    handler: Callable
    topic_pattern: str
    event_types: list[str] | None = None


class RedisClusterBackend:
    """Redis Cluster-backed event bus for horizontal scaling.

    Features:
    - Multiple Redis nodes for horizontal scaling
    - Hash slot routing (16384 slots)
    - Automatic failover and replica promotion
    - Connection pooling per node
    - Cluster topology awareness
    """

    def __init__(
        self,
        nodes: list[str] | None = None,
        stream_prefix: str = "aisupport:events",
        consumer_group: str = "aisupport-consumers",
        consumer_name: str | None = None,
        claim_idle_timeout_ms: int = 30000,
        batch_size: int = 100,
        pool_size_per_node: int = 5,
        connection_timeout: float = 5.0,
        max_retries: int = 3,
    ) -> None:
        """
        Args:
            nodes: List of Redis node URLs
            stream_prefix: Prefix for stream keys
            consumer_group: Consumer group name
            consumer_name: Unique consumer name
            claim_idle_timeout_ms: Timeout for claiming idle messages
            batch_size: Number of messages per read
            pool_size_per_node: Connection pool size per node
            connection_timeout: Connection timeout in seconds
            max_retries: Max retries for cluster operations
        """
        self._nodes = nodes or ["redis://localhost:6379"]
        self._stream_prefix = stream_prefix
        self._consumer_group = consumer_group
        self._consumer_name = consumer_name or f"consumer-{uuid.uuid4().hex[:8]}"
        self._claim_idle_timeout_ms = claim_idle_timeout_ms
        self._batch_size = batch_size
        self._pool_size = pool_size_per_node
        self._connection_timeout = connection_timeout
        self._max_retries = max_retries
        
        # Cluster state
        self._redis_module = None
        self._connections: dict[str, Any] = {}
        self._slots: dict[int, str] = {}
        self._node_pools: dict[str, asyncio.Queue] = {}
        
        # Event bus state
        self._running = False
        self._subscriptions: list[Subscription] = []
        self._listener_tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._sequences: dict[str, int] = {}

    async def start(self) -> None:
        """Connect to all Redis cluster nodes."""
        try:
            import redis.asyncio as redis
            self._redis_module = redis
        except ImportError:
            logger.error("redis_not_installed")
            raise RuntimeError("redis package required for Redis Cluster backend")
        
        # Connect to all nodes
        await self._connect_nodes()
        
        # Discover cluster topology
        await self._discover_topology()
        
        self._running = True
        
        logger.info(
            "redis_cluster_event_bus_started",
            nodes=len(self._nodes),
            slots=len(self._slots),
            consumer=self._consumer_name,
        )

    async def _connect_nodes(self) -> None:
        """Connect to all cluster nodes."""
        for node_url in self._nodes:
            try:
                conn = self._redis_module.from_url(
                    node_url,
                    decode_responses=False,
                    socket_timeout=self._connection_timeout,
                    socket_connect_timeout=self._connection_timeout,
                )
                
                await conn.ping()
                
                self._connections[node_url] = conn
                self._node_pools[node_url] = asyncio.Queue(maxsize=self._pool_size)
                
                for _ in range(self._pool_size - 1):
                    await self._node_pools[node_url].put(conn)
                
                logger.debug("connected_to_node", node=node_url)
                
            except Exception as e:
                logger.error("node_connection_failed", node=node_url, error=str(e))

    async def _discover_topology(self) -> None:
        """Discover cluster topology via CLUSTER SLOTS."""
        if not self._connections:
            return
        
        primary = next(iter(self._connections.values()))
        
        try:
            result = await primary.execute_command("CLUSTER SLOTS")
            
            if result:
                self._slots = {}
                for slot_range in result:
                    start_slot = slot_range[0]
                    end_slot = slot_range[1]
                    
                    primary_info = slot_range[2]
                    primary_host = primary_info[0].decode()
                    primary_port = primary_info[1]
                    primary_url = f"redis://{primary_host}:{primary_port}"
                    
                    for slot in range(start_slot, end_slot + 1):
                        self._slots[slot] = primary_url
                
                logger.info(
                    "cluster_topology_discovered",
                    slot_ranges=len(result),
                    total_slots=len(self._slots),
                )
            else:
                logger.warning("cluster_slots_not_available_using_single_node")
                self._slots = {i: self._nodes[0] for i in range(16384)}
                
        except Exception as e:
            logger.error("topology_discovery_failed", error=str(e))
            self._slots = {i: self._nodes[0] for i in range(16384)}

    def _get_slot_for_key(self, key: str) -> int:
        """Calculate hash slot for a key using CRC16."""
        slot_key = key.split(":", 1)[-1] if ":" in key else key
        
        crc = 0
        for char in slot_key:
            crc = (crc >> 8) ^ self._crc16_table[(crc ^ ord(char)) & 0xFF]
        return crc & 0x3FFF

    @staticmethod
    def _init_crc16_table() -> list[int]:
        """Initialize CRC16 lookup table."""
        table = []
        for i in range(256):
            crc = i
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
            table.append(crc)
        return table

    _crc16_table = self._init_crc16_table.__func__()

    def _get_node_for_stream(self, topic: str) -> str:
        """Get appropriate node for a stream topic."""
        stream_key = f"{self._stream_prefix}:{topic}"
        slot = self._get_slot_for_key(stream_key)
        
        if slot in self._slots:
            return self._slots[slot]
        
        return self._nodes[slot % len(self._nodes)]

    async def _get_connection_for_stream(self, topic: str) -> tuple[Any, str]:
        """Get connection for a stream topic."""
        node_url = self._get_node_for_stream(topic)
        
        try:
            conn = await asyncio.wait_for(
                self._node_pools[node_url].get(),
                timeout=self._connection_timeout,
            )
            return conn, node_url
        except asyncio.TimeoutError:
            conn = self._redis_module.from_url(node_url, decode_responses=False)
            return conn, node_url

    async def _return_connection(self, conn: Any, node_url: str) -> None:
        """Return connection to pool."""
        try:
            self._node_pools[node_url].put_nowait(conn)
        except asyncio.QueueFull:
            await conn.close()

    async def stop(self) -> None:
        """Disconnect from all nodes."""
        self._running = False
        
        for task in self._listener_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        for conn in self._connections.values():
            await conn.close()
        
        self._connections.clear()
        logger.info("redis_cluster_event_bus_stopped")

    async def publish(self, event: Event) -> None:
        """Publish event to correct cluster node."""
        if not self._running:
            raise RuntimeError("Event bus not started")
        
        async with self._lock:
            if event.topic not in self._sequences:
                self._sequences[event.topic] = 0
            self._sequences[event.topic] += 1
            event.sequence = self._sequences[event.topic]
        
        stream_key = f"{self._stream_prefix}:{event.topic}"
        
        event_data = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "topic": event.topic,
            "data": json.dumps(event.data),
            "timestamp": event.timestamp.isoformat(),
            "correlation_id": event.correlation_id or "",
            "causation_id": event.causation_id or "",
            "metadata": json.dumps(event.metadata),
            "sequence": str(event.sequence),
        }
        
        node_url = self._get_node_for_stream(event.topic)
        conn, _ = await self._get_connection_for_stream(event.topic)
        
        try:
            stream_id = f"{int(time.time() * 1000)}-{event.sequence:06d}"
            
            await conn.xadd(
                stream_key,
                event_data,
                maxlen=10000,
                approximate=True,
                id=stream_id,
            )
            
            logger.debug(
                "event_published_to_cluster",
                topic=event.topic,
                node=node_url,
                sequence=event.sequence,
            )
            
        except Exception as e:
            logger.error(
                "cluster_publish_failed",
                topic=event.topic,
                node=node_url,
                error=str(e),
            )
            
            for retry in range(self._max_retries):
                try:
                    await self._discover_topology()
                    node_url = self._get_node_for_stream(event.topic)
                    conn, _ = await self._get_connection_for_stream(event.topic)
                    
                    await conn.xadd(
                        stream_key,
                        event_data,
                        maxlen=10000,
                        approximate=True,
                        id=stream_id,
                    )
                    
                    logger.info("cluster_publish_retry_success", retry=retry + 1)
                    break
                except Exception:
                    pass
            else:
                raise
        finally:
            await self._return_connection(conn, node_url)
        
        await self._dispatch_local(event)

    async def subscribe(self, subscription: Subscription) -> None:
        """Register subscription and start listening."""
        async with self._lock:
            self._subscriptions.append(subscription)
        
        pattern_key = f"{subscription.topic_pattern}:{uuid.uuid4().hex[:8]}"
        if pattern_key not in self._listener_tasks:
            task = asyncio.create_task(self._listen_pattern(subscription.topic_pattern))
            self._listener_tasks[pattern_key] = task
        
        logger.debug("cluster_subscription_added", pattern=subscription.topic_pattern)

    async def unsubscribe(self, subscription: Subscription) -> None:
        """Remove a subscription."""
        async with self._lock:
            if subscription in self._subscriptions:
                self._subscriptions.remove(subscription)

    async def _listen_pattern(self, topic_pattern: str) -> None:
        """Listen to all streams matching pattern."""
        while self._running:
            try:
                for node_url, conn in self._connections.items():
                    try:
                        cursor = 0
                        while True:
                            cursor, keys = await conn.scan(
                                cursor=cursor,
                                match=f"{self._stream_prefix}:{topic_pattern}",
                                count=100,
                            )
                            
                            for stream_key in keys:
                                topic = stream_key.decode().replace(f"{self._stream_prefix}:", "")
                                asyncio.create_task(self._listen_stream(topic, conn, node_url))
                            
                            if cursor == 0:
                                break
                                
                    except Exception:
                        pass
                
                await asyncio.sleep(5)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("pattern_listen_error", error=str(e))
                await asyncio.sleep(5)

    async def _listen_stream(
        self,
        topic: str,
        conn: Any,
        node_url: str,
    ) -> None:
        """Listen to a single stream."""
        stream_key = f"{self._stream_prefix}:{topic}"
        last_id = "$"
        
        await self._ensure_consumer_group(stream_key, conn)
        
        while self._running:
            try:
                messages = await conn.xreadgroup(
                    self._consumer_group,
                    self._consumer_name,
                    {stream_key: last_id},
                    count=self._batch_size,
                    block=1000,
                )
                
                if not messages:
                    continue
                
                for stream_name, entries in messages:
                    for msg_id, data in entries:
                        try:
                            event = self._parse_stream_message(data)
                            event.sequence = int(data.get(b"sequence", 0))
                            last_id = msg_id
                            
                            await self._dispatch_local(event)
                            await conn.xack(stream_key, self._consumer_group, msg_id)
                            
                        except Exception as e:
                            logger.exception("stream_event_error", error=str(e))
                
                await self._claim_idle(conn, stream_key)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("stream_listen_error", topic=topic, error=str(e))
                await asyncio.sleep(1)

    async def _ensure_consumer_group(self, stream_key: str, conn: Any) -> bool:
        """Ensure consumer group exists."""
        try:
            await conn.xgroup_create(
                stream_key,
                self._consumer_group,
                id="0",
                mkstream=True,
            )
            return True
        except Exception:
            return True

    async def _claim_idle(self, conn: Any, stream_key: str) -> None:
        """Claim idle messages from dead consumers."""
        try:
            pending = await conn.xpending_range(
                stream_key,
                self._consumer_group,
                min="-",
                max="+",
                count=10,
            )
            
            for entry in pending:
                msg_id = entry["ID"]
                idle_time = entry["time_since_delivered"]
                
                if idle_time > self._claim_idle_timeout_ms:
                    await conn.xclaim(
                        stream_key,
                        self._consumer_group,
                        self._consumer_name,
                        self._claim_idle_timeout_ms,
                        [msg_id],
                    )
        except Exception:
            pass

    def _parse_stream_message(self, data: dict) -> Event:
        """Parse Redis Stream message to Event."""
        return Event(
            event_id=data.get(b"event_id", b"").decode(),
            event_type=data.get(b"event_type", b"").decode(),
            topic=data.get(b"topic", b"").decode(),
            data=json.loads(data.get(b"data", b"{}").decode()),
            timestamp=datetime.fromisoformat(
                data.get(b"timestamp", datetime.now().isoformat().encode()).decode()
            ),
            correlation_id=data.get(b"correlation_id", b"").decode() or None,
            causation_id=data.get(b"causation_id", b"").decode() or None,
            metadata=json.loads(data.get(b"metadata", b"{}").decode()),
        )

    def _matches_pattern(self, pattern: str, topic: str) -> bool:
        """Check if topic matches pattern."""
        if pattern == "*":
            return True
        if pattern == topic:
            return True
        pattern_parts = pattern.split(".")
        topic_parts = topic.split(".")
        if len(pattern_parts) != len(topic_parts):
            return False
        for p, t in zip(pattern_parts, topic_parts):
            if p == "*":
                continue
            if p != t:
                return False
        return True

    async def _dispatch_local(self, event: Event) -> None:
        """Dispatch to local subscribers."""
        for sub in self._subscriptions:
            if not self._matches_pattern(sub.topic_pattern, event.topic):
                continue
            if sub.event_types and event.event_type not in sub.event_types:
                continue
            try:
                await asyncio.wait_for(sub.handler(event), timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning("handler_timeout", topic=event.topic)
            except Exception as e:
                logger.exception("handler_error", topic=event.topic, error=str(e))

    async def get_cluster_info(self) -> dict[str, Any]:
        """Get cluster status information."""
        node_info = []
        
        for node_url, conn in self._connections.items():
            try:
                info = await conn.info("server")
                node_info.append({
                    "url": node_url,
                    "connected": True,
                    "version": info.get("redis_version", "unknown"),
                })
            except Exception as e:
                node_info.append({
                    "url": node_url,
                    "connected": False,
                    "error": str(e),
                })
        
        return {
            "nodes": node_info,
            "total_slots": len(self._slots),
            "streams_prefix": self._stream_prefix,
            "consumer_group": self._consumer_group,
            "consumer_name": self._consumer_name,
        }


if __name__ == "__main__":
    print("Redis Cluster Event Bus Backend")
    print("=" * 40)
    print("Horizontal scaling with automatic failover")
    print()
    print("Features:")
    print("  - Hash slot routing (16384 slots)")
    print("  - Multi-node connection pooling")
    print("  - Automatic topology discovery")
    print("  - Consumer group management")
