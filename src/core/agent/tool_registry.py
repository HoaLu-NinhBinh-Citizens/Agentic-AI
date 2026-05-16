"""Tool registry with concurrency control for Phase 2B/2C.

Central component for dispatching tool calls within a session.
Handles semaphore-based concurrency limits and timeout enforcement.
Phase 2C: Adds cancellation token support and cancel_call method.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from domain.models.tool_call import ToolCallRecord, ToolCallState
from domain.models.execution import ExecutionContext, ToolExecutionResult
from infrastructure.tool_execution.executor import ToolExecutor
from core.execution.tool_tracker import ToolTracker
from core.execution.cancellation import CancellationToken, ProcessHandle, NoOpProcessHandle
from shared.exceptions.tool_errors import (
    ToolBusyError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolSessionClosedError,
    normalize_tool_error,
)

if TYPE_CHECKING:
    from core.execution.cancellation import CancellationRegistry

logger = logging.getLogger(__name__)


class CancellationTokenRegistry:
    """Simple registry for tracking cancellation tokens per call.

    Phase 2C: Provides a lightweight alternative to CancellationRegistry
    when full cross-session tracking is not needed.
    """

    def __init__(self) -> None:
        """Initialize the token registry."""
        self._tokens: dict[str, CancellationToken] = {}

    def register(self, call_id: str, token: CancellationToken) -> None:
        """Register a cancellation token."""
        self._tokens[call_id] = token

    def get(self, call_id: str) -> CancellationToken | None:
        """Get a cancellation token."""
        return self._tokens.get(call_id)

    def unregister(self, call_id: str) -> None:
        """Unregister a cancellation token."""
        self._tokens.pop(call_id, None)

    def clear(self) -> None:
        """Clear all tokens."""
        self._tokens.clear()


class ToolRegistry:
    """Registry for executing tools within a session.

    Provides:
    - Semaphore-based concurrency control
    - Timeout enforcement
    - State tracking via ToolTracker
    - Guaranteed cleanup of records
    - Max pending enforcement for backpressure
    - Phase 2C: Cancellation token support and cancel_call method

    Attributes:
        session_id: The session this registry belongs to.
        timeout_seconds: Default timeout for tool executions.
    """

    def __init__(
        self,
        session_id: str,
        executor: ToolExecutor,
        tracker: ToolTracker,
        max_concurrent: int = 5,
        timeout_seconds: float = 30.0,
        cancellation_registry: CancellationRegistry | None = None,
    ) -> None:
        """Initialize the tool registry.

        Args:
            session_id: Session identifier.
            executor: Tool executor for actual execution.
            tracker: Tool tracker for state management.
            max_concurrent: Maximum concurrent tool calls per session.
            timeout_seconds: Default timeout for each tool call.
            cancellation_registry: Optional cancellation registry for Phase 2C.
        """
        self._session_id = session_id
        self._executor = executor
        self._tracker = tracker
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._timeout = timeout_seconds
        self._closed = False
        self._max_concurrent = max_concurrent
        self._cancellation_registry = cancellation_registry or CancellationTokenRegistry()
        self._process_handles: dict[str, ProcessHandle] = {}

    @property
    def session_id(self) -> str:
        """Return the session ID."""
        return self._session_id

    @property
    def max_concurrent(self) -> int:
        """Return the max concurrent limit."""
        return self._max_concurrent

    def get_executor_capabilities(self) -> Any:
        """Get the capabilities of the underlying executor.

        Returns:
            ToolCapabilities instance.
        """
        return self._executor.capabilities if hasattr(self._executor, "capabilities") else None

    def check_capability(self, required_capability: str) -> bool:
        """Check if the executor supports a required capability.

        Args:
            required_capability: The capability to check (e.g., "cancellable", "streaming").

        Returns:
            True if supported, False otherwise.
        """
        caps = self.get_executor_capabilities()
        if caps is None:
            return False
        return getattr(caps, required_capability, False)

    def register_process_handle(self, call_id: str, handle: ProcessHandle) -> None:
        """Register a process handle for a call.

        Args:
            call_id: The call identifier.
            handle: Process handle to register.
        """
        self._process_handles[call_id] = handle

    async def cancel_call(self, call_id: str) -> bool:
        """Cancel a running or pending tool call.

        Phase 2C: This method provides true cancellation by:
        1. Cancelling the associated cancellation token
        2. Terminating the underlying process (if applicable)

        Args:
            call_id: The call to cancel.

        Returns:
            True if the call was found and cancellation was requested, False otherwise.
        """
        if self._closed:
            logger.warning("Cannot cancel: registry is closed, call_id=%s", call_id)
            return False

        token = await self._tracker.get_cancellation_token(call_id)
        if not token:
            logger.warning("No cancellation token found: call_id=%s", call_id)
            return False

        token.cancel()

        handle = self._process_handles.pop(call_id, None)
        if handle:
            await self._terminate_handle(handle)

        await self._tracker.transition_record(call_id, ToolCallState.CANCELLED)

        logger.info("Call cancelled: session_id=%s, call_id=%s", self._session_id, call_id)
        return True

    async def _terminate_handle(self, handle: ProcessHandle) -> None:
        """Terminate a process handle with graceful shutdown followed by force kill.

        Args:
            handle: The process handle to terminate.
        """
        try:
            await handle.terminate()
            await asyncio.sleep(0.1)
            await handle.kill()
        except Exception as e:
            logger.warning("Error terminating process handle: error=%s", str(e))

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        call_id: str | None = None,
        trace_id: str | None = None,
        parent_call_id: str | None = None,
        client_id: str = "",
        cancellation_token: CancellationToken | None = None,
    ) -> tuple[str, ToolExecutionResult]:
        """Execute a tool call with full state management.

        This method guarantees that:
        1. A ToolCallRecord is created in PENDING state
        2. Max pending enforcement before adding to queue
        3. The semaphore is acquired before execution
        4. The record transitions to RUNNING when execution starts
        5. The record transitions to final state (COMPLETED/FAILED/TIMED_OUT)
        6. The record is moved to history when finished

        Phase 2C: Supports cancellation tokens for true cancellation.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Tool input arguments.
            call_id: Optional call ID (generated if not provided).
            trace_id: Optional trace ID for observability.
            parent_call_id: Optional parent call ID for nested calls.
            client_id: WebSocket client ID that initiated the call.
            cancellation_token: Optional cancellation token for Phase 2C.

        Returns:
            Tuple of (call_id, ToolExecutionResult).

        Raises:
            ToolSessionClosedError: If the session is closed.
            ToolBusyError: If max pending or concurrency limit is reached.
        """
        if self._closed:
            raise ToolSessionClosedError("Session closed")

        call_id = call_id or str(uuid.uuid4())
        trace_id = trace_id or str(uuid.uuid4())

        token = cancellation_token or CancellationToken()

        record = ToolCallRecord(
            call_id=call_id,
            session_id=self._session_id,
            tool_name=tool_name,
            arguments=arguments,
            state=ToolCallState.PENDING,
            trace_id=trace_id,
            parent_call_id=parent_call_id,
            client_id=client_id,
        )

        try:
            await self._tracker.add_pending(record, enforce_max_pending=True)
            await self._tracker.register_cancellation_token(call_id, token)
            self._cancellation_registry.register(call_id, token)
        except ToolBusyError:
            logger.warning(
                "Tool call rejected: max pending reached. session_id=%s, call_id=%s, tool_name=%s",
                self._session_id,
                call_id,
                tool_name,
            )
            return call_id, ToolExecutionResult.error_result(
                error=f"Max pending calls ({self._tracker.max_pending}) reached",
                error_code="TOO_MANY_CONCURRENT",
            )

        logger.info(
            "Tool call started",
            extra={
                "session_id": self._session_id,
                "call_id": call_id,
                "tool_name": tool_name,
                "trace_id": trace_id,
            }
        )

        try:
            await self._semaphore.acquire()

            try:
                if token.is_cancelled:
                    await self._tracker.transition_record(call_id, ToolCallState.CANCELLED)
                    return call_id, ToolExecutionResult.error_result(
                        error="Cancelled before execution",
                        error_code="CANCELLED",
                    )

                record.started_at = datetime.now(timezone.utc)
                await self._tracker.transition_record(call_id, ToolCallState.RUNNING)

                timeout = self._timeout
                try:
                    result = await asyncio.wait_for(
                        self._executor.execute(tool_name, arguments),
                        timeout=timeout,
                    )
                except asyncio.TimeoutError:
                    if token.is_cancelled:
                        await self._tracker.transition_record(call_id, ToolCallState.CANCELLED)
                        return call_id, ToolExecutionResult.error_result(
                            error="Cancelled during execution",
                            error_code="CANCELLED",
                        )
                    raise

                if token.is_cancelled:
                    await self._tracker.transition_record(call_id, ToolCallState.CANCELLED)
                    return call_id, ToolExecutionResult.error_result(
                        error="Cancelled during execution",
                        error_code="CANCELLED",
                    )

                content = result.get("content", []) if result else []
                await self._tracker.transition_record(
                    call_id,
                    ToolCallState.COMPLETED,
                    result_content=content,
                )

                logger.info(
                    "Tool call completed",
                    extra={
                        "session_id": self._session_id,
                        "call_id": call_id,
                        "tool_name": tool_name,
                        "trace_id": trace_id,
                    }
                )

                return call_id, ToolExecutionResult.success_result(content=content)

            except asyncio.TimeoutError:
                if token.is_cancelled:
                    await self._tracker.transition_record(call_id, ToolCallState.CANCELLED)
                    return call_id, ToolExecutionResult.error_result(
                        error="Cancelled during timeout",
                        error_code="CANCELLED",
                    )
                await self._tracker.transition_record(call_id, ToolCallState.TIMED_OUT)
                logger.warning(
                    "Tool call timed out",
                    extra={
                        "session_id": self._session_id,
                        "call_id": call_id,
                        "tool_name": tool_name,
                        "timeout": timeout,
                    }
                )
                return call_id, ToolExecutionResult.error_result(
                    error=f"Tool execution timed out after {timeout}s",
                    error_code="TIMEOUT",
                )

            except Exception as e:
                if token.is_cancelled:
                    await self._tracker.transition_record(call_id, ToolCallState.CANCELLED)
                    return call_id, ToolExecutionResult.error_result(
                        error="Cancelled during execution",
                        error_code="CANCELLED",
                    )
                await self._tracker.transition_record(
                    call_id,
                    ToolCallState.FAILED,
                    error_message=str(e),
                )
                code, msg = normalize_tool_error(e)
                logger.warning(
                    "Tool call failed",
                    extra={
                        "session_id": self._session_id,
                        "call_id": call_id,
                        "tool_name": tool_name,
                        "error": msg,
                        "code": code,
                    }
                )
                return call_id, ToolExecutionResult.error_result(
                    error=msg,
                    error_code=code,
                )

            finally:
                self._semaphore.release()
                await self._tracker.unregister_cancellation_token(call_id)
                self._cancellation_registry.unregister(call_id)

        except ToolSessionClosedError:
            await self._tracker.transition_record(call_id, ToolCallState.CANCELLED)
            raise

    async def call_tool_with_context(
        self,
        context: ExecutionContext,
        tool_name: str,
        arguments: dict[str, Any],
        call_id: str | None = None,
    ) -> tuple[str, ToolExecutionResult]:
        """Execute a tool call with execution context.

        This method provides the same functionality as call_tool but accepts
        an ExecutionContext instead of individual parameters.

        Args:
            context: Execution context with session, trace, and other metadata.
            tool_name: Name of the tool to execute.
            arguments: Tool input arguments.
            call_id: Optional call ID (generated if not provided).

        Returns:
            Tuple of (call_id, ToolExecutionResult).
        """
        return await self.call_tool(
            tool_name=tool_name,
            arguments=arguments,
            call_id=call_id,
            trace_id=context.trace_id,
            parent_call_id=context.parent_call_id,
        )

    async def close(self, cancel_pending: bool = True) -> None:
        """Close the registry and clean up resources.

        Args:
            cancel_pending: If True, mark pending calls as CANCELLED.
        """
        if self._closed:
            return

        self._closed = True

        if cancel_pending:
            pending = await self._tracker.get_pending_ids()
            for call_id in pending:
                await self._tracker.transition_record(call_id, ToolCallState.CANCELLED)
            logger.info(
                "Tool registry closed with pending cancellation",
                session_id=self._session_id,
                cancelled_count=len(pending),
            )

        await self._tracker.close(mark_orphaned=True)

    async def get_pending_count(self) -> int:
        """Get the number of pending tool calls.

        Returns:
            Count of pending calls.
        """
        return await self._tracker.get_pending_count()
