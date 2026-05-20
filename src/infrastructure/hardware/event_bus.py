"""Event bus for hardware domain events.

This module implements the event bus pattern for publishing and subscribing
to hardware domain events with support for async handlers and dead letter queues.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable
import structlog

from .exceptions import EventHandlerError, EventPublishError

logger = structlog.get_logger(__name__)


class EventPriority(Enum):
    """Event priority levels."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class EventSchema:
    """Event schema definition."""

    event_type: str
    version: str = "1.0"
    fields: dict[str, type] = field(default_factory=dict)

    def validate(self, data: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate event data against schema.

        Args:
            data: Event data to validate

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        for field_name, field_type in self.fields.items():
            if field_name not in data:
                errors.append(f"Missing required field: {field_name}")
            elif not isinstance(data[field_name], field_type):
                errors.append(
                    f"Field '{field_name}' expected {field_type.__name__}, "
                    f"got {type(data[field_name]).__name__}"
                )

        return len(errors) == 0, errors


@dataclass
class DomainEvent:
    """Base class for all domain events.

    Attributes:
        event_id: Unique event identifier
        event_type: Event type name
        schema_version: Schema version for compatibility
        correlation_id: ID for tracing related events
        causation_id: ID of event that caused this one
        timestamp: Event timestamp
        priority: Event priority
        source: Event source component
        data: Event payload
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    schema_version: str = "1.0"
    correlation_id: str | None = None
    causation_id: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    priority: EventPriority = EventPriority.NORMAL
    source: str = "hardware"
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "timestamp": self.timestamp.isoformat(),
            "priority": self.priority.name,
            "source": self.source,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DomainEvent":
        """Create event from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now()

        priority = data.get("priority", "NORMAL")
        if isinstance(priority, str):
            priority = EventPriority[priority]

        return cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            event_type=data.get("event_type", ""),
            schema_version=data.get("schema_version", "1.0"),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            timestamp=timestamp,
            priority=priority,
            source=data.get("source", "hardware"),
            data=data.get("data", {}),
        )


# Predefined event types
class TargetDetectedEvent(DomainEvent):
    """Event emitted when a target is detected."""

    def __init__(
        self,
        target_id: str,
        chip_family: str,
        probe_serial: str | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.event_type = "TargetDetected"
        self.data = {
            "target_id": target_id,
            "chip_family": chip_family,
            "probe_serial": probe_serial,
        }


class TargetConnectedEvent(DomainEvent):
    """Event emitted when a target is connected."""

    def __init__(
        self,
        target_id: str,
        state: str,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.event_type = "TargetConnected"
        self.data = {
            "target_id": target_id,
            "state": state,
        }


class SnapshotCapturedEvent(DomainEvent):
    """Event emitted when a snapshot is captured."""

    def __init__(
        self,
        snapshot_id: str,
        target_id: str,
        size_bytes: int,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.event_type = "SnapshotCaptured"
        self.data = {
            "snapshot_id": snapshot_id,
            "target_id": target_id,
            "size_bytes": size_bytes,
        }


class CapabilityNegotiatedEvent(DomainEvent):
    """Event emitted when capabilities are negotiated."""

    def __init__(
        self,
        target_id: str,
        capabilities: list[str],
        chosen_method: str,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.event_type = "CapabilityNegotiated"
        self.data = {
            "target_id": target_id,
            "capabilities": capabilities,
            "chosen_method": chosen_method,
        }


class HardFaultDetectedEvent(DomainEvent):
    """Event emitted when a hard fault is detected."""

    def __init__(
        self,
        target_id: str,
        fault_type: str,
        pc: int,
        reason: str | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.event_type = "HardFaultDetected"
        self.priority = EventPriority.HIGH
        self.data = {
            "target_id": target_id,
            "fault_type": fault_type,
            "pc": pc,
            "reason": reason,
        }


# Handler type aliases
EventHandler = Callable[[DomainEvent], Awaitable[None]]
DeadLetterHandler = Callable[[DomainEvent, Exception], Awaitable[None]]


@dataclass
class EventHandlerRegistration:
    """Registration for an event handler."""

    handler: EventHandler
    event_type: str | None = None  # None means all events
    version_range: tuple[str, str] | None = None  # (min_version, max_version)
    priority: EventPriority = EventPriority.NORMAL
    async_context: bool = True


class DeadLetterQueue:
    """Dead letter queue for failed events."""

    def __init__(self, storage_path: Path | None = None, max_size: int = 1000):
        self.storage_path = storage_path
        self.max_size = max_size
        self._queue: list[dict[str, Any]] = []
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Load DLQ from disk if available."""
        if self.storage_path and self.storage_path.exists():
            try:
                with open(self.storage_path) as f:
                    self._queue = json.load(f)
            except Exception:
                self._queue = []

    def _save_to_disk(self) -> None:
        """Save DLQ to disk."""
        if self.storage_path:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "w") as f:
                json.dump(self._queue, f, indent=2)

    def add(self, event: DomainEvent, error: Exception) -> None:
        """Add failed event to DLQ.

        Args:
            event: The failed event
            error: The exception that occurred
        """
        entry = {
            "event": event.to_dict(),
            "error": {
                "type": type(error).__name__,
                "message": str(error),
            },
            "added_at": datetime.now().isoformat(),
        }

        self._queue.append(entry)

        # Trim if over max size
        while len(self._queue) > self.max_size:
            self._queue.pop(0)

        self._save_to_disk()
        logger.warning("dlq_event_added", event_id=event.event_id, error=str(error))

    def get_all(self) -> list[dict[str, Any]]:
        """Get all DLQ entries."""
        return self._queue.copy()

    def clear(self) -> int:
        """Clear DLQ and return number of items removed."""
        count = len(self._queue)
        self._queue.clear()
        self._save_to_disk()
        return count

    @property
    def size(self) -> int:
        """Get DLQ size."""
        return len(self._queue)


class InMemoryEventBus:
    """In-memory event bus implementation.

    This event bus supports:
    - Topic-based subscriptions (subscribe to specific event types)
    - Async handlers
    - Version-based filtering
    - Priority ordering
    - Dead letter queue for failed events
    """

    def __init__(self, dlq: DeadLetterQueue | None = None):
        self._handlers: list[EventHandlerRegistration] = []
        self._schemas: dict[str, EventSchema] = {}
        self._dlq = dlq or DeadLetterQueue()
        self._running = False
        self._metrics = {
            "events_published": 0,
            "events_handled": 0,
            "events_failed": 0,
        }

    def register_schema(self, schema: EventSchema) -> None:
        """Register event schema.

        Args:
            schema: Event schema to register
        """
        self._schemas[schema.event_type] = schema

    def subscribe(
        self,
        handler: EventHandler,
        event_type: str | None = None,
        version_range: tuple[str, str] | None = None,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> None:
        """Subscribe to events.

        Args:
            handler: Async handler function
            event_type: Event type to subscribe to (None = all events)
            version_range: (min, max) version range (None = all versions)
            priority: Handler priority
        """
        registration = EventHandlerRegistration(
            handler=handler,
            event_type=event_type,
            version_range=version_range,
            priority=priority,
        )
        self._handlers.append(registration)

        # Sort by priority (highest first)
        self._handlers.sort(key=lambda r: r.priority.value, reverse=True)

        logger.debug("handler_subscribed", event_type=event_type, priority=priority.name)

    def unsubscribe(self, handler: EventHandler) -> bool:
        """Unsubscribe a handler.

        Args:
            handler: Handler to remove

        Returns:
            True if handler was found and removed
        """
        for i, reg in enumerate(self._handlers):
            if reg.handler == handler:
                del self._handlers[i]
                logger.debug("handler_unsubscribed", handler=handler)
                return True
        return False

    async def publish(self, event: DomainEvent) -> None:
        """Publish an event to all matching handlers.

        Args:
            event: Event to publish
        """
        self._metrics["events_published"] += 1

        # Validate against schema if registered
        if event.event_type in self._schemas:
            schema = self._schemas[event.event_type]
            is_valid, errors = schema.validate(event.data)
            if not is_valid:
                logger.warning(
                    "event_validation_failed",
                    event_type=event.event_type,
                    errors=errors,
                )

        # Find matching handlers
        matching_handlers = [
            reg for reg in self._handlers
            if self._matches_handler(reg, event)
        ]

        if not matching_handlers:
            logger.debug("no_handlers_for_event", event_type=event.event_type)
            return

        # Execute handlers
        for registration in matching_handlers:
            try:
                await asyncio.wait_for(
                    registration.handler(event),
                    timeout=30.0,
                )
                self._metrics["events_handled"] += 1
            except asyncio.TimeoutError:
                error = EventHandlerError(
                    event_type=event.event_type,
                    handler_name=getattr(registration.handler, "__name__", "unknown"),
                    original_error=TimeoutError("Handler timed out"),
                )
                self._dlq.add(event, error)
                self._metrics["events_failed"] += 1
                logger.error(
                    "handler_timeout",
                    event_id=event.event_id,
                    event_type=event.event_type,
                )
            except Exception as e:
                error = EventHandlerError(
                    event_type=event.event_type,
                    handler_name=getattr(registration.handler, "__name__", "unknown"),
                    original_error=e,
                )
                self._dlq.add(event, e)
                self._metrics["events_failed"] += 1
                logger.exception(
                    "handler_error",
                    event_id=event.event_id,
                    event_type=event.event_type,
                    error=str(e),
                )

    def _matches_handler(
        self,
        registration: EventHandlerRegistration,
        event: DomainEvent,
    ) -> bool:
        """Check if event matches handler registration."""
        # Check event type
        if registration.event_type is not None:
            if registration.event_type != event.event_type:
                return False

        # Check version range
        if registration.version_range is not None:
            min_ver, max_ver = registration.version_range
            if event.schema_version < min_ver or event.schema_version > max_ver:
                return False

        return True

    def get_metrics(self) -> dict[str, Any]:
        """Get event bus metrics."""
        return {
            **self._metrics,
            "handler_count": len(self._handlers),
            "dlq_size": self._dlq.size,
            "schemas_registered": len(self._schemas),
        }

    async def start(self) -> None:
        """Start the event bus."""
        self._running = True
        logger.info("event_bus_started")

    async def stop(self) -> None:
        """Stop the event bus."""
        self._running = False
        logger.info("event_bus_stopped", metrics=self._metrics)


# Global event bus instance
_event_bus: InMemoryEventBus | None = None


def get_event_bus() -> InMemoryEventBus:
    """Get the global event bus instance.

    Returns:
        Global event bus
    """
    global _event_bus
    if _event_bus is None:
        _event_bus = InMemoryEventBus()
    return _event_bus


def set_event_bus(bus: InMemoryEventBus) -> None:
    """Set the global event bus instance.

    Args:
        bus: Event bus to use as global instance
    """
    global _event_bus
    _event_bus = bus
