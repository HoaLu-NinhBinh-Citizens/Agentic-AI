"""Unit tests for PersistentSessionManager (Phase 1B)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
import asyncio

import pytest

from core.session.persistent_manager import PersistentSessionManager
from infrastructure.persistence.sqlite.session_store import SessionStore


class TestPersistentSessionManager:
    """Test suite for PersistentSessionManager."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database file."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        yield db_path
        db_path.unlink(missing_ok=True)

    @pytest.fixture
    async def manager(self, temp_db):
        """Create a PersistentSessionManager instance."""
        store = SessionStore(db_path=temp_db)
        manager = PersistentSessionManager(store)
        await manager.initialize()
        yield manager
        await manager.close()

    @pytest.mark.asyncio
    async def test_initialize_loads_active_sessions(self, manager):
        """Test that initialize loads active sessions from DB."""
        assert len(manager.list_sessions()) == 0

    @pytest.mark.asyncio
    async def test_create_and_save_session(self, manager):
        """Test creating and saving a session."""
        session_id = manager.create_session(workspace="/test")
        await manager.save_session(session_id)

        assert manager.get_session(session_id) is not None
        assert manager.get_session(session_id)["workspace"] == "/test"

    @pytest.mark.asyncio
    async def test_create_and_save_session_works(self, manager):
        """Test creating and saving session (async version)."""
        session_id = await manager.create_and_save_session(workspace="/async/test")

        assert manager.get_session(session_id) is not None
        assert manager.get_session(session_id)["workspace"] == "/async/test"

    @pytest.mark.asyncio
    async def test_get_session_nonexistent(self, manager):
        """Test getting nonexistent session."""
        assert manager.get_session("nonexistent") is None

    @pytest.mark.asyncio
    async def test_delete_session(self, temp_db):
        """Test deleting a session."""
        store = SessionStore(db_path=temp_db)
        manager = PersistentSessionManager(store)
        await manager.initialize()

        session_id = manager.create_session()
        await manager.save_session(session_id)

        assert manager.get_session(session_id) is not None

        await manager.delete_session(session_id)

        assert manager.get_session(session_id) is None

        await manager.close()

    @pytest.mark.asyncio
    async def test_end_session(self, temp_db):
        """Test ending a session."""
        store = SessionStore(db_path=temp_db)
        manager = PersistentSessionManager(store)
        await manager.initialize()

        session_id = manager.create_session()
        await manager.save_session(session_id)

        await manager.end_session(session_id)

        session = manager.get_session(session_id)
        assert session is not None
        assert session["state"] == "ended"

        await manager.close()

    @pytest.mark.asyncio
    async def test_list_sessions(self, manager):
        """Test listing sessions."""
        session_id1 = manager.create_session()
        await manager.save_session(session_id1)

        session_id2 = manager.create_session(workspace="/test")
        await manager.save_session(session_id2)

        sessions = manager.list_sessions()
        assert len(sessions) == 2

    @pytest.mark.asyncio
    async def test_persistence_across_restarts(self, temp_db):
        """Test that sessions persist across manager restarts."""
        store1 = SessionStore(db_path=temp_db)
        manager1 = PersistentSessionManager(store1)
        await manager1.initialize()

        session_id = manager1.create_session(workspace="/persist")
        await manager1.save_session(session_id)

        await manager1.close()

        store2 = SessionStore(db_path=temp_db)
        manager2 = PersistentSessionManager(store2)
        await manager2.initialize()

        session = manager2.get_session(session_id)
        assert session is not None
        assert session["workspace"] == "/persist"

        await manager2.close()

    @pytest.mark.asyncio
    async def test_save_session_not_found(self, temp_db):
        """Test saving nonexistent session raises KeyError."""
        store = SessionStore(db_path=temp_db)
        manager = PersistentSessionManager(store)
        await manager.initialize()

        with pytest.raises(KeyError):
            await manager.save_session("nonexistent")

        await manager.close()
