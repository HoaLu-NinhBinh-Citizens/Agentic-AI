"""Session manager for Phase 1A.

Provides in-memory session management with full lifecycle support.
Sessions are NOT persisted - data is lost on restart.

Note: For Phase 1B and later, use PersistentSessionManager from
core.session.persistent_manager for SQLite-backed persistence.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


class SessionManager:
    """Manages agent sessions."""

    def __init__(self):
        self._sessions: dict[str, dict[str, Any]] = {}

    def create_session(self, workspace: str | None = None) -> str:
        """Create a new session.

        Args:
            workspace: Optional workspace path for the session.

        Returns:
            The unique session ID as a string.
        """
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._sessions[session_id] = {
            "id": session_id,
            "created_at": now,
            "workspace": workspace,
            "status": "active",
        }
        return session_id

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session by ID."""
        return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> None:
        """Delete a session by ID."""
        if session_id in self._sessions:
            del self._sessions[session_id]

    def end_session(self, session_id: str) -> None:
        """End a session."""
        if session_id in self._sessions:
            self._sessions[session_id]["status"] = "ended"

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions."""
        return list(self._sessions.values())


class InMemorySessionManager(SessionManager):
    """In-memory session manager with extended features.

    Alias for SessionManager with Phase 1A capabilities.
    Backward compatible with existing code.
    """

    pass
