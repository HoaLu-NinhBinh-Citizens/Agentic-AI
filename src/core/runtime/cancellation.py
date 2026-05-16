"""
Runtime Cancellation - Hierarchical cancellation propagation

Prevents zombie tasks by propagating cancellation through task hierarchies.

When workflow cancelled:
1. Cancel all child tasks
2. Cancel tool execution
3. Abort pending retries
4. Close event streams
5. Release resources

Usage:
    scope = CancellationScope()
    
    async def parent_work():
        child_scope = scope.fork()
        
        # Pass child_scope to child tasks
        await child_task(child_scope)
        
        if should_cancel:
            scope.cancel("User requested")
    
    try:
        await parent_work()
    except CancelledError as e:
        print(f"Cancelled: {e.reason}")
"""

import asyncio
import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)


class CancelledError(Exception):
    """
    Raised when a scope is cancelled.

    Attributes:
        reason: Why cancellation was requested
        scope_id: ID of cancelled scope
    """

    def __init__(self, reason: str = "cancelled", scope_id: str = ""):
        self.reason = reason
        self.scope_id = scope_id
        super().__init__(f"Cancelled: {reason}")


@dataclass
class CleanupHandler:
    """Handler to run during cleanup."""

    name: str
    callback: Callable
    order: int = 0  # Lower = run first


@dataclass
class CancellationScope:
    """
    Hierarchical cancellation scope.

    Manages cancellation for a task and its children.

    Usage:
        scope = CancellationScope()

        async def work():
            # Check if cancelled
            scope.check()

            # Fork for child work
            child_scope = scope.fork()
            await child_work(child_scope)

        if need_to_cancel:
            scope.cancel("Reason")

        try:
            await work()
        except CancelledError as e:
            print(f"Cancelled: {e.reason}")
    """

    scope_id: str = field(default_factory=lambda: str(id(object())))
    parent: "CancellationScope | None" = field(default=None, repr=False)
    _children: list["CancellationScope"] = field(default_factory=list, repr=False)
    _cancelled: bool = False
    _cancel_reason: str | None = None
    _cleanup_handlers: list[CleanupHandler] = field(default_factory=list)

    def cancel(self, reason: str = "cancelled") -> None:
        """
        Cancel this scope and all children.

        Args:
            reason: Why cancellation was requested
        """
        if self._cancelled:
            return

        self._cancelled = True
        self._cancel_reason = reason

        logger.debug(f"CancellationScope {self.scope_id}: cancelled ({reason})")

        # Cancel all children
        for child in self._children:
            child.cancel(reason)

        # Run cleanup handlers
        self._run_cleanup()

    def cancelled(self) -> bool:
        """
        Check if this scope is cancelled.

        Returns True if this scope or any parent is cancelled.
        """
        if self._cancelled:
            return True
        if self.parent:
            return self.parent.cancelled()
        return False

    def check(self) -> None:
        """
        Raise CancelledError if scope is cancelled.

        Use this inside long-running operations to check for cancellation.

        Raises:
            CancelledError: If scope is cancelled
        """
        if self.cancelled():
            raise CancelledError(self._cancel_reason or "cancelled", self.scope_id)

    def fork(self) -> "CancellationScope":
        """
        Create a child scope.

        Child inherits parent's cancellation. When parent is cancelled,
        child is also cancelled.

        Returns:
            New CancellationScope
        """
        child = CancellationScope(parent=self)
        self._children.append(child)
        return child

    def add_cleanup(self, name: str, callback: Callable, order: int = 0) -> None:
        """
        Add a cleanup handler.

        Handlers are called in order when scope is cancelled or closed.

        Args:
            name: Handler name for logging
            callback: Async function to call
            order: Execution order (lower = first)
        """
        handler = CleanupHandler(name=name, callback=callback, order=order)
        self._cleanup_handlers.append(handler)
        self._cleanup_handlers.sort(key=lambda h: h.order)

    def _run_cleanup(self) -> None:
        """Run all cleanup handlers."""
        for handler in self._cleanup_handlers:
            try:
                logger.debug(f"Running cleanup: {handler.name}")
                if asyncio.iscoroutinefunction(handler.callback):
                    # Schedule but don't await - we don't want cleanup to fail
                    asyncio.create_task(self._run_handler(handler))
                else:
                    handler.callback()
            except Exception as e:
                logger.error(f"Cleanup handler {handler.name} failed: {e}")

    async def _run_handler(self, handler: CleanupHandler) -> None:
        """Run a single cleanup handler."""
        try:
            await handler.callback()
        except Exception as e:
            logger.error(f"Cleanup handler {handler.name} failed: {e}")

    def remove_child(self, child: "CancellationScope") -> None:
        """Remove a child scope (e.g., when child completes)."""
        if child in self._children:
            self._children.remove(child)

    def is_root(self) -> bool:
        """Check if this is a root scope (no parent)."""
        return self.parent is None


@dataclass
class CancellationToken:
    """
    Token for passing cancellation to async functions.

    Provides a simpler interface than CancellationScope for most use cases.

    Usage:
        token = CancellationToken()

        async def work(token):
            while not token.is_cancelled:
                await do_step()
                token.check()

        # Cancel after timeout
        asyncio.create_task(cancel_after(token, 30))

        try:
            await work(token)
        except CancelledError:
            print("Work was cancelled")
    """

    _scope: CancellationScope = field(default_factory=CancellationScope)

    def cancel(self, reason: str = "cancelled") -> None:
        """Cancel the token."""
        self._scope.cancel(reason)

    def is_cancelled(self) -> bool:
        """Check if cancelled."""
        return self._scope.cancelled()

    def check(self) -> None:
        """Raise if cancelled."""
        self._scope.check()

    def fork(self) -> "CancellationToken":
        """Fork token for child task."""
        return CancellationToken(_scope=self._scope.fork())

    def add_cleanup(self, name: str, callback: Callable, order: int = 0) -> None:
        """Add cleanup handler."""
        self._scope.add_cleanup(name, callback, order)


# Context variable for current cancellation
_cancellation_context: ContextVar[CancellationScope | None] = ContextVar(
    "cancellation_context", default=None
)


def get_current_cancellation() -> CancellationScope | None:
    """Get current cancellation scope from context."""
    return _cancellation_context.get()


def set_cancellation(scope: CancellationScope | None) -> None:
    """Set current cancellation scope in context."""
    _cancellation_context.set(scope)


@property
def cancellation_token() -> CancellationToken:
    """
    Get cancellation token for current context.

    Creates a new token if none in context.

    Usage:
        token = cancellation_token()

        async def long_running():
            for step in steps:
                token.check()
                await process(step)
    """
    scope = get_current_cancellation()
    if scope is None:
        scope = CancellationScope()
        set_cancellation(scope)
    return CancellationToken(_scope=scope)


# Helper for scoped cancellation
class CancellationScopeManager:
    """
    Context manager for cancellation scopes.

    Usage:
        async with CancellationScopeManager() as scope:
            scope.add_cleanup("release", cleanup_resource)

            # Work with scope
            child = scope.fork()
            await child_work(child)

            if error:
                scope.cancel("Error occurred")
    """

    def __init__(self, parent: CancellationScope | None = None):
        self._scope = CancellationScope(parent=parent)
        self._token = set(_cancellation_context.set(self._scope))

    async def __aenter__(self) -> CancellationScope:
        return self._scope

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        # Reset context
        _cancellation_context.reset(self._token)

        # If cancelled, run cleanup
        if self._scope.cancelled():
            self._scope._run_cleanup()


async def cancel_after(token: CancellationToken | CancellationScope, seconds: float) -> None:
    """
    Cancel a token after a timeout.

    Args:
        token: Token or scope to cancel
        seconds: Seconds to wait before cancelling

    Usage:
        token = CancellationToken()
        asyncio.create_task(cancel_after(token, 60))

        await work(token)
    """
    await asyncio.sleep(seconds)

    if hasattr(token, "cancel"):
        token.cancel(f"Timeout after {seconds}s")
    else:
        token.cancel(f"Timeout after {seconds}s")


async def wait_with_cancellation(
    awaitable,
    scope: CancellationScope,
) -> any:
    """
    Wait for an awaitable while checking for cancellation.

    Args:
        awaitable: Thing to await
        scope: Cancellation scope to check

    Returns:
        Result of awaitable

    Raises:
        CancelledError: If scope cancelled while waiting
    """
    while True:
        scope.check()

        try:
            result = await asyncio.wait_for(awaitable, timeout=0.1)
            return result
        except asyncio.TimeoutError:
            continue
