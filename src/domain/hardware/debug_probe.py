"""Debug probe interfaces and base implementations."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

from .embedded_target import (
    DebugInterface,
    DebugProbeType,
    IDCODE,
    ProbeInterface,
    ResetMode,
)


@dataclass
class ProbeCapabilities:
    """Debug probe capabilities."""
    
    supports_swd: bool = True
    supports_jtag: bool = True
    supports_swo: bool = False
    supports_streaming_trace: bool = False
    max_breakpoints: int = 8
    max_watchpoints: int = 4
    supports_flash_patch: bool = False
    supports_rtt: bool = False  # SEGGER RTT
    supports_swo_uart: bool = False
    supports_swo_manchester: bool = False
    programmable_speed: bool = True
    min_speed_khz: int = 100
    max_speed_khz: int = 10000


@dataclass
class ProbeInfo:
    """Connected probe information."""
    
    serial: str
    probe_type: DebugProbeType
    firmware_version: str | None = None
    hardware_version: str | None = None
    capabilities: ProbeCapabilities | None = None
    idcode: IDCODE | None = None
    name: str | None = None


@dataclass
class ProbeEvent:
    """Debug probe event."""
    
    probe_serial: str
    event_type: str
    data: dict | None = None
    timestamp: float | None = None


class ProbeEventHandler:
    """Handler for probe events."""
    
    def __init__(self):
        self._handlers: dict[str, list[Callable[[ProbeEvent], None]]] = {}
    
    def register(self, event_type: str, handler: Callable[[ProbeEvent], None]) -> None:
        """Register event handler."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
    
    def emit(self, event: ProbeEvent) -> None:
        """Emit event to handlers."""
        for handler in self._handlers.get(event.event_type, []):
            handler(event)


class BaseProbe(ABC):
    """Base class for debug probes."""
    
    def __init__(
        self,
        serial: str | None = None,
        interface: DebugInterface = DebugInterface.SWD,
        speed_khz: int = 4000,
    ):
        self.serial = serial
        self.interface = interface
        self.speed_khz = speed_khz
        self._connected = False
        self._target_idcode: IDCODE | None = None
        self._event_handler = ProbeEventHandler()
    
    @property
    def is_connected(self) -> bool:
        """Check if probe is connected to target."""
        return self._connected
    
    @abstractmethod
    async def connect(self) -> IDCODE:
        """Connect to target and return IDCODE."""
        ...
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from target."""
        ...
    
    @abstractmethod
    async def reset(self, mode: ResetMode = ResetMode.HALT_AFTER_RESET) -> None:
        """Reset target."""
        ...
    
    @abstractmethod
    async def halt(self) -> None:
        """Halt target execution."""
        ...
    
    @abstractmethod
    async def resume(self) -> None:
        """Resume target execution."""
        ...
    
    @abstractmethod
    async def read_dp(self, addr: int) -> int:
        """Read debug port register."""
        ...
    
    @abstractmethod
    async def write_dp(self, addr: int, value: int) -> None:
        """Write debug port register."""
        ...
    
    @abstractmethod
    async def read_ap(self, addr: int) -> int:
        """Read access port register."""
        ...
    
    @abstractmethod
    async def write_ap(self, addr: int, value: int) -> None:
        """Write access port register."""
        ...
    
    @abstractmethod
    async def get_target_idcode(self) -> IDCODE | None:
        """Get target IDCODE."""
        ...
    
    @abstractmethod
    async def get_probe_info(self) -> ProbeInfo:
        """Get probe information."""
        ...
    
    @abstractmethod
    async def set_speed(self, speed_khz: int) -> None:
        """Set debug interface speed."""
        ...
    
    @abstractmethod
    def get_capabilities(self) -> ProbeCapabilities:
        """Get probe capabilities."""
        ...
    
    def register_event_handler(
        self,
        event_type: str,
        handler: Callable[[ProbeEvent], None],
    ) -> None:
        """Register event handler."""
        self._event_handler.register(event_type, handler)
    
    def _emit_event(self, event_type: str, data: dict | None = None) -> None:
        """Emit event."""
        event = ProbeEvent(
            probe_serial=self.serial or "",
            event_type=event_type,
            data=data,
        )
        self._event_handler.emit(event)


class JLinkProbe(BaseProbe):
    """SEGGER J-Link probe implementation."""
    
    def __init__(
        self,
        serial: str | None = None,
        interface: DebugInterface = DebugInterface.SWD,
        speed_khz: int = 4000,
    ):
        super().__init__(serial, interface, speed_khz)
        self._jlink_handle: int | None = None
    
    async def connect(self) -> IDCODE:
        """Connect to target via J-Link."""
        # Placeholder - actual implementation would use pylink library
        self._connected = True
        idcode = IDCODE(manufacturer_id=0x2B, part_id=0x1234, device_id=0, revision=0)
        self._target_idcode = idcode
        self._emit_event("connected", {"idcode": idcode.full_code})
        return idcode
    
    async def disconnect(self) -> None:
        """Disconnect from target."""
        self._connected = False
        self._jlink_handle = None
        self._emit_event("disconnected", {})
    
    async def reset(self, mode: ResetMode = ResetMode.HALT_AFTER_RESET) -> None:
        """Reset target via J-Link."""
        # J-Link-specific reset implementation
        self._emit_event("reset", {"mode": mode.value})
    
    async def halt(self) -> None:
        """Halt target."""
        self._emit_event("halted", {})
    
    async def resume(self) -> None:
        """Resume target."""
        self._emit_event("resumed", {})
    
    async def read_dp(self, addr: int) -> int:
        """Read debug port."""
        return 0
    
    async def write_dp(self, addr: int, value: int) -> None:
        """Write debug port."""
        pass
    
    async def read_ap(self, addr: int) -> int:
        """Read access port."""
        return 0
    
    async def write_ap(self, addr: int, value: int) -> None:
        """Write access port."""
        pass
    
    async def get_target_idcode(self) -> IDCODE | None:
        """Get target IDCODE."""
        return self._target_idcode
    
    async def get_probe_info(self) -> ProbeInfo:
        """Get probe information."""
        return ProbeInfo(
            serial=self.serial or "unknown",
            probe_type=DebugProbeType.JLINK,
            capabilities=self.get_capabilities(),
        )
    
    async def set_speed(self, speed_khz: int) -> None:
        """Set J-Link speed."""
        self.speed_khz = speed_khz
    
    def get_capabilities(self) -> ProbeCapabilities:
        """Get J-Link capabilities."""
        return ProbeCapabilities(
            supports_swd=True,
            supports_jtag=True,
            supports_swo=True,
            supports_streaming_trace=True,
            max_breakpoints=128,
            max_watchpoints=16,
            supports_flash_patch=True,
            supports_rtt=True,
            supports_swo_uart=True,
            supports_swo_manchester=True,
            programmable_speed=True,
            min_speed_khz=100,
            max_speed_khz=50000,
        )


class STLinkProbe(BaseProbe):
    """ST-Link probe implementation."""
    
    def __init__(
        self,
        serial: str | None = None,
        interface: DebugInterface = DebugInterface.SWD,
        speed_khz: int = 4000,
    ):
        super().__init__(serial, interface, speed_khz)
    
    async def connect(self) -> IDCODE:
        """Connect to target via ST-Link."""
        self._connected = True
        idcode = IDCODE(manufacturer_id=0x2B, part_id=0, device_id=0, revision=0)
        self._target_idcode = idcode
        self._emit_event("connected", {"idcode": idcode.full_code})
        return idcode
    
    async def disconnect(self) -> None:
        """Disconnect from target."""
        self._connected = False
        self._emit_event("disconnected", {})
    
    async def reset(self, mode: ResetMode = ResetMode.HALT_AFTER_RESET) -> None:
        """Reset target via ST-Link."""
        self._emit_event("reset", {"mode": mode.value})
    
    async def halt(self) -> None:
        """Halt target."""
        self._emit_event("halted", {})
    
    async def resume(self) -> None:
        """Resume target."""
        self._emit_event("resumed", {})
    
    async def read_dp(self, addr: int) -> int:
        """Read debug port."""
        return 0
    
    async def write_dp(self, addr: int, value: int) -> None:
        """Write debug port."""
        pass
    
    async def read_ap(self, addr: int) -> int:
        """Read access port."""
        return 0
    
    async def write_ap(self, addr: int, value: int) -> None:
        """Write access port."""
        pass
    
    async def get_target_idcode(self) -> IDCODE | None:
        """Get target IDCODE."""
        return self._target_idcode
    
    async def get_probe_info(self) -> ProbeInfo:
        """Get probe information."""
        return ProbeInfo(
            serial=self.serial or "unknown",
            probe_type=DebugProbeType.STLINK,
            capabilities=self.get_capabilities(),
        )
    
    async def set_speed(self, speed_khz: int) -> None:
        """Set ST-Link speed."""
        self.speed_khz = speed_khz
    
    def get_capabilities(self) -> ProbeCapabilities:
        """Get ST-Link capabilities."""
        return ProbeCapabilities(
            supports_swd=True,
            supports_jtag=True,
            supports_swo=True,
            supports_streaming_trace=False,
            max_breakpoints=8,
            max_watchpoints=4,
            supports_flash_patch=False,
            supports_rtt=False,
            supports_swo_uart=True,
            supports_swo_manchester=False,
            programmable_speed=True,
            min_speed_khz=125,
            max_speed_khz=8000,
        )


class CMSISDAPProbe(BaseProbe):
    """CMSIS-DAP probe implementation."""
    
    def __init__(
        self,
        serial: str | None = None,
        interface: DebugInterface = DebugInterface.SWD,
        speed_khz: int = 4000,
    ):
        super().__init__(serial, interface, speed_khz)
    
    async def connect(self) -> IDCODE:
        """Connect to target via CMSIS-DAP."""
        self._connected = True
        idcode = IDCODE(manufacturer_id=0, part_id=0, device_id=0, revision=0)
        self._target_idcode = idcode
        self._emit_event("connected", {"idcode": idcode.full_code})
        return idcode
    
    async def disconnect(self) -> None:
        """Disconnect from target."""
        self._connected = False
        self._emit_event("disconnected", {})
    
    async def reset(self, mode: ResetMode = ResetMode.HALT_AFTER_RESET) -> None:
        """Reset target via CMSIS-DAP."""
        self._emit_event("reset", {"mode": mode.value})
    
    async def halt(self) -> None:
        """Halt target."""
        self._emit_event("halted", {})
    
    async def resume(self) -> None:
        """Resume target."""
        self._emit_event("resumed", {})
    
    async def read_dp(self, addr: int) -> int:
        """Read debug port."""
        return 0
    
    async def write_dp(self, addr: int, value: int) -> None:
        """Write debug port."""
        pass
    
    async def read_ap(self, addr: int) -> int:
        """Read access port."""
        return 0
    
    async def write_ap(self, addr: int, value: int) -> None:
        """Write access port."""
        pass
    
    async def get_target_idcode(self) -> IDCODE | None:
        """Get target IDCODE."""
        return self._target_idcode
    
    async def get_probe_info(self) -> ProbeInfo:
        """Get probe information."""
        return ProbeInfo(
            serial=self.serial or "unknown",
            probe_type=DebugProbeType.CMSIS_DAP,
            capabilities=self.get_capabilities(),
        )
    
    async def set_speed(self, speed_khz: int) -> None:
        """Set CMSIS-DAP speed."""
        self.speed_khz = speed_khz
    
    def get_capabilities(self) -> ProbeCapabilities:
        """Get CMSIS-DAP capabilities."""
        return ProbeCapabilities(
            supports_swd=True,
            supports_jtag=True,
            supports_swo=False,
            supports_streaming_trace=False,
            max_breakpoints=8,
            max_watchpoints=4,
            supports_flash_patch=False,
            supports_rtt=False,
            supports_swo_uart=False,
            supports_swo_manchester=False,
            programmable_speed=True,
            min_speed_khz=100,
            max_speed_khz=10000,
        )


class QEMUProbe(BaseProbe):
    """QEMU emulator probe (for testing)."""
    
    def __init__(self, machine: str = "vexpress-a9"):
        super().__init__(serial="qemu", interface=DebugInterface.SWD, speed_khz=10000)
        self.machine = machine
        self._gdb_port = 1234
    
    async def connect(self) -> IDCODE:
        """Connect to QEMU gdbserver."""
        self._connected = True
        idcode = IDCODE(manufacturer_id=0x41, part_id=0x0A15, device_id=0, revision=0)
        self._target_idcode = idcode
        return idcode
    
    async def disconnect(self) -> None:
        """Disconnect from QEMU."""
        self._connected = False
    
    async def reset(self, mode: ResetMode = ResetMode.HALT_AFTER_RESET) -> None:
        """Reset QEMU."""
        pass
    
    async def halt(self) -> None:
        """Halt QEMU."""
        pass
    
    async def resume(self) -> None:
        """Resume QEMU."""
        pass
    
    async def read_dp(self, addr: int) -> int:
        """Read debug port."""
        return 0
    
    async def write_dp(self, addr: int, value: int) -> None:
        """Write debug port."""
        pass
    
    async def read_ap(self, addr: int) -> int:
        """Read access port."""
        return 0
    
    async def write_ap(self, addr: int, value: int) -> None:
        """Write access port."""
        pass
    
    async def get_target_idcode(self) -> IDCODE | None:
        """Get target IDCODE."""
        return self._target_idcode
    
    async def get_probe_info(self) -> ProbeInfo:
        """Get probe information."""
        return ProbeInfo(
            serial=f"qemu:{self.machine}",
            probe_type=DebugProbeType.QEMU,
            capabilities=self.get_capabilities(),
        )
    
    async def set_speed(self, speed_khz: int) -> None:
        """Set speed (no-op for QEMU)."""
        pass
    
    def get_capabilities(self) -> ProbeCapabilities:
        """Get QEMU capabilities."""
        return ProbeCapabilities(
            supports_swd=True,
            supports_jtag=True,
            supports_swo=False,
            supports_streaming_trace=False,
            max_breakpoints=256,
            max_watchpoints=256,
            supports_flash_patch=True,
            supports_rtt=False,
            programmable_speed=False,
            min_speed_khz=10000,
            max_speed_khz=10000,
        )


def create_probe(
    probe_type: DebugProbeType,
    serial: str | None = None,
    interface: DebugInterface = DebugInterface.SWD,
    speed_khz: int = 4000,
) -> BaseProbe:
    """Factory function to create probe instances."""
    probes: dict[DebugProbeType, type[BaseProbe]] = {
        DebugProbeType.JLINK: JLinkProbe,
        DebugProbeType.STLINK: STLinkProbe,
        DebugProbeType.CMSIS_DAP: CMSISDAPProbe,
        DebugProbeType.QEMU: QEMUProbe,
        DebugProbeType.OPENOCD: CMSISDAPProbe,  # OpenOCD uses CMSIS-DAP
        DebugProbeType.pyOCD: CMSISDAPProbe,  # pyOCD uses CMSIS-DAP
    }
    
    probe_class = probes.get(probe_type, CMSISDAPProbe)
    return probe_class(serial=serial, interface=interface, speed_khz=speed_khz)
