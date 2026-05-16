"""
Event Middleware

Middleware for event processing pipeline.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from .event import Event
from .types import EventType

logger = logging.getLogger(__name__)


class EventMiddleware(ABC):
    """
    Abstract base class for event middleware.

    Middleware can intercept events before and after processing.
    """

    @abstractmethod
    def on_emit(self, event: Event) -> Optional[Event]:
        """
        Called before event handlers execute.

        Return modified event or None to stop propagation.

        Args:
            event: Event to process

        Returns:
            Modified event or None
        """
        pass

    def after_emit(self, event: Event) -> None:
        """
        Called after all handlers complete.

        Args:
            event: Event that was processed
        """
        pass

    async def on_emit_async(self, event: Event) -> Optional[Event]:
        """Async version of on_emit."""
        return self.on_emit(event)

    async def after_emit_async(self, event: Event) -> None:
        """Async version of after_emit."""
        self.after_emit(event)


class LoggingMiddleware(EventMiddleware):
    """
    Middleware for logging events.

    Features:
    - Configurable log levels per event type
    - Log formatting options
    - Rate limiting for noisy events
    """

    def __init__(
        self,
        log_level: int = logging.DEBUG,
        log_format: str = "[{timestamp}] {type}: {source} - {data}",
        rate_limit: Optional[Dict[EventType, int]] = None,
    ):
        """
        Initialize logging middleware.

        Args:
            log_level: Default log level
            log_format: Format string for log messages
            rate_limit: Max events per second per event type
        """
        self.log_level = log_level
        self.log_format = log_format
        self.rate_limit = rate_limit or {}
        self._last_log_time: Dict[EventType, float] = {}
        self._min_interval: Dict[EventType, float] = {
            et: 1.0 / rate for et, rate in (rate_limit or {}).items()
        }

    def on_emit(self, event: Event) -> Optional[Event]:
        """Log event before processing."""
        # Check rate limiting
        if event.type in self._min_interval:
            now = time.time()
            last = self._last_log_time.get(event.type, 0)
            if now - last < self._min_interval[event.type]:
                return event  # Skip logging due to rate limit
            self._last_log_time[event.type] = now

        # Determine log level for this event type
        level = self.log_level

        # Format message
        try:
            message = self.log_format.format(
                timestamp=event.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                type=event.type.value,
                source=event.source,
                data=self._format_data(event.data),
                correlation_id=event.correlation_id,
            )
        except KeyError:
            message = f"{event.type.value} from {event.source}"

        # Log
        logger.log(level, message)
        return event

    def _format_data(self, data: Dict[str, Any]) -> str:
        """Format event data for logging."""
        if not data:
            return ""
        if len(data) <= 3:
            return str(data)
        # Truncate long data
        return str({k: (v[:50] + "..." if isinstance(v, str) and len(v) > 50 else v)
                     for k, v in list(data.items())[:5]})


class MetricsMiddleware(EventMiddleware):
    """
    Middleware for collecting event metrics.

    Collects:
    - Event counts by type
    - Event throughput (events/second)
    - Handler execution times
    - Error rates
    """

    def __init__(self, window_size: int = 60):
        """
        Initialize metrics middleware.

        Args:
            window_size: Time window for rate calculations (seconds)
        """
        self.window_size = window_size
        self._event_counts: Dict[EventType, int] = defaultdict(int)
        self._event_times: Dict[EventType, List[float]] = defaultdict(list)
        self._error_counts: Dict[EventType, int] = defaultdict(int)
        self._total_events = 0
        self._start_time = time.time()
        self._lock = asyncio.Lock()

    def on_emit(self, event: Event) -> Optional[Event]:
        """Record event metrics."""
        self._event_counts[event.type] += 1
        self._total_events += 1
        return event

    def record_handler_time(self, event_type: EventType, duration: float) -> None:
        """Record handler execution time."""
        self._event_times[event_type].append(duration)
        # Keep only recent times
        cutoff = time.time() - self.window_size
        self._event_times[event_type] = [
            t for t in self._event_times[event_type] if t > cutoff
        ]

    def record_error(self, event_type: EventType) -> None:
        """Record an error for an event type."""
        self._error_counts[event_type] += 1

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        elapsed = time.time() - self._start_time
        return {
            "total_events": self._total_events,
            "events_per_second": self._total_events / max(elapsed, 1),
            "event_counts": dict(self._event_counts),
            "error_counts": dict(self._error_counts),
            "uptime_seconds": elapsed,
            "recent_types": self._get_recent_types(),
        }

    def _get_recent_types(self) -> List[str]:
        """Get most frequent event types recently."""
        sorted_types = sorted(
            self._event_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return [et.value for et, count in sorted_types[:10]]

    def get_event_rate(self, event_type: EventType) -> float:
        """Get events per second for a specific type."""
        times = self._event_times.get(event_type, [])
        if not times:
            return 0.0
        return len(times) / self.window_size

    def get_error_rate(self, event_type: EventType) -> float:
        """Get error rate for a specific event type."""
        count = self._event_counts.get(event_type, 0)
        errors = self._error_counts.get(event_type, 0)
        if count == 0:
            return 0.0
        return errors / count

    def reset(self) -> None:
        """Reset all metrics."""
        self._event_counts.clear()
        self._event_times.clear()
        self._error_counts.clear()
        self._total_events = 0
        self._start_time = time.time()


class FilterMiddleware(EventMiddleware):
    """
    Middleware for filtering events.

    Can filter based on:
    - Event type whitelist/blacklist
    - Source whitelist/blacklist
    - Custom filter functions
    """

    def __init__(
        self,
        allowed_types: Optional[List[EventType]] = None,
        blocked_types: Optional[List[EventType]] = None,
        allowed_sources: Optional[List[str]] = None,
        blocked_sources: Optional[List[str]] = None,
        filter_func: Optional[callable] = None,
    ):
        """
        Initialize filter middleware.

        Args:
            allowed_types: Only allow these event types (None = allow all)
            blocked_types: Block these event types
            allowed_sources: Only allow these sources (None = allow all)
            blocked_sources: Block these sources
            filter_func: Custom filter function (Event -> bool)
        """
        self.allowed_types = set(allowed_types or [])
        self.blocked_types = set(blocked_types or [])
        self.allowed_sources = set(allowed_sources or [])
        self.blocked_sources = set(blocked_sources or [])
        self.filter_func = filter_func

    def on_emit(self, event: Event) -> Optional[Event]:
        """Filter event based on rules."""
        # Check allowed types
        if self.allowed_types and event.type not in self.allowed_types:
            logger.debug(f"Event filtered (type): {event.type.value}")
            return None

        # Check blocked types
        if event.type in self.blocked_types:
            logger.debug(f"Event filtered (blocked type): {event.type.value}")
            return None

        # Check allowed sources
        if self.allowed_sources and event.source not in self.allowed_sources:
            logger.debug(f"Event filtered (source): {event.source}")
            return None

        # Check blocked sources
        if event.source in self.blocked_sources:
            logger.debug(f"Event filtered (blocked source): {event.source}")
            return None

        # Check custom filter
        if self.filter_func and not self.filter_func(event):
            logger.debug(f"Event filtered (custom): {event.type.value}")
            return None

        return event


class TransformMiddleware(EventMiddleware):
    """
    Middleware for transforming events.

    Can:
    - Add default data to events
    - Rename fields
    - Enrich events with additional data
    """

    def __init__(
        self,
        default_data: Optional[Dict[str, Any]] = None,
        transformers: Optional[Dict[str, callable]] = None,
    ):
        """
        Initialize transform middleware.

        Args:
            default_data: Default data to add to all events
            transformers: Dict of {field: transformer_func}
        """
        self.default_data = default_data or {}
        self.transformers = transformers or {}

    def on_emit(self, event: Event) -> Optional[Event]:
        """Transform event data."""
        # Add default data
        for key, value in self.default_data.items():
            if key not in event.data:
                event.data[key] = value

        # Apply transformers
        for field, transformer in self.transformers.items():
            if field in event.data:
                try:
                    event.data[field] = transformer(event.data[field])
                except Exception as e:
                    logger.warning(f"Transform failed for {field}: {e}")

        return event


class ThrottleMiddleware(EventMiddleware):
    """
    Middleware for throttling events.

    Prevents event flooding by:
    - Maximum events per time window
    - Coalescing similar events
    """

    def __init__(
        self,
        max_events: int = 100,
        window_seconds: float = 1.0,
        coalesce_keys: Optional[List[str]] = None,
    ):
        """
        Initialize throttle middleware.

        Args:
            max_events: Maximum events per window
            window_seconds: Time window in seconds
            coalesce_keys: Keys to use for event coalescing
        """
        self.max_events = max_events
        self.window_seconds = window_seconds
        self.coalesce_keys = coalesce_keys or []
        self._event_times: List[float] = []
        self._coalesce_cache: Dict[str, Event] = {}

    def on_emit(self, event: Event) -> Optional[Event]:
        """Throttle events based on rules."""
        now = time.time()

        # Clean old events
        cutoff = now - self.window_seconds
        self._event_times = [t for t in self._event_times if t > cutoff]

        # Check if over limit
        if len(self._event_times) >= self.max_events:
            logger.warning(
                f"Event throttled: {event.type.value} "
                f"(limit: {self.max_events}/{self.window_seconds}s)"
            )
            return None

        # Check for coalescing
        if self.coalesce_keys:
            coalesce_key = self._get_coalesce_key(event)
            if coalesce_key:
                # Replace cached event instead of adding new one
                self._coalesce_cache[coalesce_key] = event
                logger.debug(f"Event coalesced: {coalesce_key}")
                return None

        self._event_times.append(now)
        return event

    def _get_coalesce_key(self, event: Event) -> Optional[str]:
        """Generate coalesce key for event."""
        if not self.coalesce_keys:
            return None

        parts = [event.type.value]
        for key in self.coalesce_keys:
            value = event.data.get(key, "unknown")
            parts.append(f"{key}={value}")

        return "|".join(parts)


class CorrelationMiddleware(EventMiddleware):
    """
    Middleware for event correlation.

    Adds correlation tracking across event chains.
    """

    def __init__(self):
        self._chains: Dict[str, List[Event]] = defaultdict(list)

    def on_emit(self, event: Event) -> Optional[Event]:
        """Track event correlation."""
        if event.correlation_id:
            self._chains[event.correlation_id].append(event)
        return event

    def get_chain(self, correlation_id: str) -> List[Event]:
        """Get all events in a correlation chain."""
        return self._chains.get(correlation_id, [])

    def get_chain_summary(self, correlation_id: str) -> Dict[str, Any]:
        """Get summary of event chain."""
        chain = self.get_chain(correlation_id)
        return {
            "correlation_id": correlation_id,
            "event_count": len(chain),
            "types": [e.type.value for e in chain],
            "sources": list(set(e.source for e in chain)),
            "duration_ms": (
                (chain[-1].timestamp - chain[0].timestamp).total_seconds() * 1000
                if len(chain) > 1 else 0
            ),
        }


# Middleware factory functions
def create_logging_middleware(
    level: str = "DEBUG",
    rate_limit: Optional[int] = None,
) -> LoggingMiddleware:
    """Create logging middleware with common settings."""
    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    return LoggingMiddleware(
        log_level=levels.get(level.upper(), logging.DEBUG),
        rate_limit={et: rate_limit for et in EventType} if rate_limit else None,
    )


def create_metrics_middleware(window_size: int = 60) -> MetricsMiddleware:
    """Create metrics middleware."""
    return MetricsMiddleware(window_size=window_size)


def create_filter_middleware(
    include_types: Optional[List[str]] = None,
    exclude_types: Optional[List[str]] = None,
) -> FilterMiddleware:
    """Create filter middleware."""
    allowed = [EventType(t) for t in include_types] if include_types else None
    blocked = [EventType(t) for t in exclude_types] if exclude_types else None
    return FilterMiddleware(allowed_types=allowed, blocked_types=blocked)
