"""Mock agent for Phase 1B.

This module provides a streaming mock agent that responds character by character.
Supports cancellation via asyncio.Event.

FIX W-004: Added trace_id support for distributed tracing.
FIX W-006: Added metrics counter for error tracking.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextvars import ContextVar
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# W-004: Context variable for request tracing
_trace_id: ContextVar[str] = ContextVar('trace_id', default='')
_session_id: ContextVar[str] = ContextVar('session_id', default='')


def set_trace_context(trace_id: str | None = None, session_id: str | None = None) -> None:
    """Set trace context for the current async task."""
    if trace_id:
        _trace_id.set(trace_id)
    if session_id:
        _session_id.set(session_id)


def get_trace_context() -> tuple[str, str]:
    """Get current trace context."""
    return _trace_id.get(), _session_id.get()


# W-006: Simple metrics counter
class AgentMetrics:
    """Simple in-memory metrics for agent operations."""
    
    def __init__(self):
        self._counters: dict[str, int] = {}
        self._lock = asyncio.Lock()
    
    async def increment(self, name: str, tags: dict | None = None) -> None:
        """Increment a counter."""
        async with self._lock:
            key = name
            if tags:
                tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
                key = f"{name}[{tag_str}]"
            self._counters[key] = self._counters.get(key, 0) + 1
    
    def get_counter(self, name: str) -> int:
        return self._counters.get(name, 0)
    
    def get_all(self) -> dict[str, int]:
        return dict(self._counters)


_agent_metrics = AgentMetrics()


def get_agent_metrics() -> AgentMetrics:
    """Get the global agent metrics instance."""
    return _agent_metrics


class MockAgent:
    """Mock agent that streams character-by-character responses.

    This is a deterministic mock for testing purposes.
    Each character is sent as a separate token with a 50ms delay.
    Supports cancellation via cancellation_event.
    """

    async def stream_response(
        self,
        message: str,
        send_event: Callable[[dict], Awaitable[None]],
        cancellation_event: asyncio.Event | None = None,
        trace_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Stream a response by sending each character as a token.

        Args:
            message: The message to respond to.
            send_event: Callback to send events to the client.
            cancellation_event: Optional event to check for cancellation.
            trace_id: Optional trace ID for distributed tracing.
            session_id: Optional session ID for context.
        """
        # W-004: Set trace context
        if trace_id:
            set_trace_context(trace_id=trace_id, session_id=session_id)
        
        metrics = get_agent_metrics()
        trace_id, session_id = get_trace_context()
        
        try:
            if not message:
                await send_event({
                    "type": "done",
                    "data": {"success": True},
                })
                return

            for i, ch in enumerate(message):
                if cancellation_event and cancellation_event.is_set():
                    await send_event({
                        "type": "cancelled",
                        "data": {},
                    })
                    logger.info("stream_cancelled", trace_id=trace_id, session_id=session_id)
                    await metrics.increment("agent.stream.cancelled")
                    return

                event = {
                    "type": "token",
                    "data": {
                        "content": ch,
                        "is_last": i == len(message) - 1,
                    },
                }
                await send_event(event)
                await asyncio.sleep(0.05)

            if cancellation_event and cancellation_event.is_set():
                return

            await send_event({
                "type": "done",
                "data": {"success": True},
            })
            await metrics.increment("agent.stream.completed", {"session_id": session_id or "unknown"})
            
        except Exception as e:
            # W-006: Track errors with metrics
            await metrics.increment("agent.error", {"error_type": type(e).__name__})
            logger.error(
                "agent_error",
                trace_id=trace_id,
                session_id=session_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            await send_event({
                "type": "error",
                "data": {
                    "code": "INTERNAL_ERROR",
                    "message": str(e),
                },
            })
