"""Session manager with persistence support.

Provides in-memory session management with full lifecycle support.
Sessions are persisted to SQLite for crash recovery.

Note: For Phase 1B and later, use PersistentSessionManager from
core.session.persistent_manager for full SQLite-backed persistence.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import aiosqlite
    HAS_SQLITE = True
except ImportError:
    HAS_SQLITE = False

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages agent sessions with optional SQLite persistence.
    
    FIX W-001: Added persistence to prevent session loss on restart.
    """

    def __init__(self, db_path: str | None = None, auto_persist: bool = True):
        """
        Args:
            db_path: Optional SQLite database path for persistence.
            auto_persist: If True, sessions are persisted to SQLite.
        """
        self._sessions: dict[str, dict[str, Any]] = {}
        self._db_path = db_path
        self._auto_persist = auto_persist and HAS_SQLITE
        self._conn = None
        self._lock = asyncio.Lock()
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize SQLite persistence if enabled."""
        if not self._auto_persist or self._initialized:
            self._initialized = True
            return
        
        if not self._db_path:
            self._db_path = Path("data/sessions.db")
        
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        
        self._conn = await aiosqlite.connect(self._db_path)
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                workspace TEXT,
                status TEXT NOT NULL,
                data TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.commit()
        
        # Load existing sessions
        cursor = await self._conn.execute("SELECT id, created_at, workspace, status, data FROM sessions")
        rows = await cursor.fetchall()
        for row in rows:
            self._sessions[row[0]] = {
                "id": row[0],
                "created_at": row[1],
                "workspace": row[2],
                "status": row[3],
                "data": json.loads(row[4]) if row[4] else {},
            }
        
        self._initialized = True
        logger.info("session_manager_persistence_initialized", sessions=len(self._sessions))
    
    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None
    
    def _get_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
    
    async def _persist_session(self, session_id: str) -> None:
        """Persist session to SQLite atomically."""
        if not self._auto_persist or not self._conn:
            return
        
        session = self._sessions.get(session_id)
        if not session:
            return
        
        try:
            await self._conn.execute("""
                INSERT INTO sessions (id, created_at, workspace, status, data, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    workspace = excluded.workspace,
                    status = excluded.status,
                    data = excluded.data,
                    updated_at = excluded.updated_at
            """, (
                session["id"],
                session["created_at"],
                session.get("workspace"),
                session["status"],
                json.dumps(session.get("data", {})),
                self._get_now(),
            ))
            await self._conn.commit()
        except Exception as e:
            logger.error("session_persist_failed", session_id=session_id, error=str(e))

    async def create_session(self, workspace: str | None = None, data: dict[str, Any] | None = None) -> str:
        """Create a new session.

        Args:
            workspace: Optional workspace path for the session.
            data: Optional additional session data.

        Returns:
            The unique session ID as a string.
        """
        session_id = str(uuid.uuid4())
        now = self._get_now()
        self._sessions[session_id] = {
            "id": session_id,
            "created_at": now,
            "workspace": workspace,
            "status": "active",
            "data": data or {},
        }
        await self._persist_session(session_id)
        return session_id

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session by ID."""
        return self._sessions.get(session_id)

    async def update_session(self, session_id: str, **kwargs) -> bool:
        """Update session fields and persist.
        
        Args:
            session_id: Session ID to update.
            **kwargs: Fields to update.
            
        Returns:
            True if updated, False if not found.
        """
        if session_id not in self._sessions:
            return False
        
        self._sessions[session_id].update(kwargs)
        await self._persist_session(session_id)
        return True
    
    async def delete_session(self, session_id: str) -> None:
        """Delete a session by ID."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            if self._auto_persist and self._conn:
                try:
                    await self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                    await self._conn.commit()
                except Exception as e:
                    logger.error("session_delete_failed", session_id=session_id, error=str(e))

    async def end_session(self, session_id: str) -> None:
        """End a session."""
        if session_id in self._sessions:
            self._sessions[session_id]["status"] = "ended"
            await self._persist_session(session_id)

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions."""
        return list(self._sessions.values())


class InMemorySessionManager(SessionManager):
    """In-memory session manager with extended features.

    Alias for SessionManager with Phase 1A capabilities.
    Backward compatible with existing code.
    """

    def __init__(self):
        super().__init__(auto_persist=False)
