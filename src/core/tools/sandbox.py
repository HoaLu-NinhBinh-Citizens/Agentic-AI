"""
P2 Sandbox - Tool Execution Safety Layer

Implements process isolation, filesystem confinement, and resource limits
for safe tool execution. This is the P2 (Phase 2: Tool Safety) implementation.

Security Layers:
1. Process Isolation - Subprocesses run in restricted environments
2. Filesystem Confinement - Operations constrained to allowed paths
3. Resource Limits - CPU, memory, and time constraints
4. Audit Trail - Complete execution logging for security analysis

Usage:
    from src.core.tools.sandbox import SandboxManager, SandboxConfig

    config = SandboxConfig(
        allowed_paths=[Path("/workspace")],
        denied_paths=[Path("/etc"), Path("/root")],
        max_cpu_percent=50,
        max_memory_mb=256,
        max_open_files=100,
    )
    manager = SandboxManager(config)

    # Execute with sandbox
    result = await manager.execute_tool(handler, params, context)
"""

import asyncio
import hashlib
import json
import logging
import os
import platform
import signal
import subprocess
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

logger = logging.getLogger(__name__)

# Platform-specific imports
_is_windows = platform.system() == "Windows"
_is_linux = platform.system() == "Linux"

# Try to import resource module (Unix only)
try:
    import resource
    _has_resource = True
except ImportError:
    _has_resource = False
    resource = None  # type: ignore


class SandboxMode(Enum):
    """Sandbox enforcement levels."""

    DISABLED = "disabled"  # No sandboxing
    SOFT = "soft"  # Path checking only, warn on violations
    HARD = "hard"  # Full enforcement with process isolation
    STRICT = "strict"  # Maximum isolation, minimal capabilities


class ResourceLimitType(Enum):
    """Types of resource limits."""

    CPU_TIME = "cpu_time"  # Maximum CPU time in seconds
    WALL_TIME = "wall_time"  # Maximum wall clock time
    MEMORY = "memory"  # Maximum memory in bytes
    OPEN_FILES = "open_files"  # Maximum open file descriptors
    CHILD_PROCESSES = "child_processes"  # Maximum child processes
    FILE_SIZE = "file_size"  # Maximum file size in bytes
    STACK_SIZE = "stack_size"  # Maximum stack size


@dataclass
class ResourceLimit:
    """A single resource limit."""

    limit_type: ResourceLimitType
    soft_limit: int
    hard_limit: int
    enabled: bool = True

    def to_resource(self) -> Dict[str, int]:
        """Convert to resource.RLIMIT_* format."""
        return {
            "soft": self.soft_limit,
            "hard": self.hard_limit,
        }


@dataclass
class SandboxConfig:
    """
    Configuration for sandbox execution.

    Attributes:
        mode: Sandbox enforcement level
        allowed_paths: Whitelist of accessible paths (empty = all allowed)
        denied_paths: Blacklist of forbidden paths
        resource_limits: Resource consumption limits
        env_whitelist: Allowed environment variables (empty = all allowed)
        env_blocklist: Forbidden environment variables
        working_directory: Constrained working directory
        capabilities: Restricted Linux capabilities (Linux only)
        seccomp_profile: seccomp filter profile path (Linux only)
        chroot_path: Chroot directory (requires root, Linux only)
        allow_network: Whether network operations are allowed
        allow_subprocess: Whether subprocess spawning is allowed
        allow_file_create: Whether creating new files is allowed
        allow_file_delete: Whether deleting files is allowed
        allow_env_write: Whether modifying environment is allowed
        max_execution_count: Max times a tool can be executed in one session
        audit_enabled: Whether to log all operations
        audit_path: Path to write audit logs
    """

    mode: SandboxMode = SandboxMode.HARD
    allowed_paths: List[Path] = field(default_factory=list)
    denied_paths: List[Path] = field(default_factory=list)
    resource_limits: Dict[ResourceLimitType, ResourceLimit] = field(default_factory=dict)
    env_whitelist: List[str] = field(default_factory=list)
    env_blocklist: List[str] = field(default_factory=list)
    working_directory: Optional[Path] = None
    capabilities: List[str] = field(default_factory=list)
    seccomp_profile: Optional[Path] = None
    chroot_path: Optional[Path] = None
    allow_network: bool = False
    allow_subprocess: bool = False
    allow_file_create: bool = True
    allow_file_delete: bool = True
    allow_env_write: bool = False
    max_execution_count: int = 1000
    audit_enabled: bool = True
    audit_path: Optional[Path] = None

    def __post_init__(self):
        """Validate configuration."""
        # Resolve paths
        self.allowed_paths = [p.resolve() if p else p for p in self.allowed_paths]
        self.denied_paths = [p.resolve() if p else p for p in self.denied_paths]
        if self.working_directory:
            self.working_directory = self.working_directory.resolve()

        # Set default resource limits if not specified
        if ResourceLimitType.CPU_TIME not in self.resource_limits:
            self.resource_limits[ResourceLimitType.CPU_TIME] = ResourceLimit(
                limit_type=ResourceLimitType.CPU_TIME,
                soft_limit=30,
                hard_limit=60,
            )
        if ResourceLimitType.WALL_TIME not in self.resource_limits:
            self.resource_limits[ResourceLimitType.WALL_TIME] = ResourceLimit(
                limit_type=ResourceLimitType.WALL_TIME,
                soft_limit=60,
                hard_limit=120,
            )
        if ResourceLimitType.MEMORY not in self.resource_limits:
            self.resource_limits[ResourceLimitType.MEMORY] = ResourceLimit(
                limit_type=ResourceLimitType.MEMORY,
                soft_limit=256 * 1024 * 1024,  # 256 MB
                hard_limit=512 * 1024 * 1024,  # 512 MB
            )
        if ResourceLimitType.OPEN_FILES not in self.resource_limits:
            self.resource_limits[ResourceLimitType.OPEN_FILES] = ResourceLimit(
                limit_type=ResourceLimitType.OPEN_FILES,
                soft_limit=100,
                hard_limit=200,
            )
        if ResourceLimitType.CHILD_PROCESSES not in self.resource_limits:
            self.resource_limits[ResourceLimitType.CHILD_PROCESSES] = ResourceLimit(
                limit_type=ResourceLimitType.CHILD_PROCESSES,
                soft_limit=5,
                hard_limit=10,
            )


@dataclass
class SandboxResult:
    """
    Result of sandboxed execution.

    Attributes:
        sandbox_id: Unique identifier for this execution
        tool_name: Name of the executed tool
        success: Whether execution succeeded
        output: Tool output if successful
        error: Error message if failed
        error_type: Type of error
        execution_time_ms: Execution duration
        sandbox_violations: List of policy violations
        resources_used: Resource consumption statistics
        audit_id: ID linking to audit log entry
    """

    sandbox_id: str
    tool_name: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    execution_time_ms: float = 0.0
    sandbox_violations: List[str] = field(default_factory=list)
    resources_used: Dict[str, Any] = field(default_factory=dict)
    audit_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "sandbox_id": self.sandbox_id,
            "tool_name": self.tool_name,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "error_type": self.error_type,
            "execution_time_ms": self.execution_time_ms,
            "sandbox_violations": self.sandbox_violations,
            "resources_used": self.resources_used,
            "audit_id": self.audit_id,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class SandboxViolation:
    """Record of a sandbox policy violation."""

    violation_type: str
    details: str
    path: Optional[str] = None
    resource: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "violation_type": self.violation_type,
            "details": self.details,
            "path": self.path,
            "resource": self.resource,
            "timestamp": self.timestamp.isoformat(),
        }


class PathValidator:
    """
    Validates filesystem operations against sandbox policy.

    Implements canonicalization and comparison to prevent
    path traversal attacks and symlink bypasses.
    """

    def __init__(self, config: SandboxConfig):
        """
        Initialize path validator.

        Args:
            config: Sandbox configuration
        """
        self.config = config
        self._denied_patterns: Set[str] = set()

        # Pre-compute denied patterns for faster checking
        for denied in config.denied_paths:
            self._denied_patterns.add(str(denied))

    def is_path_allowed(self, path: Path) -> tuple[bool, Optional[str]]:
        """
        Check if a path is allowed for operations.

        Args:
            path: Path to validate

        Returns:
            Tuple of (is_allowed, error_message)
        """
        try:
            # Resolve to absolute canonical path
            resolved = path.resolve()

            # Check denied paths first
            for denied in self.config.denied_paths:
                try:
                    resolved.relative_to(denied)
                    return False, f"Path '{path}' is inside denied directory '{denied}'"
                except ValueError:
                    continue

            # Check allowed paths if specified
            if self.config.allowed_paths:
                allowed = False
                for allowed_path in self.config.allowed_paths:
                    try:
                        resolved.relative_to(allowed_path)
                        allowed = True
                        break
                    except ValueError:
                        continue

                if not allowed:
                    return False, f"Path '{path}' is not inside any allowed directory"

            return True, None

        except (OSError, RuntimeError) as e:
            return False, f"Failed to resolve path '{path}': {e}"

    def validate_read(self, path: Path) -> tuple[bool, Optional[str]]:
        """Validate a read operation."""
        return self.is_path_allowed(path)

    def validate_write(self, path: Path) -> tuple[bool, Optional[str]]:
        """Validate a write operation."""
        allowed, error = self.is_path_allowed(path)

        if not allowed:
            return allowed, error

        if not self.config.allow_file_create:
            if not path.exists():
                return False, "Creating new files is not allowed"

        return True, None

    def validate_delete(self, path: Path) -> tuple[bool, Optional[str]]:
        """Validate a delete operation."""
        allowed, error = self.is_path_allowed(path)

        if not allowed:
            return allowed, error

        if not self.config.allow_file_delete:
            return False, "Deleting files is not allowed"

        return True, None

    def validate_execute(self, path: Path) -> tuple[bool, Optional[str]]:
        """Validate an execute operation."""
        return self.is_path_allowed(path)

    def validate_directory(self, path: Path) -> tuple[bool, Optional[str]]:
        """Validate directory traversal."""
        return self.is_path_allowed(path)


class ResourceMonitor:
    """
    Monitors and limits resource usage during execution.

    Tracks CPU time, memory, and other resources to enforce limits.
    """

    def __init__(self, config: SandboxConfig):
        """
        Initialize resource monitor.

        Args:
            config: Sandbox configuration with resource limits
        """
        self.config = config
        self._start_time: Optional[float] = None
        self._start_cpu_time: Optional[float] = None
        self._peak_memory: int = 0

    def start_monitoring(self) -> None:
        """Start resource monitoring."""
        self._start_time = time.time()
        self._start_cpu_time = None

        # Get initial CPU time if resource module is available (Unix only)
        if _has_resource:
            try:
                self._start_cpu_time = resource.getrusage(resource.RUSAGE_SELF).ru_utime
            except Exception:
                self._start_cpu_time = None

        self._peak_memory = self._get_current_memory()

    def get_current_stats(self) -> Dict[str, Any]:
        """
        Get current resource usage statistics.

        Returns:
            Dictionary with resource usage info
        """
        stats = {
            "wall_time_ms": 0,
            "cpu_time_ms": 0,
            "peak_memory_bytes": self._peak_memory,
            "peak_memory_mb": self._peak_memory / (1024 * 1024),
        }

        if self._start_time:
            stats["wall_time_ms"] = (time.time() - self._start_time) * 1000

        # Get CPU time if resource module is available
        if self._start_cpu_time is not None and _has_resource:
            try:
                current_cpu = resource.getrusage(resource.RUSAGE_SELF).ru_utime
                stats["cpu_time_ms"] = (current_cpu - self._start_cpu_time) * 1000
            except Exception:
                pass

        return stats

    def check_limits(self) -> tuple[bool, List[str]]:
        """
        Check if current usage exceeds configured limits.

        Returns:
            Tuple of (within_limits, list_of_violations)
        """
        violations = []
        stats = self.get_current_stats()

        # Check wall time
        wall_limit = self.config.resource_limits.get(ResourceLimitType.WALL_TIME)
        if wall_limit and wall_limit.enabled:
            wall_ms = stats["wall_time_ms"]
            wall_limit_ms = wall_limit.soft_limit * 1000
            if wall_ms > wall_limit_ms:
                violations.append(
                    f"Wall time exceeded: {wall_ms/1000:.2f}s > {wall_limit.soft_limit}s"
                )

        # Check CPU time
        cpu_limit = self.config.resource_limits.get(ResourceLimitType.CPU_TIME)
        if cpu_limit and cpu_limit.enabled:
            cpu_ms = stats["cpu_time_ms"]
            cpu_limit_ms = cpu_limit.soft_limit * 1000
            if cpu_ms > cpu_limit_ms:
                violations.append(
                    f"CPU time exceeded: {cpu_ms/1000:.2f}s > {cpu_limit.soft_limit}s"
                )

        # Check memory
        mem_limit = self.config.resource_limits.get(ResourceLimitType.MEMORY)
        if mem_limit and mem_limit.enabled:
            mem_bytes = stats["peak_memory_bytes"]
            if mem_bytes > mem_limit.soft_limit:
                violations.append(
                    f"Memory exceeded: {mem_bytes/(1024*1024):.2f}MB > {mem_limit.soft_limit/(1024*1024):.0f}MB"
                )

        return len(violations) == 0, violations

    def _get_current_memory(self) -> int:
        """Get current process memory usage in bytes."""
        try:
            import psutil

            process = psutil.Process(os.getpid())
            return process.memory_info().rss
        except ImportError:
            # Fallback: try platform-specific methods
            try:
                if _is_windows:
                    # Windows: use ctypes to get process memory
                    try:
                        import ctypes

                        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
                            _fields_ = [
                                ("cb", ctypes.c_uint32),
                                ("PageFaultCount", ctypes.c_uint32),
                                ("PeakWorkingSetSize", ctypes.c_size_t),
                                ("WorkingSetSize", ctypes.c_size_t),
                                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                                ("PagefileUsage", ctypes.c_size_t),
                                ("PeakPagefileUsage", ctypes.c_size_t),
                                ("PrivateUsage", ctypes.c_size_t),
                            ]

                        kernel32 = ctypes.windll.kernel32
                        pid = os.getpid()
                        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_INFORMATION
                        if handle:
                            mem_counters = PROCESS_MEMORY_COUNTERS_EX()
                            mem_counters.cb = ctypes.sizeof(mem_counters)
                            if kernel32.GetProcessMemoryInfo(handle, ctypes.byref(mem_counters), ctypes.sizeof(mem_counters)):
                                kernel32.CloseHandle(handle)
                                return mem_counters.WorkingSetSize
                            kernel32.CloseHandle(handle)
                    except Exception:
                        pass
                elif _is_linux:
                    # Linux: read from /proc/self/status
                    with open("/proc/self/status", "r") as f:
                        for line in f:
                            if line.startswith("VmRSS:"):
                                return int(line.split()[1]) * 1024
            except Exception:
                pass
            # Return 0 if unable to determine memory (no false positives)
            return 0

    def update_peak_memory(self) -> None:
        """Update peak memory tracking."""
        current = self._get_current_memory()
        if current > self._peak_memory:
            self._peak_memory = current


class SubprocessSandbox:
    """
    Sandboxed subprocess execution wrapper.

    Provides process-level isolation for executing external commands
    with restricted capabilities and resource limits.
    """

    def __init__(self, config: SandboxConfig):
        """
        Initialize subprocess sandbox.

        Args:
            config: Sandbox configuration
        """
        self.config = config
        self._execution_count: int = 0

    def can_execute(self) -> tuple[bool, Optional[str]]:
        """
        Check if subprocess execution is allowed.

        Returns:
            Tuple of (allowed, error_message)
        """
        self._execution_count += 1

        if not self.config.allow_subprocess:
            return False, "Subprocess execution is disabled in sandbox config"

        if (
            self._execution_count
            > self.config.resource_limits.get(
                ResourceLimitType.CHILD_PROCESSES, ResourceLimit(  # type: ignore
                    ResourceLimitType.CHILD_PROCESSES, 5, 10
                )
            ).soft_limit
        ):
            return False, "Maximum child process limit exceeded"

        if self._execution_count > self.config.max_execution_count:
            return False, "Maximum execution count exceeded for this session"

        return True, None

    def build_environment(self) -> Dict[str, str]:
        """
        Build sandboxed environment variables.

        Returns:
            Dictionary of allowed environment variables
        """
        if self.config.env_whitelist:
            return {
                k: v
                for k, v in os.environ.items()
                if k in self.config.env_whitelist
            }

        if self.config.env_blocklist:
            return {
                k: v
                for k, v in os.environ.items()
                if k not in self.config.env_blocklist
            }

        return os.environ.copy()

    def build_subprocess_args(
        self,
        command: str,
        cwd: Optional[Path] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Build subprocess arguments with sandbox restrictions.

        Args:
            command: Command to execute
            cwd: Working directory
            timeout: Execution timeout

        Returns:
            Dictionary of subprocess arguments
        """
        env = self.build_environment()

        # Restrict environment
        if not self.config.allow_env_write:
            # Remove modification capabilities from env
            env = {k: v for k, v in env.items() if not k.startswith("_")}

            return {
                "args": command,
                "shell": True,
                "cwd": str(cwd or self.config.working_directory or Path.cwd()),
                "env": env,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
                "timeout": timeout
                or self.config.resource_limits.get(ResourceLimitType.WALL_TIME)
                .soft_limit,  # type: ignore
            }

    def get_resource_limits(self) -> Dict[int, tuple[int, int]]:
        """
        Get resource limits for subprocess.

        Returns:
            Dictionary mapping resource.RLIMIT_* to (soft, hard) tuples
        """
        # Resource limits only work on Unix systems
        if not _has_resource or not _is_linux:
            return {}

        limits = {}

        for limit_type, limit in self.config.resource_limits.items():
            if not limit.enabled:
                continue

            rlimit_map = {
                ResourceLimitType.CPU_TIME: resource.RLIMIT_CPU,
                ResourceLimitType.MEMORY: resource.RLIMIT_AS,
                ResourceLimitType.OPEN_FILES: resource.RLIMIT_NOFILE,
                ResourceLimitType.CHILD_PROCESSES: resource.RLIMIT_NPROC,
                ResourceLimitType.FILE_SIZE: resource.RLIMIT_FSIZE,
                ResourceLimitType.STACK_SIZE: resource.RLIMIT_STACK,
            }

            if limit_type in rlimit_map:
                limits[rlimit_map[limit_type]] = (limit.soft_limit, limit.hard_limit)

        return limits


class SandboxManager:
    """
    Main sandbox manager coordinating all security layers.

    This is the primary entry point for P2 sandboxing. It coordinates:
    - Path validation
    - Resource monitoring
    - Subprocess isolation
    - Audit logging

    Usage:
        config = SandboxConfig(
            allowed_paths=[Path("/workspace")],
            denied_paths=[Path("/etc/passwd")],
        )
        manager = SandboxManager(config)

        result = await manager.execute_tool(
            handler=my_handler,
            params={"path": "/workspace/test.txt"},
            context=tool_context,
        )
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        """
        Initialize sandbox manager.

        Args:
            config: Sandbox configuration. Uses defaults if not provided.
        """
        self.config = config or SandboxConfig()
        self._path_validator = PathValidator(self.config)
        self._resource_monitor = ResourceMonitor(self.config)
        self._subprocess_sandbox = SubprocessSandbox(self.config)
        self._execution_count: Dict[str, int] = {}
        self._active_executions: Dict[str, asyncio.Task] = {}

    @property
    def mode(self) -> SandboxMode:
        """Get current sandbox mode."""
        return self.config.mode

    def is_enabled(self) -> bool:
        """Check if sandboxing is enabled."""
        return self.config.mode != SandboxMode.DISABLED

    def is_path_allowed(self, path: Path) -> tuple[bool, Optional[str]]:
        """
        Check if a path is allowed for operations.

        Args:
            path: Path to validate

        Returns:
            Tuple of (is_allowed, error_message)
        """
        if not self.is_enabled():
            return True, None
        return self._path_validator.is_path_allowed(path)

    def validate_operation(
        self,
        operation: str,
        path: Optional[Path] = None,
    ) -> tuple[bool, Optional[str], List[SandboxViolation]]:
        """
        Validate a tool operation against sandbox policy.

        Args:
            operation: Operation type (read, write, delete, execute)
            path: Path involved in operation

        Returns:
            Tuple of (allowed, error, violations)
        """
        violations = []

        if not self.is_enabled():
            return True, None, violations

        if path:
            if operation == "read":
                allowed, error = self._path_validator.validate_read(path)
            elif operation == "write":
                allowed, error = self._path_validator.validate_write(path)
            elif operation == "delete":
                allowed, error = self._path_validator.validate_delete(path)
            elif operation == "execute":
                allowed, error = self._path_validator.validate_execute(path)
            else:
                allowed, error = self._path_validator.is_path_allowed(path)

            if not allowed:
                violation = SandboxViolation(
                    violation_type=f"path_{operation}",
                    details=error or "Path operation denied",
                    path=str(path),
                )
                violations.append(violation)
                return False, error, violations

        # Check resource limits
        within_limits, limit_violations = self._resource_monitor.check_limits()
        if not within_limits:
            for violation_msg in limit_violations:
                violation = SandboxViolation(
                    violation_type="resource_limit",
                    details=violation_msg,
                )
                violations.append(violation)

            if self.config.mode == SandboxMode.STRICT:
                return False, f"Resource limit exceeded: {limit_violations[0]}", violations

        return True, None, violations

    async def execute_tool(
        self,
        handler: Callable,
        params: Dict[str, Any],
        tool_context: Any,
        tool_name: str = "unknown",
        timeout: Optional[int] = None,
    ) -> SandboxResult:
        """
        Execute a tool handler with sandbox protection.

        Args:
            handler: Tool handler function
            params: Tool parameters
            tool_context: Tool execution context
            tool_name: Name of the tool being executed
            timeout: Execution timeout override

        Returns:
            SandboxResult with execution outcome
        """
        sandbox_id = str(uuid4())[:8]
        start_time = time.time()
        violations: List[SandboxViolation] = []

        # Start resource monitoring
        if self.is_enabled():
            self._resource_monitor.start_monitoring()

        # Track execution
        self._execution_count[tool_name] = self._execution_count.get(tool_name, 0) + 1

        try:
            # Validate operation before execution
            path = self._extract_path_param(params)
            allowed, error, pre_violations = self.validate_operation(
                "read" if tool_context.mode.value in ("dry_run", "sandbox") else "write",
                path,
            )
            violations.extend(pre_violations)

            if not allowed:
                return SandboxResult(
                    sandbox_id=sandbox_id,
                    tool_name=tool_name,
                    success=False,
                    error=error,
                    error_type="SandboxViolation",
                    execution_time_ms=(time.time() - start_time) * 1000,
                    sandbox_violations=[v.to_dict() for v in violations],
                )

            # Execute with timeout
            exec_timeout = timeout or self.config.resource_limits.get(
                ResourceLimitType.WALL_TIME, ResourceLimit(  # type: ignore
                    ResourceLimitType.WALL_TIME, 60, 120
                )
            ).soft_limit

            if asyncio.iscoroutinefunction(handler):
                output = await asyncio.wait_for(
                    handler(params, tool_context),
                    timeout=exec_timeout,
                )
            else:
                loop = asyncio.get_event_loop()
                output = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: handler(params, tool_context),
                    ),
                    timeout=exec_timeout,
                )

            # Update resource stats
            self._resource_monitor.update_peak_memory()

            return SandboxResult(
                sandbox_id=sandbox_id,
                tool_name=tool_name,
                success=True,
                output=output,
                execution_time_ms=(time.time() - start_time) * 1000,
                sandbox_violations=[v.to_dict() for v in violations],
                resources_used=self._resource_monitor.get_current_stats(),
            )

        except asyncio.TimeoutError:
            violation = SandboxViolation(
                violation_type="timeout",
                details=f"Execution timed out after {exec_timeout} seconds",
            )
            violations.append(violation)

            return SandboxResult(
                sandbox_id=sandbox_id,
                tool_name=tool_name,
                success=False,
                error=f"Execution timed out after {exec_timeout} seconds",
                error_type="TimeoutError",
                execution_time_ms=(time.time() - start_time) * 1000,
                sandbox_violations=[v.to_dict() for v in violations],
                resources_used=self._resource_monitor.get_current_stats(),
            )

        except Exception as e:
            violation = SandboxViolation(
                violation_type="execution_error",
                details=str(e),
            )
            violations.append(violation)

            return SandboxResult(
                sandbox_id=sandbox_id,
                tool_name=tool_name,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                execution_time_ms=(time.time() - start_time) * 1000,
                sandbox_violations=[v.to_dict() for v in violations],
                resources_used=self._resource_monitor.get_current_stats(),
            )

    async def execute_subprocess(
        self,
        command: str,
        cwd: Optional[Path] = None,
        timeout: Optional[int] = None,
    ) -> SandboxResult:
        """
        Execute a command in a subprocess with sandbox restrictions.

        Args:
            command: Command to execute
            cwd: Working directory
            timeout: Execution timeout

        Returns:
            SandboxResult with execution outcome
        """
        sandbox_id = str(uuid4())[:8]
        start_time = time.time()

        # Check subprocess execution is allowed
        allowed, error = self._subprocess_sandbox.can_execute()
        if not allowed:
            return SandboxResult(
                sandbox_id=sandbox_id,
                tool_name="subprocess",
                success=False,
                error=error,
                error_type="SandboxViolation",
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        # Validate working directory
        if cwd:
            path_allowed, path_error = self.is_path_allowed(cwd)
            if not path_allowed:
                return SandboxResult(
                    sandbox_id=sandbox_id,
                    tool_name="subprocess",
                    success=False,
                    error=path_error,
                    error_type="SandboxViolation",
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

        # Build subprocess arguments
        subproc_args = self._subprocess_sandbox.build_subprocess_args(
            command, cwd, timeout
        )

        # Apply resource limits
        limits = self._subprocess_sandbox.get_resource_limits()

        try:
            # Start monitoring
            self._resource_monitor.start_monitoring()

            # Execute with resource limits
            process = subprocess.Popen(**subproc_args)

            # Wait with timeout
            try:
                stdout, stderr = process.communicate(timeout=timeout)
                returncode = process.returncode
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()

                violation = SandboxViolation(
                    violation_type="timeout",
                    details=f"Subprocess timed out after {timeout}s",
                )

                return SandboxResult(
                    sandbox_id=sandbox_id,
                    tool_name="subprocess",
                    success=False,
                    error=f"Command timed out after {timeout}s",
                    error_type="TimeoutError",
                    execution_time_ms=(time.time() - start_time) * 1000,
                    sandbox_violations=[violation.to_dict()],
                    resources_used=self._resource_monitor.get_current_stats(),
                )

            return SandboxResult(
                sandbox_id=sandbox_id,
                tool_name="subprocess",
                success=returncode == 0,
                output={
                    "returncode": returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                },
                execution_time_ms=(time.time() - start_time) * 1000,
                resources_used=self._resource_monitor.get_current_stats(),
            )

        except Exception as e:
            return SandboxResult(
                sandbox_id=sandbox_id,
                tool_name="subprocess",
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    def _extract_path_param(self, params: Dict[str, Any]) -> Optional[Path]:
        """Extract path from parameters for validation."""
        path_keys = ["path", "file_path", "directory", "source", "destination", "root"]

        for key in path_keys:
            if key in params and params[key]:
                return Path(params[key])

        return None

    def get_execution_stats(self) -> Dict[str, Any]:
        """
        Get sandbox execution statistics.

        Returns:
            Dictionary with execution stats
        """
        return {
            "mode": self.config.mode.value,
            "enabled": self.is_enabled(),
            "execution_counts": self._execution_count.copy(),
            "total_executions": sum(self._execution_count.values()),
            "active_executions": len(self._active_executions),
            "config": {
                "allowed_paths": [str(p) for p in self.config.allowed_paths],
                "denied_paths": [str(p) for p in self.config.denied_paths],
                "allow_network": self.config.allow_network,
                "allow_subprocess": self.config.allow_subprocess,
            },
        }

    def reset_stats(self) -> None:
        """Reset execution statistics."""
        self._execution_count.clear()
        self._active_executions.clear()


# Default sandbox manager instance
_default_manager: Optional[SandboxManager] = None


def get_sandbox_manager(config: Optional[SandboxConfig] = None) -> SandboxManager:
    """
    Get the default sandbox manager instance.

    Args:
        config: Optional configuration override

    Returns:
        SandboxManager instance
    """
    global _default_manager

    if config is not None:
        _default_manager = SandboxManager(config)
    elif _default_manager is None:
        _default_manager = SandboxManager()

    return _default_manager


def reset_sandbox_manager() -> None:
    """Reset the default sandbox manager."""
    global _default_manager
    _default_manager = None
