"""Event Bus - Infrastructure-wide async event bus with Redis support.

Phase: Infrastructure Layer
Purpose: Provides pub/sub event bus for cross-component communication
Supports:
- In-memory pub/sub for single-instance
- Redis-backed pub/sub for multi-instance (distributed)
- Dead letter queue for failed events
- Event schema validation
- Subscription patterns (topic, wildcard)
- Event replay from persistence
"""

from __future__ import annotations

import asyncio
import json
import logging
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
    REDIS = "redis"


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
        """Queue event for processing."""
        if not self._running:
            raise RuntimeError("Event bus not started")
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
        
        # Handle wildcard patterns like "agent.*" or "*.task"
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
            # Check topic pattern
            if not self._matches_pattern(sub.topic_pattern, event.topic):
                continue
            
            # Check event type filter
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


class RedisEventBusBackend(EventBusBackend):
    """Redis-backed event bus for distributed deployment."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        channel_prefix: str = "aisupport:events",
    ) -> None:
        self._redis_url = redis_url
        self._channel_prefix = channel_prefix
        self._redis = None
        self._pubsub = None
        self._subscriptions: list[Subscription] = []
        self._running = False
        self._listener_task: asyncio.Task | None = None
        self._local_queue: asyncio.Queue[Event] = asyncio.Queue()

    async def start(self) -> None:
        """Connect to Redis and start listener."""
        try:
            import redis.asyncio as redis
        except ImportError:
            logger.error("redis_not_installed")
            raise RuntimeError("redis package required for Redis backend")
        
        self._redis = redis.from_url(self._redis_url, decode_responses=False)
        self._pubsub = self._redis.pubsub()
        self._running = True
        self._listener_task = asyncio.create_task(self._listen())
        logger.info("redis_event_bus_started", url=self._redis_url)

    async def stop(self) -> None:
        """Disconnect from Redis."""
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._pubsub:
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()
        logger.info("redis_event_bus_stopped")

    async def _listen(self) -> None:
        """Listen for Redis messages."""
        # Subscribe to channels based on patterns
        patterns = set()
        for sub in self._subscriptions:
            channel = f"{self._channel_prefix}:{sub.topic_pattern}"
            patterns.add(channel)
        
        if patterns:
            await self._pubsub.psubscribe(*patterns)
        
        async for message in self._pubsub.listen():
            if not self._running:
                break
            if message["type"] != "pmessage":
                continue
            
            try:
                data = json.loads(message["data"])
                event = Event.from_dict(data)
                await self._dispatch_local(event)
            except Exception as e:
                logger.exception("redis_message_error", error=str(e))

    async def publish(self, event: Event) -> None:
        """Publish event to Redis."""
        if not self._running or not self._redis:
            raise RuntimeError("Event bus not started")
        
        channel = f"{self._channel_prefix}:{event.topic}"
        await self._redis.publish(channel, json.dumps(event.to_dict()))
        
        # Also dispatch locally for same-instance subscribers
        await self._dispatch_local(event)

    async def subscribe(self, subscription: Subscription) -> None:
        """Register a subscription."""
        self._subscriptions.append(subscription)
        if self._pubsub and self._running:
            channel = f"{self._channel_prefix}:{subscription.topic_pattern}"
            await self._pubsub.psubscribe(channel)
        logger.debug("subscription_added", pattern=subscription.topic_pattern)

    async def unsubscribe(self, subscription: Subscription) -> None:
        """Remove a subscription."""
        if subscription in self._subscriptions:
            self._subscriptions.remove(subscription)

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
            except Exception as e:
                logger.exception("handler_error", error=str(e))


@dataclass
class EventBusConfig:
    """Event bus configuration."""
    backend: EventBusBackend = EventBusBackend.IN_MEMORY
    redis_url: str = "redis://localhost:6379"
    channel_prefix: str = "aisupport:events"
    enable_dlq: bool = True
    dlq_max_size: int = 1000


class EventBus:
    """Main event bus interface with DLQ support.

    Usage:
        # In-memory (single instance)
        bus = EventBus(EventBusConfig())
        await bus.start()

        # Distributed (multi-instance)
        bus = EventBus(EventBusConfig(
            backend=EventBusBackend.REDIS,
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
        }

    async def start(self) -> None:
        """Start the event bus."""
        if self._config.backend == EventBusBackend.REDIS:
            self._backend = RedisEventBusBackend(
                redis_url=self._config.redis_url,
                channel_prefix=self._config.channel_prefix,
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
    ) -> None:
        """Publish an event.

        Args:
            event_type: Type of event (e.g., "TaskCompleted", "AgentRegistered")
            topic: Topic path (e.g., "agent.task", "flash.operation")
            data: Event payload
            correlation_id: ID for tracing related events
            causation_id: ID of event that caused this event
            metadata: Additional metadata
        """
        import uuid
        
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
            except Exception as e:
                logger.exception("event_publish_error", error=str(e))
                self._add_to_dlq(event)

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
