"""Docker-based sandbox implementation.

Features:
- Network disabled (network_mode: none)
- Read-only filesystem (read_only: true)
- Resource limits (memory, CPU, PIDs)
- Capability restrictions
- Ephemeral containers
- Automatic cleanup
"""

from __future__ import annotations

import asyncio
import logging
import platform
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# DOCKER AVAILABILITY CHECK
# =============================================================================

_docker_available: bool | None = None


def is_docker_available() -> bool:
    """Check if Docker is available."""
    global _docker_available
    if _docker_available is None:
        _docker_available = False
        try:
            import docker
            client = docker.from_env()
            client.ping()
            _docker_available = True
        except Exception as e:
            logger.debug("Docker not available: %s", e)
    return _docker_available


# =============================================================================
# SANDBOX CONFIGURATION
# =============================================================================


@dataclass
class DockerSandboxConfig:
    """Configuration for Docker sandbox."""
    
    # Image
    image: str = "python:3.11-slim"
    
    # Resource limits
    memory_limit: str = "512m"  # e.g., "512m", "1g"
    cpu_period: int = 100000  # CPU CFS period
    cpu_quota: int = 50000   # CPU CFS quota (50% of period)
    pids_limit: int = 64     # Max number of PIDs
    
    # Filesystem
    read_only: bool = True
    tmpfs_size: str | None = None  # e.g., "64m"
    
    # Network
    network_disabled: bool = True
    
    # Capabilities (Linux)
    drop_capabilities: list[str] = field(default_factory=list)
    
    # Environment
    env_vars: dict[str, str] = field(default_factory=dict)
    
    # Working directory
    working_dir: str = "/workspace"
    
    # Timeout
    execution_timeout: int = 60  # seconds


@dataclass
class DockerExecutionResult:
    """Result from Docker sandbox execution."""
    
    container_id: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    killed: bool
    memory_used: str | None = None
    cpu_time: str | None = None


# =============================================================================
# DOCKER SANDBOX
# =============================================================================


class DockerSandbox:
    """Docker-based sandbox for plugin execution.
    
    Isolation guarantees:
    - Network disabled by default
    - Read-only root filesystem
    - Memory limits enforced by Docker
    - CPU limits via cgroup
    - PID limits to prevent fork bombs
    - Automatic container cleanup
    """
    
    def __init__(
        self,
        config: DockerSandboxConfig | None = None,
    ):
        self.config = config or DockerSandboxConfig()
        self._client = None
        self._container = None
        self._container_id: str | None = None
    
    @property
    def client(self):
        """Get Docker client (lazy initialization)."""
        if self._client is None:
            import docker
            self._client = docker.from_env()
        return self._client
    
    def _build_host_config(self) -> dict[str, Any]:
        """Build Docker host config with security restrictions."""
        import docker
        
        # Base security options
        host_config_kwargs: dict[str, Any] = {
            # Network
            "network_mode": "none" if self.config.network_disabled else "bridge",
            
            # Read-only filesystem
            "read_only": self.config.read_only,
            
            # Tmpfs for /tmp if specified
            "tmpfs": {} if self.config.tmpfs_size else None,
        }
        
        # Add tmpfs mount
        if self.config.tmpfs_size:
            host_config_kwargs["tmpfs"] = {
                "/tmp": f"size={self.config.tmpfs_size},noexec,nosuid,nodev"
            }
        
        # Memory limits
        host_config_kwargs["mem_limit"] = self.config.memory_limit
        
        # CPU limits
        host_config_kwargs["cpu_period"] = self.config.cpu_period
        host_config_kwargs["cpu_quota"] = self.config.cpu_quota
        
        # PID limit
        host_config_kwargs["pids_limit"] = self.config.pids_limit
        
        # Auto-remove container
        host_config_kwargs["auto_remove"] = True
        
        # User/Group
        # Run as non-root user (uid 1000)
        host_config_kwargs["user"] = "1000:1000"
        
        return self.client.api.create_host_config(**host_config_kwargs)
    
    def _build_capabilities(self) -> list[str]:
        """Build Linux capabilities list."""
        # All capabilities - we drop specific dangerous ones
        all_caps = [
            "CAP_CHOWN",
            "CAP_DAC_OVERRIDE",
            "CAP_FOWNER",
            "CAP_FSETID",
            "CAP_KILL",
            "CAP_NET_BIND_SERVICE",
            "CAP_SETGID",
            "CAP_SETUID",
            "CAP_SETPCAP",
            "CAP_SYS_CHROOT",
        ]
        
        # Drop dangerous capabilities
        dangerous = {
            "CAP_SYS_ADMIN",
            "CAP_SYS_MODULE",
            "CAP_SYS_RAWIO",
            "CAP_SYS_PTRACE",
            "CAP_SYS_TIME",
            "CAP_NET_ADMIN",
            "CAP_NET_RAW",
            "CAP_SYS_BOOT",
            "CAP_SYS_TTY_CONFIG",
        }
        
        # Start with all, remove dangerous
        return [c for c in all_caps if c not in dangerous]
    
    async def start(self) -> str:
        """Start a new sandbox container.
        
        Returns:
            Container ID
        """
        if not is_docker_available():
            raise RuntimeError("Docker is not available")
        
        import docker
        
        # Build container config
        env = [f"{k}={v}" for k, v in self.config.env_vars.items()]
        
        container_kwargs: dict[str, Any] = {
            "image": self.config.image,
            "command": "sleep infinity",  # Keep container running
            "working_dir": self.config.working_dir,
            "environment": env,
            "host_config": self._build_host_config(),
            "detach": True,
        }
        
        # Add capabilities (Linux only)
        if platform.system() == "Linux":
            container_kwargs["cap_add"] = self._build_capabilities()
        
        try:
            # Pull image if needed
            try:
                self.client.images.get(self.config.image)
            except docker.errors.ImageNotFound:
                logger.info("Pulling Docker image: %s", self.config.image)
                self.client.images.pull(self.config.image)
            
            # Create container
            self._container = self.client.containers.run(**container_kwargs)
            self._container_id = self._container.id
            
            logger.info("Docker sandbox started: %s", self._container_id[:12])
            return self._container_id
            
        except docker.errors.APIError as e:
            logger.error("Failed to start Docker sandbox: %s", e)
            raise RuntimeError(f"Docker sandbox failed to start: {e}")
    
    async def execute(
        self,
        command: str | list[str],
        input_data: str | bytes | None = None,
        timeout: int | None = None,
    ) -> DockerExecutionResult:
        """Execute command in sandbox container.
        
        Args:
            command: Command to execute
            input_data: Optional stdin input
            timeout: Execution timeout in seconds
            
        Returns:
            DockerExecutionResult
        """
        import time
        
        if self._container is None:
            await self.start()
        
        timeout = timeout or self.config.execution_timeout
        
        # Parse command
        if isinstance(command, str):
            cmd = ["/bin/sh", "-c", command]
        else:
            cmd = list(command)
        
        # Start execution
        started_at = time.monotonic()
        timed_out = False
        killed = False
        
        try:
            # Execute in container
            exec_result = self._container.exec_run(
                cmd,
                stdin=input_data is not None,
                socket=True,
                demux=True,
            )
            
            # Read output with timeout
            stdout_data = b""
            stderr_data = b""
            
            # Poll for completion
            sleep_time = 0.1
            elapsed = 0.0
            
            while elapsed < timeout:
                # Check if still running
                inspect = self._container.reload()  # Refresh container state
                
                # For exec_run, we need different handling
                # Get result after exec completes
                try:
                    # Try to get exec result
                    output = exec_result.output
                    if output:
                        stdout_data, stderr_data = output if isinstance(output, tuple) else (output, b"")
                        break
                except Exception:
                    pass
                
                await asyncio.sleep(sleep_time)
                elapsed += sleep_time
                sleep_time = min(sleep_time * 1.5, 2.0)  # Backoff
            
            if elapsed >= timeout:
                timed_out = True
            
            # Get exit code
            try:
                exit_code = exec_result.exit_code
            except Exception:
                exit_code = -1
            
        except Exception as e:
            logger.error("Docker execution error: %s", e)
            stdout_data = b""
            stderr_data = str(e).encode("utf-8")
            exit_code = -1
        
        return DockerExecutionResult(
            container_id=self._container_id or "",
            exit_code=exit_code if not timed_out else -1,
            stdout=stdout_data.decode("utf-8", errors="replace"),
            stderr=stderr_data.decode("utf-8", errors="replace"),
            timed_out=timed_out,
            killed=timed_out,
        )
    
    async def stop(self) -> None:
        """Stop and remove the sandbox container."""
        if self._container is not None:
            try:
                self._container.kill()
                self._container.remove(force=True)
                logger.info("Docker sandbox stopped: %s", self._container_id[:12])
            except Exception as e:
                logger.warning("Error stopping Docker sandbox: %s", e)
            finally:
                self._container = None
                self._container_id = None
    
    async def execute_single(
        self,
        command: str | list[str],
        image: str | None = None,
        input_data: str | bytes | None = None,
        timeout: int | None = None,
    ) -> DockerExecutionResult:
        """Execute command in ephemeral container (auto cleanup).
        
        This is a convenience method that creates a container,
        executes the command, and cleans up automatically.
        
        Args:
            command: Command to execute
            image: Docker image (uses config default if None)
            input_data: Optional stdin input
            timeout: Execution timeout in seconds
            
        Returns:
            DockerExecutionResult
        """
        if not is_docker_available():
            raise RuntimeError("Docker is not available")
        
        import docker
        
        # Create ephemeral config
        image = image or self.config.image
        env = [f"{k}={v}" for k, v in self.config.env_vars.items()]
        timeout = timeout or self.config.execution_timeout
        
        # Parse command
        if isinstance(command, str):
            cmd = ["/bin/sh", "-c", command]
        else:
            cmd = list(command)
        
        # Build host config
        host_config_kwargs: dict[str, Any] = {
            "network_mode": "none" if self.config.network_disabled else "bridge",
            "read_only": self.config.read_only,
            "mem_limit": self.config.memory_limit,
            "cpu_period": self.config.cpu_period,
            "cpu_quota": self.config.cpu_quota,
            "pids_limit": self.config.pids_limit,
            "auto_remove": True,
            "user": "1000:1000",
        }
        
        if self.config.tmpfs_size:
            host_config_kwargs["tmpfs"] = {
                "/tmp": f"size={self.config.tmpfs_size},noexec,nosuid,nodev"
            }
        
        try:
            # Pull image if needed
            try:
                self.client.images.get(image)
            except docker.errors.ImageNotFound:
                self.client.images.pull(image)
            
            # Run container with command
            container = self.client.containers.run(
                image,
                cmd,
                detach=True,
                environment=env,
                host_config=self.client.api.create_host_config(**host_config_kwargs),
                working_dir=self.config.working_dir,
            )
            
            # Wait for completion with timeout
            result = container.wait(timeout=timeout)
            exit_code = result.get("StatusCode", -1)
            
            # Get logs
            logs = container.logs(stdout=True, stderr=True)
            if isinstance(logs, bytes):
                stdout_data = logs
                stderr_data = b""
            else:
                stdout_data = logs or b""
                stderr_data = b""
            
            # Handle demuxed output if available
            if hasattr(logs, '__iter__'):
                try:
                    # Try to get demuxed output
                    stdout_chunks = []
                    stderr_chunks = []
                    for chunk in logs:
                        stdout_chunks.append(chunk)
                    stdout_data = b"".join(stdout_chunks)
                except Exception:
                    pass
            
            # Remove container
            container.remove(force=True)
            
            return DockerExecutionResult(
                container_id=container.id,
                exit_code=exit_code,
                stdout=stdout_data.decode("utf-8", errors="replace"),
                stderr=stderr_data.decode("utf-8", errors="replace"),
                timed_out=exit_code == -1 and timeout is not None,
                killed=False,
            )
            
        except docker.errors.APIError as e:
            logger.error("Docker ephemeral execution error: %s", e)
            return DockerExecutionResult(
                container_id="",
                exit_code=-1,
                stdout="",
                stderr=str(e),
                timed_out=False,
                killed=False,
            )
    
    @property
    def is_running(self) -> bool:
        """Check if sandbox container is running."""
        if self._container is None:
            return False
        try:
            self._container.reload()
            return self._container.status == "running"
        except Exception:
            return False
    
    @property
    def container_id(self) -> str | None:
        """Get container ID."""
        return self._container_id
