"""
Tool Executor

Executes tools with validation, timeout, error handling, and sandbox protection.
"""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from src.core.tools.schema import (
    Tool,
    ToolResult,
    ToolExecutionRequest,
    ToolPermission,
    ParameterType,
)
from src.core.tools.registry import ToolRegistry
from src.core.tools.context import ToolContext, ToolPermissionContext, ToolExecutionMode
from src.core.tools.cache import ToolResultCache

if TYPE_CHECKING:
    from src.core.tools.sandbox import SandboxManager, SandboxConfig, SandboxResult
    from src.core.tools.audit import AuditLogger

logger = logging.getLogger(__name__)


class ToolExecutionError(Exception):
    """Base exception for tool execution errors."""

    pass


class ToolNotFoundError(ToolExecutionError):
    """Tool not found in registry."""

    pass


class ToolValidationError(ToolExecutionError):
    """Tool parameter validation failed."""

    pass


class ToolPermissionError(ToolExecutionError):
    """Permission denied for tool execution."""

    pass


class ToolTimeoutError(ToolExecutionError):
    """Tool execution timed out."""

    pass


class SandboxViolationError(ToolExecutionError):
    """Sandbox policy violation."""

    pass


class ToolExecutor:
    """
    Tool execution engine with sandbox integration.

    Features:
    - Parameter validation
    - Permission checking
    - Sandbox integration (P2)
    - Audit logging (P2)
    - Timeout handling
    - Retry logic
    - Result caching
    - Async/sync execution
    - Event emission

    Usage:
        executor = ToolExecutor(registry)

        # Execute a tool
        result = await executor.execute("read_file", {"path": "/tmp/test.txt"})

        # Execute with sandbox
        context = create_sandbox_context(Path("/workspace"))
        result = await executor.execute("read_file", {"path": "/tmp/test.txt"}, context)
    """

    def __init__(
        self,
        registry: ToolRegistry,
        cache: Optional[ToolResultCache] = None,
        max_retries: int = 3,
        default_timeout: int = 30,
        enable_events: bool = True,
        sandbox_config: Optional["SandboxConfig"] = None,
        audit_enabled: bool = True,
    ):
        """
        Initialize ToolExecutor.

        Args:
            registry: Tool registry
            cache: Optional result cache
            max_retries: Maximum retry attempts
            default_timeout: Default timeout in seconds
            enable_events: Whether to emit events
            sandbox_config: Optional sandbox configuration
            audit_enabled: Whether to enable audit logging
        """
        self.registry = registry
        self.cache = cache
        self.max_retries = max_retries
        self.default_timeout = default_timeout
        self.enable_events = enable_events
        self.sandbox_config = sandbox_config
        self.sandbox_manager: Optional["SandboxManager"] = None
        self.audit_enabled = audit_enabled
        self.audit_logger: Optional["AuditLogger"] = None
        self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="tool_")

        # Initialize sandbox if config provided
        if sandbox_config:
            self._init_sandbox(sandbox_config)

        # Event handlers
        self._on_execution_start: List[Callable] = []
        self._on_execution_complete: List[Callable] = []
        self._on_execution_error: List[Callable] = []

    def _init_sandbox(self, config: "SandboxConfig") -> None:
        """Initialize sandbox manager."""
        from src.core.tools.sandbox import SandboxManager
        from src.core.tools.audit import AuditLogger

        self.sandbox_manager = SandboxManager(config)
        if self.audit_enabled:
            self.audit_logger = AuditLogger()

    def set_sandbox_manager(self, manager: "SandboxManager") -> None:
        """
        Set the sandbox manager.

        Args:
            manager: Sandbox manager instance
        """
        self.sandbox_manager = manager

    def set_audit_logger(self, logger: "AuditLogger") -> None:
        """
        Set the audit logger.

        Args:
            logger: Audit logger instance
        """
        self.audit_logger = logger
        self.audit_enabled = logger is not None

    def on_execution_start(self, handler: Callable) -> None:
        """Register execution start handler."""
        self._on_execution_start.append(handler)

    def on_execution_complete(self, handler: Callable) -> None:
        """Register execution complete handler."""
        self._on_execution_complete.append(handler)

    def on_execution_error(self, handler: Callable) -> None:
        """Register execution error handler."""
        self._on_execution_error.append(handler)

    async def execute(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Optional[ToolContext] = None,
        use_cache: bool = True,
        timeout: Optional[int] = None,
    ) -> ToolResult:
        """
        Execute a tool with sandbox protection and audit logging.

        Args:
            tool_name: Name of tool to execute
            parameters: Tool parameters
            context: Execution context
            use_cache: Whether to use cache
            timeout: Execution timeout override

        Returns:
            ToolResult

        Raises:
            ToolNotFoundError: Tool not found
            ToolValidationError: Parameter validation failed
            ToolPermissionError: Permission denied
            ToolTimeoutError: Execution timed out
            SandboxViolationError: Sandbox policy violation
        """
        context = context or ToolContext()
        timeout = timeout or self.default_timeout

        # Get tool from registry
        tool = self.registry.get(tool_name)
        if not tool:
            raise ToolNotFoundError(f"Tool '{tool_name}' not found")

        # Create request for caching
        request = ToolExecutionRequest(
            tool_name=tool_name,
            parameters=parameters,
            use_cache=use_cache,
        )

        # Check cache
        if use_cache and tool.cacheable and self.cache:
            cached = self.cache.get(request.get_cache_key())
            if cached:
                logger.debug(f"Cache hit for {tool_name}")
                cached.cached = True
                return cached

        # Emit start events
        if self.enable_events:
            for handler in self._on_execution_start:
                try:
                    handler(tool_name, parameters)
                except Exception as e:
                    logger.warning(f"Start handler error: {e}")

        start_time = time.time()

        # Log audit event
        if self.audit_logger:
            self.audit_logger.log_tool_execution(
                tool_name=tool_name,
                params=parameters,
                context=context,
                result=None,
                correlation_id=context.correlation_id,
            )

        try:
            # Validate permissions
            self._check_permissions(tool, context)

            # Validate parameters
            is_valid, error = tool.validate_params(parameters)
            if not is_valid:
                raise ToolValidationError(error)

            # Sandbox path validation for file operations
            if self.sandbox_manager and context.sandbox_enabled:
                self._check_sandbox_policy(tool, parameters, context)

            # Execute with sandbox if available
            if self.sandbox_manager and context.sandbox_enabled:
                result = await self._execute_with_sandbox(
                    tool, parameters, context, timeout
                )
            else:
                # Execute with retry
                result = await self._execute_with_retry(
                    tool, parameters, context, timeout
                )

        except SandboxViolationError:
            # Log violation
            if self.audit_logger:
                self.audit_logger.log_sandbox_violation(
                    violation_type="path_violation",
                    details=str(SandboxViolationError),
                    tool_name=tool_name,
                    context=context,
                )
            raise

        except Exception as e:
            # Log error
            if self.audit_logger:
                self.audit_logger.log(
                    event_type=type(e).__name__,
                    action=f"error:{tool_name}",
                    severity="error",
                    agent_id=context.agent_id,
                    session_id=context.session_id,
                    tool_name=tool_name,
                    result=str(e),
                )

            result = ToolResult(
                tool_name=tool_name,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                execution_time_ms=(time.time() - start_time) * 1000,
            )

            if self.enable_events:
                for handler in self._on_execution_error:
                    try:
                        handler(tool_name, e)
                    except Exception as handler_error:
                        logger.warning(f"Error handler error: {handler_error}")

        else:
            result.execution_time_ms = (time.time() - start_time) * 1000

            # Log success
            if self.audit_logger:
                self.audit_logger.log_tool_execution(
                    tool_name=tool_name,
                    params=parameters,
                    context=context,
                    result=result,
                    correlation_id=context.correlation_id,
                )

        finally:
            if self.enable_events:
                for handler in self._on_execution_complete:
                    try:
                        handler(tool_name, result)
                    except Exception as e:
                        logger.warning(f"Complete handler error: {e}")

        # Cache result
        if result.success and use_cache and tool.cacheable and self.cache:
            self.cache.set(request.get_cache_key(), result)

        return result

    def _check_sandbox_policy(
        self,
        tool: Tool,
        parameters: Dict[str, Any],
        context: ToolContext,
    ) -> None:
        """
        Check sandbox policy for tool execution.

        Args:
            tool: Tool being executed
            parameters: Tool parameters
            context: Execution context

        Raises:
            SandboxViolationError: If policy is violated
        """
        from pathlib import Path

        # Check path parameters
        for param in tool.parameters:
            if param.type in (ParameterType.FILE_PATH, ParameterType.DIRECTORY_PATH):
                path_val = parameters.get(param.name)
                if path_val:
                    path = Path(path_val)
                    if not self.sandbox_manager.is_path_allowed(path)[0]:
                        violation = f"Path '{path_val}' is not allowed in sandbox mode for tool '{tool.name}'"
                        logger.warning(violation)
                        raise SandboxViolationError(violation)

    async def _execute_with_sandbox(
        self,
        tool: Tool,
        parameters: Dict[str, Any],
        context: ToolContext,
        timeout: int,
    ) -> ToolResult:
        """
        Execute tool with sandbox protection.

        Args:
            tool: Tool to execute
            parameters: Tool parameters
            context: Execution context
            timeout: Timeout in seconds

        Returns:
            ToolResult with sandbox metadata
        """
        if not tool.handler:
            raise ToolExecutionError(f"Tool '{tool.name}' has no handler")

        # Execute via sandbox manager
        sandbox_result = await self.sandbox_manager.execute_tool(
            handler=tool.handler,
            params=parameters,
            tool_context=context,
            tool_name=tool.name,
            timeout=timeout,
        )

        # Convert SandboxResult to ToolResult
        result = ToolResult(
            tool_name=tool.name,
            success=sandbox_result.success,
            output=sandbox_result.output,
            error=sandbox_result.error,
            error_type=sandbox_result.error_type,
            execution_time_ms=sandbox_result.execution_time_ms,
            metadata={
                "sandbox_id": sandbox_result.sandbox_id,
                "sandbox_violations": sandbox_result.sandbox_violations,
                "resources_used": sandbox_result.resources_used,
                "audit_id": sandbox_result.audit_id,
            },
        )

        return result

    async def _execute_with_retry(
        self,
        tool: Tool,
        parameters: Dict[str, Any],
        context: ToolContext,
        timeout: int,
    ) -> ToolResult:
        """Execute tool with retry logic."""
        last_error = None

        for attempt in range(self.max_retries if tool.retryable else 1):
            try:
                return await self._execute_single(tool, parameters, context, timeout)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    # Exponential backoff
                    wait_time = min(2**attempt, 10)
                    logger.debug(f"Retry {attempt + 1}/{self.max_retries} for {tool.name} after {wait_time}s")
                    await asyncio.sleep(wait_time)

        raise last_error

    async def _execute_single(
        self,
        tool: Tool,
        parameters: Dict[str, Any],
        context: ToolContext,
        timeout: int,
    ) -> ToolResult:
        """Execute tool a single time."""
        if not tool.handler:
            raise ToolExecutionError(f"Tool '{tool.name}' has no handler")

        # Determine timeout
        exec_timeout = min(tool.timeout, timeout)

        # Run in executor for sync handlers
        loop = asyncio.get_event_loop()
        try:
            if asyncio.iscoroutinefunction(tool.handler):
                result = await asyncio.wait_for(
                    tool.handler(parameters, context),
                    timeout=exec_timeout,
                )
            else:
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        self._executor,
                        lambda: tool.handler(parameters, context),
                    ),
                    timeout=exec_timeout,
                )

        except asyncio.TimeoutError:
            raise ToolTimeoutError(
                f"Tool '{tool.name}' timed out after {exec_timeout}s"
            )

        return ToolResult(
            tool_name=tool.name,
            success=True,
            output=result,
            execution_time_ms=0,  # Will be set by caller
        )

    def _check_permissions(self, tool: Tool, context: ToolContext) -> None:
        """
        Check if context has required permissions.

        Args:
            tool: Tool to check
            context: Execution context

        Raises:
            ToolPermissionError: If permission is denied
        """
        # In dry_run mode, only allow read operations
        if context.mode == ToolExecutionMode.DRY_RUN:
            for perm in tool.permissions:
                if perm not in (ToolPermission.READ,):
                    raise ToolPermissionError(
                        f"Tool '{tool.name}' requires {perm.value} permission which is not allowed in dry_run mode"
                    )

        # In sandbox mode, check all permissions
        if context.mode == ToolExecutionMode.SANDBOX:
            for perm in tool.permissions:
                if perm == ToolPermission.FILESYSTEM:
                    # FILESYSTEM permission needs stricter checking
                    if context.sandbox_enabled and not context.allowed_paths:
                        # If no allowed paths specified, require explicit permission
                        logger.warning(
                            f"Tool '{tool.name}' requests FILESYSTEM permission in sandbox mode"
                        )

        # Check path permissions for file/directory parameters
        if context.mode == ToolExecutionMode.SANDBOX and self.sandbox_manager:
            from pathlib import Path

            for param in tool.parameters:
                if param.type in (ParameterType.FILE_PATH, ParameterType.DIRECTORY_PATH):
                    path_val = context.variables.get(param.name)
                    if path_val:
                        path = Path(path_val)
                        is_allowed, error = self.sandbox_manager.is_path_allowed(path)
                        if not is_allowed:
                            raise ToolPermissionError(error)

        # Log permission check
        if self.audit_logger:
            for perm in tool.permissions:
                self.audit_logger.log_permission_check(
                    tool_name=tool.name,
                    permission=perm.value,
                    allowed=True,
                    context=context,
                )

    def execute_sync(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Optional[ToolContext] = None,
        use_cache: bool = True,
        timeout: Optional[int] = None,
    ) -> ToolResult:
        """
        Synchronous version of execute.

        Args:
            tool_name: Tool name
            parameters: Parameters
            context: Context
            use_cache: Use cache
            timeout: Timeout

        Returns:
            ToolResult
        """
        return asyncio.run(
            self.execute(tool_name, parameters, context, use_cache, timeout)
        )

    def execute_batch(
        self,
        requests: List[ToolExecutionRequest],
        context: Optional[ToolContext] = None,
    ) -> List[ToolResult]:
        """
        Execute multiple tools in parallel.

        Args:
            requests: List of execution requests
            context: Shared context

        Returns:
            List of results
        """
        return asyncio.run(
            asyncio.gather(
                *[
                    self.execute(
                        req.tool_name,
                        req.parameters,
                        context,
                        req.use_cache,
                    )
                    for req in requests
                ]
            )
        )


# Global executor
_executor: Optional[ToolExecutor] = None


def get_tool_executor() -> ToolExecutor:
    """Get the global tool executor instance."""
    global _executor
    if _executor is None:
        from src.core.tools.registry import get_tool_registry

        _executor = ToolExecutor(get_tool_registry())
    return _executor
