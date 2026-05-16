"""Integration tests for WebSocket chat flow."""

from __future__ import annotations

import pytest

from interfaces.server.main import app


@pytest.mark.asyncio
async def test_chat_flow():
    """Test complete chat flow: create session, connect, send chat, receive tokens."""
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.post("/sessions")
        assert response.status_code == 201
        session_data = response.json()
        session_id = session_data["session_id"]

        with client.websocket_connect(f"/ws/{session_id}") as websocket:
            websocket.send_json({"type": "chat", "message": "Hi"})

            events = []
            while True:
                event = websocket.receive_json()
                events.append(event)
                if event.get("type") == "done":
                    break

            token_events = [e for e in events if e.get("type") == "token"]
            done_events = [e for e in events if e.get("type") == "done"]

            assert len(token_events) == 2
            assert token_events[0]["data"]["content"] == "H"
            assert token_events[1]["data"]["content"] == "i"
            assert len(done_events) == 1
            assert done_events[0]["data"]["success"] is True


@pytest.mark.asyncio
async def test_busy_behavior():
    """Test BUSY error handling when second chat is sent while first is streaming.

    When a second chat message is sent while the first is still streaming,
    the second message is ignored (or returns BUSY error) because the session
    is already processing the first message.

    Note: FastAPI's TestClient runs synchronously, so we can send both messages
    before receiving. The server processes them in order, and the BUSY check
    ensures only one message is processed at a time.
    """
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.post("/sessions")
        session_id = response.json()["session_id"]

        with client.websocket_connect(f"/ws/{session_id}") as websocket:
            websocket.send_json({"type": "chat", "message": "Hello"})
            websocket.send_json({"type": "chat", "message": "Second"})

            events = []
            while True:
                try:
                    event = websocket.receive_json()
                    events.append(event)
                    if event.get("type") == "done":
                        break
                except Exception:
                    break

            done_events = [e for e in events if e.get("type") == "done"]
            assert len(done_events) == 1, (
                f"Expected 1 done event (only first message processed), got {len(done_events)}"
            )

            token_events = [e for e in events if e.get("type") == "token"]
            full_response = "".join(e["data"]["content"] for e in token_events)
            assert full_response == "Hello", (
                f"Expected only first message 'Hello', got '{full_response}'"
            )


@pytest.mark.asyncio
async def test_websocket_invalid_session():
    """Test that WebSocket connection with invalid session ID is rejected."""
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/invalid-session-id") as websocket:
                websocket.receive_json()


@pytest.mark.asyncio
async def test_health_endpoint():
    """Test health endpoint returns ok status."""
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_multiple_messages_in_sequence():
    """Test sending multiple chat messages in sequence."""
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.post("/sessions")
        session_id = response.json()["session_id"]

        with client.websocket_connect(f"/ws/{session_id}") as websocket:
            websocket.send_json({"type": "chat", "message": "Hi"})

            events1 = []
            while True:
                event = websocket.receive_json()
                events1.append(event)
                if event.get("type") == "done":
                    break

            assert len([e for e in events1 if e.get("type") == "token"]) == 2

            websocket.send_json({"type": "chat", "message": "Bye"})

            events2 = []
            while True:
                event = websocket.receive_json()
                events2.append(event)
                if event.get("type") == "done":
                    break

            token_events = [e for e in events2 if e.get("type") == "token"]
            assert len(token_events) == 3
            contents = "".join(e["data"]["content"] for e in token_events)
            assert contents == "Bye"
