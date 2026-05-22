"""Agent Sandbox - tool permissions, resource quota, token budget, filesystem scope.

Provides security boundaries for agent execution:
- Tool permission enforcement
- Resource quotas (CPU, memory, time)
- Token budget enforcement
- Filesystem access control
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SandboxPermission(str, Enum):
    """Sandbox permission types."""

    TOOL_CALL = "tool_call"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    NETWORK = "network"
    EXECUTE = "execute"
    SPAWN_PROCESS = "spawn_process"


@dataclass
class ResourceQuota:
    """Resource quota limits."""

    max_tokens: int = 100000
    max_memory_mb: int = 512
    max_cpu_seconds: float = 60.0
    max_execution_seconds: float = 300.0
    max_tool_calls: int = 100
    max_file_size_mb: int = 10

    def is_exhausted(self, current_tokens: int = 0, elapsed_seconds: float = 0) -> tuple[bool, str]:
        """Check if quota is exhausted.

        Returns:
            Tuple of (is_exhausted, reason).
        """
        if current_tokens >= self.max_tokens:
            return True, f"Token limit reached: {current_tokens}/{self.max_tokens}"
        if elapsed_seconds >= self.max_execution_seconds:
            return True, f"Execution time limit: {elapsed_seconds:.1f}s/{self.max_execution_seconds}s"
        return False, ""


@dataclass
class SandboxConfig:
    """Sandbox configuration."""

    enabled: bool = True
    allowed_tools: list[str] = field(default_factory=list)
    denied_tools: list[str] = field(default_factory=list)
    allowed_paths: list[str] = field(default_factory=list)
    denied_paths: list[str] = field(default_factory=list)
    quota: ResourceQuota = field(default_factory=ResourceQuota)
    allow_network: bool = False
    allow_spawn: bool = False


class SandboxPermissionResult:
    """Result of a permission check."""

    def __init__(
        self,
        allowed: bool,
        reason: str = "",
        permission: SandboxPermission | None = None,
    ):
        self.allowed = allowed
        self.reason = reason
        self.permission = permission

    def __bool__(self) -> bool:
        return self.allowed


class AgentSandbox:
    """Sandbox for agent execution with permission enforcement.

    Enforces:
    - Tool call permissions
    - Resource quotas
    - Filesystem access control
    - Token budget tracking
    """

    def __init__(self, config: SandboxConfig | None = None) -> None:
        """Initialize sandbox.

        Args:
            config: Sandbox configuration.
        """
        self._config = config or SandboxConfig()
        self._tool_calls = 0
        self._tokens_used = 0
        self._start_time: float | None = None
        self._lock = asyncio.Lock()

    @property
    def config(self) -> SandboxConfig:
        """Get sandbox configuration."""
        return self._config

    def is_enabled(self) -> bool:
        """Check if sandbox is enabled."""
        return self._config.enabled

    async def check_tool_permission(self, tool_name: str) -> SandboxPermissionResult:
        """Check if tool is allowed.

        Args:
            tool_name: Name of the tool.

        Returns:
            SandboxPermissionResult with permission check result.
        """
        if not self._config.enabled:
            return SandboxPermissionResult(True, "Sandbox disabled")

        if tool_name in self._config.denied_tools:
            return SandboxPermissionResult(
                False,
                f"Tool '{tool_name}' is explicitly denied",
                SandboxPermission.TOOL_CALL,
            )

        if self._config.allowed_tools:
            if tool_name not in self._config.allowed_tools:
                return SandboxPermissionResult(
                    False,
                    f"Tool '{tool_name}' not in allowed list",
                    SandboxPermission.TOOL_CALL,
                )

        if self._tool_calls >= self._config.quota.max_tool_calls:
            return SandboxPermissionResult(
                False,
                f"Tool call limit reached: {self._tool_calls}/{self._config.quota.max_tool_calls}",
                SandboxPermission.TOOL_CALL,
            )

        return SandboxPermissionResult(
            True,
            f"Tool '{tool_name}' is allowed",
            SandboxPermission.TOOL_CALL,
        )

    async def check_file_permission(
        self,
        path: str,
        permission: SandboxPermission,
    ) -> SandboxPermissionResult:
        """Check filesystem permission.

        Args:
            path: File path.
            permission: Type of file permission.

        Returns:
            SandboxPermissionResult with permission check result.
        """
        if not self._config.enabled:
            return SandboxPermissionResult(True, "Sandbox disabled")

        if permission == SandboxPermission.FILE_READ:
            if self._config.denied_paths:
                for denied in self._config.denied_paths:
                    if path.startswith(denied):
                        return SandboxPermissionResult(
                            False,
                            f"Path '{path}' is in denied list",
                            permission,
                        )

            if self._config.allowed_paths:
                allowed = any(path.startswith(p) for p in self._config.allowed_paths)
                if not allowed:
                    return SandboxPermissionResult(
                        False,
                        f"Path '{path}' not in allowed list",
                        permission,
                    )

        return SandboxPermissionResult(True, "File permission granted", permission)

    async def check_resource_quota(
        self,
        tokens: int | None = None,
    ) -> SandboxPermissionResult:
        """Check if resource quota allows execution.

        Args:
            tokens: Current token count.

        Returns:
            SandboxPermissionResult with quota check result.
        """
        if not self._config.enabled:
            return SandboxPermissionResult(True, "Sandbox disabled")

        elapsed = self.get_elapsed_seconds()
        exhausted, reason = self._config.quota.is_exhausted(
            current_tokens=self._tokens_used + (tokens or 0),
            elapsed_seconds=elapsed,
        )

        if exhausted:
            return SandboxPermissionResult(False, reason)

        return SandboxPermissionResult(True, "Quota check passed")

    async def record_tool_call(self, tool_name: str, tokens_used: int = 0) -> bool:
        """Record a tool call and update quotas.

        Args:
            tool_name: Name of the tool called.
            tokens_used: Number of tokens used.

        Returns:
            True if recorded successfully.
        """
        async with self._lock:
            permission = await self.check_tool_permission(tool_name)
            if not permission.allowed:
                logger.warning(
                    "Tool call denied: agent=%s tool=%s reason=%s",
                    id(self),
                    tool_name,
                    permission.reason,
                )
                return False

            self._tool_calls += 1
            self._tokens_used += tokens_used

            logger.debug(
                "Tool call recorded: tool=%s calls=%d tokens=%d",
                tool_name,
                self._tool_calls,
                self._tokens_used,
            )

            return True

    async def check_and_enforce(self, operation: str, **kwargs: Any) -> SandboxPermissionResult:
        """Check and enforce sandbox for an operation.

        Args:
            operation: Operation type (tool_call, file_read, etc.).
            **kwargs: Operation-specific arguments.

        Returns:
            SandboxPermissionResult.
        """
        if operation == "tool_call":
            return await self.check_tool_permission(kwargs.get("tool_name", ""))

        if operation == "file_read":
            return await self.check_file_permission(
                kwargs.get("path", ""),
                SandboxPermission.FILE_READ,
            )

        if operation == "file_write":
            return await self.check_file_permission(
                kwargs.get("path", ""),
                SandboxPermission.FILE_WRITE,
            )

        if operation == "resource_quota":
            return await self.check_resource_quota(kwargs.get("tokens"))

        return SandboxPermissionResult(True, f"Unknown operation: {operation}")

    def start(self) -> None:
        """Start execution timer."""
        if self._start_time is None:
            self._start_time = time.time()

    def get_elapsed_seconds(self) -> float:
        """Get elapsed execution time.

        Returns:
            Elapsed seconds.
        """
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    def get_stats(self) -> dict[str, Any]:
        """Get sandbox statistics.

        Returns:
            Statistics dictionary.
        """
        return {
            "enabled": self._config.enabled,
            "tool_calls": self._tool_calls,
            "tool_calls_limit": self._config.quota.max_tool_calls,
            "tokens_used": self._tokens_used,
            "tokens_limit": self._config.quota.max_tokens,
            "elapsed_seconds": self.get_elapsed_seconds(),
            "execution_limit_seconds": self._config.quota.max_execution_seconds,
        }

    def reset(self) -> None:
        """Reset sandbox counters."""
        self._tool_calls = 0
        self._tokens_used = 0
        self._start_time = None
