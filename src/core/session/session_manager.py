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
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import aiosqlite
    HAS_SQLITE = True
except ImportError:
    HAS_SQLITE = False

try:
    from cachetools import TTLCache
    HAS_CACHETOOLS = True
except ImportError:
    HAS_CACHETOOLS = False

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages agent sessions with optional SQLite persistence.

    FIX W-001: Added persistence to prevent session loss on restart.

    W-012 Fix: TTLCache replaces unbounded dict to prevent OOM after 8h.
    W-012 Fix: get_session() is now async and holds lock to fix read race.
    """

    _DEFAULT_MAX_SESSIONS = 1000
    _DEFAULT_TTL_SECONDS = 3600.0  # 1 hour idle before eviction

    def __init__(
        self,
        db_path: str | None = None,
        auto_persist: bool = True,
        max_sessions: int | None = None,
        session_ttl_seconds: float | None = None,
    ):
        """
        Args:
            db_path: Optional SQLite database path for persistence.
            auto_persist: If True, sessions are persisted to SQLite.
            max_sessions: Max in-memory sessions (default 1000).
            session_ttl_seconds: TTL per session in seconds (default 3600s).
        """
        self._db_path = db_path
        self._auto_persist = auto_persist and HAS_SQLITE
        self._conn = None
        self._lock = asyncio.Lock()
        self._initialized = False
        self._persist_needed = False

        max_sess = max_sessions or self._DEFAULT_MAX_SESSIONS
        ttl = session_ttl_seconds or self._DEFAULT_TTL_SECONDS
        if HAS_CACHETOOLS:
            self._sessions: dict[str, dict[str, Any]] = TTLCache(
                maxsize=max_sess, ttl=ttl
            )
        else:
            self._sessions = {}  # type: ignore[assignment]
            self._session_ttl = ttl
            self._session_access: dict[str, float] = {}
    
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
        async with self._lock:
            session_id = str(uuid.uuid4())
            now = self._get_now()
            session = {
                "id": session_id,
                "created_at": now,
                "workspace": workspace,
                "status": "active",
                "data": data or {},
            }
            self._sessions[session_id] = session
            if HAS_CACHETOOLS:
                pass  # TTLCache handles eviction internally
            else:
                self._session_access[session_id] = time.time()

        await self._persist_session(session_id)
        return session_id

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session by ID (thread-safe, with TTL eviction for fallback)."""
        async with self._lock:
            if HAS_CACHETOOLS:
                return self._sessions.get(session_id)
            # Fallback: evict stale sessions before lookup
            now = time.time()
            stale = [
                sid for sid, last_access in self._session_access.items()
                if now - last_access > self._session_ttl
            ]
            for sid in stale:
                self._sessions.pop(sid, None)
                self._session_access.pop(sid, None)
            self._session_access[session_id] = now
            return self._sessions.get(session_id)

    async def update_session(self, session_id: str, **kwargs) -> bool:
        """Update session fields and persist.

        Args:
            session_id: Session ID to update.
            **kwargs: Fields to update.

        Returns:
            True if updated, False if not found.
        """
        async with self._lock:
            if session_id not in self._sessions:
                return False

            self._sessions[session_id].update(kwargs)
            if HAS_CACHETOOLS:
                # Access updates TTL on TTLCache
                self._sessions[session_id] = self._sessions[session_id]
            else:
                self._session_access[session_id] = time.time()

        await self._persist_session(session_id)
        return True
    
    async def delete_session(self, session_id: str) -> None:
        """Delete a session by ID."""
        async with self._lock:
            in_cache = session_id in self._sessions
            if in_cache:
                del self._sessions[session_id]
                if not HAS_CACHETOOLS:
                    self._session_access.pop(session_id, None)

        if in_cache and self._auto_persist and self._conn:
            try:
                await self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                await self._conn.commit()
            except Exception as e:
                logger.error("session_delete_failed", session_id=session_id, error=str(e))

    async def end_session(self, session_id: str) -> None:
        """End a session."""
        async with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["status"] = "ended"

        await self._persist_session(session_id)

    async def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions (thread-safe snapshot)."""
        async with self._lock:
            return list(self._sessions.values())


class InMemorySessionManager(SessionManager):
    """In-memory session manager with extended features.

    Alias for SessionManager with Phase 1A capabilities.
    Backward compatible with existing code.
    """

    def __init__(self):
        super().__init__(auto_persist=False)
