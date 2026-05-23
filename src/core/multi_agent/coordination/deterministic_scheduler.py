"""
Deterministic Scheduler for Multi-Agent Coordination.

Provides:
- Deterministic event ordering
- Logical clock (Lamport timestamps)
- Replay capability for debugging
- Audit trail
- Redis-backed persistence for distributed coordination
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

logger = logging.getLogger(__name__)

# Optional Redis support
try:
    import redis.asyncio as redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    logger.warning("redis_not_installed_scheduler")


class EventType(str, Enum):
    """Types of scheduled events."""
    TASK_SUBMIT = "task_submit"
    TASK_COMPLETE = "task_complete"
    TASK_CANCEL = "task_cancel"
    TASK_FAIL = "task_fail"
    AGENT_REGISTER = "agent_register"
    AGENT_HEARTBEAT = "agent_heartbeat"
    AGENT_STATUS_CHANGE = "agent_status_change"
    MESSAGE_SEND = "message_send"
    MESSAGE_RECEIVE = "message_receive"
    COORDINATOR_ACTION = "coordinator_action"


@dataclass
class LogicalClock:
    """Lamport logical clock."""
    counter: int = 0
    node_id: str = ""
    
    def tick(self) -> int:
        """Increment clock."""
        self.counter += 1
        return self.counter
    
    def update(self, other: int) -> int:
        """Update clock based on received timestamp."""
        self.counter = max(self.counter, other) + 1
        return self.counter
    
    def to_dict(self) -> Dict[str, Any]:
        return {"counter": self.counter, "node_id": self.node_id}


@dataclass
class ScheduledEvent:
    """A scheduled event in the deterministic scheduler."""
    event_id: str
    event_type: EventType
    clock: LogicalClock
    timestamp: datetime
    data: Dict[str, Any]
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    causality_dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class ExecutionRecord:
    """Record of an execution for replay."""
    event: ScheduledEvent
    result: Any
    duration_ms: float
    success: bool
    error: Optional[str] = None


class DeterministicScheduler:
    """
    Deterministic scheduler for multi-agent coordination.
    
    Features:
    - Logical clock (Lamport timestamps)
    - Causal ordering of events
    - Deterministic replay
    - Audit trail
    - Redis-backed persistence for distributed coordination
    - Event replay across restarts
    
    Usage:
        # Local-only
        scheduler = DeterministicScheduler(node_id="agent-1")
        
        # With Redis persistence
        scheduler = DeterministicScheduler(
            node_id="agent-1",
            redis_url="redis://localhost:6379",
            enable_persistence=True
        )
    """
    
    def __init__(
        self,
        node_id: str,
        enable_replay: bool = True,
        max_history: int = 10000,
        redis_url: str | None = None,
        enable_persistence: bool = False,
    ):
        self.node_id = node_id
        self.enable_replay = enable_replay
        self.max_history = max_history
        self.enable_persistence = enable_persistence and HAS_REDIS
        
        self._clock = LogicalClock(counter=0, node_id=node_id)
        self._events: deque[ScheduledEvent] = deque(maxlen=max_history)
        self._execution_log: List[ExecutionRecord] = []
        self._pending_events: Dict[str, ScheduledEvent] = {}
        self._lock = asyncio.Lock()
        
        # Replay state
        self._is_replaying = False
        self._replay_index = 0
        
        # Event handlers
        self._handlers: Dict[EventType, List[Callable]] = defaultdict(list)
        
        # Causality tracking
        self._causality_graph: Dict[str, Set[str]] = defaultdict(set)
        
        # Redis persistence
        self._redis: redis.Redis | None = None
        self._redis_url = redis_url
        self._persistence_key = f"aisupport:scheduler:{node_id}"
        
        # Start Redis connection if enabled
        if self.enable_persistence and self._redis_url:
            asyncio.create_task(self._connect_redis())
    
    async def _connect_redis(self) -> None:
        """Connect to Redis for persistence."""
        if not self.enable_persistence or not self._redis_url:
            return
        
        try:
            self._redis = redis.from_url(self._redis_url)
            await self._redis.ping()
            logger.info("scheduler_redis_connected", node_id=self.node_id)
            
            # Restore state from Redis
            await self._restore_from_redis()
        except Exception as e:
            logger.error("scheduler_redis_connect_failed", error=str(e))
            self._redis = None
            self.enable_persistence = False
    
    async def _restore_from_redis(self) -> None:
        """Restore scheduler state from Redis."""
        if not self._redis:
            return
        
        try:
            # Restore clock
            clock_data = await self._redis.hget(self._persistence_key, "clock")
            if clock_data:
                clock_dict = json.loads(clock_data)
                self._clock.counter = clock_dict.get("counter", 0)
            
            # Restore pending events
            pending_data = await self._redis.hget(self._persistence_key, "pending")
            if pending_data:
                pending_list = json.loads(pending_data)
                for event_dict in pending_list:
                    event = self._dict_to_event(event_dict)
                    self._pending_events[event.event_id] = event
            
            logger.info(
                "scheduler_state_restored",
                node_id=self.node_id,
                clock=self._clock.counter,
                pending=len(self._pending_events)
            )
        except Exception as e:
            logger.error("scheduler_restore_failed", error=str(e))
    
    async def _persist_to_redis(self) -> None:
        """Persist scheduler state to Redis."""
        if not self._redis or not self.enable_persistence:
            return
        
        try:
            # Persist clock
            clock_data = json.dumps({"counter": self._clock.counter, "node_id": self.node_id})
            await self._redis.hset(self._persistence_key, "clock", clock_data)
            
            # Persist pending events
            pending_list = [self._event_to_dict(e) for e in self._pending_events.values()]
            await self._redis.hset(self._persistence_key, "pending", json.dumps(pending_list))
            
            # Set TTL (1 hour)
            await self._redis.expire(self._persistence_key, 3600)
            
        except Exception as e:
            logger.error("scheduler_persist_failed", error=str(e))
    
    def _event_to_dict(self, event: ScheduledEvent) -> dict:
        """Convert event to dict for serialization."""
        return {
            "event_id": event.event_id,
            "event_type": event.event_type.value if isinstance(event.event_type, Enum) else event.event_type,
            "clock": {"counter": event.clock.counter, "node_id": event.clock.node_id},
            "timestamp": event.timestamp.isoformat(),
            "data": event.data,
            "agent_id": event.agent_id,
            "task_id": event.task_id,
            "causality_dependencies": event.causality_dependencies,
            "metadata": event.metadata,
        }
    
    def _dict_to_event(self, data: dict) -> ScheduledEvent:
        """Convert dict back to event."""
        clock = LogicalClock(
            counter=data["clock"]["counter"],
            node_id=data["clock"]["node_id"]
        )
        event_type = EventType(data["event_type"]) if data["event_type"] in [e.value for e in EventType] else EventType.COORDINATOR_ACTION
        
        return ScheduledEvent(
            event_id=data["event_id"],
            event_type=event_type,
            clock=clock,
            timestamp=datetime.fromisoformat(data["timestamp"]),
            data=data["data"],
            agent_id=data.get("agent_id"),
            task_id=data.get("task_id"),
            causality_dependencies=data.get("causality_dependencies", []),
            metadata=data.get("metadata", {}),
        )
    
    def register_handler(
        self,
        event_type: EventType,
        handler: Callable[[ScheduledEvent], Any],
    ) -> None:
        """Register a handler for an event type."""
        self._handlers[event_type].append(handler)
    
    async def emit(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        dependencies: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ScheduledEvent:
        """
        Emit a deterministic event.
        
        Events are ordered by logical clock and timestamp.
        """
        async with self._lock:
            # Increment logical clock
            clock_value = self._clock.tick()
            
            event = ScheduledEvent(
                event_id=str(uuid4()),
                event_type=event_type,
                clock=LogicalClock(counter=clock_value, node_id=self.node_id),
                timestamp=datetime.now(),
                data=data,
                agent_id=agent_id,
                task_id=task_id,
                causality_dependencies=dependencies or [],
                metadata=metadata or {},
            )
            
            # Add to event log
            self._events.append(event)
            self._pending_events[event.event_id] = event
            
            # Update causality graph
            for dep_id in event.causality_dependencies:
                self._causality_graph[event.event_id].add(dep_id)
            
            # Persist to Redis if enabled
            if self.enable_persistence:
                asyncio.create_task(self._persist_to_redis())
            
            return event
    
    async def receive(
        self,
        event: ScheduledEvent,
        remote_clock: Dict[str, Any],
    ) -> ScheduledEvent:
        """
        Receive an event from another node.
        
        Updates logical clock based on remote clock.
        """
        async with self._lock:
            # Update logical clock
            remote_counter = remote_clock.get("counter", 0)
            clock_value = self._clock.update(remote_counter)
            
            # Create local event
            local_event = ScheduledEvent(
                event_id=event.event_id,
                event_type=event.event_type,
                clock=LogicalClock(counter=clock_value, node_id=self.node_id),
                timestamp=datetime.now(),
                data=event.data,
                agent_id=event.agent_id,
                task_id=event.task_id,
                causality_dependencies=event.causality_dependencies,
                metadata=event.metadata,
            )
            
            self._events.append(local_event)
            self._pending_events[local_event.event_id] = local_event
            
            return local_event
    
    async def process_next(self) -> Optional[ScheduledEvent]:
        """
        Process the next event in causal order.
        
        Returns the event that was processed, or None if no events ready.
        """
        async with self._lock:
            if self._is_replaying:
                return await self._replay_next()
            
            # Find events ready to process (all dependencies satisfied)
            ready = []
            for event_id, event in self._pending_events.items():
                deps = event.causality_dependencies
                if all(dep_id not in self._pending_events for dep_id in deps):
                    ready.append(event)
            
            if not ready:
                return None
            
            # Sort by logical clock (deterministic order)
            ready.sort(key=lambda e: (e.clock.counter, e.event_id))
            
            # Process first
            event = ready[0]
            await self._process_event(event)
            
            return event
    
    async def _process_event(self, event: ScheduledEvent) -> None:
        """Process a single event."""
        # Remove from pending
        self._pending_events.pop(event.event_id, None)
        
        # Call handlers
        for handler in self._handlers.get(event.event_type, []):
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    result = await result
            except Exception as e:
                logger.error(f"Handler error for {event.event_id}: {e}")
    
    async def _replay_next(self) -> Optional[ScheduledEvent]:
        """Replay the next event from history."""
        if self._replay_index >= len(self._execution_log):
            self._is_replaying = False
            return None
        
        record = self._execution_log[self._replay_index]
        self._replay_index += 1
        
        return record.event
    
    async def replay(
        self,
        from_event_id: Optional[str] = None,
        to_event_id: Optional[str] = None,
    ) -> List[ExecutionRecord]:
        """
        Replay events from history.
        
        Args:
            from_event_id: Start replay from this event (inclusive)
            to_event_id: End replay at this event (inclusive)
            
        Returns:
            List of execution records during replay
        """
        async with self._lock:
            self._is_replaying = True
            self._replay_index = 0
            
            results = []
            
            # Find start index
            start_idx = 0
            if from_event_id:
                for i, record in enumerate(self._execution_log):
                    if record.event.event_id == from_event_id:
                        start_idx = i
                        break
            
            # Find end index
            end_idx = len(self._execution_log)
            if to_event_id:
                for i, record in enumerate(self._execution_log):
                    if record.event.event_id == to_event_id:
                        end_idx = i + 1
                        break
            
            self._replay_index = start_idx
            
            # Process events
            while self._replay_index < end_idx:
                event = await self._replay_next()
                if event is None:
                    break
                results.append(self._execution_log[self._replay_index - 1])
            
            self._is_replaying = False
            return results
    
    async def get_event_sequence(
        self,
        agent_id: Optional[str] = None,
        event_types: Optional[List[EventType]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get sequence of events for debugging.
        
        Returns events in deterministic order.
        """
        events = list(self._events)
        
        # Filter
        if agent_id:
            events = [e for e in events if e.agent_id == agent_id]
        if event_types:
            events = [e for e in events if e.event_type in event_types]
        
        # Sort by logical clock
        events.sort(key=lambda e: (e.clock.counter, e.event_id))
        
        # Limit
        events = events[-limit:]
        
        return [
            {
                "event_id": e.event_id,
                "event_type": e.event_type.value,
                "clock": e.clock.counter,
                "timestamp": e.timestamp.isoformat(),
                "agent_id": e.agent_id,
                "task_id": e.task_id,
                "data": e.data,
            }
            for e in events
        ]
    
    async def verify_causality(self) -> Dict[str, Any]:
        """
        Verify causality is preserved.
        
        Returns verification result.
        """
        events = list(self._events)
        events.sort(key=lambda e: e.clock.counter)
        
        clock_values = [e.clock.counter for e in events]
        
        # Check clock is monotonically increasing
        monotonic = all(
            clock_values[i] < clock_values[i + 1]
            for i in range(len(clock_values) - 1)
        )
        
        # Check all dependencies are before dependent
        violations = []
        for event in events:
            for dep_id in event.causality_dependencies:
                dep_event = next((e for e in events if e.event_id == dep_id), None)
                if dep_event and dep_event.clock.counter >= event.clock.counter:
                    violations.append({
                        "event_id": event.event_id,
                        "depends_on": dep_id,
                        "violation": f"dep_clock={dep_event.clock.counter} >= event_clock={event.clock.counter}",
                    })
        
        return {
            "valid": monotonic and len(violations) == 0,
            "monotonic_clock": monotonic,
            "causality_violations": violations,
            "total_events": len(events),
            "total_clocks": len(set(clock_values)),
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get scheduler metrics."""
        return {
            "node_id": self.node_id,
            "clock_value": self._clock.counter,
            "total_events": len(self._events),
            "pending_events": len(self._pending_events),
            "execution_records": len(self._execution_log),
            "is_replaying": self._is_replaying,
            "replay_index": self._replay_index,
            "persistence_enabled": self.enable_persistence,
            "redis_connected": self._redis is not None,
        }
    
    async def shutdown(self) -> None:
        """Shutdown scheduler and close Redis connection."""
        # Persist final state
        if self.enable_persistence:
            await self._persist_to_redis()
        
        # Close Redis
        if self._redis:
            await self._redis.close()
            self._redis = None
        
        logger.info("scheduler_shutdown", node_id=self.node_id)
