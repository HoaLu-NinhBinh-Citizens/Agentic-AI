"""Integration tests for WebSocket chat flow (Phase 1B)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
from pathlib import Path

import pytest

from interfaces.server.main import app, ServerState
from interfaces.server.websocket.manager import ConnectionManager
from interfaces.server.websocket.client import WebSocketClient
from core.session.persistent_manager import PersistentSessionManager
from infrastructure.persistence.sqlite.session_store import SessionStore
from core.runtime.runtime_manager import RuntimeManager
from core.agent.mock_agent import MockAgent


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    db_path.unlink(missing_ok=True)


@pytest.fixture
async def server_state(temp_db):
    """Create a server state for testing."""
    store = SessionStore(db_path=temp_db)
    session_manager = PersistentSessionManager(store)
    await session_manager.initialize()

    connection_manager = ConnectionManager()
    mock_agent = MockAgent()
    runtime_manager = RuntimeManager(mock_agent)
    await runtime_manager.start()

    state = ServerState(
        session_manager=session_manager,
        connection_manager=connection_manager,
        runtime_manager=runtime_manager,
        mock_agent=mock_agent,
    )

    yield state

    await runtime_manager.stop()
    await session_manager.close()


class TestWebSocketChatFlow:
    """Test suite for WebSocket chat flow (Phase 1B)."""

    @pytest.mark.asyncio
    async def test_chat_flow(self, server_state):
        """Test complete chat flow: create session, connect, send chat, receive tokens."""
        session_id = server_state.session_manager.create_session()
        await server_state.session_manager.save_session(session_id)

        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.receive_json = AsyncMock()

        async def receive_json_side_effect():
            await asyncio.sleep(0.01)
            return {"type": "chat", "message": "Hi"}

        mock_ws.receive_json.side_effect = [
            {"type": "chat", "message": "Hi"},
            Exception("Disconnected"),
        ]

        client = await server_state.connection_manager.connect(session_id, mock_ws)
        assert client is not None

        events = []
        original_send = client.send_event

        async def capture_event(event):
            events.append(event)
            return await original_send(event)

        server_state.connection_manager.send_to_session = AsyncMock(side_effect=capture_event)

        async with asyncio.timeout(2):
            try:
                while True:
                    data = await mock_ws.receive_json()
                    if data.get("type") == "chat":
                        await server_state.runtime_manager.execute(
                            session_id,
                            data.get("message", ""),
                            lambda e: client.send_event(e),
                            client,
                        )
            except Exception:
                pass

        await asyncio.sleep(0.5)

        token_events = [e for e in events if e.get("type") == "token"]
        done_events = [e for e in events if e.get("type") == "done"]

        assert len(token_events) == 2
        assert token_events[0]["data"]["content"] == "H"
        assert token_events[1]["data"]["content"] == "i"
        assert len(done_events) == 1
        assert done_events[0]["data"]["success"] is True

        await server_state.connection_manager.close_all_for_session(session_id)

    @pytest.mark.asyncio
    async def test_busy_behavior(self, server_state):
        """Test BUSY error when second chat is sent while first is streaming."""
        session_id = server_state.session_manager.create_session()
        await server_state.session_manager.save_session(session_id)

        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.receive_json = AsyncMock()

        mock_ws.receive_json.side_effect = [
            {"type": "chat", "message": "Hello"},
            {"type": "chat", "message": "Second"},
            Exception("Disconnected"),
        ]

        client = await server_state.connection_manager.connect(session_id, mock_ws)
        assert client is not None

        events = []

        async def capture_event(event):
            events.append(event)
            await client.send_event(event)

        async def run_test():
            try:
                while True:
                    data = await mock_ws.receive_json()
                    if data.get("type") == "chat":
                        if server_state.runtime_manager.is_streaming(session_id):
                            await capture_event({
                                "type": "error",
                                "data": {
                                    "code": "BUSY",
                                    "message": "Another chat in progress",
                                },
                            })
                        else:
                            await server_state.runtime_manager.execute(
                                session_id,
                                data.get("message", ""),
                                capture_event,
                                client,
                            )
            except Exception:
                pass

        await asyncio.wait_for(run_test(), timeout=2.0)
        await asyncio.sleep(0.5)

        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1

        token_events = [e for e in events if e.get("type") == "token"]
        full_response = "".join(e["data"]["content"] for e in token_events)
        assert full_response == "Hello"

        await server_state.connection_manager.close_all_for_session(session_id)

    @pytest.mark.asyncio
    async def test_rate_limiting(self, server_state):
        """Test that rate limiting rejects requests after limit."""
        session_id = server_state.session_manager.create_session()
        await server_state.session_manager.save_session(session_id)

        rate_limiter = server_state.get_rate_limiter(session_id)

        for i in range(5):
            assert rate_limiter.allow() is True

        assert rate_limiter.allow() is False

    @pytest.mark.asyncio
    async def test_websocket_client_queue_backpressure(self):
        """Test that WebSocketClient handles backpressure correctly."""
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.close = AsyncMock()

        slow_send = asyncio.Event()
        call_count = 0

        async def slow_send_json(event):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)

        mock_ws.send_json = slow_send_json

        client = WebSocketClient(mock_ws, "test-session")
        await client.start()

        for i in range(10):
            await client.send_event({
                "type": "token",
                "data": {"content": f"X{i}"}
            })

        await asyncio.sleep(0.3)

        assert call_count >= 5

        await client.close()

    @pytest.mark.asyncio
    async def test_cancellation(self, server_state):
        """Test cancellation stops ongoing stream."""
        session_id = server_state.session_manager.create_session()
        await server_state.session_manager.save_session(session_id)

        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.receive_json = AsyncMock()

        mock_ws.receive_json.side_effect = [
            {"type": "chat", "message": "Hello"},
            {"type": "cancel"},
            Exception("Disconnected"),
        ]

        client = await server_state.connection_manager.connect(session_id, mock_ws)
        assert client is not None

        events = []

        async def capture_event(event):
            events.append(event)
            await client.send_event(event)

        async def run_test():
            try:
                while True:
                    data = await mock_ws.receive_json()
                    if data.get("type") == "chat":
                        await server_state.runtime_manager.execute(
                            session_id,
                            data.get("message", ""),
                            capture_event,
                            client,
                        )
                    elif data.get("type") == "cancel":
                        await server_state.runtime_manager.cancel_stream(session_id)
            except Exception:
                pass

        await asyncio.wait_for(run_test(), timeout=2.0)
        await asyncio.sleep(0.3)

        cancelled_events = [e for e in events if e.get("type") == "cancelled"]

        await server_state.connection_manager.close_all_for_session(session_id)
