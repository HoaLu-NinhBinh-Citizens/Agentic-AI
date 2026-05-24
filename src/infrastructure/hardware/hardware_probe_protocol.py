"""Hardware Probe Protocol - Decoupled hardware probe interface.

Fixes Critical Gap: Hardware probe manager ↔ mock defaults coupling.

Features:
- Protocol-based probe interface
- Mock probe for testing
- Real probe abstraction
- Probe registry
- Connection pooling
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# PROBE TYPES
# =============================================================================


class ProbeType(Enum):
    """Types of hardware probes."""
    
    JLink = auto()      # SEGGER J-Link
    STLink = auto()     # ST-Link
    CMSIS_DAP = auto()   # CMSIS-DAP
    PicKit = auto()     # PICkit
    Custom = auto()      # Custom probe


class ConnectionState(Enum):
    """Connection state."""
    
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class ProbeInfo:
    """Hardware probe information."""
    
    probe_id: str
    probe_type: ProbeType
    name: str
    serial_number: str = ""
    firmware_version: str = ""
    
    connection_state: ConnectionState = ConnectionState.DISCONNECTED
    connected_at: datetime | None = None
    
    # Capabilities
    supports_debug: bool = True
    supports_flash: bool = True
    supports_rtt: bool = False


# =============================================================================
# PROBE INTERFACE (PROTOCOL)
# =============================================================================


class HardwareProbe(ABC):
    """Abstract interface for hardware probes.
    
    Implement this to add support for different probe types.
    All probe operations MUST go through this interface.
    """
    
    @property
    @abstractmethod
    def probe_info(self) -> ProbeInfo:
        """Get probe information."""
        pass
    
    @abstractmethod
    async def connect(self, target_id: str) -> bool:
        """Connect to target.
        
        Args:
            target_id: Target identifier
            
        Returns:
            True if connected
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from target."""
        pass
    
    @abstractmethod
    async def read_memory(self, address: int, length: int) -> bytes:
        """Read memory.
        
        Args:
            address: Memory address
            length: Number of bytes
            
        Returns:
            Read bytes
        """
        pass
    
    @abstractmethod
    async def write_memory(self, address: int, data: bytes) -> bool:
        """Write memory.
        
        Args:
            address: Memory address
            data: Data to write
            
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    async def erase(self, address: int, length: int) -> bool:
        """Erase flash.
        
        Args:
            address: Start address
            length: Length to erase
            
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    async def reset(self) -> bool:
        """Reset target.
        
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    async def halt(self) -> bool:
        """Halt CPU.
        
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    async def resume(self) -> bool:
        """Resume CPU.
        
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    async def step(self) -> bool:
        """Single step.
        
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    async def read_register(self, register: str) -> int:
        """Read CPU register.
        
        Args:
            register: Register name (e.g., "R0", "PC", "SP")
            
        Returns:
            Register value
        """
        pass
    
    @abstractmethod
    async def write_register(self, register: str, value: int) -> bool:
        """Write CPU register.
        
        Args:
            register: Register name
            value: Value to write
            
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    async def set_breakpoint(self, address: int) -> bool:
        """Set breakpoint.
        
        Args:
            address: Breakpoint address
            
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    async def remove_breakpoint(self, address: int) -> bool:
        """Remove breakpoint.
        
        Args:
            address: Breakpoint address
            
        Returns:
            True if successful
        """
        pass


# =============================================================================
# MOCK PROBE (FOR TESTING)
# =============================================================================


class MockProbe(HardwareProbe):
    """Mock hardware probe for testing.
    
    Simulates hardware behavior without actual hardware.
    """
    
    def __init__(self, probe_id: str = "mock-001"):
        self._probe_id = probe_id
        self._info = ProbeInfo(
            probe_id=probe_id,
            probe_type=ProbeType.Custom,
            name=f"Mock Probe {probe_id}",
            serial_number="MOCK-SERIAL",
            firmware_version="1.0.0",
            supports_debug=True,
            supports_flash=True,
            supports_rtt=True,
        )
        
        self._connected = False
        self._target_id: str | None = None
        self._memory: dict[int, bytes] = {}
        self._breakpoints: set[int] = set()
    
    @property
    def probe_info(self) -> ProbeInfo:
        return self._info
    
    async def connect(self, target_id: str) -> bool:
        await asyncio.sleep(0.01)  # Simulate connection
        self._connected = True
        self._target_id = target_id
        self._info.connection_state = ConnectionState.CONNECTED
        self._info.connected_at = datetime.utcnow()
        logger.info("mock_probe_connected: probe=%s target=%s", self._probe_id, target_id)
        return True
    
    async def disconnect(self) -> None:
        self._connected = False
        self._target_id = None
        self._info.connection_state = ConnectionState.DISCONNECTED
        self._info.connected_at = None
        logger.info("mock_probe_disconnected: probe=%s", self._probe_id)
    
    async def read_memory(self, address: int, length: int) -> bytes:
        if not self._connected:
            raise RuntimeError("Not connected")
        
        if address in self._memory:
            content = self._memory[address]
            return content[:length] if len(content) >= length else content
        
        return bytes(length)
    
    async def write_memory(self, address: int, data: bytes) -> bool:
        if not self._connected:
            raise RuntimeError("Not connected")
        
        self._memory[address] = data
        return True
    
    async def erase(self, address: int, length: int) -> bool:
        if not self._connected:
            raise RuntimeError("Not connected")
        
        # Remove all memory in range
        to_remove = [addr for addr in self._memory if address <= addr < address + length]
        for addr in to_remove:
            del self._memory[addr]
        
        return True
    
    async def reset(self) -> bool:
        if not self._connected:
            raise RuntimeError("Not connected")
        
        self._memory.clear()
        self._breakpoints.clear()
        return True
    
    async def halt(self) -> bool:
        if not self._connected:
            raise RuntimeError("Not connected")
        return True
    
    async def resume(self) -> bool:
        if not self._connected:
            raise RuntimeError("Not connected")
        return True
    
    async def step(self) -> bool:
        if not self._connected:
            raise RuntimeError("Not connected")
        return True
    
    async def read_register(self, register: str) -> int:
        if not self._connected:
            raise RuntimeError("Not connected")
        return 0
    
    async def write_register(self, register: str, value: int) -> bool:
        if not self._connected:
            raise RuntimeError("Not connected")
        return True
    
    async def set_breakpoint(self, address: int) -> bool:
        if not self._connected:
            raise RuntimeError("Not connected")
        self._breakpoints.add(address)
        return True
    
    async def remove_breakpoint(self, address: int) -> bool:
        if not self._connected:
            raise RuntimeError("Not connected")
        self._breakpoints.discard(address)
        return True
    
    def inject_memory(self, address: int, data: bytes) -> None:
        """Inject memory content for testing."""
        self._memory[address] = data


# =============================================================================
# PROBE REGISTRY
# =============================================================================


class ProbeRegistry:
    """Registry for hardware probes.
    
    Manages probe lifecycle and provides probe access.
    """
    
    def __init__(self):
        self._probes: dict[str, HardwareProbe] = {}
        self._default_probe: str | None = None
        self._lock = asyncio.Lock()
    
    def register_probe(
        self,
        probe_id: str,
        probe: HardwareProbe,
        set_default: bool = False,
    ) -> None:
        """Register a probe.
        
        Args:
            probe_id: Unique probe ID
            probe: Hardware probe instance
            set_default: Set as default probe
        """
        self._probes[probe_id] = probe
        
        if set_default or self._default_probe is None:
            self._default_probe = probe_id
        
        logger.info("probe_registered: id=%s type=%s", probe_id, probe.probe_info.probe_type.name)
    
    def get_probe(self, probe_id: str | None = None) -> HardwareProbe | None:
        """Get probe by ID or default."""
        if probe_id:
            return self._probes.get(probe_id)
        if self._default_probe:
            return self._probes.get(self._default_probe)
        return None
    
    def list_probes(self) -> list[ProbeInfo]:
        """List all registered probes."""
        return [p.probe_info for p in self._probes.values()]
    
    def unregister_probe(self, probe_id: str) -> bool:
        """Unregister a probe."""
        if probe_id in self._probes:
            del self._probes[probe_id]
            if self._default_probe == probe_id:
                self._default_probe = next(iter(self._probes.keys())) if self._probes else None
            logger.info("probe_unregistered: id=%s", probe_id)
            return True
        return False


# =============================================================================
# PROBE FACTORY
# =============================================================================


class ProbeFactory:
    """Factory for creating probes.
    
    Provides dependency injection for probes.
    """
    
    _registry: ProbeRegistry | None = None
    
    @classmethod
    def get_registry(cls) -> ProbeRegistry:
        """Get global probe registry."""
        if cls._registry is None:
            cls._registry = ProbeRegistry()
        return cls._registry
    
    @classmethod
    def create_mock_probe(
        cls,
        probe_id: str = "mock-001",
        set_default: bool = False,
    ) -> MockProbe:
        """Create a mock probe for testing."""
        registry = cls.get_registry()
        probe = MockProbe(probe_id)
        registry.register_probe(probe_id, probe, set_default)
        return probe
    
    @classmethod
    async def create_real_probe(
        cls,
        probe_id: str,
        probe_type: ProbeType,
        connection_params: dict[str, Any],
        set_default: bool = False,
    ) -> HardwareProbe:
        """Create a real probe (placeholder for actual implementation).
        
        In production, this would instantiate the actual probe driver.
        """
        # Placeholder - in production, use actual probe implementations
        logger.warning("create_real_probe called - using mock implementation")
        return cls.create_mock_probe(probe_id, set_default)


# =============================================================================
# PROBE CONTEXT MANAGER
# =============================================================================


class ProbeContext:
    """Context manager for probe operations."""
    
    def __init__(self, probe: HardwareProbe, target_id: str):
        self.probe = probe
        self.target_id = target_id
        self._connected = False
    
    async def __aenter__(self) -> HardwareProbe:
        self._connected = await self.probe.connect(self.target_id)
        if not self._connected:
            raise RuntimeError(f"Failed to connect to {self.target_id}")
        return self.probe
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._connected:
            await self.probe.disconnect()


# =============================================================================
# GLOBAL INSTANCES
# =============================================================================


_global_registry: ProbeRegistry | None = None


def get_probe_registry() -> ProbeRegistry:
    """Get global probe registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ProbeRegistry()
    return _global_registry
