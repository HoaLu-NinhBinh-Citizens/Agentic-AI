"""Session manager facade for backward compatibility.

DEPRECATED: This module is kept for backward compatibility only.

For new code, import directly from core.session.persistent_manager:
    from core.session.persistent_manager import PersistentSessionManager

The SessionManagerFacade wraps PersistentSessionManager and provides the same
API as the legacy SessionManager, while enabling tool registry lifecycle
management for Phase 2B/2C.

Usage (deprecated):
    from core.session.session_manager import SessionManagerFacade
    facade = SessionManagerFacade(db_path="data/sessions.db")
    await facade.initialize()

Usage (preferred):
    from core.session.persistent_manager import PersistentSessionManager
    from infrastructure.persistence.sqlite.session_store import SessionStore
    store = SessionStore(Path("data/sessions.db"))
    manager = PersistentSessionManager(store)
    await manager.initialize()
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    from cachetools import TTLCache
    HAS_CACHETOOLS = True
except ImportError:
    HAS_CACHETOOLS = False

from infrastructure.persistence.sqlite.session_store import SessionStore
from core.session.persistent_manager import PersistentSessionManager

if TYPE_CHECKING:
    from application.orchestration.tool_execution.config import ToolExecutionConfig
    from core.agent.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class SessionManagerFacade:
    """Facade wrapping PersistentSessionManager with legacy SessionManager API.

    This class exists to preserve backward compatibility while delegating all
    session operations to PersistentSessionManager. Tool registry lifecycle
    (ToolTracker, ToolRegistry, MCPToolExecutor) is managed here via the
    wrapped PersistentSessionManager.

    Differences from legacy SessionManager:
    - create_session and get_session are async (matching PersistentSessionManager).
    - delete_session accepts an optional grace_period parameter.
    - Exposes set_mcp_manager, set_config, get_tool_registry for tool lifecycle.
    - Stores optional 'data' dict in memory only (not persisted to SQLite store).
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        auto_persist: bool = True,
        max_sessions: int | None = None,
        session_ttl_seconds: float | None = None,
        mcp_manager: Any = None,
        config: Any = None,
    ) -> None:
        """
        Args:
            db_path: SQLite database path for persistence.
            auto_persist: If True, sessions are persisted to SQLite.
            max_sessions: Max in-memory sessions (default 1000).
            session_ttl_seconds: TTL per session in seconds (default 3600s).
            mcp_manager: Optional MCP client manager for tool execution.
            config: Optional ToolExecutionConfig.
        """
        self._db_path = Path(db_path) if db_path else SessionStore()._db_path
        self._auto_persist = auto_persist

        max_sess = max_sessions or PersistentSessionManager._DEFAULT_MAX_SESSIONS
        ttl = session_ttl_seconds or PersistentSessionManager._DEFAULT_TTL_SECONDS

        self._store: SessionStore = SessionStore(self._db_path)
        self._inner = PersistentSessionManager(
            store=self._store,
            mcp_manager=mcp_manager,
            config=config,
            max_sessions=max_sess,
            session_ttl_seconds=ttl,
        )

        # In-memory stash for 'data' kwarg that create_session accepts but
        # the store schema does not persist. Kept separate from the cache
        # so PersistentSessionManager.delete_session still works correctly.
        self._data_stash: dict[str, dict[str, Any]] = {}

        self._initialized = False

    def set_mcp_manager(self, mcp_manager: Any) -> None:
        """Set the MCP manager for tool execution.

        Args:
            mcp_manager: MCPClientManager instance.
        """
        self._inner.set_mcp_manager(mcp_manager)

    def set_config(self, config: ToolExecutionConfig) -> None:
        """Set the tool execution configuration.

        Args:
            config: ToolExecutionConfig instance.
        """
        self._inner.set_config(config)

    async def initialize(self) -> None:
        """Initialize the store and load active sessions into memory cache."""
        if self._initialized:
            return
        await self._store.initialize()
        await self._inner.initialize()
        self._initialized = True
        logger.info("SessionManagerFacade initialized", sessions=len(self._inner.list_sessions()))

    async def close(self) -> None:
        """Close the facade and underlying manager."""
        await self._inner.close()
        await self._store.close()
        self._initialized = False

    def _get_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def create_session(
        self,
        workspace: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> str:
        """Create a new session.

        Args:
            workspace: Optional workspace path for the session.
            data: Optional additional session data (kept in memory only).

        Returns:
            The unique session ID as a string.
        """
        if self._auto_persist:
            session_id = self._inner.create_session(workspace)
            await self._inner.save_session(session_id)
        else:
            session_id = self._inner.create_session(workspace)

        if data:
            self._data_stash[session_id] = data

        logger.debug("Created session: %s", session_id)
        return session_id

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session by ID.

        Args:
            session_id: The session ID.

        Returns:
            Session dict (with 'status' and 'data' fields) or None.
        """
        session = self._inner.get_session(session_id)
        if session is None:
            return None

        # Align field names: store uses 'state', legacy API used 'status'
        result = dict(session)
        result["status"] = result.pop("state", "active")

        # Merge in-memory 'data' stash so callers receive the full dict
        if session_id in self._data_stash:
            result["data"] = self._data_stash[session_id]

        if HAS_CACHETOOLS:
            pass  # TTLCache handles TTL internally
        else:
            self._inner._session_access[session_id] = time.time()

        return result

    async def update_session(self, session_id: str, **kwargs: Any) -> bool:
        """Update session fields and persist.

        Args:
            session_id: Session ID to update.
            **kwargs: Fields to update (e.g. status="active", data={...}).

        Returns:
            True if updated, False if not found.
        """
        session = self._inner.get_session(session_id)
        if session is None:
            return False

        # 'status' in kwargs maps to 'state' in the store schema
        if "status" in kwargs:
            kwargs["state"] = kwargs.pop("status")

        # 'data' in kwargs goes to the in-memory stash only
        if "data" in kwargs:
            self._data_stash[session_id] = kwargs.pop("data")

        session.update(kwargs)

        if self._auto_persist:
            await self._inner.save_session(session_id)

        if HAS_CACHETOOLS:
            pass
        else:
            self._inner._session_access[session_id] = time.time()

        return True

    async def delete_session(self, session_id: str, grace_period: float = 2.0) -> None:
        """Delete a session and its tool registry.

        Args:
            session_id: The session ID to delete.
            grace_period: Grace period in seconds before force cleanup (Phase 2C).
        """
        self._data_stash.pop(session_id, None)
        if self._auto_persist:
            await self._inner.delete_session(session_id, grace_period=grace_period)
        else:
            self._inner._cache.pop(session_id, None)
            await self._inner._close_tool_registry(session_id)
        logger.info("Deleted session: %s", session_id)

    async def end_session(self, session_id: str) -> None:
        """Mark a session as ended.

        Args:
            session_id: The session ID.
        """
        session = self._inner.get_session(session_id)
        if session is None:
            return
        session["state"] = "ended"
        if self._auto_persist:
            await self._inner.save_session(session_id)
        logger.info("Ended session: %s", session_id)

    async def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions from cache.

        Returns:
            List of session dicts with 'status' field (not 'state').
        """
        sessions = self._inner.list_sessions()
        result = []
        for session in sessions:
            out = dict(session)
            out["status"] = out.pop("state", "active")
            if session["id"] in self._data_stash:
                out["data"] = self._data_stash[session["id"]]
            result.append(out)
        return result

    def get_tool_registry(self, session_id: str) -> ToolRegistry | None:
        """Get the tool registry for a session.

        Args:
            session_id: Session identifier.

        Returns:
            ToolRegistry if session has one, None otherwise.
        """
        return self._inner.get_tool_registry(session_id)


# ----------------------------------------------------------------------
# Backward-compatible aliases — keep existing code working without changes
# ----------------------------------------------------------------------
#: Alias for code that imports SessionManager directly.
SessionManager = SessionManagerFacade


class InMemorySessionManager(SessionManagerFacade):
    """In-memory session manager with extended features.

    Alias for SessionManagerFacade with Phase 1A capabilities.
    Backward compatible with existing code (synchronous API).
    """

    def __init__(self) -> None:
        super().__init__(auto_persist=False)

    def create_session(
        self,
        workspace: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> str:
        """Synchronous wrapper — see SessionManagerFacade.create_session."""
        import asyncio
        return asyncio.get_event_loop_policy().get_event_loop().run_until_complete(
            super().create_session(workspace=workspace, data=data)
        )

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Synchronous wrapper — see SessionManagerFacade.get_session."""
        import asyncio
        return asyncio.get_event_loop_policy().get_event_loop().run_until_complete(
            super().get_session(session_id)
        )

    def update_session(self, session_id: str, **kwargs: Any) -> bool:
        """Synchronous wrapper — see SessionManagerFacade.update_session."""
        import asyncio
        return asyncio.get_event_loop_policy().get_event_loop().run_until_complete(
            super().update_session(session_id, **kwargs)
        )

    def delete_session(self, session_id: str) -> None:
        """Synchronous wrapper — see SessionManagerFacade.delete_session."""
        import asyncio
        asyncio.get_event_loop_policy().get_event_loop().run_until_complete(
            super().delete_session(session_id)
        )

    def end_session(self, session_id: str) -> None:
        """Synchronous wrapper — see SessionManagerFacade.end_session."""
        import asyncio
        asyncio.get_event_loop_policy().get_event_loop().run_until_complete(
            super().end_session(session_id)
        )

    def list_sessions(self) -> list[dict[str, Any]]:
        """Synchronous wrapper — see SessionManagerFacade.list_sessions."""
        import asyncio
        return asyncio.get_event_loop_policy().get_event_loop().run_until_complete(
            super().list_sessions()
        )
