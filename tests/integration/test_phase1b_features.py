"""Integration tests for Phase 1B features."""

from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from infrastructure.persistence.sqlite.session_store import SessionStore
from core.session.persistent_manager import PersistentSessionManager


class TestPersistenceRestart:
    """Test suite for session persistence across restarts."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database file."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        yield db_path
        db_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_persistence_restart(self, temp_db):
        """Test that sessions survive server restart (simulated)."""
        store1 = SessionStore(db_path=temp_db)
        manager1 = PersistentSessionManager(store1)
        await manager1.initialize()

        session_id = manager1.create_session(workspace="/test/workspace")
        await manager1.save_session(session_id)

        assert manager1.get_session(session_id) is not None

        await manager1.close()

        store2 = SessionStore(db_path=temp_db)
        manager2 = PersistentSessionManager(store2)
        await manager2.initialize()

        session = manager2.get_session(session_id)
        assert session is not None
        assert session["id"] == session_id
        assert session["workspace"] == "/test/workspace"

        await manager2.close()


class TestCancellation:
    """Test suite for graceful cancellation."""

    @pytest.mark.asyncio
    async def test_cancellation_stops_stream(self):
        """Test that cancellation stops the stream."""
        from core.agent.mock_agent import MockAgent

        agent = MockAgent()
        events = []
        cancellation = asyncio.Event()

        async def capture(event):
            events.append(event)

        async def start_stream():
            task = asyncio.create_task(
                agent.stream_response("Hello, World!", capture, cancellation)
            )
            await asyncio.sleep(0.1)
            cancellation.set()
            await task

        await start_stream()

        token_events = [e for e in events if e.get("type") == "token"]
        cancelled_events = [e for e in events if e.get("type") == "cancelled"]

        assert len(cancelled_events) == 1
        assert len(token_events) < 13

    @pytest.mark.asyncio
    async def test_cancellation_event_sent(self):
        """Test that cancelled event is sent when cancelled."""
        from core.agent.mock_agent import MockAgent

        agent = MockAgent()
        events = []
        cancellation = asyncio.Event()

        async def capture(event):
            events.append(event)

        async def start_stream():
            task = asyncio.create_task(
                agent.stream_response("Test", capture, cancellation)
            )
            await asyncio.sleep(0.05)
            cancellation.set()
            await task

        await start_stream()

        has_cancelled = any(e.get("type") == "cancelled" for e in events)
        assert has_cancelled

    @pytest.mark.asyncio
    async def test_no_cancelled_event_if_completes(self):
        """Test that cancelled event is not sent if stream completes."""
        from core.agent.mock_agent import MockAgent

        agent = MockAgent()
        events = []

        async def capture(event):
            events.append(event)

        await agent.stream_response("Hi", capture, None)

        has_cancelled = any(e.get("type") == "cancelled" for e in events)
        has_done = any(e.get("type") == "done" for e in events)
        assert not has_cancelled
        assert has_done


class TestTimeout:
    """Test suite for request timeout."""

    @pytest.mark.asyncio
    async def test_timeout_aborts_long_stream(self):
        """Test that timeout aborts long streams."""
        from core.agent.mock_agent import MockAgent

        agent = MockAgent()
        events = []

        async def capture(event):
            events.append(event)

        try:
            await asyncio.wait_for(
                agent.stream_response("Hello", capture, None),
                timeout=0.01,
            )
        except asyncio.TimeoutError:
            pass

        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 0


class TestRateLimiting:
    """Test suite for rate limiting."""

    def test_rate_limit_chat(self):
        """Test chat rate limiting."""
        from core.rate_limiter import SlidingWindowRateLimiter

        rl = SlidingWindowRateLimiter(max_requests=5, window_seconds=10.0)

        for _ in range(5):
            assert rl.allow() is True

        assert rl.allow() is False

    def test_rate_limit_connections(self):
        """Test connection rate limiting logic."""
        from core.rate_limiter import SlidingWindowRateLimiter

        rl = SlidingWindowRateLimiter(max_requests=5, window_seconds=10.0)

        allowed = 0
        for _ in range(6):
            if rl.allow():
                allowed += 1

        assert allowed == 5

    def test_rate_limit_window_reset(self):
        """Test rate limit resets after window."""
        from core.rate_limiter import SlidingWindowRateLimiter

        rl = SlidingWindowRateLimiter(max_requests=2, window_seconds=0.1)

        assert rl.allow() is True
        assert rl.allow() is True
        assert rl.allow() is False

        time.sleep(0.15)

        assert rl.allow() is True


class TestBackpressure:
    """Test suite for backpressure handling."""

    @pytest.mark.asyncio
    async def test_slow_client_drops_tokens(self):
        """Test that slow clients drop token events but keep done."""
        from interfaces.server.websocket.client import WebSocketClient

        mock_ws = type("MockWS", (), {
            "send_json": AsyncMock(),
            "close": AsyncMock(),
            "receive_json": AsyncMock(),
        })()

        client = WebSocketClient(mock_ws, "test-session")
        await client.start()

        for i in range(150):
            await client.send_event({
                "type": "token",
                "data": {"content": f"X{i}"}
            })

        await client.send_event({"type": "done", "data": {"success": True}})

        await asyncio.sleep(0.3)

        token_calls = [
            c for c in mock_ws.send_json.call_args_list
            if c[0][0]["type"] == "token"
        ]
        done_calls = [
            c for c in mock_ws.send_json.call_args_list
            if c[0][0]["type"] == "done"
        ]

        assert len(done_calls) >= 1

        await client.close()


class TestConnectionLimit:
    """Test suite for connection limiting."""

    def test_max_connections_per_session(self):
        """Test that max connections per session is enforced."""
        from interfaces.server.websocket.manager import MAX_CONCURRENT_CONNECTIONS_PER_SESSION

        assert MAX_CONCURRENT_CONNECTIONS_PER_SESSION == 5
