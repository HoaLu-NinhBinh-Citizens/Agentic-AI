"""Tool execution context and result models.

Provides structured context for tool execution and normalized result abstraction.
Phase 2C extends with unified ExecutionContext (immutable) and ExecutionRequest (immutable with copy-on-write).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExecutionContext:
    """Immutable context passed to all tool executions.

    This dataclass provides future-proofing for tool execution by allowing
    additional fields to be added without changing method signatures.

    Phase 2C: Added client_id for ownership verification.

    Attributes:
        session_id: ID of the session executing this tool.
        trace_id: Unique trace identifier for observability.
        client_id: WebSocket client ID that initiated the call.
        workspace: Optional workspace path for the session.
        parent_call_id: Optional parent call ID for nested executions.
        timeout_seconds: Execution timeout override (None = use default).
    """

    session_id: str
    trace_id: str
    client_id: str = ""
    workspace: str | None = None
    parent_call_id: str | None = None
    timeout_seconds: float | None = None

    def with_trace_id(self, trace_id: str) -> ExecutionContext:
        """Create a new context with a different trace_id.

        Args:
            trace_id: New trace ID.

        Returns:
            New ExecutionContext with updated trace_id.
        """
        return ExecutionContext(
            session_id=self.session_id,
            trace_id=trace_id,
            client_id=self.client_id,
            workspace=self.workspace,
            parent_call_id=self.parent_call_id,
            timeout_seconds=self.timeout_seconds,
        )

    def with_parent(self, parent_call_id: str) -> ExecutionContext:
        """Create a new context marking this as a nested call.

        Args:
            parent_call_id: Parent call ID.

        Returns:
            New ExecutionContext with parent_call_id set.
        """
        return ExecutionContext(
            session_id=self.session_id,
            trace_id=self.trace_id,
            client_id=self.client_id,
            workspace=self.workspace,
            parent_call_id=parent_call_id,
            timeout_seconds=self.timeout_seconds,
        )


@dataclass
class ToolExecutionResult:
    """Normalized result from tool execution.

    This dataclass abstracts away MCP schema and provides a unified
    interface for all tool execution results.

    Attributes:
        success: Whether the tool executed successfully.
        content: List of result content items.
        error: Error message if execution failed.
        error_code: Machine-readable error code.
        metadata: Additional execution metadata.
    """

    success: bool
    content: list[Any] = field(default_factory=list)
    error: str | None = None
    error_code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolExecutionResult:
        """Create a result from a dictionary.

        Args:
            data: Dictionary with result data.

        Returns:
            ToolExecutionResult instance.
        """
        return cls(
            success=data.get("success", False),
            content=data.get("content", []),
            error=data.get("error"),
            error_code=data.get("code"),
            metadata={k: v for k, v in data.items()
                     if k not in ("success", "content", "error", "code")},
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary.

        Returns:
            Dictionary representation.
        """
        result = {
            "success": self.success,
            "content": self.content,
        }
        if self.error:
            result["error"] = self.error
        if self.error_code:
            result["code"] = self.error_code
        result.update(self.metadata)
        return result

    @classmethod
    def success_result(
        cls,
        content: list[Any],
        metadata: dict[str, Any] | None = None,
    ) -> ToolExecutionResult:
        """Create a successful result.

        Args:
            content: Result content.
            metadata: Optional metadata.

        Returns:
            Successful ToolExecutionResult.
        """
        return cls(
            success=True,
            content=content,
            metadata=metadata or {},
        )

    @classmethod
    def error_result(
        cls,
        error: str,
        error_code: str,
        metadata: dict[str, Any] | None = None,
    ) -> ToolExecutionResult:
        """Create an error result.

        Args:
            error: Error message.
            error_code: Error code.
            metadata: Optional metadata.

        Returns:
            Error ToolExecutionResult.
        """
        return cls(
            success=False,
            error=error,
            error_code=error_code,
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class ExecutionRequest:
    """Immutable request object for tool execution pipeline.

    Phase 2C: This is the unified request object that flows through
    the middleware pipeline. It is IMMUTABLE to prevent side effects.

    When changes are needed (e.g., retry_count increment), middleware
    creates a new request instance using the with_* methods.

    Attributes:
        call_id: Unique identifier for this tool call.
        tool_name: Name of the tool to execute.
        arguments: Tool input arguments.
        context: Execution context with session, trace, and client info.
        retry_count: Current retry attempt number.
        cancellation_token: Token for cancelling this execution.
        idempotency_key: Optional key for idempotent retry support.
    """

    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    context: ExecutionContext
    retry_count: int = 0
    cancellation_token: Any = None
    idempotency_key: str | None = None

    def with_retry_count(self, retry_count: int) -> ExecutionRequest:
        """Create a new request with updated retry_count.

        Args:
            retry_count: New retry count value.

        Returns:
            New ExecutionRequest with updated retry_count.
        """
        return ExecutionRequest(
            call_id=self.call_id,
            tool_name=self.tool_name,
            arguments=self.arguments,
            context=self.context,
            retry_count=retry_count,
            cancellation_token=self.cancellation_token,
            idempotency_key=self.idempotency_key,
        )

    def with_cancellation_token(self, token: Any) -> ExecutionRequest:
        """Create a new request with updated cancellation token.

        Args:
            token: New cancellation token.

        Returns:
            New ExecutionRequest with updated token.
        """
        return ExecutionRequest(
            call_id=self.call_id,
            tool_name=self.tool_name,
            arguments=self.arguments,
            context=self.context,
            retry_count=self.retry_count,
            cancellation_token=token,
            idempotency_key=self.idempotency_key,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert request to dictionary for logging/serialization.

        Returns:
            Dictionary representation.
        """
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "session_id": self.context.session_id,
            "trace_id": self.context.trace_id,
            "client_id": self.context.client_id,
            "retry_count": self.retry_count,
            "idempotency_key": self.idempotency_key,
        }
