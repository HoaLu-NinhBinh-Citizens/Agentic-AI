"""
Event Handlers

Built-in event handlers for common use cases.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .event import Event
from .types import EventType

logger = logging.getLogger(__name__)


class EventHandler(ABC):
    """
    Abstract base class for event handlers.

    Handlers receive events and perform specific actions.
    """

    @abstractmethod
    def handle(self, event: Event) -> Any:
        """
        Handle an event.

        Args:
            event: Event to handle

        Returns:
            Handler result (optional)
        """
        pass

    async def handle_async(self, event: Event) -> Any:
        """
        Async version of handle.

        Default implementation calls sync handle.

        Args:
            event: Event to handle

        Returns:
            Handler result (optional)
        """
        return self.handle(event)


class LoggingHandler(EventHandler):
    """
    Handler that logs events to various outputs.

    Features:
    - Configurable log levels
    - Event filtering
    - Formatted output
    """

    def __init__(
        self,
        min_level: int = logging.INFO,
        format_template: str = "[{type}] {source}: {data}",
        filter_types: Optional[List[EventType]] = None,
    ):
        """
        Initialize logging handler.

        Args:
            min_level: Minimum log level
            format_template: Format template for log messages
            filter_types: Only log these event types (None = all)
        """
        self.min_level = min_level
        self.format_template = format_template
        self.filter_types = set(filter_types or [])
        self.logger = logging.getLogger("event.handler")

    def handle(self, event: Event) -> None:
        """Log the event."""
        # Check filter
        if self.filter_types and event.type not in self.filter_types:
            return

        # Format message
        try:
            message = self.format_template.format(
                type=event.type.value,
                source=event.source,
                data=event.data,
                timestamp=event.timestamp.isoformat(),
            )
        except KeyError:
            message = f"{event.type.value} from {event.source}"

        self.logger.log(self.min_level, message)


class MetricsHandler(EventHandler):
    """
    Handler that collects event metrics.

    Features:
    - Event counts
    - Timing statistics
    - Error tracking
    - Historical buffer
    """

    def __init__(
        self,
        history_size: int = 1000,
        collect_timing: bool = True,
    ):
        """
        Initialize metrics handler.

        Args:
            history_size: Number of events to keep in history
            collect_timing: Whether to collect timing stats
        """
        self.history_size = history_size
        self.collect_timing = collect_timing
        self._history: deque = deque(maxlen=history_size)
        self._counts: Dict[EventType, int] = {}
        self._errors: Dict[EventType, int] = {}
        self._total_count = 0
        self._start_time = datetime.now()

    def handle(self, event: Event) -> None:
        """Record event metrics."""
        self._total_count += 1
        self._counts[event.type] = self._counts.get(event.type, 0) + 1

        # Record in history
        record = {
            "type": event.type.value,
            "source": event.source,
            "timestamp": event.timestamp,
            "correlation_id": event.correlation_id,
        }

        if self.collect_timing:
            record["processing_time_ms"] = 0  # Will be updated if tracked

        self._history.append(record)

    def record_error(self, event_type: EventType) -> None:
        """Record an error for event type."""
        self._errors[event_type] = self._errors.get(event_type, 0) + 1

    def get_stats(self) -> Dict[str, Any]:
        """Get collected statistics."""
        uptime = (datetime.now() - self._start_time).total_seconds()
        return {
            "total_events": self._total_count,
            "events_per_second": self._total_count / max(uptime, 1),
            "event_counts": dict(self._counts),
            "error_counts": dict(self._errors),
            "uptime_seconds": uptime,
            "history_size": len(self._history),
        }

    def get_recent_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent events from history."""
        return list(self._history)[-limit:]


class AlertHandler(EventHandler):
    """
    Handler that triggers alerts based on events.

    Features:
    - Configurable alert conditions
    - Multiple alert channels
    - Alert deduplication
    - Severity levels
    """

    class Severity:
        DEBUG = "debug"
        INFO = "info"
        WARNING = "warning"
        ERROR = "error"
        CRITICAL = "critical"

    def __init__(
        self,
        conditions: Optional[List[Callable[[Event], bool]]] = None,
        channels: Optional[List[Callable]] = None,
        dedup_window_seconds: float = 60.0,
    ):
        """
        Initialize alert handler.

        Args:
            conditions: List of condition functions (Event -> bool)
            channels: List of alert channel functions
            dedup_window_seconds: Deduplication window
        """
        self.conditions = conditions or []
        self.channels = channels or []
        self.dedup_window = dedup_window_seconds
        self._alert_history: Dict[str, datetime] = {}

    def handle(self, event: Event) -> Optional[Dict[str, Any]]:
        """Check conditions and trigger alerts."""
        # Check all conditions
        triggered = all(condition(event) for condition in self.conditions)

        if not triggered:
            return None

        # Check deduplication
        alert_key = self._get_alert_key(event)
        if self._is_deduplicated(alert_key):
            return None

        # Build alert
        alert = {
            "event": event.type.value,
            "source": event.source,
            "timestamp": event.timestamp.isoformat(),
            "data": event.data,
            "severity": self.Severity.WARNING,
        }

        # Send to channels
        for channel in self.channels:
            try:
                if asyncio.iscoroutinefunction(channel):
                    asyncio.create_task(channel(alert))
                else:
                    channel(alert)
            except Exception as e:
                logger.error(f"Alert channel error: {e}")

        # Record alert
        self._record_alert(alert_key)
        return alert

    def _get_alert_key(self, event: Event) -> str:
        """Generate alert key for deduplication."""
        return f"{event.type.value}:{event.source}"

    def _is_deduplicated(self, key: str) -> bool:
        """Check if alert should be deduplicated."""
        import time
        now = time.time()

        if key in self._alert_history:
            last_alert = self._alert_history[key]
            if now - last_alert.timestamp() < self.dedup_window:
                return True

        return False

    def _record_alert(self, key: str) -> None:
        """Record alert for deduplication."""
        import time
        self._alert_history[key] = type("AlertTime", (), {"timestamp": lambda: time.time()})()


class BufferHandler(EventHandler):
    """
    Handler that buffers events for batch processing.

    Features:
    - Configurable buffer size
    - Flush on size or time threshold
    - Batch processing callback
    """

    def __init__(
        self,
        buffer_size: int = 100,
        flush_interval_seconds: float = 5.0,
        on_flush: Optional[Callable[[List[Event]], None]] = None,
    ):
        """
        Initialize buffer handler.

        Args:
            buffer_size: Max events before auto-flush
            flush_interval_seconds: Time threshold for flush
            on_flush: Callback when buffer flushes
        """
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval_seconds
        self.on_flush = on_flush
        self._buffer: List[Event] = []
        self._last_flush = datetime.now()

    def handle(self, event: Event) -> None:
        """Buffer the event."""
        self._buffer.append(event)

        # Check if should flush
        should_flush = (
            len(self._buffer) >= self.buffer_size or
            self._should_flush_by_time()
        )

        if should_flush:
            self.flush()

    def flush(self) -> List[Event]:
        """Flush buffer and return events."""
        events = self._buffer.copy()
        self._buffer.clear()
        self._last_flush = datetime.now()

        if self.on_flush and events:
            try:
                self.on_flush(events)
            except Exception as e:
                logger.error(f"Buffer flush error: {e}")

        return events

    def _should_flush_by_time(self) -> bool:
        """Check if should flush by time threshold."""
        elapsed = (datetime.now() - self._last_flush).total_seconds()
        return elapsed >= self.flush_interval

    @property
    def buffer(self) -> List[Event]:
        """Get current buffer contents."""
        return self._buffer.copy()


class TaskStateHandler(EventHandler):
    """
    Handler that tracks task state transitions.

    Features:
    - Task state tracking
    - State transition validation
    - Task history
    """

    class TaskState:
        PENDING = "pending"
        RUNNING = "running"
        COMPLETED = "completed"
        FAILED = "failed"
        CANCELLED = "cancelled"

    def __init__(self):
        self._task_states: Dict[str, str] = {}
        self._task_history: Dict[str, List[Dict]] = {}
        self._pending_tasks: List[str] = []
        self._running_tasks: List[str] = []

    def handle(self, event: Event) -> None:
        """Track task state from src.core.events."""
        task_id = event.data.get("task_id")

        if not task_id:
            return

        # Track state transitions
        if event.type == EventType.TASK_RECEIVED:
            self._set_state(task_id, self.TaskState.PENDING)
            self._pending_tasks.append(task_id)

        elif event.type == EventType.TASK_STARTED:
            self._set_state(task_id, self.TaskState.RUNNING)
            if task_id in self._pending_tasks:
                self._pending_tasks.remove(task_id)
            if task_id not in self._running_tasks:
                self._running_tasks.append(task_id)

        elif event.type == EventType.TASK_COMPLETED:
            self._set_state(task_id, self.TaskState.COMPLETED)
            self._running_tasks = [t for t in self._running_tasks if t != task_id]

        elif event.type == EventType.TASK_FAILED:
            self._set_state(task_id, self.TaskState.FAILED)
            self._running_tasks = [t for t in self._running_tasks if t != task_id]

        elif event.type == EventType.TASK_CANCELLED:
            self._set_state(task_id, self.TaskState.CANCELLED)
            self._running_tasks = [t for t in self._running_tasks if t != task_id]
            self._pending_tasks = [t for t in self._pending_tasks if t != task_id]

    def _set_state(self, task_id: str, state: str) -> None:
        """Set task state and record history."""
        self._task_states[task_id] = state

        if task_id not in self._task_history:
            self._task_history[task_id] = []

        self._task_history[task_id].append({
            "state": state,
            "timestamp": datetime.now(),
            "event_type": EventType.TASK_PROGRESS.value,
        })

    def get_task_state(self, task_id: str) -> Optional[str]:
        """Get current state of a task."""
        return self._task_states.get(task_id)

    def get_pending_tasks(self) -> List[str]:
        """Get list of pending tasks."""
        return self._pending_tasks.copy()

    def get_running_tasks(self) -> List[str]:
        """Get list of running tasks."""
        return self._running_tasks.copy()

    def get_task_history(self, task_id: str) -> List[Dict]:
        """Get state history for a task."""
        return self._task_history.get(task_id, []).copy()


class ErrorTrackingHandler(EventHandler):
    """
    Handler that tracks and analyzes errors.

    Features:
    - Error categorization
    - Error frequency tracking
    - Error patterns detection
    """

    def __init__(self, pattern_window: int = 100):
        """
        Initialize error tracking handler.

        Args:
            pattern_window: Number of events to analyze for patterns
        """
        self.pattern_window = pattern_window
        self._error_log: deque = deque(maxlen=pattern_window)
        self._error_counts: Dict[str, int] = {}
        self._errors_by_source: Dict[str, Dict[str, int]] = {}

    def handle(self, event: Event) -> None:
        """Track error from failed events."""
        if event.type not in {
            EventType.TASK_FAILED,
            EventType.LLM_REQUEST_FAILED,
            EventType.RETRIEVAL_FAILED,
            EventType.TOOL_EXECUTION_FAILED,
            EventType.WORKFLOW_FAILED,
            EventType.SYSTEM_ERROR,
        }:
            return

        error_type = event.data.get("error_type", "unknown")
        error_msg = event.data.get("error", str(event.data))

        # Record error
        self._error_log.append({
            "type": event.type.value,
            "error_type": error_type,
            "message": error_msg[:200],  # Truncate
            "source": event.source,
            "timestamp": event.timestamp,
        })

        # Update counts
        self._error_counts[error_type] = self._error_counts.get(error_type, 0) + 1

        if event.source not in self._errors_by_source:
            self._errors_by_source[event.source] = {}
        self._errors_by_source[event.source][error_type] = (
            self._errors_by_source[event.source].get(error_type, 0) + 1
        )

    def get_error_summary(self) -> Dict[str, Any]:
        """Get error summary."""
        return {
            "total_errors": len(self._error_log),
            "error_counts": dict(self._error_counts),
            "errors_by_source": dict(self._errors_by_source),
            "recent_errors": list(self._error_log)[-10:],
        }

    def get_top_errors(self, limit: int = 5) -> List[tuple]:
        """Get most frequent errors."""
        return sorted(
            self._error_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]


# Handler factory functions
def create_task_state_handler() -> TaskStateHandler:
    """Create task state tracking handler."""
    return TaskStateHandler()


def create_error_tracking_handler() -> ErrorTrackingHandler:
    """Create error tracking handler."""
    return ErrorTrackingHandler()


def create_metrics_handler() -> MetricsHandler:
    """Create metrics collection handler."""
    return MetricsHandler()


def create_alert_handler(
    alert_channels: Optional[List[Callable]] = None,
) -> AlertHandler:
    """Create alert handler."""
    return AlertHandler(channels=alert_channels or [])
