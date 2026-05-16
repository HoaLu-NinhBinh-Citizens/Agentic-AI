"""
Unit Tests for AI_support Events Module
"""

import asyncio
import time
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.events.event import (
    Event,
    EventContext,
    create_task_event,
    create_llm_event,
    create_retrieval_event,
    create_tool_event,
    create_workflow_event,
)
from src.events.types import EventType, EventCategory, get_event_category, get_events_by_category
from src.events.emitter import EventEmitter, get_event_emitter
from src.events.middleware import (
    LoggingMiddleware,
    MetricsMiddleware,
    FilterMiddleware,
    TransformMiddleware,
    ThrottleMiddleware,
    CorrelationMiddleware,
)
from src.events.handlers import (
    LoggingHandler,
    MetricsHandler,
    AlertHandler,
    BufferHandler,
    TaskStateHandler,
    ErrorTrackingHandler,
)


# ============ EventType Tests ============

class TestEventType:
    def test_event_type_values(self):
        """Test EventType enum values."""
        assert EventType.TASK_RECEIVED.value == "task.received"
        assert EventType.LLM_REQUEST_STARTED.value == "llm.request_started"
        assert EventType.RETRIEVAL_COMPLETED.value == "retrieval.completed"

    def test_event_category_mapping(self):
        """Test event category mapping."""
        assert get_event_category(EventType.TASK_COMPLETED) == EventCategory.TASK
        assert get_event_category(EventType.LLM_REQUEST_FAILED) == EventCategory.LLM
        assert get_event_category(EventType.MEMORY_STORED) == EventCategory.MEMORY

    def test_get_events_by_category(self):
        """Test getting events by category."""
        task_events = get_events_by_category(EventCategory.TASK)
        assert EventType.TASK_RECEIVED in task_events
        assert EventType.TASK_COMPLETED in task_events
        assert EventType.RETRIEVAL_STARTED not in task_events


# ============ Event Tests ============

class TestEvent:
    def test_event_creation(self):
        """Test basic event creation."""
        event = Event(type=EventType.TASK_RECEIVED, source="test")
        assert event.type == EventType.TASK_RECEIVED
        assert event.source == "test"
        assert event.id is not None
        assert event.correlation_id == event.id
        assert event.timestamp is not None

    def test_event_with_data(self):
        """Test event with data payload."""
        event = Event(
            type=EventType.LLM_REQUEST_STARTED,
            source="llm",
            data={"prompt": "test", "model": "gpt-4"},
        )
        assert event.data["prompt"] == "test"
        assert event.data["model"] == "gpt-4"

    def test_event_correlation_id(self):
        """Test event correlation ID."""
        parent = Event(type=EventType.TASK_RECEIVED, source="test")
        child = Event(
            type=EventType.LLM_REQUEST_STARTED,
            source="llm",
            parent_id=parent.id,
            correlation_id=parent.correlation_id,
        )
        assert child.parent_id == parent.id
        assert child.correlation_id == parent.correlation_id

    def test_event_to_dict(self):
        """Test event serialization."""
        event = Event(
            type=EventType.TASK_COMPLETED,
            source="agent",
            data={"task_id": "123", "result": "success"},
        )
        data = event.to_dict()
        assert data["type"] == "task.completed"
        assert data["source"] == "agent"
        assert data["data"]["task_id"] == "123"

    def test_event_from_dict(self):
        """Test event deserialization."""
        original = Event(
            type=EventType.TASK_FAILED,
            source="agent",
            data={"task_id": "456"},
        )
        data = original.to_dict()
        restored = Event.from_dict(data)
        assert restored.type == original.type
        assert restored.source == original.source
        assert restored.id == original.id

    def test_event_invalid_source(self):
        """Test event with invalid source."""
        with pytest.raises(ValueError):
            Event(type=EventType.TASK_RECEIVED, source="")

    def test_event_immutability(self):
        """Test event immutability (with_metadata)."""
        event = Event(type=EventType.TASK_RECEIVED, source="test")
        event2 = event.with_metadata(tags=["important"])
        assert event.metadata == {}
        assert event2.metadata == {"tags": ["important"]}


# ============ Event Factory Tests ============

class TestEventFactory:
    def test_create_task_event(self):
        """Test task event factory."""
        event = create_task_event(
            task_id="task-1",
            task_type="codegen",
            action=EventType.TASK_RECEIVED,
            source="agent",
        )
        assert event.type == EventType.TASK_RECEIVED
        assert event.data["task_id"] == "task-1"
        assert event.data["task_type"] == "codegen"

    def test_create_llm_event(self):
        """Test LLM event factory."""
        event = create_llm_event(
            provider="openai",
            action=EventType.LLM_REQUEST_STARTED,
            source="llm",
        )
        assert event.type == EventType.LLM_REQUEST_STARTED
        assert event.data["provider"] == "openai"

    def test_create_retrieval_event(self):
        """Test retrieval event factory."""
        event = create_retrieval_event(
            query="STM32F407 UART",
            action=EventType.RETRIEVAL_STARTED,
            source="retrieval",
        )
        assert event.type == EventType.RETRIEVAL_STARTED
        assert event.data["query"] == "STM32F407 UART"

    def test_create_tool_event(self):
        """Test tool event factory."""
        event = create_tool_event(
            tool_name="file_read",
            action=EventType.TOOL_EXECUTION_STARTED,
            source="tools",
        )
        assert event.type == EventType.TOOL_EXECUTION_STARTED
        assert event.data["tool_name"] == "file_read"


# ============ EventContext Tests ============

class TestEventContext:
    def test_context_creation(self):
        """Test EventContext creation."""
        event = Event(type=EventType.TASK_RECEIVED, source="test")
        ctx = EventContext(event=event)
        assert ctx.event == event
        assert ctx.handled is False
        assert ctx.stopped is False

    def test_context_stop_propagation(self):
        """Test stopping event propagation."""
        event = Event(type=EventType.TASK_RECEIVED, source="test")
        ctx = EventContext(event=event)
        ctx.stop_propagation()
        assert ctx.stopped is True

    def test_context_mark_handled(self):
        """Test marking event as handled."""
        event = Event(type=EventType.TASK_RECEIVED, source="test")
        ctx = EventContext(event=event)
        ctx.mark_handled({"result": "success"})
        assert ctx.handled is True
        assert ctx.results["handler_result"] == {"result": "success"}

    def test_context_set_error(self):
        """Test setting error in context."""
        event = Event(type=EventType.TASK_RECEIVED, source="test")
        ctx = EventContext(event=event)
        error = ValueError("test error")
        ctx.set_error(error)
        assert ctx.error == error
        assert ctx.stopped is True


# ============ EventEmitter Tests ============

class TestEventEmitter:
    def test_emitter_creation(self):
        """Test EventEmitter creation."""
        emitter = EventEmitter()
        assert emitter.listener_count() == 0

    def test_on_and_emit(self):
        """Test basic subscribe and emit."""
        emitter = EventEmitter(enable_logging=False)
        received = []

        def handler(event):
            received.append(event)

        emitter.on(EventType.TASK_COMPLETED, handler)
        event = Event(type=EventType.TASK_COMPLETED, source="test")
        emitter.emit(event)

        assert len(received) == 1
        assert received[0].type == EventType.TASK_COMPLETED

    def test_off(self):
        """Test unsubscribe."""
        emitter = EventEmitter(enable_logging=False)
        received = []

        def handler(event):
            received.append(event)

        emitter.on(EventType.TASK_COMPLETED, handler)
        emitter.emit(Event(type=EventType.TASK_COMPLETED, source="test"))
        assert len(received) == 1

        emitter.off(EventType.TASK_COMPLETED, handler)
        emitter.emit(Event(type=EventType.TASK_COMPLETED, source="test"))
        assert len(received) == 1  # No new events received

    def test_off_all(self):
        """Test unsubscribe all."""
        emitter = EventEmitter(enable_logging=False)

        def handler1(event):
            pass

        def handler2(event):
            pass

        emitter.on(EventType.TASK_COMPLETED, handler1)
        emitter.on(EventType.TASK_FAILED, handler2)
        emitter.off_all()

        assert emitter.listener_count() == 0

    def test_once(self):
        """Test once subscription."""
        emitter = EventEmitter(enable_logging=False)
        received = []

        def handler(event):
            received.append(event)

        emitter.once(EventType.TASK_COMPLETED, handler)
        emitter.emit(Event(type=EventType.TASK_COMPLETED, source="test"))
        emitter.emit(Event(type=EventType.TASK_COMPLETED, source="test"))

        assert len(received) == 1  # Only received once

    def test_priority(self):
        """Test handler priority."""
        emitter = EventEmitter(enable_logging=False)
        order = []

        def handler_low(event):
            order.append("low")

        def handler_high(event):
            order.append("high")

        def handler_medium(event):
            order.append("medium")

        emitter.on(EventType.TASK_COMPLETED, handler_low, priority=0)
        emitter.on(EventType.TASK_COMPLETED, handler_high, priority=10)
        emitter.on(EventType.TASK_COMPLETED, handler_medium, priority=5)

        emitter.emit(Event(type=EventType.TASK_COMPLETED, source="test"))

        assert order == ["high", "medium", "low"]

    def test_has_listeners(self):
        """Test listener check."""
        emitter = EventEmitter(enable_logging=False)

        def handler(event):
            pass

        assert not emitter.has_listeners(EventType.TASK_COMPLETED)

        emitter.on(EventType.TASK_COMPLETED, handler)
        assert emitter.has_listeners(EventType.TASK_COMPLETED)

    def test_listener_count(self):
        """Test listener count."""
        emitter = EventEmitter(enable_logging=False)

        def handler1(event):
            pass

        def handler2(event):
            pass

        emitter.on(EventType.TASK_COMPLETED, handler1)
        emitter.on(EventType.TASK_COMPLETED, handler2)

        assert emitter.listener_count(EventType.TASK_COMPLETED) == 2
        assert emitter.listener_count() == 2

    def test_get_subscribed_events(self):
        """Test getting subscribed events."""
        emitter = EventEmitter(enable_logging=False)

        def handler(event):
            pass

        emitter.on(EventType.TASK_COMPLETED, handler)
        emitter.on(EventType.LLM_REQUEST_STARTED, handler)

        subscribed = emitter.get_subscribed_events()
        assert EventType.TASK_COMPLETED in subscribed
        assert EventType.LLM_REQUEST_STARTED in subscribed


# ============ Async EventEmitter Tests ============

class TestAsyncEventEmitter:
    @pytest.mark.asyncio
    async def test_emit_async(self):
        """Test async emit."""
        emitter = EventEmitter(enable_logging=False)
        received = []

        async def handler(event):
            received.append(event)

        emitter.on(EventType.TASK_COMPLETED, handler)
        event = Event(type=EventType.TASK_COMPLETED, source="test")
        await emitter.emit_async(event)

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_emit_batch_async(self):
        """Test async batch emit."""
        emitter = EventEmitter(enable_logging=False)
        received = []

        def handler(event):
            received.append(event)

        emitter.on(EventType.TASK_COMPLETED, handler)

        events = [
            Event(type=EventType.TASK_COMPLETED, source="test")
            for _ in range(5)
        ]
        await emitter.emit_batch_async(events)

        assert len(received) == 5


# ============ Middleware Tests ============

class TestLoggingMiddleware:
    def test_logging_middleware(self):
        """Test logging middleware."""
        middleware = LoggingMiddleware(log_level=10)
        event = Event(type=EventType.TASK_COMPLETED, source="test")
        result = middleware.on_emit(event)
        assert result == event  # Should pass through


class TestMetricsMiddleware:
    def test_metrics_collection(self):
        """Test metrics middleware."""
        middleware = MetricsMiddleware()
        event = Event(type=EventType.TASK_COMPLETED, source="test")

        middleware.on_emit(event)
        middleware.on_emit(event)

        metrics = middleware.get_metrics()
        assert metrics["total_events"] == 2
        assert EventType.TASK_COMPLETED in metrics["event_counts"]

    def test_metrics_reset(self):
        """Test metrics reset."""
        middleware = MetricsMiddleware()
        event = Event(type=EventType.TASK_COMPLETED, source="test")
        middleware.on_emit(event)
        middleware.reset()

        metrics = middleware.get_metrics()
        assert metrics["total_events"] == 0


class TestFilterMiddleware:
    def test_allow_filter(self):
        """Test allow filter."""
        middleware = FilterMiddleware(
            allowed_types=[EventType.TASK_COMPLETED]
        )
        event = Event(type=EventType.TASK_COMPLETED, source="test")
        result = middleware.on_emit(event)
        assert result is not None

        event2 = Event(type=EventType.TASK_FAILED, source="test")
        result2 = middleware.on_emit(event2)
        assert result2 is None  # Blocked

    def test_block_filter(self):
        """Test block filter."""
        middleware = FilterMiddleware(
            blocked_types=[EventType.TASK_FAILED]
        )
        event = Event(type=EventType.TASK_FAILED, source="test")
        result = middleware.on_emit(event)
        assert result is None  # Blocked


class TestTransformMiddleware:
    def test_transform_add_default_data(self):
        """Test adding default data."""
        middleware = TransformMiddleware(
            default_data={"env": "test", "version": "1.0"}
        )
        event = Event(type=EventType.TASK_COMPLETED, source="test")
        result = middleware.on_emit(event)

        assert result.data["env"] == "test"
        assert result.data["version"] == "1.0"


class TestThrottleMiddleware:
    def test_throttle_limit(self):
        """Test throttling at limit."""
        middleware = ThrottleMiddleware(max_events=2, window_seconds=10)

        for i in range(5):
            event = Event(type=EventType.TASK_COMPLETED, source="test")
            result = middleware.on_emit(event)

        # First 2 should pass, rest should be blocked
        assert len(middleware._event_times) <= 2


class TestCorrelationMiddleware:
    def test_correlation_tracking(self):
        """Test correlation tracking."""
        middleware = CorrelationMiddleware()
        correlation_id = "test-correlation-123"

        event1 = Event(
            type=EventType.TASK_RECEIVED,
            source="test",
            correlation_id=correlation_id,
        )
        event2 = Event(
            type=EventType.TASK_COMPLETED,
            source="test",
            correlation_id=correlation_id,
        )

        middleware.on_emit(event1)
        middleware.on_emit(event2)

        chain = middleware.get_chain(correlation_id)
        assert len(chain) == 2

        summary = middleware.get_chain_summary(correlation_id)
        assert summary["event_count"] == 2


# ============ Handler Tests ============

class TestLoggingHandler:
    def test_logging_handler(self):
        """Test logging handler."""
        handler = LoggingHandler()
        event = Event(type=EventType.TASK_COMPLETED, source="test")
        handler.handle(event)  # Should not raise


class TestMetricsHandler:
    def test_metrics_handler(self):
        """Test metrics handler."""
        handler = MetricsHandler()

        event = Event(type=EventType.TASK_COMPLETED, source="test")
        handler.handle(event)
        handler.handle(event)

        stats = handler.get_stats()
        assert stats["total_events"] == 2


class TestBufferHandler:
    def test_buffer_handler(self):
        """Test buffer handler."""
        flushed = []

        def on_flush(events):
            flushed.extend(events)

        handler = BufferHandler(buffer_size=3, on_flush=on_flush)

        for i in range(5):
            event = Event(type=EventType.TASK_COMPLETED, source="test")
            handler.handle(event)

        assert len(flushed) >= 3


class TestTaskStateHandler:
    def test_task_state_tracking(self):
        """Test task state tracking."""
        handler = TaskStateHandler()

        # Simulate task lifecycle
        handler.handle(Event(
            type=EventType.TASK_RECEIVED,
            source="test",
            data={"task_id": "task-1"},
        ))
        handler.handle(Event(
            type=EventType.TASK_STARTED,
            source="test",
            data={"task_id": "task-1"},
        ))
        handler.handle(Event(
            type=EventType.TASK_COMPLETED,
            source="test",
            data={"task_id": "task-1"},
        ))

        assert handler.get_task_state("task-1") == "completed"
        assert "task-1" not in handler.get_pending_tasks()


class TestErrorTrackingHandler:
    def test_error_tracking(self):
        """Test error tracking."""
        handler = ErrorTrackingHandler()

        event = Event(
            type=EventType.TASK_FAILED,
            source="test",
            data={"error_type": "timeout", "error": "Request timeout"},
        )
        handler.handle(event)

        summary = handler.get_error_summary()
        assert summary["total_errors"] == 1
        assert "timeout" in summary["error_counts"]


# ============ Integration Tests ============

class TestEventIntegration:
    def test_full_event_flow(self):
        """Test complete event flow."""
        emitter = EventEmitter(enable_logging=False)
        received_events = []

        def handler(event):
            received_events.append(event)

        emitter.on(EventType.TASK_COMPLETED, handler)

        event = Event(
            type=EventType.TASK_COMPLETED,
            source="test-agent",
            data={"task_id": "task-123", "result": "success"},
        )
        emitter.emit(event)

        assert len(received_events) == 1
        assert received_events[0].data["task_id"] == "task-123"

    def test_middleware_chain(self):
        """Test middleware chain."""
        emitter = EventEmitter(enable_logging=False)

        transform_middleware = TransformMiddleware(
            default_data={"middleware": "added"}
        )
        emitter.use(transform_middleware)

        received = []

        def handler(event):
            received.append(event)

        emitter.on(EventType.TASK_COMPLETED, handler)

        event = Event(type=EventType.TASK_COMPLETED, source="test")
        emitter.emit(event)

        assert len(received) == 1
        assert received[0].data["middleware"] == "added"

    def test_handler_priority_chain(self):
        """Test handler priority in chain."""
        emitter = EventEmitter(enable_logging=False)
        execution_order = []

        def handler3(event):
            execution_order.append(3)

        def handler1(event):
            execution_order.append(1)

        def handler2(event):
            execution_order.append(2)

        emitter.on(EventType.TASK_COMPLETED, handler3, priority=0)
        emitter.on(EventType.TASK_COMPLETED, handler1, priority=10)
        emitter.on(EventType.TASK_COMPLETED, handler2, priority=5)

        emitter.emit(Event(type=EventType.TASK_COMPLETED, source="test"))

        assert execution_order == [1, 2, 3]


# ============ Global Emitter Tests ============

class TestGlobalEmitter:
    def test_get_event_emitter(self):
        """Test getting global emitter."""
        emitter = get_event_emitter()
        assert emitter is not None
        assert isinstance(emitter, EventEmitter)

    def test_global_emitter_singleton(self):
        """Test global emitter is singleton."""
        emitter1 = get_event_emitter()
        emitter2 = get_event_emitter()
        assert emitter1 is emitter2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
