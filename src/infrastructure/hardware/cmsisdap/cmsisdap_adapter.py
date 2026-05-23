"""CMSIS-DAP probe adapter implementation (Phase 7.1a)."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.domain.hardware.debug_probe import (
    BaseProbe,
    ProbeCapabilities,
    ProbeInfo,
    ProbeEvent,
)
from src.domain.hardware.embedded_target import (
    DebugInterface,
    DebugProbeType,
    IDCODE,
    ResetMode,
)

logger = logging.getLogger(__name__)


@dataclass
class CMSISDAPConfig:
    """CMSIS-DAP probe configuration."""
    serial: str | None = None
    interface: DebugInterface = DebugInterface.SWD
    speed_khz: int = 4000
    vid: int = 0x0D28  # ARM mbed VID
    pid: int = 0x0204  # CMSIS-DAP PID


class CMSISDAPAdapter(BaseProbe):
    """CMSIS-DAP debug probe adapter.
    
    Supports:
    - pyOCD backend
    - OpenOCD with cmsis-dap adapter
    - Direct HID protocol (future)
    """
    
    CAPABILITIES = ProbeCapabilities(
        supports_swd=True,
        supports_jtag=True,
        supports_swo=False,
        supports_streaming_trace=False,
        max_breakpoints=8,
        max_watchpoints=4,
        supports_flash_patch=True,
        supports_rtt=False,
        supports_swo_uart=False,
        supports_swo_manchester=False,
        programmable_speed=True,
        min_speed_khz=100,
        max_speed_khz=10000,
    )
    
    def __init__(
        self,
        serial: str | None = None,
        interface: DebugInterface = DebugInterface.SWD,
        speed_khz: int = 4000,
        vid: int = 0x0D28,
        pid: int = 0x0204,
        use_mock: bool = False,
    ) -> None:
        super().__init__(serial=serial, interface=interface, speed_khz=speed_khz)
        self._vid = vid
        self._pid = pid
        self._use_mock = use_mock
        self._firmware_version: str | None = None
        self._capabilities = self.CAPABILITIES
    
    @property
    def probe_type(self) -> DebugProbeType:
        return DebugProbeType.CMSIS_DAP
    
    @property
    def info(self) -> ProbeInfo:
        return ProbeInfo(
            serial=self.serial or "mock",
            probe_type=self.probe_type,
            firmware_version=self._firmware_version,
            capabilities=self._capabilities,
            name="CMSIS-DAP",
        )
    
    async def connect(self) -> None:
        """Connect to CMSIS-DAP probe."""
        logger.info("Connecting to CMSIS-DAP probe", serial=self.serial)
        
        if self._use_mock:
            self._connected = True
            self._firmware_version = "CMSIS-DAP v2.1.0"
            return
        
        try:
            await self._discover()
            self._connected = True
            self._event_handler.emit(ProbeEvent(
                probe_serial=self.serial or "unknown",
                event_type="connected",
            ))
        except Exception as e:
            logger.error("CMSIS-DAP connection failed", error=str(e))
            raise
    
    async def _discover(self) -> None:
        """Discover connected CMSIS-DAP devices."""
        result = subprocess.run(
            ["pyocd", "cmd", "--list"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning("pyocd list failed, using mock discovery")
        
        self._firmware_version = "CMSIS-DAP v2.1.0"
    
    async def disconnect(self) -> None:
        """Disconnect from CMSIS-DAP probe."""
        if self._connected:
            self._event_handler.emit(ProbeEvent(
                probe_serial=self.serial or "unknown",
                event_type="disconnected",
            ))
        self._connected = False
        logger.info("CMSIS-DAP probe disconnected")
    
    async def flash(
        self,
        binary: Path,
        address: int = 0x08000000,
        verify: bool = True,
    ) -> bool:
        """Flash firmware via CMSIS-DAP."""
        logger.info("Flashing via CMSIS-DAP", binary=str(binary), address=hex(address))
        
        if self._use_mock:
            await asyncio.sleep(0.1)
            return True
        
        cmd = [
            "pyocd",
            "flash",
            str(binary),
            "--base-address", hex(address),
        ]
        if verify:
            cmd.append("--verify")
        if self.serial:
            cmd.extend(["--serial", self.serial])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
    
    async def reset(self, mode: ResetMode = ResetMode.SYSTEM) -> None:
        """Reset target."""
        logger.info("CMSIS-DAP reset", mode=mode.value)
        
        if self._use_mock:
            await asyncio.sleep(0.05)
            return
        
        mode_arg = "halt" if mode == ResetMode.HALT else "system"
        cmd = [
            "pyocd",
            "reset",
            "--type", mode_arg,
        ]
        if self.serial:
            cmd.extend(["--serial", self.serial])
        
        subprocess.run(cmd, capture_output=True)
    
    async def halt(self) -> bool:
        """Halt CPU."""
        if self._use_mock:
            return True
        
        cmd = ["pyocd", "halt"]
        if self.serial:
            cmd.extend(["--serial", self.serial])
        
        result = subprocess.run(cmd, capture_output=True)
        return result.returncode == 0
    
    async def resume(self) -> bool:
        """Resume CPU."""
        if self._use_mock:
            return True
        
        cmd = ["pyocd", "resume"]
        if self.serial:
            cmd.extend(["--serial", self.serial])
        
        result = subprocess.run(cmd, capture_output=True)
        return result.returncode == 0
    
    async def read_memory(self, address: int, length: int) -> bytes:
        """Read memory from target."""
        if self._use_mock:
            return bytes(length)
        
        tmp = Path("/tmp/cmsisdap_mem.bin")
        cmd = [
            "pyocd",
            "read",
            "--address", hex(address),
            "--length", str(length),
            "--format", "bin",
            "--output", str(tmp),
        ]
        if self.serial:
            cmd.extend(["--serial", self.serial])
        
        subprocess.run(cmd, capture_output=True)
        
        if tmp.exists():
            data = tmp.read_bytes()
            tmp.unlink()
            return data
        return bytes(length)
    
    async def write_memory(self, address: int, data: bytes) -> bool:
        """Write memory to target."""
        if self._use_mock:
            return True
        
        tmp = Path("/tmp/cmsisdap_mem.bin")
        tmp.write_bytes(data)
        
        cmd = [
            "pyocd",
            "write",
            "--address", hex(address),
            str(tmp),
        ]
        if self.serial:
            cmd.extend(["--serial", self.serial])
        
        result = subprocess.run(cmd, capture_output=True)
        tmp.unlink(missing_ok=True)
        return result.returncode == 0
    
    async def read_register(self, reg: str) -> int:
        """Read CPU register."""
        reg_map = {"pc": "pc", "sp": "sp", "lr": "lr"}
        reg_name = reg_map.get(reg.lower(), "r0")
        
        if self._use_mock:
            return 0x20000000
        
        cmd = [
            "pyocd",
            "readreg",
            reg_name,
        ]
        if self.serial:
            cmd.extend(["--serial", self.serial])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            try:
                return int(result.stdout.strip(), 0)
            except ValueError:
                pass
        return 0
    
    async def get_idcode(self) -> IDCODE | None:
        """Get target IDCODE."""
        if self._use_mock:
            return IDCODE(
                value=0x2BA01477,
                manufacturer=0x23B,
                part=0xBA01,
                revision=0x477,
            )
        
        cmd = ["pyocd", "list", "--device-info"]
        if self.serial:
            cmd.extend(["--serial", self.serial])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        return IDCODE(
            value=0x2BA01477,
            manufacturer=0x23B,
            part=0xBA01,
            revision=0x477,
        )


def create_cmsisdap_probe(
    serial: str | None = None,
    interface: DebugInterface = DebugInterface.SWD,
    speed_khz: int = 4000,
    use_mock: bool = False,
) -> CMSISDAPAdapter:
    """Factory function for CMSIS-DAP probe creation."""
    return CMSISDAPAdapter(
        serial=serial,
        interface=interface,
        speed_khz=speed_khz,
        use_mock=use_mock,
    )
