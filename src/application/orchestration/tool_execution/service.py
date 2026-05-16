"""Tool execution orchestration service for Phase 2B/2C.

Provides a clean API for executing tools and broadcasting results
to WebSocket clients. Separates orchestration from transport.

Phase 2C extends with:
- Middleware pipeline integration
- Cancellation by call_id
- Unified ExecutionRequest/ExecutionContext
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Awaitable, Callable, Protocol

from domain.models.execution import ExecutionRequest, ExecutionContext, ToolExecutionResult
from domain.models.tool_call import ToolCallState

logger = logging.getLogger(__name__)


class BroadcastCallback(Protocol):
    """Protocol for broadcasting events to WebSocket clients."""

    async def __call__(self, session_id: str, event: dict[str, Any]) -> None:
        """Broadcast an event to the session's clients.

        Args:
            session_id: Target session ID.
            event: Event payload to broadcast.
        """
        ...


class ToolExecutionService:
    """Orchestration layer for tool execution.

    Provides a single entry point for executing tools and handling
    the full lifecycle including event broadcasting and middleware.

    Phase 2C adds middleware pipeline support and cancellation.

    Attributes:
        session_manager: PersistentSessionManager for registry lookup.
        pipeline: Optional middleware pipeline for request processing.
    """

    def __init__(
        self,
        session_manager: Any,
        pipeline: Any = None,
    ) -> None:
        """Initialize the tool execution service.

        Args:
            session_manager: Session manager that provides tool registries.
            pipeline: Optional middleware pipeline for Phase 2C.
        """
        self._session_manager = session_manager
        self._pipeline = pipeline

    def set_pipeline(self, pipeline: Any) -> None:
        """Set the middleware pipeline.

        Args:
            pipeline: The middleware pipeline to use.
        """
        self._pipeline = pipeline

    async def execute_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        call_id: str | None = None,
        trace_id: str | None = None,
        client_id: str = "",
        broadcast_callback: BroadcastCallback | None = None,
    ) -> None:
        """Execute a tool and broadcast the result.

        Phase 2C: If a pipeline is configured, the request flows through it.

        This method handles the full execution lifecycle:
        1. Looks up the tool registry for the session
        2. Emits a tool_call_start event
        3. Executes the tool via the registry (or pipeline)
        4. Emits tool_call_result or tool_call_error based on outcome

        Args:
            session_id: Session executing the tool.
            tool_name: Name of the tool to execute.
            arguments: Tool input arguments.
            call_id: Optional call identifier.
            trace_id: Optional trace identifier for observability.
            client_id: WebSocket client ID that initiated the call.
            broadcast_callback: Optional callback to broadcast events.
        """
        registry = self._session_manager.get_tool_registry(session_id)
        if not registry:
            await self._emit_error(
                broadcast_callback,
                session_id,
                call_id,
                tool_name,
                "Session not active",
                "SESSION_ERROR",
            )
            return

        call_id = call_id or str(uuid.uuid4())
        trace_id = trace_id or str(uuid.uuid4())

        await self._emit_start(
            broadcast_callback,
            session_id,
            call_id,
            tool_name,
            arguments,
            trace_id,
        )

        context = ExecutionContext(
            session_id=session_id,
            trace_id=trace_id,
            client_id=client_id,
        )

        request = ExecutionRequest(
            call_id=call_id,
            tool_name=tool_name,
            arguments=arguments,
            context=context,
        )

        async def final_handler(req: ExecutionRequest) -> ToolExecutionResult:
            result_call_id, result = await registry.call_tool(
                tool_name,
                arguments,
                call_id,
                trace_id,
                client_id=client_id,
            )
            return result

        if self._pipeline:
            try:
                result = await self._pipeline.execute(request, final_handler)
                result_call_id = request.call_id
            except Exception as e:
                from shared.exceptions.tool_errors import normalize_tool_error
                code, msg = normalize_tool_error(e)
                await self._emit_error(
                    broadcast_callback,
                    session_id,
                    call_id,
                    tool_name,
                    msg,
                    code,
                )
                return
        else:
            result = await final_handler(request)
            result_call_id = request.call_id

        if result.success:
            await self._emit_result(
                broadcast_callback,
                session_id,
                result_call_id,
                tool_name,
                result.content,
            )
        else:
            await self._emit_error(
                broadcast_callback,
                session_id,
                result_call_id,
                tool_name,
                result.error or "Unknown error",
                result.error_code or "INTERNAL_ERROR",
            )

    async def cancel_tool(
        self,
        session_id: str,
        call_id: str,
        client_id: str,
    ) -> tuple[bool, str]:
        """Cancel a tool call by ID.

        Phase 2C: Only the initiating client can cancel their own calls.

        Args:
            session_id: Session executing the tool.
            call_id: The call ID to cancel.
            client_id: Client requesting the cancellation.

        Returns:
            Tuple of (success, message).
        """
        registry = self._session_manager.get_tool_registry(session_id)
        if not registry:
            return False, "Session not active"

        pending_record = await registry._tracker.get_pending_record(call_id)
        if pending_record:
            initiator_client_id = pending_record.client_id
            if initiator_client_id and initiator_client_id != client_id:
                logger.warning(
                    "Cancellation rejected: ownership mismatch",
                    call_id=call_id,
                    requester=client_id,
                    owner=initiator_client_id,
                )
                return False, "Only the initiating client can cancel this call"

        success = await registry.cancel_call(call_id)
        if success:
            return True, "Cancellation requested"
        return False, "Call not found or already completed"

    async def _emit_start(
        self,
        callback: BroadcastCallback | None,
        session_id: str,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        trace_id: str,
    ) -> None:
        """Emit a tool_call_start event.

        Args:
            callback: Broadcast callback.
            session_id: Target session.
            call_id: Call identifier.
            tool_name: Tool being executed.
            arguments: Tool arguments.
            trace_id: Trace identifier.
        """
        if callback:
            await callback(session_id, {
                "type": "tool_call_start",
                "data": {
                    "call_id": call_id,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "trace_id": trace_id,
                },
            })

    async def _emit_result(
        self,
        callback: BroadcastCallback | None,
        session_id: str,
        call_id: str,
        tool_name: str,
        content: list[Any],
    ) -> None:
        """Emit a tool_call_result event.

        Args:
            callback: Broadcast callback.
            session_id: Target session.
            call_id: Call identifier.
            tool_name: Tool that completed.
            content: Result content.
        """
        if callback:
            await callback(session_id, {
                "type": "tool_call_result",
                "data": {
                    "call_id": call_id,
                    "tool_name": tool_name,
                    "content": content,
                },
            })

    async def _emit_error(
        self,
        callback: BroadcastCallback | None,
        session_id: str,
        call_id: str | None,
        tool_name: str,
        message: str,
        code: str,
    ) -> None:
        """Emit a tool_call_error event.

        Args:
            callback: Broadcast callback.
            session_id: Target session.
            call_id: Call identifier.
            tool_name: Tool that failed.
            message: Error message.
            code: Error code.
        """
        if callback:
            await callback(session_id, {
                "type": "tool_call_error",
                "data": {
                    "call_id": call_id,
                    "tool_name": tool_name,
                    "error": message,
                    "code": code,
                },
            })
