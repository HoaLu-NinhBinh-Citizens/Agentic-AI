"""Persistent session manager for Phase 1B.

Replaces in-memory SessionManager with SQLite-backed persistence.
Sessions survive server restarts.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from infrastructure.persistence.sqlite.session_store import SessionStore

logger = logging.getLogger(__name__)


class PersistentSessionManager:
    """Session manager with SQLite persistence.

    Maintains an in-memory cache backed by SQLite.
    On startup, loads all active sessions from DB into memory.
    """

    def __init__(self, store: SessionStore) -> None:
        self._store = store
        self._cache: dict[str, dict[str, Any]] = {}

    async def initialize(self) -> None:
        """Load active sessions from DB into memory cache."""
        await self._store.initialize()
        active_sessions = await self._store.list_active()
        for session in active_sessions:
            self._cache[session["id"]] = session
        logger.info(
            "Loaded %d active sessions from database", len(self._cache)
        )

    async def close(self) -> None:
        """Close the session store."""
        await self._store.close()

    def create_session(self, workspace: str | None = None) -> str:
        """Create a new session.

        Args:
            workspace: Optional workspace path for the session.

        Returns:
            The unique session ID as a string.
        """
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        session = {
            "id": session_id,
            "created_at": now,
            "workspace": workspace,
            "state": "active",
        }
        self._cache[session_id] = session
        return session_id

    async def save_session(self, session_id: str) -> None:
        """Persist session to database.

        Args:
            session_id: The session ID to persist.
        """
        if session_id not in self._cache:
            raise KeyError(f"Session {session_id} not found")
        await self._store.save(self._cache[session_id])

    async def create_and_save_session(self, workspace: str | None = None) -> str:
        """Create a new session and persist to database.

        Args:
            workspace: Optional workspace path for the session.

        Returns:
            The unique session ID as a string.
        """
        session_id = self.create_session(workspace)
        await self.save_session(session_id)
        logger.info("Created and persisted session: %s", session_id)
        return session_id

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session by ID from cache.

        Args:
            session_id: The session ID.

        Returns:
            Session dict or None if not found.
        """
        return self._cache.get(session_id)

    async def delete_session(self, session_id: str) -> None:
        """Delete a session from cache and database.

        Args:
            session_id: The session ID.
        """
        if session_id in self._cache:
            del self._cache[session_id]
        await self._store.delete(session_id)
        logger.info("Deleted session: %s", session_id)

    async def end_session(self, session_id: str) -> None:
        """Mark a session as ended.

        Args:
            session_id: The session ID.
        """
        if session_id in self._cache:
            self._cache[session_id]["state"] = "ended"
            await self._store.save(self._cache[session_id])
            logger.info("Ended session: %s", session_id)

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions from cache.

        Returns:
            List of session dicts.
        """
        return list(self._cache.values())
