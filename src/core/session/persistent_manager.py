"""Persistent session manager for Phase 1B/2B/2C.

Replaces in-memory SessionManager with SQLite-backed persistence.
Sessions survive server restarts.

Phase 2B extension:
- Creates ToolTracker, ToolExecutor, and ToolRegistry per session
- Session deletion closes and cleans up tool registries

Phase 2C extension:
- Grace period for cancellation on session deletion
- Cancellation token registration with registries
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

try:
    from cachetools import TTLCache
    HAS_CACHETOOLS = True
except ImportError:
    HAS_CACHETOOLS = False

from infrastructure.persistence.sqlite.session_store import SessionStore

if TYPE_CHECKING:
    from application.orchestration.tool_execution.config import ToolExecutionConfig
    from core.agent.tool_registry import ToolRegistry
    from core.execution.tool_tracker import ToolTracker
    from infrastructure.tool_execution.executor import ToolExecutor, MCPToolExecutor

logger = logging.getLogger(__name__)


class PersistentSessionManager:
    """Session manager with SQLite persistence and tool registry lifecycle.

    Maintains an in-memory cache backed by SQLite.
    On startup, loads all active sessions from DB into memory.

    Phase 2B: Manages tool registries per session with proper cleanup.

    W-012 Fix: TTLCache replaces unbounded _cache dict to prevent OOM after 8h.
    Tool registries are cleaned up on session deletion (already correct).

    Attributes:
        _store: SQLite session store.
        _cache: In-memory session cache (bounded, TTL-evicted).
        _tool_registries: Per-session tool registries.
        _mcp_manager: MCP manager for tool execution.
        _config: Tool execution configuration.
    """

    _DEFAULT_MAX_SESSIONS = 1000
    _DEFAULT_TTL_SECONDS = 3600.0

    def __init__(
        self,
        store: SessionStore,
        mcp_manager: Any = None,
        config: Any = None,
        max_sessions: int | None = None,
        session_ttl_seconds: float | None = None,
    ) -> None:
        """Initialize the persistent session manager.

        Args:
            store: SQLite session store.
            mcp_manager: Optional MCP manager for tool execution.
            config: Optional tool execution configuration.
            max_sessions: Max in-memory sessions (default 1000).
            session_ttl_seconds: TTL per session in seconds (default 3600s).
        """
        self._store = store
        self._mcp_manager = mcp_manager
        self._config = config

        max_sess = max_sessions or self._DEFAULT_MAX_SESSIONS
        ttl = session_ttl_seconds or self._DEFAULT_TTL_SECONDS
        if HAS_CACHETOOLS:
            self._cache: dict[str, dict[str, Any]] = TTLCache(
                maxsize=max_sess, ttl=ttl
            )
            self._session_access: dict[str, float] = {}  # not needed with TTLCache
        else:
            self._cache = {}  # type: ignore[assignment]
            self._session_ttl = ttl
            self._session_access: dict[str, float] = {}

        self._tool_registries: dict[str, Any] = {}

    def set_mcp_manager(self, mcp_manager: Any) -> None:
        """Set the MCP manager for tool execution.

        Args:
            mcp_manager: MCPClientManager instance.
        """
        self._mcp_manager = mcp_manager

    def set_config(self, config: ToolExecutionConfig) -> None:
        """Set the tool execution configuration.

        Args:
            config: Tool execution configuration.
        """
        self._config = config

    async def initialize(self) -> None:
        """Load active sessions from DB into memory cache.

        W-012 Fix: Only loads up to max_sessions most-recent sessions
        to prevent OOM when DB has thousands of stale sessions.
        """
        import time as _time

        await self._store.initialize()
        active_sessions = await self._store.list_active()
        # Sort by created_at desc and cap at max_sessions to prevent OOM on startup
        active_sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        max_sess = getattr(self, "_DEFAULT_MAX_SESSIONS", 1000)
        for session in active_sessions[:max_sess]:
            self._cache[session["id"]] = session
            if not HAS_CACHETOOLS:
                self._session_access[session["id"]] = _time.time()
        logger.info(
            "Loaded %d active sessions from database (capped at %d)",
            len(self._cache),
            max_sess,
        )

    async def close(self) -> None:
        """Close the session manager and all tool registries."""
        for session_id in list(self._tool_registries.keys()):
            await self._close_tool_registry(session_id)
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
        if not HAS_CACHETOOLS:
            import time as _time
            self._session_access[session_id] = _time.time()
        self._create_tool_registry(session_id)
        return session_id

    def _create_tool_registry(self, session_id: str) -> ToolRegistry:
        """Create a tool registry for a session.

        Args:
            session_id: Session identifier.

        Returns:
            Created ToolRegistry instance.
        """
        from core.execution.tool_tracker import ToolTracker
        from core.agent.tool_registry import ToolRegistry
        from infrastructure.tool_execution.executor import MCPToolExecutor

        tracker = ToolTracker(
            session_id,
            max_history=self._config.max_history_per_session if self._config else 100,
        )

        executor: ToolExecutor
        if self._mcp_manager:
            executor = MCPToolExecutor(self._mcp_manager)
        else:
            from infrastructure.tool_execution.executor import MockToolExecutor
            executor = MockToolExecutor()

        registry = ToolRegistry(
            session_id,
            executor,
            tracker,
            max_concurrent=(
                self._config.max_concurrent_tools_per_session
                if self._config
                else 5
            ),
            timeout_seconds=(
                self._config.default_timeout_seconds
                if self._config
                else 30.0
            ),
        )

        self._tool_registries[session_id] = registry
        logger.debug(
            "Created tool registry for session",
            session_id=session_id,
        )
        return registry

    def get_tool_registry(self, session_id: str) -> ToolRegistry | None:
        """Get the tool registry for a session.

        Args:
            session_id: Session identifier.

        Returns:
            ToolRegistry if session has one, None otherwise.
        """
        return self._tool_registries.get(session_id)

    async def _close_tool_registry(self, session_id: str) -> None:
        """Close and remove the tool registry for a session.

        Args:
            session_id: Session identifier.
        """
        registry = self._tool_registries.pop(session_id, None)
        if registry:
            await registry.close(cancel_pending=True)
            logger.debug(
                "Closed tool registry for session",
                session_id=session_id,
            )

    async def save_session(self, session_id: str) -> None:
        """Persist session to database.

        Args:
            session_id: The session ID to persist.
        """
        if session_id not in self._cache:
            raise KeyError(f"Session {session_id} not found")
        if not HAS_CACHETOOLS:
            import time as _time
            self._session_access[session_id] = _time.time()
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
        session = self._cache.get(session_id)
        if session is not None and not HAS_CACHETOOLS:
            import time as _time
            self._session_access[session_id] = _time.time()
        return session

    async def delete_session(self, session_id: str, grace_period: float = 2.0) -> None:
        """Delete a session from cache and database.

        Phase 2B: Also closes the tool registry for this session.

        Phase 2C: Implements graceful cancellation with polling-based grace period.
        Pending calls are cancelled first, then we poll until all tasks complete
        or timeout expires. This is more responsive than a fixed sleep.

        Args:
            session_id: The session ID.
            grace_period: Grace period in seconds before force cleanup.
        """
        import time

        registry = self._tool_registries.get(session_id)
        if registry:
            pending_ids = await registry._tracker.get_pending_ids()
            for call_id in pending_ids:
                await registry.cancel_call(call_id)

            if grace_period > 0:
                logger.info(
                    "Waiting for pending calls to complete: session_id=%s, grace_period=%.2f, pending_count=%d",
                    session_id,
                    grace_period,
                    len(pending_ids),
                )

                start_time = time.monotonic()
                poll_interval = 0.1

                while True:
                    remaining = await registry._tracker.get_pending_count()
                    if remaining == 0:
                        logger.info(
                            "All pending calls completed: session_id=%s",
                            session_id,
                        )
                        break

                    elapsed = time.monotonic() - start_time
                    if elapsed >= grace_period:
                        logger.warning(
                            "Grace period exceeded: session_id=%s, elapsed=%.2f, remaining=%d",
                            session_id,
                            elapsed,
                            remaining,
                        )
                        break

                    await asyncio.sleep(poll_interval)

            await self._close_tool_registry(session_id)

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
