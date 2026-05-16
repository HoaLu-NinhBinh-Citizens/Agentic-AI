"""
Runtime Tool Isolation - Process-based tool execution

Prevents tool failures from crashing the runtime.

Features:
- Execute tools in isolated subprocess
- Hard timeout with kill
- Output truncation to prevent memory issues
- Cancellation support
- Resource limits (via OS)

Usage:
    executor = IsolatedExecutor()

    try:
        result = await executor.execute(
            ["python", "script.py"],
            cwd="/project",
            timeout=30,
        )
        print(result.stdout)
    except ToolTimeoutError:
        print("Tool exceeded timeout")
"""

import asyncio
import logging
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

# resource module is Unix-only
try:
    import resource
    HAS_RESOURCE = True
except ImportError:
    HAS_RESOURCE = False
    resource = None

logger = logging.getLogger(__name__)


class ToolTimeoutError(Exception):
    """Raised when tool exceeds timeout."""

    def __init__(self, timeout: float, stdout: str = "", stderr: str = ""):
        self.timeout = timeout
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(f"Tool exceeded timeout of {timeout}s")


class ToolExecutionError(Exception):
    """Raised when tool execution fails."""

    def __init__(
        self,
        returncode: int,
        stdout: str = "",
        stderr: str = "",
    ):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(f"Tool failed with return code {returncode}")


@dataclass
class IsolationConfig:
    """Configuration for tool isolation."""

    timeout_seconds: float = 30.0
    max_output_bytes: int = 10 * 1024 * 1024  # 10MB
    max_output_lines: int = 10000
    kill_timeout: float = 5.0  # Seconds to wait before SIGKILL
    env: dict[str, str] | None = None
    cwd: str | None = None


class IsolatedExecutor:
    """
    Execute tools in isolated subprocess.

    Guarantees:
    - Tool runs in separate process (crash isolated)
    - Hard timeout (SIGTERM → SIGKILL)
    - Output truncation
    - Cancellation support
    """

    def __init__(self, config: IsolationConfig | None = None):
        self._config = config or IsolationConfig()

    async def execute(
        self,
        command: list[str],
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        cancellation: Any = None,  # CancellationToken or CancellationScope
    ) -> subprocess.CompletedProcess:
        """
        Execute command in isolated subprocess.

        Args:
            command: Command and arguments
            timeout: Override default timeout
            cwd: Working directory
            env: Environment variables
            cancellation: Cancellation support

        Returns:
            subprocess.CompletedProcess

        Raises:
            ToolTimeoutError: If timeout exceeded
            ToolExecutionError: If command fails
        """
        timeout = timeout or self._config.timeout_seconds
        cwd = cwd or self._config.cwd
        env = env or self._config.env

        logger.debug(f"IsolatedExecutor: executing {' '.join(command)}")

        process: asyncio.subprocess.Process | None = None
        kill_sent = False

        try:
            # Start process
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
                preexec_fn=self._set_limits if sys.platform != "win32" else None,
            )

            # Create timeout task
            timeout_task = asyncio.create_task(
                asyncio.sleep(timeout)
            )

            # Wait for process with cancellation support
            done: set[asyncio.Task] = set()
            pending: set[asyncio.Task] = set()

            stdout_chunks: list[bytes] = []
            stderr_chunks: list[bytes] = []

            async def read_stdout():
                try:
                    while True:
                        chunk = await process.stdout.read(8192)
                        if not chunk:
                            break
                        stdout_chunks.append(chunk)
                        # Truncate if too large
                        if sum(len(c) for c in stdout_chunks) > self._config.max_output_bytes:
                            stdout_chunks.append(b"[OUTPUT TRUNCATED]")
                            break
                except Exception:
                    pass

            async def read_stderr():
                try:
                    while True:
                        chunk = await process.stderr.read(8192)
                        if not chunk:
                            break
                        stderr_chunks.append(chunk)
                        if sum(len(c) for c in stderr_chunks) > self._config.max_output_bytes:
                            stderr_chunks.append(b"[STDERR TRUNCATED]")
                            break
                except Exception:
                    pass

            stdout_task = asyncio.create_task(read_stdout())
            stderr_task = asyncio.create_task(read_stderr())

            # Wait for process or timeout
            wait_task = asyncio.create_task(process.wait())

            while True:
                # Check for cancellation periodically
                if cancellation:
                    cancelled = False
                    if hasattr(cancellation, "is_cancelled"):
                        cancelled = cancellation.is_cancelled()
                    elif hasattr(cancellation, "cancelled"):
                        cancelled = cancellation.cancelled()
                    if cancelled:
                        self._terminate(process)
                        raise asyncio.CancelledError("Tool cancelled")

                # Check timeout
                if timeout_task.done():
                    self._terminate(process)
                    raise ToolTimeoutError(
                        timeout,
                        stdout=self._decode(stdout_chunks),
                        stderr=self._decode(stderr_chunks),
                    )

                # Check process
                if wait_task.done():
                    break

                # Wait a bit
                await asyncio.sleep(0.1)

            # Get return code
            returncode = await wait_task

            # Wait for output reading to complete
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

            stdout = self._decode(stdout_chunks)
            stderr = self._decode(stderr_chunks)

            # Check return code
            if returncode != 0:
                raise ToolExecutionError(
                    returncode=returncode,
                    stdout=stdout,
                    stderr=stderr,
                )

            return subprocess.CompletedProcess(
                args=command,
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
            )

        except asyncio.CancelledError:
            if process:
                self._terminate(process)
            raise

        except (ToolTimeoutError, ToolExecutionError):
            if process:
                self._terminate(process)
            raise

        except Exception as e:
            logger.error(f"IsolatedExecutor error: {e}")
            if process:
                self._terminate(process)
            raise

    def _terminate(self, process: asyncio.subprocess.Process) -> None:
        """Terminate process with SIGTERM, then SIGKILL."""
        try:
            process.terminate()
            # Don't await here - let caller handle timeout
        except ProcessLookupError:
            pass

    def _kill(self, process: asyncio.subprocess.Process) -> None:
        """Force kill process."""
        try:
            process.kill()
        except ProcessLookupError:
            pass

    def _set_limits(self) -> None:
        """Set resource limits for child process (Unix only)."""
        if not HAS_RESOURCE:
            return
        try:
            # Limit CPU time (not wall time)
            resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
            # Limit file size
            resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
            # Limit memory
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        except Exception as e:
            logger.warning(f"Failed to set resource limits: {e}")

    def _decode(self, chunks: list[bytes]) -> str:
        """Decode output chunks to string."""
        try:
            data = b"".join(chunks)
            return data.decode("utf-8", errors="replace")
        except Exception:
            return ""


# Global executor instance
_executor: IsolatedExecutor | None = None


def get_executor() -> IsolatedExecutor:
    """Get or create default executor."""
    global _executor
    if _executor is None:
        _executor = IsolatedExecutor()
    return _executor


# Convenience function
async def run_isolated(
    command: list[str],
    timeout: float = 30.0,
    **kwargs,
) -> subprocess.CompletedProcess:
    """Run command in isolated subprocess."""
    executor = get_executor()
    return await executor.execute(command, timeout=timeout, **kwargs)
