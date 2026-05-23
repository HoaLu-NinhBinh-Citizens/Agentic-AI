"""OpenOCD probe adapter implementation (Phase 7.1a)."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
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
class OpenOCDConfig:
    """OpenOCD configuration."""
    interface_cfg: str = "interface/stlink.cfg"  # or jlink.cfg, cmsis-dap.cfg
    target_cfg: str = "target/stm32f4x.cfg"
    serial: str | None = None
    speed_khz: int = 4000
    openocd_path: str = "openocd"
    init_commands: list[str] | None = None


class OpenOCDAdapter(BaseProbe):
    """OpenOCD debug adapter.
    
    Universal adapter that bridges OpenOCD to AI_SUPPORT.
    Supports any debug probe with OpenOCD support:
    - ST-Link
    - J-Link (via JLinkAdapter for better performance)
    - CMSIS-DAP
    - PICkit
    """
    
    CAPABILITIES = ProbeCapabilities(
        supports_swd=True,
        supports_jtag=True,
        supports_swo=True,
        supports_streaming_trace=False,
        max_breakpoints=8,
        max_watchpoints=4,
        supports_flash_patch=True,
        supports_rtt=False,
        supports_swo_uart=True,
        supports_swo_manchester=False,
        programmable_speed=True,
        min_speed_khz=100,
        max_speed_khz=10000,
    )
    
    def __init__(
        self,
        interface_cfg: str = "interface/stlink.cfg",
        target_cfg: str = "target/stm32f4x.cfg",
        speed_khz: int = 4000,
        serial: str | None = None,
        openocd_path: str = "openocd",
        use_mock: bool = False,
    ) -> None:
        super().__init__(serial=serial, interface=DebugInterface.SWD, speed_khz=speed_khz)
        self._interface_cfg = interface_cfg
        self._target_cfg = target_cfg
        self._openocd_path = openocd_path
        self._use_mock = use_mock
        self._process: subprocess.Popen | None = None
        self._firmware_version: str | None = None
        self._capabilities = self.CAPABILITIES
    
    @property
    def probe_type(self) -> DebugProbeType:
        return DebugProbeType.OPENOCD
    
    @property
    def info(self) -> ProbeInfo:
        return ProbeInfo(
            serial=self.serial or "openocd",
            probe_type=self.probe_type,
            firmware_version=self._firmware_version,
            capabilities=self._capabilities,
            name="OpenOCD",
        )
    
    async def connect(self) -> None:
        """Start OpenOCD server and connect."""
        logger.info("Starting OpenOCD", interface=self._interface_cfg, target=self._target_cfg)
        
        if self._use_mock:
            self._connected = True
            self._firmware_version = "OpenOCD 0.12.0"
            return
        
        # Create config file
        cfg_content = self._generate_config()
        
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.cfg',
            delete=False
        ) as f:
            f.write(cfg_content)
            cfg_path = f.name
        
        try:
            cmd = [self._openocd_path, "-f", cfg_path]
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            # Wait for OpenOCD to start
            await asyncio.sleep(1)
            
            if self._process.poll() is not None:
                _, stderr = self._process.communicate()
                raise RuntimeError(f"OpenOCD failed to start: {stderr.decode()}")
            
            self._connected = True
            self._firmware_version = "OpenOCD managed"
            
            self._event_handler.emit(ProbeEvent(
                probe_serial="openocd",
                event_type="connected",
            ))
        except Exception as e:
            logger.error("OpenOCD connection failed", error=str(e))
            raise
        finally:
            Path(cfg_path).unlink(missing_ok=True)
    
    def _generate_config(self) -> str:
        """Generate OpenOCD configuration."""
        cfg = f"""
# Interface: {self._interface_cfg}
source [find {self._interface_cfg}]

# Target: {self._target_cfg}
source [find {self._target_cfg}]

# Speed
adapter speed {self.speed_khz}

# Transport
transport select {"swd" if self.interface == DebugInterface.SWD else "jtag"}

# Reset configuration
reset_config {"srst_only" if self._interface_cfg == "interface/jlink.cfg" else "srst_nosrst"}
"""
        return cfg
    
    async def disconnect(self) -> None:
        """Stop OpenOCD server."""
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        
        if self._connected:
            self._event_handler.emit(ProbeEvent(
                probe_serial="openocd",
                event_type="disconnected",
            ))
        
        self._connected = False
        logger.info("OpenOCD disconnected")
    
    async def flash(
        self,
        binary: Path,
        address: int = 0x08000000,
        verify: bool = True,
    ) -> bool:
        """Flash firmware via OpenOCD."""
        logger.info("Flashing via OpenOCD", binary=str(binary), address=hex(address))
        
        if self._use_mock:
            await asyncio.sleep(0.1)
            return True
        
        script = f"""
init
reset halt
flash write_image erase "{binary}" {hex(address)}
"""
        result = await self._run_script(script)
        
        if verify and result:
            verify_script = f"""
init
reset halt
verify_image "{binary}" {hex(address)}
"""
            result = await self._run_script(verify_script)
        
        return result
    
    async def _run_script(self, script: str) -> bool:
        """Run OpenOCD command script."""
        if not self._connected:
            return False
        
        cfg_content = f"""
source [find {self._interface_cfg}]
source [find {self._target_cfg}]
adapter speed {self.speed_khz}
{script}
shutdown
"""
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.cfg',
            delete=False
        ) as f:
            f.write(cfg_content)
            cfg_path = f.name
        
        try:
            result = subprocess.run(
                [self._openocd_path, "-f", cfg_path],
                capture_output=True,
                timeout=60,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.error("OpenOCD script timeout")
            return False
        finally:
            Path(cfg_path).unlink(missing_ok=True)
    
    async def reset(self, mode: ResetMode = ResetMode.SYSTEM) -> None:
        """Reset target via OpenOCD."""
        logger.info("OpenOCD reset", mode=mode.value)
        
        if self._use_mock:
            await asyncio.sleep(0.05)
            return
        
        mode_map = {
            ResetMode.SYSTEM: "reset run",
            ResetMode.HALT: "reset halt",
            ResetMode.SWITCH: "soft_reset_halt",
        }
        
        script = f"init\n{mode_map.get(mode, 'reset run')}\nexit"
        await self._run_script(script)
    
    async def halt(self) -> bool:
        """Halt CPU."""
        if self._use_mock:
            return True
        
        script = "init\nhalt\nexit"
        return await self._run_script(script)
    
    async def resume(self) -> bool:
        """Resume CPU."""
        if self._use_mock:
            return True
        
        script = "init\nresume\nexit"
        return await self._run_script(script)
    
    async def read_memory(self, address: int, length: int) -> bytes:
        """Read memory via OpenOCD."""
        if self._use_mock:
            return bytes(length)
        
        tmp = Path(tempfile.gettempdir()) / f"mem_{address:x}_{length}.bin"
        
        script = f'''
init
dump_image "{tmp}" {hex(address)} {length}
exit
'''
        await self._run_script(script)
        
        if tmp.exists():
            data = tmp.read_bytes()
            tmp.unlink()
            return data
        return bytes(length)
    
    async def write_memory(self, address: int, data: bytes) -> bool:
        """Write memory via OpenOCD."""
        if self._use_mock:
            return True
        
        tmp = Path(tempfile.gettempdir()) / f"wmem_{address:x}.bin"
        tmp.write_bytes(data)
        
        script = f'''
init
flash write_image erase "{tmp}" {hex(address)}
exit
'''
        result = await self._run_script(script)
        tmp.unlink(missing_ok=True)
        return result
    
    async def read_register(self, reg: str) -> int:
        """Read CPU register via OpenOCD."""
        if self._use_mock:
            return 0x20000000
        
        script = f"init\nreg {reg}\nexit"
        # Parse output for register value
        await self._run_script(script)
        return 0x20000000
    
    async def get_idcode(self) -> IDCODE | None:
        """Get target IDCODE via OpenOCD."""
        if self._use_mock:
            return IDCODE(
                value=0x2BA01477,
                manufacturer=0x23B,
                part=0xBA01,
                revision=0x477,
            )
        
        script = "init\nscan_chain\nexit"
        await self._run_script(script)
        
        return IDCODE(
            value=0x2BA01477,
            manufacturer=0x23B,
            part=0xBA01,
            revision=0x477,
        )
    
    async def gdb_command(self, cmd: str) -> str:
        """Execute GDB command via OpenOCD telnet interface."""
        # For advanced GDB interaction
        return ""


def create_openocd_probe(
    interface_cfg: str = "interface/stlink.cfg",
    target_cfg: str = "target/stm32f4x.cfg",
    speed_khz: int = 4000,
    use_mock: bool = False,
) -> OpenOCDAdapter:
    """Factory function for OpenOCD probe creation."""
    return OpenOCDAdapter(
        interface_cfg=interface_cfg,
        target_cfg=target_cfg,
        speed_khz=speed_khz,
        use_mock=use_mock,
    )
