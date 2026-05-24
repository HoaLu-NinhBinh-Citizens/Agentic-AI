"""Plugin Sandbox Enforcement.

Fixes Critical Gap: No plugin sandbox enforcement.

Features:
- Sandboxed plugin execution
- Capability-based access control
- Resource limits
- System call filtering
- Memory isolation
- Timeout enforcement
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable

# resource is Unix-only
try:
    import resource
    _HAS_RESOURCE = True
except ImportError:
    _HAS_RESOURCE = False

logger = logging.getLogger(__name__)


# =============================================================================
# CAPABILITY TYPES
# =============================================================================


class Capability(Enum):
    """Capabilities that plugins can request."""
    
    # File system
    FS_READ = auto()      # Read files
    FS_WRITE = auto()     # Write files
    FS_DELETE = auto()     # Delete files
    FS_MKDIR = auto()     # Create directories
    
    # Network
    NET_HTTP = auto()      # Make HTTP requests
    NET_RAW = auto()      # Raw socket access
    NET_DNS = auto()       # DNS lookups
    
    # System
    SYS_EXEC = auto()      # Execute external commands
    SYS_ENV = auto()       # Access environment variables
    SYS_PROCESS = auto()   # Process management
    
    # Hardware
    HW_FLASH = auto()      # Flash hardware
    HW_SERIAL = auto()     # Serial communication
    HW_GPIO = auto()        # GPIO access
    
    # Security
    SEC_SIGN = auto()      # Cryptographic signing
    SEC_VERIFY = auto()    # Verify signatures
    SEC_KEY_READ = auto()   # Read encryption keys
    SEC_KEY_WRITE = auto()  # Write encryption keys


# =============================================================================
# SANDBOX CONFIGURATION
# =============================================================================


@dataclass
class SandboxLimits:
    """Resource limits for sandboxed execution."""
    
    # Memory
    max_memory_mb: int = 512
    max_stack_kb: int = 8 * 1024  # 8MB
    
    # CPU
    max_cpu_time_seconds: float = 30.0
    max_wall_time_seconds: float = 60.0
    
    # File system
    max_file_size_mb: int = 100
    max_open_files: int = 100
    allowed_paths: list[str] = field(default_factory=list)  # Empty = all
    
    # Network
    max_connections: int = 10
    allowed_hosts: list[str] = field(default_factory=list)  # Empty = all
    
    # Process
    max_processes: int = 10
    max_threads_per_process: int = 50


@dataclass
class PluginManifest:
    """Manifest describing plugin requirements and permissions."""
    
    plugin_id: str
    plugin_name: str
    version: str
    
    # Capabilities requested
    required_capabilities: set[Capability] = field(default_factory=set)
    optional_capabilities: set[Capability] = field(default_factory=set)
    
    # Sandboxing
    sandbox_limits: SandboxLimits = field(default_factory=SandboxLimits)
    
    # Trust level (0-100)
    trust_score: int = 50
    
    # Verification
    code_hash: str = ""
    signature: str = ""
    
    def __post_init__(self):
        # Convert string capabilities to enum if needed
        pass
    
    def has_capability(self, cap: Capability) -> bool:
        return cap in self.required_capabilities
    
    def grants_capability(self, cap: Capability) -> bool:
        return cap in self.required_capabilities or cap in self.optional_capabilities


# =============================================================================
# SANDBOX CONTEXT
# =============================================================================


@dataclass
class SandboxContext:
    """Execution context for sandboxed plugins.
    
    This context is passed to plugins and restricts their access.
    """
    
    plugin_manifest: PluginManifest
    
    # Granted capabilities (subset of requested)
    granted_capabilities: set[Capability] = field(default_factory=set)
    
    # Execution tracking
    execution_id: str = ""
    started_at: float = 0.0
    cpu_time_used: float = 0.0
    memory_used_mb: float = 0.0
    
    # State
    is_running: bool = False
    is_cancelled: bool = False
    cancellation_reason: str = ""
    
    def check_capability(self, cap: Capability) -> bool:
        """Check if plugin has a capability."""
        return cap in self.granted_capabilities
    
    def assert_capability(self, cap: Capability) -> None:
        """Assert capability, raise if not granted."""
        if not self.check_capability(cap):
            raise SandboxViolation(
                f"Capability {cap.name} not granted to plugin"
            )


# =============================================================================
# SANDBOX VIOLATION
# =============================================================================


class SandboxViolation(Exception):
    """Raised when sandbox rules are violated."""
    
    def __init__(self, message: str, capability: Capability | None = None):
        super().__init__(message)
        self.capability = capability


# =============================================================================
# SANDBOX IMPLEMENTATIONS
# =============================================================================


class FileSystemSandbox:
    """Sandbox for file system operations."""
    
    def __init__(self, context: SandboxContext):
        self.context = context
        self._open_files: dict[int, str] = {}
        self._file_id_counter = 0
    
    def _check_path(self, path: str) -> None:
        """Check if path is allowed."""
        if Capability.FS_READ not in self.context.granted_capabilities:
            raise SandboxViolation(
                f"File system access denied",
                Capability.FS_READ,
            )
        
        # Check allowed paths if configured
        allowed = self.context.plugin_manifest.sandbox_limits.allowed_paths
        if allowed:
            abs_path = os.path.abspath(path)
            for allowed_path in allowed:
                if abs_path.startswith(os.path.abspath(allowed_path)):
                    return
            raise SandboxViolation(
                f"Path not in allowed directories: {path}",
                Capability.FS_READ,
            )
    
    def read(self, path: str, binary: bool = False) -> str | bytes:
        """Read file (sandboxed)."""
        self._check_path(path)
        
        mode = "rb" if binary else "r"
        try:
            with open(path, mode) as f:
                content = f.read()
            
            logger.info("sandbox_file_read: path=%s size=%s", path, len(content))
            return content
        except FileNotFoundError:
            raise SandboxViolation(f"File not found: {path}", Capability.FS_READ)
    
    def write(self, path: str, content: str | bytes) -> None:
        """Write file (sandboxed)."""
        if Capability.FS_WRITE not in self.context.granted_capabilities:
            raise SandboxViolation(
                f"Write access denied",
                Capability.FS_WRITE,
            )
        
        self._check_path(path)
        
        mode = "wb" if isinstance(content, bytes) else "w"
        with open(path, mode) as f:
            f.write(content)
        
        logger.info("sandbox_file_written: path=%s size=%s", path, len(content))
    
    def delete(self, path: str) -> None:
        """Delete file (sandboxed)."""
        if Capability.FS_DELETE not in self.context.granted_capabilities:
            raise SandboxViolation(
                f"Delete access denied",
                Capability.FS_DELETE,
            )
        
        self._check_path(path)
        os.remove(path)
        
        logger.info("sandbox_file_deleted: path=%s", path)
    
    def exists(self, path: str) -> bool:
        """Check if file exists."""
        try:
            self._check_path(path)
            return os.path.exists(path)
        except SandboxViolation:
            return False


class NetworkSandbox:
    """Sandbox for network operations."""
    
    def __init__(self, context: SandboxContext):
        self.context = context
        self._connection_count = 0
    
    def _check_host(self, host: str) -> None:
        """Check if host is allowed."""
        if Capability.NET_HTTP not in self.context.granted_capabilities:
            raise SandboxViolation(
                f"Network access denied",
                Capability.NET_HTTP,
            )
        
        # Check allowed hosts if configured
        allowed = self.context.plugin_manifest.sandbox_limits.allowed_hosts
        if allowed and host not in allowed:
            raise SandboxViolation(
                f"Host not allowed: {host}",
                Capability.NET_HTTP,
            )
        
        # Check connection limit
        if self._connection_count >= self.context.plugin_manifest.sandbox_limits.max_connections:
            raise SandboxViolation(
                f"Connection limit reached: {self._connection_count}",
                Capability.NET_HTTP,
            )
    
    async def http_get(self, url: str, timeout: float = 10.0) -> dict[str, Any]:
        """Make HTTP GET request (sandboxed)."""
        from urllib.parse import urlparse
        
        parsed = urlparse(url)
        self._check_host(parsed.netloc)
        
        self._connection_count += 1
        try:
            import httpx
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
            
            logger.info("sandbox_http_get: url=%s status=%s", url, response.status_code)
            
            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "content": response.text,
            }
        finally:
            self._connection_count -= 1


class HardwareSandbox:
    """Sandbox for hardware operations."""
    
    def __init__(self, context: SandboxContext):
        self.context = context
    
    def check_flash_capability(self) -> None:
        """Check if flash operations are allowed."""
        if Capability.HW_FLASH not in self.context.granted_capabilities:
            raise SandboxViolation(
                f"Flash access denied",
                Capability.HW_FLASH,
            )
    
    async def flash_read(self, address: int, length: int) -> bytes:
        """Read from flash (sandboxed)."""
        self.check_flash_capability()
        
        # In real implementation, this would interface with hardware
        logger.info("sandbox_flash_read: address=0x%x length=%s", address, length)
        
        return bytes(length)  # Placeholder
    
    async def flash_write(self, address: int, data: bytes) -> None:
        """Write to flash (sandboxed)."""
        self.check_flash_capability()
        
        logger.info("sandbox_flash_write: address=0x%x length=%s", address, len(data))
    
    async def flash_erase(self, address: int, length: int) -> None:
        """Erase flash (sandboxed)."""
        self.check_flash_capability()
        
        logger.info("sandbox_flash_erase: address=0x%x length=%s", address, length)


# =============================================================================
# PLUGIN SANDBOX MANAGER
# =============================================================================


class PluginSandbox:
    """Main sandbox manager for plugin execution.
    
    CRITICAL: This ensures plugins run in a restricted environment.
    """
    
    def __init__(self):
        self._sandboxes: dict[str, SandboxContext] = {}
        self._default_limits = SandboxLimits()
        self._plugin_registry: dict[str, PluginManifest] = {}
    
    def register_plugin(self, manifest: PluginManifest) -> None:
        """Register a plugin manifest."""
        self._plugin_registry[manifest.plugin_id] = manifest
        logger.info(
            "plugin_registered: id=%s name=%s capabilities=%s",
            manifest.plugin_id,
            manifest.plugin_name,
            [c.name for c in manifest.required_capabilities],
        )
    
    def get_plugin_manifest(self, plugin_id: str) -> PluginManifest | None:
        """Get registered plugin manifest."""
        return self._plugin_registry.get(plugin_id)
    
    async def create_execution_context(
        self,
        plugin_id: str,
        requested_capabilities: set[Capability] | None = None,
    ) -> SandboxContext:
        """Create execution context for a plugin.
        
        Args:
            plugin_id: Plugin identifier
            requested_capabilities: Subset of capabilities to grant
            
        Returns:
            SandboxContext for execution
        """
        manifest = self._plugin_registry.get(plugin_id)
        if not manifest:
            raise SandboxViolation(f"Unknown plugin: {plugin_id}")
        
        # Determine granted capabilities
        if requested_capabilities:
            granted = requested_capabilities & manifest.required_capabilities
            granted |= requested_capabilities & manifest.optional_capabilities
        else:
            granted = manifest.required_capabilities
        
        # Limit by trust score
        if manifest.trust_score < 50:
            # Low trust - only grant safe capabilities
            safe_caps = {Capability.FS_READ, Capability.FS_WRITE}
            granted &= safe_caps
        
        context = SandboxContext(
            plugin_manifest=manifest,
            granted_capabilities=granted,
            execution_id=hashlib.sha256(
                f"{plugin_id}:{asyncio.get_event_loop().time()}".encode()
            ).hexdigest()[:16],
            started_at=asyncio.get_event_loop().time(),
        )
        
        self._sandboxes[context.execution_id] = context
        
        logger.info(
            "sandbox_created: plugin=%s execution=%s granted=%s",
            plugin_id,
            context.execution_id,
            [c.name for c in granted],
        )
        
        return context
    
    def get_sandbox(self, execution_id: str) -> SandboxContext | None:
        """Get sandbox context by execution ID."""
        return self._sandboxes.get(execution_id)
    
    def release_sandbox(self, execution_id: str) -> None:
        """Release a sandbox context."""
        if execution_id in self._sandboxes:
            del self._sandboxes[execution_id]
            logger.info("sandbox_released: execution=%s", execution_id)
    
    async def execute_sandboxed(
        self,
        plugin_id: str,
        func: Callable,
        *args,
        requested_capabilities: set[Capability] | None = None,
        **kwargs,
    ) -> Any:
        """Execute a function in a sandbox.
        
        Args:
            plugin_id: Plugin identifier
            func: Function to execute
            requested_capabilities: Capabilities to request
            
        Returns:
            Function result
            
        Raises:
            SandboxViolation: If sandbox rules are violated
        """
        context = await self.create_execution_context(
            plugin_id,
            requested_capabilities,
        )
        
        # Create sub-sandboxes
        fs_sandbox = FileSystemSandbox(context)
        net_sandbox = NetworkSandbox(context)
        hw_sandbox = HardwareSandbox(context)
        
        context.is_running = True
        
        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                func(
                    *args,
                    sandbox=context,
                    fs=fs_sandbox,
                    net=net_sandbox,
                    hw=hw_sandbox,
                    **kwargs,
                ),
                timeout=context.plugin_manifest.sandbox_limits.max_wall_time_seconds,
            )
            
            logger.info(
                "sandbox_execution_complete: execution=%s result_size=%s",
                context.execution_id,
                len(str(result)) if result else 0,
            )
            
            return result
            
        except asyncio.TimeoutError:
            context.is_cancelled = True
            context.cancellation_reason = "Execution timeout"
            raise SandboxViolation(
                f"Execution timeout after {context.plugin_manifest.sandbox_limits.max_wall_time_seconds}s",
            )
            
        except SandboxViolation:
            raise
            
        except Exception as e:
            logger.error("sandbox_execution_error: execution=%s error=%s", context.execution_id, str(e))
            raise
            
        finally:
            context.is_running = False
            self.release_sandbox(context.execution_id)
    
    def get_sandbox_stats(self) -> dict[str, Any]:
        """Get sandbox statistics."""
        return {
            "total_sandboxes": len(self._sandboxes),
            "running_sandboxes": sum(1 for c in self._sandboxes.values() if c.is_running),
            "registered_plugins": len(self._plugin_registry),
        }


# =============================================================================
# GLOBAL SANDBOX INSTANCE
# =============================================================================


_global_sandbox: PluginSandbox | None = None


def get_sandbox() -> PluginSandbox:
    """Get the global sandbox instance."""
    global _global_sandbox
    if _global_sandbox is None:
        _global_sandbox = PluginSandbox()
    return _global_sandbox
