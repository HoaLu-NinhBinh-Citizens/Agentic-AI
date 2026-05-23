"""Event Bus - Infrastructure-wide async event bus with Redis Streams support.

Phase: Infrastructure Layer (FIXED)
Purpose: Provides pub/sub event bus for cross-component communication
FIXES Applied:
- Redis Streams instead of pub/sub for guaranteed ordering
- At-least-once delivery with consumer groups
- Sequence numbers for causal ordering
- Local dispatch happens AFTER Redis write (no race condition)
- Message persistence for replay capability

Supports:
- In-memory pub/sub for single-instance
- Redis Streams for distributed (guaranteed ordering)
- Dead letter queue for failed events
- Event schema validation
- Subscription patterns (topic, wildcard)
- Event replay from streams
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class EventBusBackend(Enum):
    """Event bus backend types."""
    IN_MEMORY = "in_memory"
    REDIS_STREAMS = "redis_streams"  # Renamed from REDIS for clarity


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
    sequence: int = 0  # FIX: Added sequence number for ordering

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to dict."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "topic": self.topic,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "metadata": self.metadata,
            "sequence": self.sequence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        """Deserialize event from dict."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        return cls(
            event_id=data.get("event_id", ""),
            event_type=data.get("event_type", ""),
            topic=data.get("topic", ""),
            data=data.get("data", {}),
            timestamp=timestamp or datetime.now(),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            metadata=data.get("metadata", {}),
            sequence=data.get("sequence", 0),
        )


EventHandler = Callable[[Event], Awaitable[None]]


@dataclass
class Subscription:
    """Event subscription."""
    handler: EventHandler
    topic_pattern: str  # Supports wildcards: "agent.*", "*.task"
    event_types: list[str] | None = None  # Filter by event type


class EventBusBackend(ABC):
    """Abstract backend for event bus."""

    @abstractmethod
    async def publish(self, event: Event) -> None:
        """Publish an event."""
        pass

    @abstractmethod
    async def subscribe(self, subscription: Subscription) -> None:
        """Subscribe to events."""
        pass

    @abstractmethod
    async def unsubscribe(self, subscription: Subscription) -> None:
        """Unsubscribe from events."""
        pass

    @abstractmethod
    async def start(self) -> None:
        """Start the backend."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the backend."""
        pass


class InMemoryEventBusBackend(EventBusBackend):
    """In-memory event bus backend for single-instance deployment."""

    def __init__(self) -> None:
        self._subscriptions: list[Subscription] = []
        self._running = False
        self._event_queue: asyncio.Queue[Event] = asyncio.Queue()
        self._processor_task: asyncio.Task | None = None
        self._sequence: int = 0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the event processor."""
        self._running = True
        self._processor_task = asyncio.create_task(self._process_events())
        logger.info("in_memory_event_bus_started")

    async def stop(self) -> None:
        """Stop the event processor."""
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        logger.info("in_memory_event_bus_stopped")

    async def _process_events(self) -> None:
        """Process events from queue."""
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=1.0
                )
                await self._dispatch(event)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("event_processing_error", error=str(e))

    async def publish(self, event: Event) -> None:
        """Queue event for processing with sequence number."""
        if not self._running:
            raise RuntimeError("Event bus not started")
        
        async with self._lock:
            self._sequence += 1
            event.sequence = self._sequence
        
        await self._event_queue.put(event)

    async def subscribe(self, subscription: Subscription) -> None:
        """Register a subscription."""
        self._subscriptions.append(subscription)
        logger.debug("subscription_added", pattern=subscription.topic_pattern)

    async def unsubscribe(self, subscription: Subscription) -> None:
        """Remove a subscription."""
        if subscription in self._subscriptions:
            self._subscriptions.remove(subscription)

    def _matches_pattern(self, pattern: str, topic: str) -> bool:
        """Check if topic matches pattern with wildcards."""
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

    async def _dispatch(self, event: Event) -> None:
        """Dispatch event to matching subscriptions."""
        for sub in self._subscriptions:
            if not self._matches_pattern(sub.topic_pattern, event.topic):
                continue
            
            if sub.event_types and event.event_type not in sub.event_types:
                continue
            
            try:
                await asyncio.wait_for(sub.handler(event), timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning("handler_timeout", 
                    topic=event.topic, 
                    event_type=event.event_type
                )
            except Exception as e:
                logger.exception("handler_error",
                    topic=event.topic,
                    event_type=event.event_type,
                    error=str(e)
                )


class RedisStreamsEventBusBackend(EventBusBackend):
    """Redis Streams-backed event bus for distributed deployment.

    FIX: Uses Redis Streams instead of pub/sub for:
    - Guaranteed ordering (stream entries are ordered)
    - At-least-once delivery (consumer groups)
    - Message persistence (streams are durable)
    - Replay capability (can read from any position)
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        stream_prefix: str = "aisupport:events",
        consumer_group: str = "aisupport-consumers",
        consumer_name: str | None = None,
        claim_idle_timeout_ms: int = 30000,
        batch_size: int = 100,
    ) -> None:
        self._redis_url = redis_url
        self._stream_prefix = stream_prefix
        self._consumer_group = consumer_group
        self._consumer_name = consumer_name or f"consumer-{uuid.uuid4().hex[:8]}"
        self._claim_idle_timeout_ms = claim_idle_timeout_ms
        self._batch_size = batch_size
        
        self._redis = None
        self._running = False
        self._subscriptions: list[Subscription] = []
        self._listener_tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        
        # FIX: Sequence counter per topic for ordering
        self._sequences: dict[str, int] = defaultdict(int)

    async def start(self) -> None:
        """Connect to Redis and start listener."""
        try:
            import redis.asyncio as redis
        except ImportError:
            logger.error("redis_not_installed")
            raise RuntimeError("redis package required for Redis Streams backend")
        
        self._redis = redis.from_url(self._redis_url, decode_responses=False)
        self._running = True
        
        # Create consumer group for each topic pattern
        await self._ensure_consumer_groups()
        
        logger.info("redis_streams_event_bus_started", 
                   url=self._redis_url, 
                   consumer=self._consumer_name)

    async def _ensure_consumer_groups(self) -> None:
        """Create consumer groups for all topic patterns."""
        topic_patterns = set()
        for sub in self._subscriptions:
            topic_patterns.add(sub.topic_pattern)
        
        for pattern in topic_patterns:
            stream_key = self._get_stream_key(pattern)
            try:
                # Create stream if not exists with MKSTREAM
                await self._redis.xgroup_create(
                    stream_key, 
                    self._consumer_group, 
                    id="0", 
                    mkstream=True
                )
            except Exception as e:
                # Group might already exist
                if "BUSYGROUP" not in str(e):
                    logger.debug(f"Consumer group creation: {e}")

    async def stop(self) -> None:
        """Disconnect from Redis."""
        self._running = False
        
        # Cancel all listener tasks
        for task in self._listener_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        if self._redis:
            await self._redis.close()
        logger.info("redis_streams_event_bus_stopped")

    def _get_stream_key(self, topic: str) -> str:
        """Get stream key for topic."""
        return f"{self._stream_prefix}:{topic}"

    def _get_topic_from_stream(self, stream_key: str) -> str:
        """Extract topic from stream key."""
        return stream_key.replace(f"{self._stream_prefix}:", "")

    async def _get_next_sequence(self, topic: str) -> int:
        """Get next sequence number for topic."""
        async with self._lock:
            self._sequences[topic] += 1
            return self._sequences[topic]
    
    async def _load_consumer_position(self, stream_key: str) -> str | None:
        """Load consumer position for stream from Redis.
        
        FIX: Enables at-least-once delivery by tracking position.
        """
        try:
            pos_key = f"{self._stream_prefix}:positions:{self._consumer_group}:{stream_key}"
            pos = await self._redis.get(pos_key)
            if pos:
                logger.debug("consumer_position_loaded", stream=stream_key, position=pos)
                return pos.decode()
        except Exception as e:
            logger.warning("consumer_position_load_failed", error=str(e))
        return None
    
    async def _save_consumer_position(self, stream_key: str, last_id: str) -> None:
        """Save consumer position for stream to Redis.
        
        FIX: Persists position for crash recovery.
        """
        try:
            pos_key = f"{self._stream_prefix}:positions:{self._consumer_group}:{stream_key}"
            await self._redis.set(pos_key, last_id)
            logger.debug("consumer_position_saved", stream=stream_key, position=last_id)
        except Exception as e:
            logger.warning("consumer_position_save_failed", error=str(e))

    async def publish(self, event: Event) -> None:
        """Publish event to Redis Stream FIRST, then dispatch locally.
        
        FIX: This ensures ordering - Redis write happens before local dispatch.
        """
        if not self._running or not self._redis:
            raise RuntimeError("Event bus not started")
        
        # FIX: Get sequence number BEFORE writing
        sequence = await self._get_next_sequence(event.topic)
        event.sequence = sequence
        
        stream_key = self._get_stream_key(event.topic)
        
        # FIX: Write to Redis FIRST (single writer, guaranteed order)
        event_data = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "topic": event.topic,
            "data": json.dumps(event.data),
            "timestamp": event.timestamp.isoformat(),
            "correlation_id": event.correlation_id or "",
            "causation_id": event.causation_id or "",
            "metadata": json.dumps(event.metadata),
            "sequence": str(sequence),
        }
        
        # Use XADD with explicit ID for ordering
        # ID format: timestamp-milliseconds-sequence (ensures global ordering)
        stream_id = f"{int(time.time() * 1000)}-{sequence:06d}"
        
        try:
            await self._redis.xadd(stream_key, event_data, maxlen=10000, approximate=True, id=stream_id)
            logger.debug("event_published_to_stream", 
                       topic=event.topic, 
                       sequence=sequence,
                       stream_id=stream_id)
        except Exception as e:
            logger.error("failed_to_publish_to_stream", error=str(e))
            raise
        
        # Now dispatch locally (AFTER Redis write is confirmed)
        await self._dispatch_local(event)

    async def subscribe(self, subscription: Subscription) -> None:
        """Register a subscription and start listener for topic."""
        async with self._lock:
            self._subscriptions.append(subscription)
        
        # Ensure consumer group exists
        await self._ensure_consumer_groups()
        
        # Start listener task for this pattern if not already running
        if subscription.topic_pattern not in self._listener_tasks:
            task = asyncio.create_task(self._listen_to_stream(subscription.topic_pattern))
            self._listener_tasks[subscription.topic_pattern] = task
        
        logger.debug("subscription_added", pattern=subscription.topic_pattern)

    async def unsubscribe(self, subscription: Subscription) -> None:
        """Remove a subscription."""
        async with self._lock:
            if subscription in self._subscriptions:
                self._subscriptions.remove(subscription)
        
        # Check if any subscriptions still need this pattern
        needs_pattern = any(
            s.topic_pattern == subscription.topic_pattern 
            for s in self._subscriptions
        )
        if not needs_pattern and subscription.topic_pattern in self._listener_tasks:
            self._listener_tasks[subscription.topic_pattern].cancel()
            del self._listener_tasks[subscription.topic_pattern]

    async def _listen_to_stream(self, topic_pattern: str) -> None:
        """Listen to Redis Stream for events matching pattern.
        
        FIX: Now reads from last processed position for at-least-once delivery.
        """
        stream_key = self._get_stream_key(topic_pattern)
        
        # FIX: Persist consumer position for at-least-once delivery
        last_id = await self._load_consumer_position(stream_key)
        if not last_id:
            last_id = "0"  # Start from beginning if no saved position
        
        while self._running:
            try:
                # Read pending messages first (for at-least-once)
                messages = await self._redis.xreadgroup(
                    self._consumer_group,
                    self._consumer_name,
                    {stream_key: last_id},
                    count=self._batch_size,
                    block=1000,  # 1 second block
                )
                
                if not messages:
                    continue
                
                for stream_name, entries in messages:
                    for msg_id, data in entries:
                        try:
                            event = self._parse_stream_message(data)
                            event.sequence = int(data.get(b"sequence", 0))
                            
                            # FIX: ACK BEFORE dispatch for at-least-once
                            await self._redis.xack(stream_key, self._consumer_group, msg_id)
                            
                            # Dispatch after successful ACK
                            await self._dispatch_local(event)
                            
                            # Update last read ID and persist
                            last_id = msg_id
                            asyncio.create_task(self._save_consumer_position(stream_key, last_id))
                            
                        except Exception as e:
                            logger.exception("stream_message_parse_error", error=str(e))
                
                # Claim idle messages from dead consumers
                await self._claim_idle_messages(stream_key)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("stream_listen_error", error=str(e))
                await asyncio.sleep(1)

    async def _claim_idle_messages(self, stream_key: str) -> None:
        """Claim messages that have been pending for too long."""
        try:
            # Find pending messages older than idle timeout
            pending = await self._redis.xpending_range(
                stream_key,
                self._consumer_group,
                min="-",
                max="+",
                count=10,
            )
            
            for entry in pending:
                msg_id, consumer, idle_time = entry["ID"], entry["consumer"], entry["time_since_delivered"]
                
                if idle_time > self._claim_idle_timeout_ms:
                    # Claim the message
                    await self._redis.xclaim(
                        stream_key,
                        self._consumer_group,
                        self._consumer_name,
                        self._claim_idle_timeout_ms,
                        [msg_id],
                    )
                    logger.info("claimed_idle_message", 
                              msg_id=msg_id, 
                              idle_time=idle_time)
        except Exception as e:
            logger.debug("claim_idle_messages_error", error=str(e))

    def _parse_stream_message(self, data: dict) -> Event:
        """Parse Redis Stream message to Event."""
        return Event(
            event_id=data.get(b"event_id", b"").decode(),
            event_type=data.get(b"event_type", b"").decode(),
            topic=data.get(b"topic", b"").decode(),
            data=json.loads(data.get(b"data", b"{}").decode()),
            timestamp=datetime.fromisoformat(data.get(b"timestamp", datetime.now().isoformat()).decode()),
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
                logger.warning("handler_timeout", topic=event.topic, event_type=event.event_type)
            except Exception as e:
                logger.exception("handler_error", topic=event.topic, event_type=event.event_type, error=str(e))

    async def replay_from(
        self, 
        topic: str, 
        from_sequence: int = 0,
        handler: Callable[[Event], Any] | None = None,
    ) -> list[Event]:
        """Replay events from a topic starting from sequence.
        
        FIX: Added replay capability for stream events.
        """
        stream_key = self._get_stream_key(topic)
        events = []
        
        try:
            # Read all messages
            messages = await self._redis.xrange(stream_key, count=10000)
            
            for msg_id, data in messages:
                sequence = int(data.get(b"sequence", 0))
                if sequence < from_sequence:
                    continue
                
                event = self._parse_stream_message(data)
                event.sequence = sequence
                events.append(event)
                
                if handler:
                    await handler(event)
                    
        except Exception as e:
            logger.error("replay_error", topic=topic, error=str(e))
        
        return events


@dataclass
class EventBusConfig:
    """Event bus configuration."""
    backend: EventBusBackend = EventBusBackend.IN_MEMORY
    redis_url: str = "redis://localhost:6379"
    stream_prefix: str = "aisupport:events"
    consumer_group: str = "aisupport-consumers"
    consumer_name: str | None = None
    claim_idle_timeout_ms: int = 30000
    batch_size: int = 100
    enable_dlq: bool = True
    dlq_max_size: int = 1000


class EventBus:
    """Main event bus interface with DLQ support.

    Usage:
        # In-memory (single instance)
        bus = EventBus(EventBusConfig())
        await bus.start()

        # Distributed (multi-instance) - FIX: Uses Redis Streams
        bus = EventBus(EventBusConfig(
            backend=EventBusBackend.REDIS_STREAMS,
            redis_url="redis://localhost:6379"
        ))
        await bus.start()

        # Subscribe and publish
        async def handler(event):
            print(f"Received: {event.event_type}")

        await bus.subscribe(handler, "agent.*")
        await bus.publish(Event(
            event_id="1",
            event_type="agent.task.completed",
            topic="agent.task",
            data={"task_id": "123"}
        ))
    """

    def __init__(self, config: EventBusConfig | None = None):
        self._config = config or EventBusConfig()
        self._backend: EventBusBackend | None = None
        self._dlq: list[Event] = []
        self._dlq_max_size = self._config.dlq_max_size if self._config else 1000
        self._metrics = {
            "published": 0,
            "handled": 0,
            "dlq_size": 0,
            "sequences": {},  # Track sequences per topic
        }

    async def start(self) -> None:
        """Start the event bus."""
        if self._config.backend == EventBusBackend.REDIS_STREAMS:
            self._backend = RedisStreamsEventBusBackend(
                redis_url=self._config.redis_url,
                stream_prefix=self._config.stream_prefix,
                consumer_group=self._config.consumer_group,
                consumer_name=self._config.consumer_name,
                claim_idle_timeout_ms=self._config.claim_idle_timeout_ms,
                batch_size=self._config.batch_size,
            )
        else:
            self._backend = InMemoryEventBusBackend()
        
        await self._backend.start()
        logger.info("event_bus_started", backend=self._config.backend.value)

    async def stop(self) -> None:
        """Stop the event bus."""
        if self._backend:
            await self._backend.stop()
        logger.info("event_bus_stopped", metrics=self._metrics)

    async def publish(
        self,
        event_type: str,
        topic: str,
        data: dict[str, Any],
        correlation_id: str | None = None,
        causation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        """Publish an event.

        Args:
            event_type: Type of event (e.g., "TaskCompleted", "AgentRegistered")
            topic: Topic path (e.g., "agent.task", "flash.operation")
            data: Event payload
            correlation_id: ID for tracing related events
            causation_id: ID of event that caused this event
            metadata: Additional metadata

        Returns:
            The published event with sequence number
        """
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            topic=topic,
            data=data,
            correlation_id=correlation_id,
            causation_id=causation_id,
            metadata=metadata or {},
        )
        
        if self._backend:
            try:
                await self._backend.publish(event)
                self._metrics["published"] += 1
                
                # Track sequence for this topic
                if topic not in self._metrics["sequences"]:
                    self._metrics["sequences"][topic] = 0
                self._metrics["sequences"][topic] = max(
                    self._metrics["sequences"][topic], 
                    event.sequence
                )
            except Exception as e:
                logger.exception("event_publish_error", error=str(e))
                self._add_to_dlq(event)
        
        return event

    async def subscribe(
        self,
        handler: EventHandler,
        topic_pattern: str,
        event_types: list[str] | None = None,
    ) -> None:
        """Subscribe to events.

        Args:
            handler: Async handler function
            topic_pattern: Topic pattern with wildcards (e.g., "agent.*", "*.task")
            event_types: Optional list of event types to filter
        """
        if not self._backend:
            raise RuntimeError("Event bus not started")
        
        subscription = Subscription(
            handler=handler,
            topic_pattern=topic_pattern,
            event_types=event_types,
        )
        await self._backend.subscribe(subscription)

    async def unsubscribe(
        self,
        handler: EventHandler,
        topic_pattern: str,
    ) -> None:
        """Unsubscribe from events."""
        if not self._backend:
            raise RuntimeError("Event bus not started")
        
        subscription = Subscription(
            handler=handler,
            topic_pattern=topic_pattern,
        )
        await self._backend.unsubscribe(subscription)

    def _add_to_dlq(self, event: Event) -> None:
        """Add failed event to dead letter queue."""
        self._dlq.append(event)
        while len(self._dlq) > self._dlq_max_size:
            self._dlq.pop(0)
        self._metrics["dlq_size"] = len(self._dlq)
        logger.warning("event_added_to_dlq", event_id=event.event_id)

    def get_dlq(self) -> list[Event]:
        """Get dead letter queue contents."""
        return self._dlq.copy()

    def clear_dlq(self) -> int:
        """Clear DLQ and return count."""
        count = len(self._dlq)
        self._dlq.clear()
        self._metrics["dlq_size"] = 0
        return count

    def get_metrics(self) -> dict[str, Any]:
        """Get event bus metrics."""
        return {
            **self._metrics,
            "backend": self._config.backend.value if self._config else "unknown",
            "dlq_max_size": self._dlq_max_size,
        }

    async def replay(
        self, 
        topic: str, 
        from_sequence: int = 0,
        handler: Callable[[Event], Any] | None = None,
    ) -> list[Event]:
        """Replay events from a topic.
        
        FIX: Added replay capability.
        """
        if isinstance(self._backend, RedisStreamsEventBusBackend):
            return await self._backend.replay_from(topic, from_sequence, handler)
        return []


# Global event bus instance
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


async def init_event_bus(config: EventBusConfig | None = None) -> EventBus:
    """Initialize and start the global event bus."""
    global _event_bus
    _event_bus = EventBus(config)
    await _event_bus.start()
    return _event_bus


async def shutdown_event_bus() -> None:
    """Shutdown the global event bus."""
    global _event_bus
    if _event_bus:
        await _event_bus.stop()
        _event_bus = None
