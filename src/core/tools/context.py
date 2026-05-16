"""
Tool Context

Context for tool execution.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.tools.sandbox import SandboxConfig

import logging

logger = logging.getLogger(__name__)


class ToolExecutionMode(Enum):
    """Tool execution modes."""

    DRY_RUN = "dry_run"  # Simulate execution, no side effects
    SANDBOX = "sandbox"  # Restricted environment with sandbox protection
    FULL = "full"  # Full access (use with caution)


@dataclass
class ResourceLimits:
    """
    Resource consumption limits for tool execution.

    Attributes:
        max_cpu_time_seconds: Maximum CPU time allowed
        max_wall_time_seconds: Maximum wall clock time
        max_memory_mb: Maximum memory usage in MB
        max_open_files: Maximum open file descriptors
        max_subprocesses: Maximum child processes
        max_output_size: Maximum output size in bytes
    """

    max_cpu_time_seconds: int = 30
    max_wall_time_seconds: int = 60
    max_memory_mb: int = 256
    max_open_files: int = 100
    max_subprocesses: int = 5
    max_output_size: int = 10 * 1024 * 1024  # 10 MB

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_cpu_time_seconds": self.max_cpu_time_seconds,
            "max_wall_time_seconds": self.max_wall_time_seconds,
            "max_memory_mb": self.max_memory_mb,
            "max_open_files": self.max_open_files,
            "max_subprocesses": self.max_subprocesses,
            "max_output_size": self.max_output_size,
        }


@dataclass
class ToolContext:
    """
    Context for tool execution.

    Contains information about the execution environment,
    permissions, and state.

    Attributes:
        mode: Execution mode (dry_run, sandbox, full)
        workspace_root: Root directory for file operations
        allowed_paths: List of allowed paths (for sandbox)
        denied_paths: List of denied paths
        environment: Environment variables
        user_id: User ID executing the tool
        session_id: Current session ID
        correlation_id: Correlation ID for tracing
        variables: Custom variables for tool execution
        metadata: Additional metadata
        resource_limits: Resource consumption limits
        sandbox_config: Sandbox configuration reference
        agent_id: Agent ID executing the tool
        sandbox_enabled: Whether sandboxing is enabled
        audit_enabled: Whether audit logging is enabled
    """

    mode: ToolExecutionMode = ToolExecutionMode.FULL
    workspace_root: Optional[Path] = None
    allowed_paths: List[Path] = field(default_factory=list)
    denied_paths: List[Path] = field(default_factory=list)
    environment: Dict[str, str] = field(default_factory=dict)
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    correlation_id: Optional[str] = None
    variables: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    sandbox_config: Optional["SandboxConfig"] = field(default=None, repr=False)
    agent_id: Optional[str] = None
    sandbox_enabled: bool = True
    audit_enabled: bool = True

    def __post_init__(self):
        """Post-initialization processing."""
        # Resolve paths
        if self.workspace_root:
            self.workspace_root = self.workspace_root.resolve()
        self.allowed_paths = [p.resolve() if p else p for p in self.allowed_paths]
        self.denied_paths = [p.resolve() if p else p for p in self.denied_paths]

    def is_path_allowed(self, path: Path) -> bool:
        """
        Check if a path is allowed for this context.

        Args:
            path: Path to check

        Returns:
            True if path is allowed
        """
        path = path.resolve()

        # Check denied paths first
        for denied in self.denied_paths:
            denied = denied.resolve()
            try:
                path.relative_to(denied)
                return False  # Path is inside denied directory
            except ValueError:
                continue

        # Check allowed paths if specified
        if self.allowed_paths:
            for allowed in self.allowed_paths:
                allowed = allowed.resolve()
                try:
                    path.relative_to(allowed)
                    return True  # Path is inside allowed directory
                except ValueError:
                    continue
            return False  # Not in any allowed directory

        # Check workspace root if set
        if self.workspace_root:
            workspace = self.workspace_root.resolve()
            try:
                path.relative_to(workspace)
                return True
            except ValueError:
                return False

        return True  # No restrictions

    def is_read_allowed(self, path: Path) -> bool:
        """
        Check if read operation is allowed on path.

        Args:
            path: Path to check

        Returns:
            True if read is allowed
        """
        return self.is_path_allowed(path)

    def is_write_allowed(self, path: Path) -> bool:
        """
        Check if write operation is allowed on path.

        Args:
            path: Path to check

        Returns:
            True if write is allowed
        """
        if not self.is_path_allowed(path):
            return False
        # In sandbox mode, writes are more restricted
        if self.mode == ToolExecutionMode.SANDBOX:
            # Check if path exists or is creatable
            parent = path.parent
            if parent != path:
                return self.is_path_allowed(parent)
        return True

    def is_delete_allowed(self, path: Path) -> bool:
        """
        Check if delete operation is allowed on path.

        Args:
            path: Path to check

        Returns:
            True if delete is allowed
        """
        if not self.is_path_allowed(path):
            return False
        # In sandbox mode, delete requires stricter checks
        if self.mode == ToolExecutionMode.SANDBOX:
            # Prevent deletion of critical paths
            return True
        return True

    def get_allowed_paths_str(self) -> List[str]:
        """Get allowed paths as strings."""
        return [str(p) for p in self.allowed_paths]

    def get_denied_paths_str(self) -> List[str]:
        """Get denied paths as strings."""
        return [str(p) for p in self.denied_paths]

    def get_variable(self, key: str, default: Any = None) -> Any:
        """Get a variable value."""
        return self.variables.get(key, default)

    def set_variable(self, key: str, value: Any) -> None:
        """Set a variable value."""
        self.variables[key] = value

    def get_env(self, key: str, default: str = None) -> Optional[str]:
        """Get environment variable."""
        return self.environment.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "mode": self.mode.value,
            "workspace_root": str(self.workspace_root) if self.workspace_root else None,
            "allowed_paths": [str(p) for p in self.allowed_paths],
            "denied_paths": [str(p) for p in self.denied_paths],
            "environment": self.environment,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "correlation_id": self.correlation_id,
            "variables": self.variables,
            "metadata": self.metadata,
            "resource_limits": self.resource_limits.to_dict(),
            "agent_id": self.agent_id,
            "sandbox_enabled": self.sandbox_enabled,
            "audit_enabled": self.audit_enabled,
        }

    def with_sandbox_config(self, config: "SandboxConfig") -> "ToolContext":
        """
        Create a new context with sandbox configuration.

        Args:
            config: Sandbox configuration

        Returns:
            New ToolContext with sandbox config
        """
        new_context = ToolContext(
            mode=self.mode,
            workspace_root=self.workspace_root,
            allowed_paths=self.allowed_paths.copy(),
            denied_paths=self.denied_paths.copy(),
            environment=self.environment.copy(),
            user_id=self.user_id,
            session_id=self.session_id,
            correlation_id=self.correlation_id,
            variables=self.variables.copy(),
            metadata=self.metadata.copy(),
            resource_limits=self.resource_limits,
            sandbox_config=config,
            agent_id=self.agent_id,
            sandbox_enabled=self.sandbox_enabled,
            audit_enabled=self.audit_enabled,
        )
        return new_context


@dataclass
class ToolPermissionContext:
    """
    Permission context for tool execution.

    Tracks granted and denied permissions.
    """

    granted_permissions: List[str] = field(default_factory=list)
    denied_permissions: List[str] = field(default_factory=list)
    session_timeout: Optional[datetime] = None

    def has_permission(self, permission: str) -> bool:
        """Check if permission is granted."""
        return permission in self.granted_permissions

    def grant_permission(self, permission: str) -> None:
        """Grant a permission."""
        if permission not in self.granted_permissions:
            self.granted_permissions.append(permission)

    def deny_permission(self, permission: str) -> None:
        """Deny a permission."""
        if permission not in self.denied_permissions:
            self.denied_permissions.append(permission)


def create_default_context(
    workspace_root: Optional[Path] = None,
    mode: ToolExecutionMode = ToolExecutionMode.FULL,
) -> ToolContext:
    """
    Create a default tool context.

    Args:
        workspace_root: Root directory for operations
        mode: Execution mode

    Returns:
        ToolContext instance
    """
    return ToolContext(
        mode=mode,
        workspace_root=workspace_root,
        environment={},
    )


def create_sandbox_context(
    workspace_root: Path,
    allowed_paths: List[Path] = None,
    denied_paths: List[Path] = None,
    resource_limits: ResourceLimits = None,
    agent_id: str = None,
) -> ToolContext:
    """
    Create a sandboxed tool context.

    Args:
        workspace_root: Root directory
        allowed_paths: Paths the tool can access
        denied_paths: Paths the tool cannot access
        resource_limits: Resource consumption limits
        agent_id: Agent ID

    Returns:
        ToolContext in sandbox mode
    """
    return ToolContext(
        mode=ToolExecutionMode.SANDBOX,
        workspace_root=workspace_root.resolve() if workspace_root else None,
        allowed_paths=[p.resolve() for p in (allowed_paths or [])],
        denied_paths=[p.resolve() for p in (denied_paths or [])],
        environment={},
        resource_limits=resource_limits or ResourceLimits(),
        agent_id=agent_id,
        sandbox_enabled=True,
        audit_enabled=True,
    )


def create_strict_sandbox_context(
    workspace_root: Path,
    allowed_paths: List[Path] = None,
    denied_paths: List[Path] = None,
) -> ToolContext:
    """
    Create a strict sandboxed context with minimal permissions.

    This creates a sandbox with:
    - Reduced timeouts
    - No subprocess spawning
    - No network access
    - Strict path enforcement

    Args:
        workspace_root: Root directory
        allowed_paths: Paths the tool can access
        denied_paths: Paths the tool cannot access

    Returns:
        ToolContext in strict sandbox mode
    """
    return ToolContext(
        mode=ToolExecutionMode.SANDBOX,
        workspace_root=workspace_root.resolve() if workspace_root else None,
        allowed_paths=[p.resolve() for p in (allowed_paths or [])],
        denied_paths=[p.resolve() for p in (denied_paths or [])],
        environment={},
        resource_limits=ResourceLimits(
            max_cpu_time_seconds=10,
            max_wall_time_seconds=30,
            max_memory_mb=128,
            max_open_files=20,
            max_subprocesses=0,  # No subprocesses allowed
        ),
        sandbox_enabled=True,
        audit_enabled=True,
    )


def create_dry_run_context(workspace_root: Optional[Path] = None) -> ToolContext:
    """
    Create a dry-run context.

    Args:
        workspace_root: Root directory

    Returns:
        ToolContext in dry-run mode
    """
    return ToolContext(
        mode=ToolExecutionMode.DRY_RUN,
        workspace_root=workspace_root,
        environment={},
    )
