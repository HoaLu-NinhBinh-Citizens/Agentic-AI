"""Cancellation and process management for Phase 2C.

Provides cancellation tokens for aborting in-flight tool executions
and process handle abstraction for subprocess termination.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class CancellationToken:
    """Token for cooperative cancellation of async operations.

    Allows cancellation to be requested on a token, and async operations
    can check the cancellation state or wait for cancellation.

    Usage:
        token = CancellationToken()
        # Pass token to long-running operation
        # Request cancellation when needed
        token.cancel()
        # Operation checks token.is_cancelled or awaits token.wait()
    """

    def __init__(self) -> None:
        """Initialize the cancellation token."""
        self._event = asyncio.Event()
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation.

        Sets the cancelled flag and signals the event.
        Safe to call multiple times.
        """
        self._cancelled = True
        self._event.set()
        logger.debug("Cancellation requested")

    @property
    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested.

        Returns:
            True if cancel() has been called, False otherwise.
        """
        return self._cancelled

    async def wait(self) -> None:
        """Wait for cancellation to be requested.

        This method blocks until cancel() is called.
        Raises asyncio.CancelledError if already cancelled when called.
        """
        if self._cancelled:
            raise asyncio.CancelledError("Already cancelled")
        await self._event.wait()

    def reset(self) -> None:
        """Reset the token to initial state.

        Allows reuse of a cancelled token.
        """
        self._cancelled = False
        self._event.clear()
        logger.debug("Cancellation token reset")


class ProcessHandle(ABC):
    """Abstract handle for managing subprocess execution.

    Provides a unified interface for terminating processes,
    allowing future replacement with Docker containers, etc.
    """

    @abstractmethod
    async def terminate(self) -> None:
        """Request graceful termination of the process.

        Should give the process a chance to clean up resources.
        """
        ...

    @abstractmethod
    async def kill(self) -> None:
        """Forcefully kill the process.

        Should be called after terminate() if graceful shutdown fails.
        On Unix, this sends SIGKILL.
        On Windows, this uses TerminateProcess.
        """
        ...


class SubprocessHandle(ProcessHandle):
    """Process handle for asyncio subprocesses.

    Wraps an asyncio subprocess for cancellation and termination.
    """

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        """Initialize the subprocess handle.

        Args:
            process: The asyncio subprocess to manage.
        """
        self._process = process
        self._terminated = False

    async def terminate(self) -> None:
        """Send termination signal to the subprocess.

        On Unix, sends SIGTERM.
        On Windows, calls TerminateProcess.
        """
        if self._terminated:
            return

        try:
            self._process.terminate()
            self._terminated = True
            logger.debug("Sent terminate signal to subprocess")
        except ProcessLookupError:
            logger.debug("Process already terminated")

    async def kill(self) -> None:
        """Forcefully kill the subprocess.

        On Unix, sends SIGKILL.
        On Windows, uses TerminateProcess with exit code 1.
        """
        try:
            self._process.kill()
            logger.debug("Killed subprocess")
        except ProcessLookupError:
            logger.debug("Process already terminated")


class NoOpProcessHandle(ProcessHandle):
    """No-op process handle for non-subprocess operations.

    Used when execution doesn't involve a subprocess.
    """

    async def terminate(self) -> None:
        """No-op termination."""
        pass

    async def kill(self) -> None:
        """No-op kill."""
        pass


class CancellationRegistry:
    """Registry for managing cancellation tokens by call_id.

    Provides a centralized way to track and cancel tool calls.
    """

    def __init__(self) -> None:
        """Initialize the cancellation registry."""
        self._tokens: dict[str, CancellationToken] = {}
        self._handles: dict[str, ProcessHandle] = {}
        self._initiator_client_ids: dict[str, str] = {}

    def register(
        self,
        call_id: str,
        token: CancellationToken,
        initiator_client_id: str,
        handle: ProcessHandle | None = None,
    ) -> None:
        """Register a call for cancellation tracking.

        Args:
            call_id: Unique identifier for the tool call.
            token: Cancellation token for this call.
            initiator_client_id: Client ID that initiated this call.
            handle: Optional process handle for subprocess termination.
        """
        self._tokens[call_id] = token
        self._initiator_client_ids[call_id] = initiator_client_id
        if handle:
            self._handles[call_id] = handle
        logger.debug(
            "Registered call for cancellation",
            call_id=call_id,
            client_id=initiator_client_id,
        )

    def get_token(self, call_id: str) -> CancellationToken | None:
        """Get the cancellation token for a call.

        Args:
            call_id: The call identifier.

        Returns:
            The CancellationToken if registered, None otherwise.
        """
        return self._tokens.get(call_id)

    def get_initiator_client_id(self, call_id: str) -> str | None:
        """Get the initiator client ID for a call.

        Args:
            call_id: The call identifier.

        Returns:
            The initiator client ID if registered, None otherwise.
        """
        return self._initiator_client_ids.get(call_id)

    def get_handle(self, call_id: str) -> ProcessHandle | None:
        """Get the process handle for a call.

        Args:
            call_id: The call identifier.

        Returns:
            The ProcessHandle if registered, None otherwise.
        """
        return self._handles.get(call_id)

    async def cancel(self, call_id: str) -> bool:
        """Cancel a registered call.

        Args:
            call_id: The call to cancel.

        Returns:
            True if the call was found and cancelled, False otherwise.
        """
        token = self._tokens.get(call_id)
        if not token:
            logger.warning("Call not found for cancellation: %s", call_id)
            return False

        token.cancel()

        handle = self._handles.get(call_id)
        if handle:
            await self._terminate_handle(handle)

        logger.info("Call cancelled: %s", call_id)
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
            logger.warning("Error terminating process handle", error=str(e))

    def unregister(self, call_id: str) -> None:
        """Unregister a call from the cancellation registry.

        Args:
            call_id: The call to unregister.
        """
        self._tokens.pop(call_id, None)
        self._handles.pop(call_id, None)
        self._initiator_client_ids.pop(call_id, None)
        logger.debug("Unregistered call from cancellation: %s", call_id)

    def is_registered(self, call_id: str) -> bool:
        """Check if a call is registered.

        Args:
            call_id: The call identifier.

        Returns:
            True if registered, False otherwise.
        """
        return call_id in self._tokens

    def get_registered_ids(self) -> list[str]:
        """Get all registered call IDs.

        Returns:
            List of registered call IDs.
        """
        return list(self._tokens.keys())

    def clear(self) -> None:
        """Clear all registrations."""
        self._tokens.clear()
        self._handles.clear()
        self._initiator_client_ids.clear()
        logger.debug("Cleared cancellation registry")


class RetryPolicy:
    """Configuration for retry behavior.

    Attributes:
        max_attempts: Maximum number of retry attempts.
        base_delay_seconds: Base delay between retries.
        max_delay_seconds: Maximum delay cap.
        retryable_codes: Error codes that trigger retry.
        jitter_factor: Factor for jitter (0.0 to 1.0).
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay_seconds: float = 1.0,
        max_delay_seconds: float = 30.0,
        retryable_codes: list[str] | None = None,
        jitter_factor: float = 0.1,
    ) -> None:
        """Initialize retry policy.

        Args:
            max_attempts: Maximum number of attempts (including first).
            base_delay_seconds: Initial delay between retries.
            max_delay_seconds: Maximum delay cap.
            retryable_codes: Error codes that should trigger retry.
            jitter_factor: Random jitter factor (0.0 to 1.0).
        """
        self.max_attempts = max_attempts
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.retryable_codes = retryable_codes or ["MCP_ERROR", "TIMEOUT"]
        self.jitter_factor = jitter_factor

    def should_retry(self, error_code: str | None, attempt: int) -> bool:
        """Determine if a failure should trigger a retry.

        Args:
            error_code: The error code from the failed attempt.
            attempt: Current attempt number (1-indexed).

        Returns:
            True if should retry, False otherwise.
        """
        if attempt >= self.max_attempts:
            return False
        if not error_code:
            return False
        return error_code in self.retryable_codes

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt with exponential backoff and jitter.

        Args:
            attempt: Current attempt number (1-indexed).

        Returns:
            Delay in seconds.
        """
        import random

        delay = min(
            self.base_delay_seconds * (2 ** (attempt - 1)),
            self.max_delay_seconds,
        )
        if self.jitter_factor > 0:
            jitter = random.uniform(0, self.jitter_factor * delay)
            delay += jitter
        return delay

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetryPolicy:
        """Create policy from dictionary configuration.

        Args:
            data: Configuration dictionary.

        Returns:
            RetryPolicy instance.
        """
        return cls(
            max_attempts=data.get("max_attempts", 3),
            base_delay_seconds=data.get("base_delay_seconds", 1.0),
            max_delay_seconds=data.get("max_delay_seconds", 30.0),
            retryable_codes=data.get("retryable_codes", ["MCP_ERROR", "TIMEOUT"]),
            jitter_factor=data.get("jitter_factor", 0.1),
        )
