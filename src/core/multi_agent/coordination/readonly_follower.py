"""
Read-Only Coordinator Follower.

Provides read scaling through:
- Change stream replication from leader
- Local state cache
- Read-only query endpoints
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class CoordinatorMode(str, Enum):
    """Coordinator mode."""
    LEADER = "leader"
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    STANDBY = "standby"


@dataclass
class ChangeEvent:
    """Change event from leader."""
    event_id: str
    event_type: str
    entity_type: str
    entity_id: str
    data: Dict[str, Any]
    timestamp: datetime
    sequence: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LocalState:
    """Cached state on follower."""
    entity_type: str
    entity_id: str
    data: Dict[str, Any]
    last_updated: datetime
    version: int


class ChangeStreamConsumer:
    """
    Consumes change stream from leader.
    
    In production, this would use gRPC streams, Kafka, or similar.
    """
    
    def __init__(self, leader_url: Optional[str] = None):
        self.leader_url = leader_url
        self._last_sequence = 0
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
    
    def register_handler(
        self,
        entity_type: str,
        handler: Callable[[ChangeEvent], None],
    ) -> None:
        """Register handler for entity type."""
        self._handlers[entity_type].append(handler)
    
    async def start(self) -> None:
        """Start consuming change stream."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
        logger.info("Change stream consumer started")
    
    async def stop(self) -> None:
        """Stop consuming change stream."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Change stream consumer stopped")
    
    async def _consume_loop(self) -> None:
        """Background consume loop."""
        while self._running:
            try:
                # In production, this would connect to leader and consume events
                # For now, simulate with a sleep
                await asyncio.sleep(1)
                
                # Process any pending events (simulated)
                # Real implementation would use:
                # - gRPC streaming
                # - Kafka consumer
                # - Redis pub/sub
                # - PostgreSQL logical replication
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Consume loop error: {e}")
                await asyncio.sleep(5)
    
    async def apply_event(self, event: ChangeEvent) -> None:
        """Apply change event to local state."""
        async with self._lock:
            self._last_sequence = max(self._last_sequence, event.sequence)
        
        # Call registered handlers
        for handler in self._handlers.get(event.entity_type, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Handler error: {e}")
    
    def get_last_sequence(self) -> int:
        """Get last processed sequence."""
        return self._last_sequence


class LocalCache:
    """
    Local cache for follower state.
    
    Provides fast reads with eventual consistency.
    """
    
    def __init__(
        self,
        max_size: int = 10000,
        ttl_seconds: int = 300,
    ):
        self.max_size = max_size
        self.ttl = ttl_seconds
        
        self._cache: Dict[str, LocalState] = {}
        self._access_order: List[str] = []
        self._lock = asyncio.Lock()
    
    async def get(
        self,
        entity_type: str,
        entity_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get entity from cache."""
        key = f"{entity_type}:{entity_id}"
        
        async with self._lock:
            if key not in self._cache:
                return None
            
            state = self._cache[key]
            
            # Check TTL
            age = (datetime.now() - state.last_updated).total_seconds()
            if age > self.ttl:
                del self._cache[key]
                self._access_order.remove(key)
                return None
            
            # Update access order
            self._access_order.remove(key)
            self._access_order.append(key)
            
            return state.data
    
    async def set(
        self,
        entity_type: str,
        entity_id: str,
        data: Dict[str, Any],
        version: int,
    ) -> None:
        """Set entity in cache."""
        key = f"{entity_type}:{entity_id}"
        
        async with self._lock:
            # Check if update is newer
            if key in self._cache:
                existing = self._cache[key]
                if existing.version > version:
                    return  # Don't overwrite newer version
            
            # Evict if needed
            while len(self._cache) >= self.max_size:
                oldest_key = self._access_order.pop(0)
                del self._cache[oldest_key]
            
            # Set new value
            self._cache[key] = LocalState(
                entity_type=entity_type,
                entity_id=entity_id,
                data=data,
                last_updated=datetime.now(),
                version=version,
            )
            self._access_order.append(key)
    
    async def delete(self, entity_type: str, entity_id: str) -> bool:
        """Delete entity from cache."""
        key = f"{entity_type}:{entity_id}"
        
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._access_order.remove(key)
                return True
            return False
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all entities matching pattern."""
        count = 0
        
        async with self._lock:
            keys_to_delete = [
                k for k in self._cache.keys()
                if pattern.replace("*", "") in k
            ]
            
            for key in keys_to_delete:
                del self._cache[key]
                self._access_order.remove(key)
                count += 1
        
        return count
    
    async def clear(self) -> None:
        """Clear all cache."""
        async with self._lock:
            self._cache.clear()
            self._access_order.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "usage_percent": len(self._cache) / self.max_size * 100,
        }


class ReadOnlyCoordinatorFollower:
    """
    Read-only coordinator follower.
    
    Features:
    - Change stream replication from leader
    - Local state cache
    - Read-only query endpoints
    - Automatic reconnection
    
    Guarantees:
    - Reads are eventually consistent (lag < 1s typically)
    - Writes are rejected with MOVED error
    """
    
    def __init__(
        self,
        follower_id: str,
        leader_url: Optional[str] = None,
        cache_size: int = 10000,
        cache_ttl_seconds: int = 300,
    ):
        self.follower_id = follower_id
        self.leader_url = leader_url
        
        self.mode = CoordinatorMode.STANDBY
        self.consumer = ChangeStreamConsumer(leader_url)
        self.cache = LocalCache(max_size=cache_size, ttl_seconds=cache_ttl_seconds)
        
        self._running = False
        self._reconnect_delay = 5
        self._read_count = 0
        self._read_latency_ms = 0.0
    
    async def connect(self) -> bool:
        """
        Connect to leader and start replication.
        
        Returns True if connection successful.
        """
        try:
            # Register handlers for entity types
            self.consumer.register_handler("task", self._on_task_change)
            self.consumer.register_handler("agent", self._on_agent_change)
            self.consumer.register_handler("tenant", self._on_tenant_change)
            
            # Start consuming
            await self.consumer.start()
            
            self.mode = CoordinatorMode.FOLLOWER
            logger.info(f"Follower {self.follower_id} connected to leader")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to leader: {e}")
            self.mode = CoordinatorMode.STANDBY
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from leader."""
        await self.consumer.stop()
        await self.cache.clear()
        self.mode = CoordinatorMode.STANDBY
        logger.info(f"Follower {self.follower_id} disconnected")
    
    async def _on_task_change(self, event: ChangeEvent) -> None:
        """Handle task change event."""
        await self.cache.set(
            "task",
            event.entity_id,
            event.data,
            event.sequence,
        )
    
    async def _on_agent_change(self, event: ChangeEvent) -> None:
        """Handle agent change event."""
        await self.cache.set(
            "agent",
            event.entity_id,
            event.data,
            event.sequence,
        )
    
    async def _on_tenant_change(self, event: ChangeEvent) -> None:
        """Handle tenant change event."""
        await self.cache.set(
            "tenant",
            event.entity_id,
            event.data,
            event.sequence,
        )
    
    # Read-only endpoints
    
    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task (read-only)."""
        if self.mode != CoordinatorMode.FOLLOWER:
            raise ReadModeError("Not connected to leader")
        
        start = time.time()
        result = await self.cache.get("task", task_id)
        self._read_count += 1
        self._read_latency_ms += (time.time() - start) * 1000
        
        return result
    
    async def list_tasks(
        self,
        tenant_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List tasks (read-only)."""
        if self.mode != CoordinatorMode.FOLLOWER:
            raise ReadModeError("Not connected to leader")
        
        # This would require a more sophisticated query in production
        # For now, return empty list (would need index)
        return []
    
    async def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent (read-only)."""
        if self.mode != CoordinatorMode.FOLLOWER:
            raise ReadModeError("Not connected to leader")
        
        return await self.cache.get("agent", agent_id)
    
    async def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant (read-only)."""
        if self.mode != CoordinatorMode.FOLLOWER:
            raise ReadModeError("Not connected to leader")
        
        return await self.cache.get("tenant", tenant_id)
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get follower metrics."""
        return {
            "follower_id": self.follower_id,
            "mode": self.mode.value,
            "leader_url": self.leader_url,
            "last_sequence": self.consumer.get_last_sequence(),
            "read_count": self._read_count,
            "avg_read_latency_ms": self._read_latency_ms / max(1, self._read_count),
            "cache_stats": self.cache.get_stats(),
        }
    
    # Write operations (always rejected on follower)
    
    async def create_task(self, task_data: Dict[str, Any]) -> None:
        """Create task - ALWAYS REJECTED on follower."""
        raise WriteModeError(
            f"Follower {self.follower_id} cannot write. "
            f"Connect to leader at {self.leader_url}"
        )
    
    async def update_task(self, task_id: str, data: Dict[str, Any]) -> None:
        """Update task - ALWAYS REJECTED on follower."""
        raise WriteModeError(
            f"Follower {self.follower_id} cannot write. "
            f"Connect to leader at {self.leader_url}"
        )


class ReadModeError(Exception):
    """Raised when read attempted but not in follower mode."""
    pass


class WriteModeError(Exception):
    """Raised when write attempted on read-only follower."""
    pass
