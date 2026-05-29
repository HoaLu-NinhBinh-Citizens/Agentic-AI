"""Process isolation sandbox module.

Features:
- Isolated subprocess with strict boundaries
- No shared memory, no inherited fds, no inherited environment variables
- Capability enforcement before spawning
- Resource limits
- Timeout enforcement
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import shlex
import subprocess
import sys
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# CAPABILITY DEFINITIONS
# =============================================================================


class Capability:
    """Capability flags for subprocess isolation.
    
    These are validated BEFORE spawning the subprocess,
    ensuring the host process enforces restrictions.
    """
    
    # File system
    FS_READ = "fs:read"
    FS_WRITE = "fs:write"
    FS_DELETE = "fs:delete"
    FS_MKDIR = "fs:mkdir"
    
    # Network
    NET_HTTP = "net:http"
    NET_RAW = "net:raw"
    NET_DNS = "net:dns"
    
    # System
    SYS_EXEC = "sys:exec"
    SYS_ENV = "sys:env"
    SYS_PROCESS = "sys:process"
    
    # Hardware
    HW_FLASH = "hw:flash"
    HW_SERIAL = "hw:serial"
    HW_GPIO = "hw:gpio"
    
    # Security
    SEC_SIGN = "sec:sign"
    SEC_VERIFY = "sec:verify"
    SEC_KEY_READ = "sec:key:read"
    SEC_KEY_WRITE = "sec:key:write"
    
    # Dangerous capabilities
    DANGEROUS = {
        SYS_EXEC,
        SYS_ENV,
        NET_RAW,
        SEC_KEY_READ,
        SEC_KEY_WRITE,
    }
    
    # Trusted-only capabilities
    TRUSTED_ONLY = {
        HW_FLASH,
        HW_SERIAL,
        HW_GPIO,
    }


# =============================================================================
# CAPABILITY VALIDATOR
# =============================================================================


class CapabilityValidator:
    """Validates capability requests BEFORE subprocess spawning.
    
    This is the host-side enforcement - capabilities are validated
    before any subprocess is created.
    """
    
    @classmethod
    def validate_request(
        cls,
        requested: set[str],
        granted: set[str],
        trust_level: int = 50,
    ) -> tuple[bool, str | None]:
        """Validate capability request.
        
        Args:
            requested: Capabilities being requested
            granted: Capabilities granted to the plugin
            trust_level: Trust level 0-100
            
        Returns:
            (is_valid, error_message)
        """
        # Check all requested capabilities are in granted set
        missing = requested - granted
        if missing:
            return False, f"Missing capabilities: {missing}"
        
        # Check for dangerous capabilities
        for cap in requested & Capability.DANGEROUS:
            if cap not in granted:
                return False, f"Dangerous capability {cap} not granted"
            # Dangerous caps require high trust
            if trust_level < 80:
                return False, f"Capability {cap} requires trust level >= 80 (got {trust_level})"
        
        # Check for trusted-only capabilities
        for cap in requested & Capability.TRUSTED_ONLY:
            if cap not in granted:
                return False, f"Capability {cap} not granted"
            # Trusted caps require high trust
            if trust_level < 90:
                return False, f"Capability {cap} requires trust level >= 90 (got {trust_level})"
        
        return True, None
    
    @classmethod
    def validate_command(cls, command: str | list[str]) -> tuple[bool, str | None]:
        """Validate command before execution.
        
        Args:
            command: Command to validate
            
        Returns:
            (is_valid, error_message)
        """
        if isinstance(command, str):
            cmd_list = shlex.split(command)
        else:
            cmd_list = command
        
        if not cmd_list or not cmd_list[0]:
            return False, "Command cannot be empty"
        
        # Check for dangerous shell operators in string commands
        if isinstance(command, str):
            dangerous = [";", "|", "&", "&&", "||", ">", ">>", "<", "<<", "`", "$(", "${"]
            for op in dangerous:
                if op in command:
                    # Only allow if it looks like a path argument
                    return False, f"Potentially dangerous operator in command: {op}"
        
        return True, None
    
    @classmethod
    def filter_environment(
        cls,
        granted: set[str],
        whitelist: list[str] | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Filter environment variables based on granted capabilities.
        
        Args:
            granted: Granted capabilities
            whitelist: Explicit whitelist of env vars
            extra_env: Extra env vars to add
            
        Returns:
            Filtered environment dict
        """
        # If SYS_ENV not granted, use minimal environment
        if Capability.SYS_ENV not in granted:
            if platform.system() == "Windows":
                return {
                    "PATH": os.environ.get("PATH", "C:\\Windows\\system32;C:\\Windows"),
                    "TEMP": os.environ.get("TEMP", "C:\\Temp"),
                    "TMP": os.environ.get("TMP", "C:\\Temp"),
                }
            else:
                return {
                    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                    "HOME": os.environ.get("HOME", "/tmp"),
                    "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
                }
        
        # Use explicit whitelist if provided
        if whitelist:
            filtered = {}
            for key in whitelist:
                if key in os.environ:
                    filtered[key] = os.environ[key]
        else:
            # Include common safe vars
            safe_vars = {
                "PATH", "HOME", "TMPDIR", "TEMP", "TMP",
                "USER", "USERNAME", "LOGNAME",
                "LANG", "LC_ALL", "LANGUAGE",
                "PYTHONPATH", "PYTHONHOME",
            }
            filtered = {k: v for k, v in os.environ.items() if k in safe_vars}
        
        # Add extra env vars
        if extra_env:
            filtered.update(extra_env)
        
        return filtered


# =============================================================================
# SANDBOX LIMITS
# =============================================================================


class SandboxLimits:
    """Resource limits for sandboxed execution."""
    
    def __init__(self, **kwargs):
        # Memory
        self.max_memory_mb = kwargs.get("max_memory_mb", 512)
        self.max_stack_kb = kwargs.get("max_stack_kb", 8192)
        
        # CPU
        self.max_cpu_seconds = kwargs.get("max_cpu_seconds", 30.0)
        self.max_wall_seconds = kwargs.get("max_wall_seconds", 60.0)
        
        # File
        self.max_file_size_mb = kwargs.get("max_file_size_mb", 100)
        self.max_open_files = kwargs.get("max_open_files", 64)
        
        # Network
        self.max_connections = kwargs.get("max_connections", 10)
        
        # Process
        self.max_processes = kwargs.get("max_processes", 5)


# =============================================================================
# PROCESS ISOLATION SANDBOX (ENFORCED)
# =============================================================================


class ProcessIsolationSandbox:
    """Process-based isolation with HOST-ENFORCED capabilities.
    
    CRITICAL: Capability enforcement happens in the host process
    BEFORE spawning the subprocess. This prevents bypass via
    subprocess manipulation.
    
    Isolation guarantees:
    - No shared memory (fork creates copy-on-write)
    - No inherited fds (close_fds=True)
    - No inherited env vars (explicit filter)
    - Capability validation before execution
    - Resource limits via resource module (Unix)
    """
    
    def __init__(
        self,
        granted_capabilities: set[str] | None = None,
        limits: SandboxLimits | None = None,
        env_whitelist: list[str] | None = None,
        working_dir: str | None = None,
    ):
        self._granted_capabilities = granted_capabilities or set()
        self._limits = limits or SandboxLimits()
        self._env_whitelist = env_whitelist or []
        self._working_dir = working_dir
        self._process: subprocess.Popen | None = None
        self._execution_id: str | None = None
    
    @property
    def granted_capabilities(self) -> set[str]:
        """Get granted capabilities."""
        return self._granted_capabilities.copy()
    
    def set_capabilities(self, capabilities: set[str]) -> None:
        """Set granted capabilities."""
        self._granted_capabilities = capabilities.copy()
    
    def validate_capabilities(self, required: set[str]) -> tuple[bool, str | None]:
        """Validate that required capabilities are granted.
        
        This should be called BEFORE any subprocess spawning.
        """
        return CapabilityValidator.validate_request(
            required,
            self._granted_capabilities,
            trust_level=50,  # Default trust level
        )
    
    def _build_environment(self) -> dict[str, str]:
        """Build sanitized environment for subprocess."""
        return CapabilityValidator.filter_environment(
            self._granted_capabilities,
            self._env_whitelist,
        )
    
    def _apply_resource_limits(self) -> None:
        """Apply resource limits (Unix only)."""
        if platform.system() not in ("Linux", "Darwin"):
            return
        
        try:
            import resource
            
            # Memory limit
            max_mem = self._limits.max_memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (max_mem, max_mem))
            
            # CPU time limit
            max_cpu = int(self._limits.max_cpu_seconds)
            resource.setrlimit(resource.RLIMIT_CPU, (max_cpu, max_cpu + 1))
            
            # File size limit
            max_file = self._limits.max_file_size_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_FSIZE, (max_file, max_file))
            
            # Open files limit
            resource.setrlimit(
                resource.RLIMIT_NOFILE,
                (self._limits.max_open_files, self._limits.max_open_files)
            )
            
            # Process limit
            resource.setrlimit(
                resource.RLIMIT_NPROC,
                (self._limits.max_processes, self._limits.max_processes)
            )
            
            logger.debug("Applied resource limits: mem=%dMB, cpu=%ds, files=%d",
                        self._limits.max_memory_mb, self._limits.max_cpu_seconds,
                        self._limits.max_open_files)
        except (ValueError, OSError) as e:
            logger.warning("Failed to set resource limits: %s", e)
    
    async def execute(
        self,
        command: str | list[str],
        required_capabilities: set[str] | None = None,
        input_data: str | bytes | None = None,
    ) -> dict[str, Any]:
        """Execute command with isolation.
        
        Args:
            command: Command to execute
            required_capabilities: Capabilities required for this execution
            input_data: Optional stdin input
            
        Returns:
            Execution result dict
            
        Raises:
            PermissionError: If required capabilities not granted
        """
        import hashlib
        import time
        
        # Validate capabilities BEFORE spawning
        if required_capabilities:
            valid, error = self.validate_capabilities(required_capabilities)
            if not valid:
                raise PermissionError(f"Capability validation failed: {error}")
        
        # Validate command
        valid, error = CapabilityValidator.validate_command(command)
        if not valid:
            raise ValueError(f"Command validation failed: {error}")
        
        # Generate execution ID
        self._execution_id = hashlib.sha256(
            f"{os.getpid()}:{time.time()}:{command}".encode()
        ).hexdigest()[:16]
        
        # Parse command
        if isinstance(command, str):
            cmd_list = shlex.split(command)
        else:
            cmd_list = list(command)
        
        # Build environment
        env = self._build_environment()
        
        # Apply resource limits in child (via wrapper script on Unix)
        preexec_fn = None
        if platform.system() != "Windows":
            preexec_fn = self._apply_resource_limits
        
        # Create startup info for Windows
        startupinfo = None
        creationflags = 0
        if platform.system() == "Windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags = subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        
        try:
            self._process = subprocess.Popen(
                cmd_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE if input_data else subprocess.DEVNULL,
                env=env,
                cwd=self._working_dir,
                shell=False,  # Always use shell=False for security
                close_fds=True,  # Close inherited file descriptors
                startupinfo=startupinfo,
                creationflags=creationflags,
                preexec_fn=preexec_fn,
            )
            
            # Write input if provided
            if input_data is not None:
                if isinstance(input_data, str):
                    input_data = input_data.encode("utf-8")
                self._process.stdin.write(input_data)
                self._process.stdin.close()
            
            # Wait with timeout
            try:
                stdout, stderr = self._process.communicate(
                    timeout=self._limits.max_wall_seconds
                )
                exit_code = self._process.returncode
                timed_out = False
            except subprocess.TimeoutExpired:
                timed_out = True
                
                # Kill process tree
                if platform.system() == "Windows":
                    self._process.kill()
                else:
                    import signal
                    try:
                        os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    self._process.kill()
                
                stdout, stderr = self._process.communicate()
                exit_code = -1
            
            return {
                "execution_id": self._execution_id,
                "output": stdout.decode("utf-8", errors="replace") if stdout else "",
                "error": stderr.decode("utf-8", errors="replace") if stderr else "",
                "exit_code": exit_code,
                "timed_out": timed_out,
            }
            
        except Exception as e:
            logger.error("Process isolation error: %s", e)
            return {
                "execution_id": self._execution_id,
                "output": "",
                "error": str(e),
                "exit_code": -1,
                "timed_out": False,
            }
        finally:
            self._process = None
    
    def is_running(self) -> bool:
        """Check if subprocess is running."""
        return self._process is not None and self._process.poll() is None
    
    def terminate(self) -> None:
        """Terminate the subprocess."""
        if self._process is not None:
            if platform.system() == "Windows":
                self._process.kill()
            else:
                import signal
                try:
                    os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self._process = None
    
    @property
    def execution_id(self) -> str | None:
        """Get current execution ID."""
        return self._execution_id


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "ProcessIsolationSandbox",
    "Capability",
    "CapabilityValidator",
    "SandboxLimits",
]
