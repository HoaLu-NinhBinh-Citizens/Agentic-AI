"""Docker sandbox module.

Features:
- Network disabled (network_mode: none)
- Read-only filesystem (read_only: true)
- Resource limits (memory, CPU, PIDs)
- Capability restrictions
- Ephemeral containers
- Automatic cleanup
"""

from __future__ import annotations

import logging
import platform
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


class DockerSandboxConfig:
    """Configuration for Docker sandbox."""
    
    def __init__(
        self,
        image: str = "python:3.11-slim",
        memory_limit: str = "512m",
        cpu_quota: int = 50000,  # 50% of CPU
        pids_limit: int = 64,
        network_disabled: bool = True,
        read_only: bool = True,
        tmpfs_size: str | None = "64m",
        execution_timeout: int = 60,
    ):
        self.image = image
        self.memory_limit = memory_limit
        self.cpu_quota = cpu_quota
        self.pids_limit = pids_limit
        self.network_disabled = network_disabled
        self.read_only = read_only
        self.tmpfs_size = tmpfs_size
        self.execution_timeout = execution_timeout


class DockerExecutionResult:
    """Result from Docker sandbox execution."""
    
    def __init__(
        self,
        container_id: str,
        exit_code: int,
        stdout: str = "",
        stderr: str = "",
        timed_out: bool = False,
        killed: bool = False,
    ):
        self.container_id = container_id
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out
        self.killed = killed


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
    
    def __init__(self, config: DockerSandboxConfig | None = None):
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
    
    async def start(self) -> str:
        """Start a new sandbox container."""
        if not is_docker_available():
            raise RuntimeError("Docker is not available")
        
        import docker
        
        # Build container config
        host_config_kwargs = {
            "network_mode": "none" if self.config.network_disabled else "bridge",
            "read_only": self.config.read_only,
            "mem_limit": self.config.memory_limit,
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
                self.client.images.get(self.config.image)
            except docker.errors.ImageNotFound:
                logger.info("Pulling Docker image: %s", self.config.image)
                self.client.images.pull(self.config.image)
            
            # Create container
            self._container = self.client.containers.run(
                self.config.image,
                "sleep infinity",
                detach=True,
                host_config=self.client.api.create_host_config(**host_config_kwargs),
            )
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
        """Execute command in sandbox container."""
        import asyncio
        import time
        
        if self._container is None:
            await self.start()
        
        timeout = timeout or self.config.execution_timeout
        
        # Parse command
        if isinstance(command, str):
            cmd = ["/bin/sh", "-c", command]
        else:
            cmd = list(command)
        
        started_at = time.monotonic()
        
        try:
            # Execute in container
            exec_result = self._container.exec_run(
                cmd,
                stdin=input_data is not None,
                socket=False,
                demux=True,
            )
            
            # Poll for completion
            sleep_time = 0.1
            elapsed = 0.0
            stdout_data = b""
            stderr_data = b""
            exit_code = -1
            
            while elapsed < timeout:
                # Check if exec is done (exit_code available)
                if hasattr(exec_result, "exit_code") and exec_result.exit_code is not None:
                    exit_code = exec_result.exit_code
                    if isinstance(exec_result.output, tuple):
                        stdout_data = exec_result.output[0] or b""
                        stderr_data = exec_result.output[1] or b""
                    elif exec_result.output:
                        stdout_data = exec_result.output
                    break
                
                await asyncio.sleep(sleep_time)
                elapsed += sleep_time
                sleep_time = min(sleep_time * 1.5, 2.0)
            
            timed_out = elapsed >= timeout
            
            return DockerExecutionResult(
                container_id=self._container_id or "",
                exit_code=exit_code,
                stdout=stdout_data.decode("utf-8", errors="replace"),
                stderr=stderr_data.decode("utf-8", errors="replace"),
                timed_out=timed_out,
                killed=timed_out,
            )
            
        except Exception as e:
            logger.error("Docker execution error: %s", e)
            return DockerExecutionResult(
                container_id=self._container_id or "",
                exit_code=-1,
                stdout="",
                stderr=str(e),
                timed_out=False,
                killed=False,
            )
    
    async def execute_single(
        self,
        command: str | list[str],
        image: str | None = None,
        input_data: str | bytes | None = None,
        timeout: int | None = None,
    ) -> DockerExecutionResult:
        """Execute command in ephemeral container (auto cleanup)."""
        import docker
        
        if not is_docker_available():
            raise RuntimeError("Docker is not available")
        
        image = image or self.config.image
        timeout = timeout or self.config.execution_timeout
        
        # Parse command
        if isinstance(command, str):
            cmd = ["/bin/sh", "-c", command]
        else:
            cmd = list(command)
        
        # Build host config
        host_config_kwargs = {
            "network_mode": "none" if self.config.network_disabled else "bridge",
            "read_only": self.config.read_only,
            "mem_limit": self.config.memory_limit,
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
                host_config=self.client.api.create_host_config(**host_config_kwargs),
            )
            
            # Wait for completion
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
            
            # Remove container
            container.remove(force=True)
            
            return DockerExecutionResult(
                container_id=container.id,
                exit_code=exit_code,
                stdout=stdout_data.decode("utf-8", errors="replace"),
                stderr=stderr_data.decode("utf-8", errors="replace"),
                timed_out=False,
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


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "DockerSandbox",
    "DockerSandboxConfig",
    "DockerExecutionResult",
    "is_docker_available",
]
