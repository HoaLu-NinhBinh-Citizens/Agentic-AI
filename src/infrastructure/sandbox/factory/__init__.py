"""Sandbox factory module.

Provides a unified interface for creating sandboxes based on:
- Platform (Windows, Linux, macOS)
- Available isolation mechanisms (Docker, Job Objects, etc.)
- Required isolation level
"""

from __future__ import annotations

import logging
import platform
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# SANDBOX TYPES
# =============================================================================


class SandboxType(Enum):
    """Available sandbox types."""
    DOCKER = auto()        # Docker containers
    JOB_OBJECT = auto()    # Windows Job Objects
    ISOLATED_SUBPROCESS = auto()  # Isolated subprocess with strict boundaries
    NONE = auto()          # No sandbox (for trusted code)


class IsolationLevel(Enum):
    """Isolation level for sandbox."""
    MINIMAL = auto()   # Basic subprocess isolation
    MODERATE = auto() # Resource limits + capability filtering
    STRICT = auto()   # Full isolation (Docker/Job Objects)
    HARDENED = auto() # Maximum isolation (Docker with seccomp/gVisor)


# =============================================================================
# SANDBOX CONFIGURATION
# =============================================================================


@dataclass
class SandboxConfig:
    """Configuration for sandbox factory."""
    sandbox_type: SandboxType = SandboxType.NONE
    isolation_level: IsolationLevel = IsolationLevel.MODERATE
    
    # Resource limits
    max_memory_mb: int = 512
    max_cpu_seconds: float = 30.0
    max_wall_seconds: float = 60.0
    max_processes: int = 5
    
    # Network
    network_disabled: bool = True
    
    # Capabilities
    granted_capabilities: set[str] | None = None
    env_whitelist: list[str] | None = None


# =============================================================================
# SANDBOX FACTORY
# =============================================================================


class SandboxFactory:
    """Factory for creating sandboxes with platform-aware dispatch.
    
    Single entry point for sandbox creation. Dispatches to appropriate
    isolation backend based on:
    1. Platform (Windows uses Job Objects, others use subprocess/Docker)
    2. Available mechanisms (Docker if available)
    3. Requested isolation level
    
    Usage:
        factory = SandboxFactory()
        sandbox = await factory.create()
        result = await sandbox.execute("echo hello")
    """
    
    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig()
        self._instance: Any = None
        self._platform = platform.system()
    
    def _detect_available_sandboxes(self) -> set[SandboxType]:
        """Detect which sandbox types are available on this platform."""
        available = {SandboxType.ISOLATED_SUBPROCESS}
        
        # Check Docker
        try:
            import docker
            client = docker.from_env()
            client.ping()
            available.add(SandboxType.DOCKER)
            logger.debug("Docker sandbox available")
        except Exception as e:
            logger.debug("Docker not available: %s", e)
        
        # Check Windows Job Objects
        if self._platform == "Windows":
            available.add(SandboxType.JOB_OBJECT)
            logger.debug("Windows Job Object sandbox available")
        
        return available
    
    async def create(
        self,
        sandbox_type: SandboxType | None = None,
        isolation_level: IsolationLevel | None = None,
    ) -> Any:
        """Create a sandbox instance.
        
        Args:
            sandbox_type: Specific sandbox type (auto-detected if None)
            isolation_level: Desired isolation level
            
        Returns:
            Sandbox instance
        """
        config = self.config
        if isolation_level:
            config = SandboxConfig(
                sandbox_type=config.sandbox_type,
                isolation_level=isolation_level,
                max_memory_mb=config.max_memory_mb,
                max_cpu_seconds=config.max_cpu_seconds,
                max_wall_seconds=config.max_wall_seconds,
                max_processes=config.max_processes,
                network_disabled=config.network_disabled,
                granted_capabilities=config.granted_capabilities,
                env_whitelist=config.env_whitelist,
            )
        
        # Determine sandbox type
        if sandbox_type is None:
            sandbox_type = self._determine_sandbox_type(config.isolation_level)
        
        # Validate sandbox type is available
        available = self._detect_available_sandboxes()
        if sandbox_type not in available:
            logger.warning(
                "Requested sandbox type %s not available, falling back to %s",
                sandbox_type,
                SandboxType.ISOLATED_SUBPROCESS,
            )
            sandbox_type = SandboxType.ISOLATED_SUBPROCESS
        
        # Create instance
        self._instance = self._create_instance(sandbox_type, config)
        
        logger.info(
            "Created sandbox: type=%s platform=%s",
            sandbox_type.name,
            self._platform,
        )
        
        return self._instance
    
    def _determine_sandbox_type(
        self,
        isolation_level: IsolationLevel,
    ) -> SandboxType:
        """Determine appropriate sandbox type for platform and isolation level."""
        # Check if Docker is explicitly available
        available = self._detect_available_sandboxes()
        
        if SandboxType.DOCKER in available and isolation_level >= IsolationLevel.STRICT:
            return SandboxType.DOCKER
        
        if self._platform == "Windows":
            if SandboxType.JOB_OBJECT in available:
                return SandboxType.JOB_OBJECT
            return SandboxType.ISOLATED_SUBPROCESS
        
        # Unix-like systems
        if SandboxType.DOCKER in available:
            return SandboxType.DOCKER
        
        return SandboxType.ISOLATED_SUBPROCESS
    
    def _create_instance(
        self,
        sandbox_type: SandboxType,
        config: SandboxConfig,
    ) -> Any:
        """Create sandbox instance for given type."""
        if sandbox_type == SandboxType.DOCKER:
            from .docker import DockerSandbox, DockerSandboxConfig
            
            docker_config = DockerSandboxConfig(
                memory_limit=f"{config.max_memory_mb}m",
                cpu_quota=int(100000 * (config.max_cpu_seconds / 100)),
                pids_limit=config.max_processes,
                network_disabled=config.network_disabled,
            )
            return DockerSandbox(docker_config)
        
        elif sandbox_type == SandboxType.JOB_OBJECT:
            from .windows.job_object_sandbox import JobObjectSandbox, JobObjectSandboxConfig
            
            job_config = JobObjectSandboxConfig(
                max_memory_mb=config.max_memory_mb,
                max_cpu_seconds=config.max_cpu_seconds,
                execution_timeout_seconds=config.max_wall_seconds,
                max_processes=config.max_processes,
                kill_on_job_close=True,
            )
            return JobObjectSandbox(job_config)
        
        elif sandbox_type == SandboxType.ISOLATED_SUBPROCESS:
            from .process_isolation import (
                ProcessIsolationSandbox,
                SandboxLimits,
            )
            
            limits = SandboxLimits(
                max_memory_mb=config.max_memory_mb,
                max_cpu_seconds=config.max_cpu_seconds,
                max_wall_seconds=config.max_wall_seconds,
                max_processes=config.max_processes,
            )
            
            return ProcessIsolationSandbox(
                granted_capabilities=config.granted_capabilities,
                limits=limits,
                env_whitelist=config.env_whitelist,
            )
        
        else:
            raise ValueError(f"Unknown sandbox type: {sandbox_type}")
    
    async def execute(
        self,
        command: str | list[str],
        **kwargs,
    ) -> Any:
        """Execute command in the sandbox.
        
        Convenience method that creates sandbox if needed and executes.
        """
        if self._instance is None:
            await self.create()
        
        return await self._instance.execute(command, **kwargs)
    
    def get_instance(self) -> Any:
        """Get current sandbox instance."""
        return self._instance
    
    def get_available_types(self) -> list[str]:
        """Get list of available sandbox types."""
        return [t.name for t in self._detect_available_sandboxes()]
    
    def get_platform(self) -> str:
        """Get current platform."""
        return self._platform


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


async def create_sandbox(
    isolation_level: IsolationLevel = IsolationLevel.MODERATE,
    **kwargs,
) -> Any:
    """Create a sandbox with default configuration.
    
    Args:
        isolation_level: Desired isolation level
        **kwargs: Additional config options
        
    Returns:
        Sandbox instance
    """
    config = SandboxConfig(
        isolation_level=isolation_level,
        **kwargs,
    )
    factory = SandboxFactory(config)
    return await factory.create()


async def create_docker_sandbox(**kwargs) -> Any:
    """Create a Docker sandbox."""
    factory = SandboxFactory(SandboxConfig(sandbox_type=SandboxType.DOCKER))
    return await factory.create(SandboxType.DOCKER)


async def create_job_object_sandbox(**kwargs) -> Any:
    """Create a Windows Job Object sandbox."""
    factory = SandboxFactory(SandboxConfig(sandbox_type=SandboxType.JOB_OBJECT))
    return await factory.create(SandboxType.JOB_OBJECT)


async def create_isolated_subprocess_sandbox(
    granted_capabilities: set[str] | None = None,
    **kwargs,
) -> Any:
    """Create an isolated subprocess sandbox."""
    factory = SandboxFactory(SandboxConfig(
        sandbox_type=SandboxType.ISOLATED_SUBPROCESS,
        granted_capabilities=granted_capabilities,
        **kwargs,
    ))
    return await factory.create(SandboxType.ISOLATED_SUBPROCESS)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "SandboxFactory",
    "SandboxType",
    "IsolationLevel",
    "SandboxConfig",
    "create_sandbox",
    "create_docker_sandbox",
    "create_job_object_sandbox",
    "create_isolated_subprocess_sandbox",
]
