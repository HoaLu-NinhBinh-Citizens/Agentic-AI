"""Unit tests for SessionStore (SQLite persistence)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
import tempfile

import pytest

from infrastructure.persistence.sqlite.session_store import SessionStore


class TestSessionStore:
    """Test suite for SessionStore."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database file."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        yield db_path
        db_path.unlink(missing_ok=True)

    @pytest.fixture
    def store(self, temp_db):
        """Create a SessionStore instance."""
        return SessionStore(db_path=temp_db)

    @pytest.mark.asyncio
    async def test_initialize_creates_table(self, store, temp_db):
        """Test that initialize creates the sessions table."""
        await store.initialize()
        assert temp_db.exists()
        await store.close()

    @pytest.mark.asyncio
    async def test_save_and_load(self, store):
        """Test saving and loading a session."""
        await store.initialize()
        session = {
            "id": "test-123",
            "created_at": "2024-01-01T00:00:00Z",
            "workspace": "/path/to/workspace",
            "state": "active",
        }
        await store.save(session)
        loaded = await store.load("test-123")
        assert loaded is not None
        assert loaded["id"] == "test-123"
        assert loaded["workspace"] == "/path/to/workspace"
        assert loaded["state"] == "active"
        await store.close()

    @pytest.mark.asyncio
    async def test_load_nonexistent(self, store):
        """Test loading a nonexistent session."""
        await store.initialize()
        loaded = await store.load("nonexistent")
        assert loaded is None
        await store.close()

    @pytest.mark.asyncio
    async def test_update_session(self, store):
        """Test updating an existing session."""
        await store.initialize()
        session = {
            "id": "test-456",
            "created_at": "2024-01-01T00:00:00Z",
            "workspace": None,
            "state": "active",
        }
        await store.save(session)
        session["workspace"] = "/new/path"
        session["state"] = "ended"
        await store.save(session)
        loaded = await store.load("test-456")
        assert loaded["workspace"] == "/new/path"
        assert loaded["state"] == "ended"
        await store.close()

    @pytest.mark.asyncio
    async def test_delete(self, store):
        """Test deleting a session."""
        await store.initialize()
        session = {
            "id": "test-789",
            "created_at": "2024-01-01T00:00:00Z",
            "workspace": None,
            "state": "active",
        }
        await store.save(session)
        await store.delete("test-789")
        loaded = await store.load("test-789")
        assert loaded is None
        await store.close()

    @pytest.mark.asyncio
    async def test_list_active(self, store):
        """Test listing active sessions."""
        await store.initialize()
        await store.save({
            "id": "active-1",
            "created_at": "2024-01-01T00:00:00Z",
            "workspace": None,
            "state": "active",
        })
        await store.save({
            "id": "active-2",
            "created_at": "2024-01-01T00:00:00Z",
            "workspace": None,
            "state": "active",
        })
        await store.save({
            "id": "ended-1",
            "created_at": "2024-01-01T00:00:00Z",
            "workspace": None,
            "state": "ended",
        })
        active = await store.list_active()
        assert len(active) == 2
        active_ids = [s["id"] for s in active]
        assert "active-1" in active_ids
        assert "active-2" in active_ids
        assert "ended-1" not in active_ids
        await store.close()

    @pytest.mark.asyncio
    async def test_list_all(self, store):
        """Test listing all sessions."""
        await store.initialize()
        await store.save({
            "id": "session-1",
            "created_at": "2024-01-01T00:00:00Z",
            "workspace": None,
            "state": "active",
        })
        await store.save({
            "id": "session-2",
            "created_at": "2024-01-01T00:00:00Z",
            "workspace": None,
            "state": "ended",
        })
        all_sessions = await store.list_all()
        assert len(all_sessions) == 2
        await store.close()

    @pytest.mark.asyncio
    async def test_concurrent_save(self, store):
        """Test concurrent saves don't corrupt data."""
        await store.initialize()

        async def save_session(idx: int):
            await store.save({
                "id": f"concurrent-{idx}",
                "created_at": "2024-01-01T00:00:00Z",
                "workspace": None,
                "state": "active",
            })

        await asyncio.gather(*[save_session(i) for i in range(10)])
        all_sessions = await store.list_all()
        assert len(all_sessions) == 10
        await store.close()
