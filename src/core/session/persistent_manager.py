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

    Attributes:
        _store: SQLite session store.
        _cache: In-memory session cache.
        _tool_registries: Per-session tool registries.
        _mcp_manager: MCP manager for tool execution.
        _config: Tool execution configuration.
    """

    def __init__(
        self,
        store: SessionStore,
        mcp_manager: Any = None,
        config: ToolExecutionConfig | None = None,
    ) -> None:
        """Initialize the persistent session manager.

        Args:
            store: SQLite session store.
            mcp_manager: Optional MCP manager for tool execution.
            config: Optional tool execution configuration.
        """
        self._store = store
        self._cache: dict[str, dict[str, Any]] = {}
        self._tool_registries: dict[str, ToolRegistry] = {}
        self._mcp_manager = mcp_manager
        self._config = config

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
        """Load active sessions from DB into memory cache."""
        await self._store.initialize()
        active_sessions = await self._store.list_active()
        for session in active_sessions:
            self._cache[session["id"]] = session
        logger.info(
            "Loaded %d active sessions from database", len(self._cache)
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
