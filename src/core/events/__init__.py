"""
AI_support Events Module

Event-driven runtime foundation for src.
"""

from src.core.events.types import EventType
from src.core.events.event import Event
from src.core.events.emitter import EventEmitter, event_emitter
from src.core.events.middleware import EventMiddleware, LoggingMiddleware, MetricsMiddleware
from src.core.events.handlers import (
    EventHandler,
    LoggingHandler,
    MetricsHandler,
    AlertHandler,
)

__all__ = [
    # Types
    "EventType",
    "Event",
    # Emitter
    "EventEmitter",
    "event_emitter",
    # Middleware
    "EventMiddleware",
    "LoggingMiddleware",
    "MetricsMiddleware",
    # Handlers
    "EventHandler",
    "LoggingHandler",
    "MetricsHandler",
    "AlertHandler",
]
