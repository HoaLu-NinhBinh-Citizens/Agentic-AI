"""Unit tests for InMemorySessionManager."""

from __future__ import annotations

import pytest

from core.session.manager import InMemorySessionManager


class TestInMemorySessionManager:
    """Test suite for InMemorySessionManager."""

    def setup_method(self):
        """Create a fresh manager for each test."""
        self.manager = InMemorySessionManager()

    def test_create_session_returns_uuid(self):
        """Test that create_session returns a valid UUID string."""
        session_id = self.manager.create_session()
        assert isinstance(session_id, str)
        assert len(session_id) == 36
        assert session_id.count("-") == 4

    def test_create_session_returns_different_ids(self):
        """Test that each create_session call returns a unique ID."""
        id1 = self.manager.create_session()
        id2 = self.manager.create_session()
        id3 = self.manager.create_session()
        assert id1 != id2 != id3
        assert len({id1, id2, id3}) == 3

    def test_get_session_returns_correct_dict(self):
        """Test that get_session returns the expected session structure."""
        session_id = self.manager.create_session()
        session = self.manager.get_session(session_id)

        assert session is not None
        assert session["id"] == session_id
        assert "created_at" in session
        assert session["state"] == "active"

    def test_get_session_with_workspace(self):
        """Test that workspace is stored correctly."""
        workspace = "/path/to/workspace"
        session_id = self.manager.create_session(workspace=workspace)
        session = self.manager.get_session(session_id)

        assert session is not None
        assert session["workspace"] == workspace

    def test_get_session_nonexistent_returns_none(self):
        """Test that get_session returns None for unknown ID."""
        session = self.manager.get_session("nonexistent-id")
        assert session is None

    def test_delete_session_removes_session(self):
        """Test that delete_session removes the session."""
        session_id = self.manager.create_session()
        assert self.manager.get_session(session_id) is not None

        self.manager.delete_session(session_id)
        assert self.manager.get_session(session_id) is None

    def test_delete_session_raises_for_nonexistent(self):
        """Test that delete_session raises KeyError for unknown ID."""
        with pytest.raises(KeyError):
            self.manager.delete_session("nonexistent-id")

    def test_list_sessions_returns_all_sessions(self):
        """Test that list_sessions returns all created sessions."""
        id1 = self.manager.create_session()
        id2 = self.manager.create_session(workspace="/test")
        sessions = self.manager.list_sessions()

        assert len(sessions) == 2
        session_ids = [s["id"] for s in sessions]
        assert id1 in session_ids
        assert id2 in session_ids

    def test_list_sessions_empty_initially(self):
        """Test that list_sessions returns empty list initially."""
        assert self.manager.list_sessions() == []

    def test_delete_then_create_idempotent(self):
        """Test that deleting and recreating works correctly."""
        id1 = self.manager.create_session()
        self.manager.delete_session(id1)
        id2 = self.manager.create_session()

        assert id1 != id2
        assert self.manager.get_session(id1) is None
        assert self.manager.get_session(id2) is not None
