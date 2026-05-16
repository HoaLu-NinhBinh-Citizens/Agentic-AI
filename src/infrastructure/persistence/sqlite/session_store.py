"""SQLite session store for Phase 1B.

Provides persistence for session metadata only.
Streaming state (active stream, queues, tasks) is never persisted.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).parent / "schema.sql"
DB_PATH = Path(__file__).parent / "sessions.db"


class SessionStore:
    """SQLite-backed session store.

    Persists only session metadata (id, created_at, workspace, state).
    Streaming state is kept in memory only.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path: Path = db_path or DB_PATH
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the database and create tables if needed."""
        schema = SCHEMA_PATH.read_text()
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(schema)
        await self._conn.commit()
        logger.info("Session store initialized at %s", self._db_path)

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("Session store closed")

    async def save(self, session: dict[str, Any]) -> None:
        """Save or update a session.

        Args:
            session: Session dict with id, created_at, workspace, state keys.
        """
        async with self._lock:
            if not self._conn:
                raise RuntimeError("Session store not initialized")
            await self._conn.execute(
                """
                INSERT INTO sessions (id, created_at, workspace, state)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    workspace = excluded.workspace,
                    state = excluded.state
                """,
                (
                    session["id"],
                    session["created_at"],
                    session.get("workspace"),
                    session["state"],
                ),
            )
            await self._conn.commit()

    async def load(self, session_id: str) -> dict[str, Any] | None:
        """Load a session by ID.

        Args:
            session_id: The session ID to load.

        Returns:
            Session dict or None if not found.
        """
        async with self._lock:
            if not self._conn:
                raise RuntimeError("Session store not initialized")
            cursor = await self._conn.execute(
                "SELECT id, created_at, workspace, state FROM sessions WHERE id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return {
                "id": row["id"],
                "created_at": row["created_at"],
                "workspace": row["workspace"],
                "state": row["state"],
            }

    async def delete(self, session_id: str) -> None:
        """Delete a session by ID.

        Args:
            session_id: The session ID to delete.
        """
        async with self._lock:
            if not self._conn:
                raise RuntimeError("Session store not initialized")
            await self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            await self._conn.commit()

    async def list_active(self) -> list[dict[str, Any]]:
        """List all active sessions.

        Returns:
            List of active session dicts.
        """
        async with self._lock:
            if not self._conn:
                raise RuntimeError("Session store not initialized")
            cursor = await self._conn.execute(
                "SELECT id, created_at, workspace, state FROM sessions WHERE state = 'active'"
            )
            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "created_at": row["created_at"],
                    "workspace": row["workspace"],
                    "state": row["state"],
                }
                for row in rows
            ]

    async def list_all(self) -> list[dict[str, Any]]:
        """List all sessions.

        Returns:
            List of all session dicts.
        """
        async with self._lock:
            if not self._conn:
                raise RuntimeError("Session store not initialized")
            cursor = await self._conn.execute(
                "SELECT id, created_at, workspace, state FROM sessions"
            )
            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "created_at": row["created_at"],
                    "workspace": row["workspace"],
                    "state": row["state"],
                }
                for row in rows
            ]
