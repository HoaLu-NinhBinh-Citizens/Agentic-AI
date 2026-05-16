"""Tool execution tracker for Phase 2B/2C.

Manages pending tool calls and execution history per session.
Provides thread-safe state transitions and history management.
Phase 2C: Adds cancellation token support.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from domain.models.tool_call import (
    ToolCallRecord,
    ToolCallState,
    validate_transition,
    InvalidStateTransitionError,
)
from shared.exceptions.tool_errors import ToolBusyError

if TYPE_CHECKING:
    from core.execution.cancellation import CancellationToken

logger = logging.getLogger(__name__)


class ToolTracker:
    """Tracks tool execution state per session.

    Manages two collections:
    - _pending: Active tool calls that haven't completed
    - _history: Completed tool calls (up to max_history)

    Thread-safety is achieved via asyncio.Lock for all state mutations.

    Phase 2C: Supports cancellation tokens for true cancellation.

    Attributes:
        session_id: The session this tracker belongs to.
        max_history: Maximum number of completed calls to retain.
        max_pending: Maximum number of pending calls (for backpressure).
    """

    _FINISHED_STATES = frozenset({
        ToolCallState.COMPLETED,
        ToolCallState.FAILED,
        ToolCallState.TIMED_OUT,
        ToolCallState.CANCELLED,
    })

    def __init__(
        self,
        session_id: str,
        max_history: int = 100,
        max_pending: int = 20,
    ) -> None:
        """Initialize the tool tracker.

        Args:
            session_id: Session identifier for logging.
            max_history: Maximum number of completed calls to retain in history.
            max_pending: Maximum number of pending calls before backpressure.
        """
        self._session_id = session_id
        self._pending: dict[str, ToolCallRecord] = {}
        self._history: list[ToolCallRecord] = []
        self._max_history = max_history
        self._max_pending = max_pending
        self._lock = asyncio.Lock()
        self._cancellation_tokens: dict[str, CancellationToken] = {}

    @property
    def session_id(self) -> str:
        """Return the session ID."""
        return self._session_id

    @property
    def max_pending(self) -> int:
        """Return the max pending limit."""
        return self._max_pending

    async def add_pending(
        self,
        record: ToolCallRecord,
        enforce_max_pending: bool = True,
    ) -> None:
        """Add a new tool call to the pending queue.

        Args:
            record: The tool call record to add.
            enforce_max_pending: Whether to enforce max_pending limit.

        Raises:
            ToolBusyError: If max_pending is reached and enforce_max_pending=True.
        """
        async with self._lock:
            if enforce_max_pending and len(self._pending) >= self._max_pending:
                raise ToolBusyError(
                    f"Max pending calls ({self._max_pending}) reached for session {self._session_id}"
                )

            self._pending[record.call_id] = record
            logger.debug(
                "Tool call pending",
                session_id=self._session_id,
                call_id=record.call_id,
                tool_name=record.tool_name,
                pending_count=len(self._pending),
            )

    async def update_state(
        self,
        call_id: str,
        state: ToolCallState,
        validate: bool = True,
        **kwargs: object,
    ) -> bool:
        """Update the state of a tool call.

        When a call transitions to a finished state, it is moved from
        pending to history.

        Args:
            call_id: The call identifier.
            state: The new state.
            validate: Whether to validate the state transition.
            **kwargs: Additional fields to update on the record.

        Returns:
            True if the call was found and updated, False otherwise.

        Raises:
            InvalidStateTransitionError: If validate=True and transition is invalid.
        """
        async with self._lock:
            record = self._pending.get(call_id)
            if not record:
                logger.warning(
                    "Tool call not found for state update: call_id=%s, session_id=%s, state=%s",
                    call_id,
                    self._session_id,
                    state.value,
                )
                return False

            if validate:
                validate_transition(record.state, state, call_id)

            record.state = state
            for key, value in kwargs.items():
                setattr(record, key, value)

            if state in self._FINISHED_STATES:
                record.completed_at = datetime.now(timezone.utc)
                if record.started_at:
                    delta = record.completed_at - record.started_at
                    record.duration_ms = delta.total_seconds() * 1000

                self._history.append(record)
                del self._pending[call_id]

                if len(self._history) > self._max_history:
                    self._history.pop(0)

                logger.debug(
                    "Tool call finished",
                    session_id=self._session_id,
                    call_id=call_id,
                    state=state.value,
                    duration_ms=record.duration_ms,
                    history_size=len(self._history),
                )

            return True

    async def transition_record(
        self,
        call_id: str,
        new_state: ToolCallState,
        **kwargs: object,
    ) -> bool:
        """Centralized state transition with validation.

        This method provides a single entry point for state transitions,
        making it easier to add auditing, metrics, and validation.

        Args:
            call_id: The call identifier.
            new_state: The target state.
            **kwargs: Additional fields to update.

        Returns:
            True if transition succeeded, False if call not found.
        """
        return await self.update_state(call_id, new_state, validate=True, **kwargs)

    async def get_pending_ids(self) -> list[str]:
        """Get list of pending call IDs.

        Returns:
            List of call IDs currently in pending state.
        """
        async with self._lock:
            return list(self._pending.keys())

    async def get_pending_count(self) -> int:
        """Get the number of pending tool calls.

        Returns:
            Count of pending calls.
        """
        async with self._lock:
            return len(self._pending)

    async def get_pending_record(self, call_id: str) -> ToolCallRecord | None:
        """Get a pending tool call record by ID.

        Args:
            call_id: The call identifier.

        Returns:
            The record if found and pending, None otherwise.
        """
        async with self._lock:
            return self._pending.get(call_id)

    async def register_cancellation_token(
        self,
        call_id: str,
        token: CancellationToken,
    ) -> None:
        """Register a cancellation token for a call.

        Args:
            call_id: The call identifier.
            token: Cancellation token to register.
        """
        async with self._lock:
            self._cancellation_tokens[call_id] = token
            logger.debug(
                "Registered cancellation token",
                session_id=self._session_id,
                call_id=call_id,
            )

    async def get_cancellation_token(self, call_id: str) -> CancellationToken | None:
        """Get the cancellation token for a call.

        Args:
            call_id: The call identifier.

        Returns:
            The CancellationToken if registered, None otherwise.
        """
        async with self._lock:
            return self._cancellation_tokens.get(call_id)

    async def unregister_cancellation_token(self, call_id: str) -> None:
        """Unregister a cancellation token.

        Args:
            call_id: The call identifier.
        """
        async with self._lock:
            self._cancellation_tokens.pop(call_id, None)
            logger.debug(
                "Unregistered cancellation token",
                session_id=self._session_id,
                call_id=call_id,
            )

    async def cancel_pending(self) -> list[str]:
        """Cancel all pending calls.

        Returns:
            List of call IDs that were cancelled.
        """
        cancelled_ids = []
        async with self._lock:
            for call_id, token in self._cancellation_tokens.items():
                if call_id in self._pending:
                    token.cancel()
                    cancelled_ids.append(call_id)
        logger.info(
            "Cancelled pending calls",
            session_id=self._session_id,
            count=len(cancelled_ids),
        )
        return cancelled_ids

    async def get_history(self) -> list[ToolCallRecord]:
        """Get all completed tool call records.

        Returns:
            Copy of the history list.
        """
        async with self._lock:
            return list(self._history)

    async def close(self, mark_orphaned: bool = True) -> None:
        """Close the tracker and clean up pending calls.

        Optionally marks remaining pending calls as orphaned for debugging.
        ORPHANED state indicates execution whose lifecycle could not be
        fully observed due to shutdown or ownership loss.

        Args:
            mark_orphaned: If True, mark pending calls as ORPHANED state.
        """
        async with self._lock:
            if mark_orphaned:
                for record in self._pending.values():
                    record.state = ToolCallState.ORPHANED
                    record.completed_at = datetime.now(timezone.utc)
                    self._history.append(record)

                if len(self._history) > self._max_history:
                    self._history = self._history[-self._max_history:]

                logger.info(
                    "Tool tracker closed",
                    session_id=self._session_id,
                    orphaned_count=len(self._pending),
                    history_size=len(self._history),
                )

            self._pending.clear()
