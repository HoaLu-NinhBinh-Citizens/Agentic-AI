"""Integration tests for session lifecycle."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_session(test_client):
    """Test creating a new session."""
    response = await test_client.post("/sessions")
    assert response.status_code == 201
    data = response.json()
    assert "session_id" in data
    assert "ws_url" in data
    assert data["session_id"].count("-") == 4


@pytest.mark.asyncio
async def test_create_session_with_workspace(test_client):
    """Test creating a session with workspace path."""
    workspace = "/path/to/project"
    response = await test_client.post("/sessions", json={"workspace": workspace})
    assert response.status_code == 201
    data = response.json()
    session_id = data["session_id"]

    get_response = await test_client.get(f"/sessions/{session_id}")
    assert get_response.status_code == 200
    session = get_response.json()
    assert session["workspace"] == workspace


@pytest.mark.asyncio
async def test_get_session(test_client):
    """Test retrieving session info."""
    create_response = await test_client.post("/sessions")
    session_id = create_response.json()["session_id"]

    get_response = await test_client.get(f"/sessions/{session_id}")
    assert get_response.status_code == 200
    session = get_response.json()
    assert session["id"] == session_id
    assert session["status"] == "active"
    assert "created_at" in session


@pytest.mark.asyncio
async def test_get_nonexistent_session(test_client):
    """Test that getting a nonexistent session returns 404."""
    response = await test_client.get("/sessions/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_session(test_client):
    """Test deleting a session."""
    create_response = await test_client.post("/sessions")
    session_id = create_response.json()["session_id"]

    delete_response = await test_client.delete(f"/sessions/{session_id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"status": "deleted"}

    get_response = await test_client.get(f"/sessions/{session_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_session(test_client):
    """Test that deleting a nonexistent session returns 404."""
    response = await test_client.delete("/sessions/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_multiple_sessions(test_client):
    """Test creating and managing multiple sessions."""
    ids = []
    for _ in range(3):
        response = await test_client.post("/sessions")
        ids.append(response.json()["session_id"])

    assert len(set(ids)) == 3

    for session_id in ids:
        response = await test_client.get(f"/sessions/{session_id}")
        assert response.status_code == 200

    for session_id in ids:
        response = await test_client.delete(f"/sessions/{session_id}")
        assert response.status_code == 200

    for session_id in ids:
        response = await test_client.get(f"/sessions/{session_id}")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_websocket_url_format(test_client):
    """Test that WebSocket URL is correctly formatted."""
    response = await test_client.post("/sessions")
    data = response.json()
    assert data["ws_url"].startswith("ws://")
    assert data["session_id"] in data["ws_url"]
