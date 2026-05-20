"""Event Bus with async handlers, dead letter queue, and schema versioning.

Phase 6.1: Central event bus for hardware events (TargetDetected, SnapshotCaptured,
HardFaultDetected) with pub/sub pattern, DLQ for failed events, and version-aware handlers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Coroutine,
    Generic,
    TypeVar,
)

if TYPE_CHECKING:
    from .exceptions import EventPublishError, EventHandlerError, EventSchemaVersionError

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ============================================================================
# Event Types
# ============================================================================


class EventType(Enum):
    """Standard hardware event types."""

    # Target events
    TARGET_DISCOVERED = "target.discovered"
    TARGET_CONNECTED = "target.connected"
    TARGET_DISCONNECTED = "target.disconnected"
    TARGET_HALTED = "target.halted"
    TARGET_RESUMED = "target.resumed"
    TARGET_FAULT = "target.fault"
    TARGET_RESET = "target.reset"
    TARGET_STATE_CHANGED = "target.state_changed"

    # Snapshot events
    SNAPSHOT_CAPTURED = "snapshot.captured"
    SNAPSHOT_RESTORED = "snapshot.restored"
    SNAPSHOT_DELETED = "snapshot.deleted"
    SNAPSHOT_DIFF = "snapshot.diff"

    # Capability events
    CAPABILITY_DETECTED = "capability.detected"
    CAPABILITY_NEGOTIATED = "capability.negotiated"
    CAPABILITY_CHANGED = "capability.changed"

    # Probe events
    PROBE_CONNECTED = "probe.connected"
    PROBE_DISCONNECTED = "probe.disconnected"
    PROBE_ERROR = "probe.error"

    # Plugin events
    PLUGIN_LOADED = "plugin.loaded"
    PLUGIN_UNLOADED = "plugin.unloaded"
    PLUGIN_ERROR = "plugin.error"

    # System events
    SYSTEM_ERROR = "system.error"
    SYSTEM_WARNING = "system.warning"
    SYSTEM_READY = "system.ready"
    SYSTEM_SHUTDOWN = "system.shutdown"

    # Custom events
    CUSTOM = "custom"


# ============================================================================
# Event Schema Versioning
# ============================================================================


SCHEMA_VERSION = "1.0"


@dataclass
class EventSchema:
    """Schema version information for an event type."""

    event_type: str
    version: str = SCHEMA_VERSION
    fields: list[str] = field(default_factory=list)
    required_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_type": self.event_type,
            "version": self.version,
            "fields": self.fields,
            "required_fields": self.required_fields,
        }


class EventSchemaRegistry:
    """Registry of event schemas for versioning."""

    _schemas: dict[str, EventSchema] = {}

    @classmethod
    def register(cls, schema: EventSchema) -> None:
        """Register an event schema."""
        key = f"{schema.event_type}:{schema.version}"
        cls._schemas[key] = schema

    @classmethod
    def get(cls, event_type: str, version: str = SCHEMA_VERSION) -> EventSchema | None:
        """Get schema for event type."""
        key = f"{event_type}:{version}"
        return cls._schemas.get(key)

    @classmethod
    def get_versions(cls, event_type: str) -> list[str]:
        """Get all versions for an event type."""
        return [k.split(":")[1] for k in cls._schemas if k.startswith(f"{event_type}:")]


# ============================================================================
# Base Event
# ============================================================================


@dataclass
class DomainEvent:
    """Base class for all domain events.

    All events include:
    - Unique ID for tracing
    - Correlation ID for request tracing
    - Timestamp
    - Schema version for compatibility
    - Source information
    """

    # Identity
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""

    # Tracing
    correlation_id: str | None = None
    causation_id: str | None = None

    # Timestamps
    timestamp: datetime = field(default_factory=datetime.now)
    occurred_at: datetime = field(default_factory=datetime.now)

    # Schema
    schema_version: str = SCHEMA_VERSION

    # Source
    source: str = ""  # Component that generated the event
    source_version: str = ""

    # Session
    session_id: str | None = None

    # Error handling
    retry_count: int = 0
    max_retries: int = 3

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "timestamp": self.timestamp.isoformat(),
            "schema_version": self.schema_version,
            "source": self.source,
            "source_version": self.source_version,
            "session_id": self.session_id,
            "retry_count": self.retry_count,
        }

    def to_json(self) -> str:
        """Convert event to JSON string."""
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DomainEvent:
        """Create event from dictionary."""
        event = cls()
        event.event_id = data.get("event_id", event.event_id)
        event.event_type = data.get("event_type", "")
        event.correlation_id = data.get("correlation_id")
        event.causation_id = data.get("causation_id")
        event.schema_version = data.get("schema_version", SCHEMA_VERSION)
        event.source = data.get("source", "")
        event.source_version = data.get("source_version", "")
        event.session_id = data.get("session_id")
        event.retry_count = data.get("retry_count", 0)

        if "timestamp" in data:
            if isinstance(data["timestamp"], str):
                event.timestamp = datetime.fromisoformat(data["timestamp"])
            else:
                event.timestamp = data["timestamp"]

        return event


# ============================================================================
# Hardware-Specific Events
# ============================================================================


@dataclass
class TargetEvent(DomainEvent):
    """Base class for target-related events."""

    target_id: str = ""
    target_name: str = ""
    target_state: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "target_id": self.target_id,
            "target_name": self.target_name,
            "target_state": self.target_state,
        })
        return data


@dataclass
class TargetDiscoveredEvent(TargetEvent):
    """Target was discovered (probe connected or auto-detected)."""

    probe_serial: str | None = None
    probe_type: str = ""
    chip_family: str = ""
    confidence: float = 1.0

    def __post_init__(self) -> None:
        """Initialize event type."""
        self.event_type = EventType.TARGET_DISCOVERED.value
        super().__post_init__()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "probe_serial": self.probe_serial,
            "probe_type": self.probe_type,
            "chip_family": self.chip_family,
            "confidence": self.confidence,
        })
        return data


@dataclass
class TargetConnectedEvent(TargetEvent):
    """Target was connected."""

    probe_serial: str | None = None
    connection_time_ms: float = 0.0

    def __post_init__(self) -> None:
        """Initialize event type."""
        self.event_type = EventType.TARGET_CONNECTED.value
        super().__post_init__()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "probe_serial": self.probe_serial,
            "connection_time_ms": self.connection_time_ms,
        })
        return data


@dataclass
class TargetFaultEvent(TargetEvent):
    """Target entered fault state."""

    fault_type: str = ""
    fault_address: int = 0
    registers: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize event type."""
        self.event_type = EventType.TARGET_FAULT.value
        super().__post_init__()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "fault_type": self.fault_type,
            "fault_address": hex(self.fault_address) if self.fault_address else None,
            "registers": {k: hex(v) for k, v in self.registers.items()},
        })
        return data


@dataclass
class SnapshotEvent(DomainEvent):
    """Base class for snapshot events."""

    snapshot_id: str = ""
    target_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "snapshot_id": self.snapshot_id,
            "target_name": self.target_name,
        })
        return data


@dataclass
class SnapshotCapturedEvent(SnapshotEvent):
    """Snapshot was captured."""

    capture_time_ms: float = 0.0
    size_bytes: int = 0
    is_incremental: bool = False
    parent_snapshot_id: str | None = None

    def __post_init__(self) -> None:
        """Initialize event type."""
        self.event_type = EventType.SNAPSHOT_CAPTURED.value
        super().__post_init__()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "capture_time_ms": self.capture_time_ms,
            "size_bytes": self.size_bytes,
            "is_incremental": self.is_incremental,
            "parent_snapshot_id": self.parent_snapshot_id,
        })
        return data


@dataclass
class CapabilityNegotiatedEvent(DomainEvent):
    """Capability negotiation completed."""

    target_id: str = ""
    probe_id: str = ""
    selected_method: str = ""
    usable_capabilities: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Initialize event type."""
        self.event_type = EventType.CAPABILITY_NEGOTIATED.value
        super().__post_init__()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "target_id": self.target_id,
            "probe_id": self.probe_id,
            "selected_method": self.selected_method,
            "usable_capabilities": self.usable_capabilities,
        })
        return data


@dataclass
class PluginEvent(DomainEvent):
    """Base class for plugin events."""

    plugin_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data["plugin_name"] = self.plugin_name
        return data


@dataclass
class PluginLoadedEvent(PluginEvent):
    """Plugin was loaded."""

    plugin_version: str = ""

    def __post_init__(self) -> None:
        """Initialize event type."""
        self.event_type = EventType.PLUGIN_LOADED.value
        super().__post_init__()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data["plugin_version"] = self.plugin_version
        return data


@dataclass
class PluginErrorEvent(PluginEvent):
    """Plugin encountered an error."""

    error_code: str = ""
    error_message: str = ""
    is_fatal: bool = False

    def __post_init__(self) -> None:
        """Initialize event type."""
        self.event_type = EventType.PLUGIN_ERROR.value
        super().__post_init__()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "error_code": self.error_code,
            "error_message": self.error_message,
            "is_fatal": self.is_fatal,
        })
        return data


# ============================================================================
# Event Handler Types
# ============================================================================


EventHandler = Callable[[DomainEvent], Awaitable[None]] | Callable[[DomainEvent], None]

HandlerSubscription = tuple[str, EventHandler, str | None]  # (event_type, handler, version_range)


# ============================================================================
# Dead Letter Queue
# ============================================================================


@dataclass
class DLQEntry:
    """Entry in the dead letter queue."""

    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    error_type: str = ""
    handler_name: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    original_event_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entry_id": self.entry_id,
            "event": self.event,
            "error": self.error,
            "error_type": self.error_type,
            "handler_name": self.handler_name,
            "timestamp": self.timestamp.isoformat(),
            "retry_count": self.retry_count,
            "original_event_id": self.original_event_id,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


class DeadLetterQueue(ABC):
    """Abstract dead letter queue for failed events."""

    @abstractmethod
    async def push(self, entry: DLQEntry) -> None:
        """Push entry to DLQ."""
        ...

    @abstractmethod
    async def pop(self) -> DLQEntry | None:
        """Pop entry from DLQ."""
        ...

    @abstractmethod
    async def size(self) -> int:
        """Get DLQ size."""
        ...

    @abstractmethod
    async def clear(self) -> None:
        """Clear DLQ."""
        ...

    @abstractmethod
    async def peek(self, count: int = 10) -> list[DLQEntry]:
        """Peek at DLQ entries."""
        ...


class FileDeadLetterQueue(DeadLetterQueue):
    """File-based DLQ implementation."""

    def __init__(self, directory: Path, max_size: int = 10000) -> None:
        """Initialize file DLQ.

        Args:
            directory: Directory to store DLQ files
            max_size: Maximum number of entries
        """
        self._directory = directory
        self._max_size = max_size
        self._directory.mkdir(parents=True, exist_ok=True)
        self._queue: list[DLQEntry] = []
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Load entries from disk."""
        for file_path in sorted(self._directory.glob("*.dlq")):
            try:
                with open(file_path) as f:
                    entry = json.load(f)
                    self._queue.append(DLQEntry(**entry))
            except Exception:
                pass

    def _get_file_path(self, entry: DLQEntry) -> Path:
        """Get file path for entry."""
        return self._directory / f"{entry.entry_id}.dlq"

    async def push(self, entry: DLQEntry) -> None:
        """Push entry to DLQ."""
        if len(self._queue) >= self._max_size:
            oldest = self._queue.pop(0)
            old_file = self._get_file_path(oldest)
            if old_file.exists():
                old_file.unlink()

        self._queue.append(entry)
        file_path = self._get_file_path(entry)
        with open(file_path, "w") as f:
            json.dump(entry.to_dict(), f, default=str)

    async def pop(self) -> DLQEntry | None:
        """Pop entry from DLQ."""
        if not self._queue:
            return None

        entry = self._queue.pop(0)
        file_path = self._get_file_path(entry)
        if file_path.exists():
            file_path.unlink()

        return entry

    async def size(self) -> int:
        """Get DLQ size."""
        return len(self._queue)

    async def clear(self) -> None:
        """Clear DLQ."""
        for entry in self._queue:
            file_path = self._get_file_path(entry)
            if file_path.exists():
                file_path.unlink()
        self._queue.clear()

    async def peek(self, count: int = 10) -> list[DLQEntry]:
        """Peek at DLQ entries."""
        return self._queue[:count]


class InMemoryDeadLetterQueue(DeadLetterQueue):
    """In-memory DLQ implementation (for testing)."""

    def __init__(self, max_size: int = 1000) -> None:
        """Initialize in-memory DLQ."""
        self._queue: list[DLQEntry] = []
        self._max_size = max_size

    async def push(self, entry: DLQEntry) -> None:
        """Push entry to DLQ."""
        if len(self._queue) >= self._max_size:
            self._queue.pop(0)
        self._queue.append(entry)

    async def pop(self) -> DLQEntry | None:
        """Pop entry from DLQ."""
        if not self._queue:
            return None
        return self._queue.pop(0)

    async def size(self) -> int:
        """Get DLQ size."""
        return len(self._queue)

    async def clear(self) -> None:
        """Clear DLQ."""
        self._queue.clear()

    async def peek(self, count: int = 10) -> list[DLQEntry]:
        """Peek at DLQ entries."""
        return self._queue[:count]


# ============================================================================
# Event Bus Interface
# ============================================================================


class EventBus(ABC):
    """Abstract event bus interface."""

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        """Publish an event to the bus."""
        ...

    @abstractmethod
    async def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
        version_range: str | None = None,
    ) -> str:
        """Subscribe to an event type.

        Returns:
            Subscription ID
        """
        ...

    @abstractmethod
    async def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe from an event."""
        ...

    @abstractmethod
    async def get_dlq_size(self) -> int:
        """Get dead letter queue size."""
        ...

    @abstractmethod
    async def drain_dlq(self, count: int = 100) -> list[DLQEntry]:
        """Drain entries from DLQ."""
        ...


# ============================================================================
# Event Bus Implementation
# ============================================================================


class AsyncEventBus(EventBus):
    """Async event bus with pub/sub pattern.

    Features:
    - Async handlers with configurable timeout
    - Dead letter queue for failed events
    - Version-aware handlers
    - Correlation ID propagation
    - Metrics collection
    """

    def __init__(
        self,
        dlq: DeadLetterQueue | None = None,
        default_timeout: float = 30.0,
        enable_metrics: bool = True,
    ) -> None:
        """Initialize event bus.

        Args:
            dlq: Dead letter queue (defaults to in-memory)
            default_timeout: Default handler timeout in seconds
            enable_metrics: Enable metrics collection
        """
        self._dlq = dlq or InMemoryDeadLetterQueue()
        self._default_timeout = default_timeout
        self._enable_metrics = enable_metrics

        # Subscriptions: event_type -> list of (sub_id, handler, version_range)
        self._subscriptions: dict[str, list[tuple[str, EventHandler, str | None]]] = {}

        # Subscription metadata
        self._subscription_info: dict[str, dict[str, Any]] = {}

        # Metrics
        self._metrics = {
            "published": 0,
            "delivered": 0,
            "failed": 0,
            "dlq_size": 0,
        }

        # Lock for thread safety
        self._lock = asyncio.Lock()

    async def publish(self, event: DomainEvent) -> None:
        """Publish an event to the bus."""
        async with self._lock:
            self._metrics["published"] += 1

        event_type = event.event_type
        if event_type not in self._subscriptions:
            logger.debug(f"No subscribers for event type: {event_type}")
            return

        async with self._lock:
            subscriptions = self._subscriptions.get(event_type, []).copy()

        # Deliver to all subscribers
        for sub_id, handler, version_range in subscriptions:
            try:
                # Check version compatibility
                if version_range and not self._check_version(event, version_range):
                    continue

                # Execute handler with timeout
                await asyncio.wait_for(
                    self._execute_handler(handler, event),
                    timeout=self._default_timeout,
                )

                async with self._lock:
                    self._metrics["delivered"] += 1

            except asyncio.TimeoutError:
                logger.warning(f"Handler timeout for {event_type}, subscription {sub_id}")
                await self._handle_failure(event, sub_id, "Handler timeout")

            except Exception as e:
                logger.exception(f"Handler error for {event_type}, subscription {sub_id}: {e}")
                await self._handle_failure(event, sub_id, str(e))

    async def _execute_handler(self, handler: EventHandler, event: DomainEvent) -> None:
        """Execute event handler."""
        result = handler(event)
        if asyncio.iscoroutine(result):
            await result

    def _check_version(self, event: DomainEvent, version_range: str) -> bool:
        """Check if event version matches handler version range."""
        # Simple version matching (can be enhanced with semver)
        if version_range == "*":
            return True
        if version_range == event.schema_version:
            return True
        return True  # Default to accepting all versions

    async def _handle_failure(self, event: DomainEvent, subscription_id: str, error: str) -> None:
        """Handle handler failure."""
        async with self._lock:
            self._metrics["failed"] += 1

        event.retry_count += 1

        if event.retry_count >= event.max_retries:
            # Move to DLQ
            dlq_entry = DLQEntry(
                event=event.to_dict(),
                error=error,
                error_type="HandlerError",
                handler_name=subscription_id,
                original_event_id=event.event_id,
            )
            await self._dlq.push(dlq_entry)

            async with self._lock:
                self._metrics["dlq_size"] = await self._dlq.size()

            logger.warning(f"Event {event.event_id} moved to DLQ after {event.max_retries} retries")

    async def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
        version_range: str | None = None,
        handler_name: str | None = None,
    ) -> str:
        """Subscribe to an event type.

        Args:
            event_type: Event type to subscribe to
            handler: Handler function
            version_range: Version range (e.g., "1.0", ">=1.0,<2.0")
            handler_name: Optional name for the handler

        Returns:
            Subscription ID
        """
        sub_id = str(uuid.uuid4())

        async with self._lock:
            if event_type not in self._subscriptions:
                self._subscriptions[event_type] = []

            self._subscriptions[event_type].append((sub_id, handler, version_range))

            self._subscription_info[sub_id] = {
                "event_type": event_type,
                "version_range": version_range,
                "handler_name": handler_name or "anonymous",
                "subscribed_at": datetime.now().isoformat(),
            }

        logger.debug(f"Subscribed to {event_type} with subscription {sub_id}")
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe from an event."""
        async with self._lock:
            for event_type, subs in self._subscriptions.items():
                self._subscriptions[event_type] = [
                    (sid, h, v) for sid, h, v in subs if sid != subscription_id
                ]

            if subscription_id in self._subscription_info:
                del self._subscription_info[subscription_id]

        logger.debug(f"Unsubscribed from {subscription_id}")

    async def get_dlq_size(self) -> int:
        """Get dead letter queue size."""
        return await self._dlq.size()

    async def drain_dlq(self, count: int = 100) -> list[DLQEntry]:
        """Drain entries from DLQ."""
        entries = []
        for _ in range(count):
            entry = await self._dlq.pop()
            if entry is None:
                break
            entries.append(entry)

        async with self._lock:
            self._metrics["dlq_size"] = await self._dlq.size()

        return entries

    def get_metrics(self) -> dict[str, int]:
        """Get event bus metrics."""
        return self._metrics.copy()

    def get_subscriptions(self, event_type: str | None = None) -> dict[str, Any]:
        """Get subscription information."""
        if event_type:
            subs = self._subscriptions.get(event_type, [])
            return {
                "event_type": event_type,
                "count": len(subs),
                "subscriptions": [
                    {"id": sid, "version_range": v, **self._subscription_info.get(sid, {})}
                    for sid, _, v in subs
                ],
            }

        return {
            "total_event_types": len(self._subscriptions),
            "total_subscriptions": sum(len(s) for s in self._subscriptions.values()),
            "by_type": {
                et: len(subs)
                for et, subs in self._subscriptions.items()
            },
        }


# ============================================================================
# Event Bus Factory
# ============================================================================


def create_event_bus(
    backend: str = "memory",
    dlq_path: Path | None = None,
    **kwargs: Any,
) -> EventBus:
    """Create an event bus with specified backend.

    Args:
        backend: "memory" or "file"
        dlq_path: Path for file-based DLQ
        **kwargs: Additional arguments

    Returns:
        EventBus instance
    """
    if backend == "file":
        dlq = FileDeadLetterQueue(dlq_path or Path("./dlq"))
    else:
        dlq = InMemoryDeadLetterQueue()

    return AsyncEventBus(dlq=dlq, **kwargs)


# ============================================================================
# Event Decorators
# ============================================================================


def event_handler(
    event_type: str,
    version_range: str | None = None,
) -> Callable[[EventHandler], EventHandler]:
    """Decorator for event handlers.

    Usage:
        @event_handler("target.connected")
        async def on_target_connected(event):
            print(f"Target connected: {event.target_name}")
    """
    def decorator(handler: EventHandler) -> EventHandler:
        handler._event_type = event_type  # type: ignore
        handler._version_range = version_range  # type: ignore
        return handler
    return decorator
