"""
Event Data Structure

Core event class for AI_support event-driven runtime.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from .types import EventType


@dataclass
class Event:
    """
    Core event class for src.

    All events in the system follow this structure for consistency
    and traceability.

    Attributes:
        type: Event type from EventType enum
        source: Source component that emitted the event
        data: Event payload (dict of any data)
        correlation_id: ID for tracing related events
        timestamp: When the event was created
        id: Unique event identifier
        parent_id: Parent event ID (for event chains)
        metadata: Additional metadata (tags, priority, etc.)
    """

    type: EventType
    source: str
    data: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=lambda: str(uuid4()))
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate event after initialization."""
        if not self.source:
            raise ValueError("Event source is required")
        if self.correlation_id is None:
            self.correlation_id = self.id

    def with_metadata(self, **kwargs) -> "Event":
        """Add metadata to event (immutable)."""
        new_metadata = {**self.metadata, **kwargs}
        return dataclass_replace(self, metadata=new_metadata)

    def with_correlation_id(self, correlation_id: str) -> "Event":
        """Set correlation ID (immutable)."""
        return dataclass_replace(self, correlation_id=correlation_id)

    def with_parent(self, parent_id: str) -> "Event":
        """Set parent event ID (immutable)."""
        return dataclass_replace(self, parent_id=parent_id)

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "parent_id": self.parent_id,
            "data": self.data,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """Create event from dictionary."""
        return cls(
            id=data["id"],
            type=EventType(data["type"]),
            source=data["source"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            correlation_id=data.get("correlation_id"),
            parent_id=data.get("parent_id"),
            data=data.get("data", {}),
            metadata=data.get("metadata", {}),
        )


@dataclass
class EventContext:
    """
    Context object passed through event handlers.

    Allows handlers to share state and modify event flow.
    """

    event: Event
    handled: bool = False
    stopped: bool = False
    error: Optional[Exception] = None
    results: Dict[str, Any] = field(default_factory=dict)

    def stop_propagation(self):
        """Stop event from propagating to other handlers."""
        self.stopped = True

    def mark_handled(self, result: Any = None):
        """Mark event as handled."""
        self.handled = True
        if result is not None:
            self.results["handler_result"] = result

    def set_error(self, error: Exception):
        """Set error in context."""
        self.error = error
        self.stop_propagation()


def dataclass_replace(obj, **kwargs):
    """Create a new dataclass instance with updated fields."""
    from dataclasses import replace
    return replace(obj, **kwargs)


# Factory functions for common events
def create_task_event(
    task_id: str,
    task_type: str,
    action: EventType,
    source: str,
    **kwargs
) -> Event:
    """Create a task-related event."""
    if not action.name.startswith("TASK_"):
        raise ValueError(f"Invalid task event type: {action}")
    return Event(
        type=action,
        source=source,
        data={"task_id": task_id, "task_type": task_type, **kwargs},
    )


def create_llm_event(
    provider: str,
    action: EventType,
    source: str,
    **kwargs
) -> Event:
    """Create an LLM-related event."""
    if not action.name.startswith("LLM_"):
        raise ValueError(f"Invalid LLM event type: {action}")
    return Event(
        type=action,
        source=source,
        data={"provider": provider, **kwargs},
    )


def create_retrieval_event(
    query: str,
    action: EventType,
    source: str,
    **kwargs
) -> Event:
    """Create a retrieval-related event."""
    if not action.name.startswith("RETRIEVAL_"):
        raise ValueError(f"Invalid retrieval event type: {action}")
    return Event(
        type=action,
        source=source,
        data={"query": query, **kwargs},
    )


def create_tool_event(
    tool_name: str,
    action: EventType,
    source: str,
    **kwargs
) -> Event:
    """Create a tool-related event."""
    if not action.name.startswith("TOOL_"):
        raise ValueError(f"Invalid tool event type: {action}")
    return Event(
        type=action,
        source=source,
        data={"tool_name": tool_name, **kwargs},
    )


def create_workflow_event(
    workflow_id: str,
    action: EventType,
    source: str,
    **kwargs
) -> Event:
    """Create a workflow-related event."""
    if not action.name.startswith("WORKFLOW_"):
        raise ValueError(f"Invalid workflow event type: {action}")
    return Event(
        type=action,
        source=source,
        data={"workflow_id": workflow_id, **kwargs},
    )
