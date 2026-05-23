"""Real J-Link backend using pylink2 library.

Provides:
- Real memory read/write via J-Link SDK
- Register access
- Flash programming
- Core register reading (ARM Cortex-M)

Usage:
    backend = PylinkBackend(serial="123456789")
    backend.connect()
    data = backend.read_bytes(0x08000000, 256)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Try to import pylink2
try:
    import pylink2
    HAS_PYLINK = True
except ImportError:
    HAS_PYLINK = False
    logger.warning("pylink2 not installed. Install with: pip install pylink2")


class PylinkBackend:
    """Real J-Link backend using pylink2 library.
    
    This provides actual hardware access via SEGGER J-Link debugger.
    """
    
    def __init__(
        self,
        serial: str | None = None,
        interface: int = 1,  # SWD = 1, JTAG = 0
        speed_khz: int = 4000,
    ):
        """
        Args:
            serial: J-Link serial number (optional)
            interface: 0 = JTAG, 1 = SWD
            speed_khz: Interface speed in kHz
        """
        self._serial = serial
        self._interface = interface
        self._speed_khz = speed_khz
        self._jlink: pylink2.JLink | None = None
        self._connected = False
        
        if not HAS_PYLINK:
            logger.warning(
                "pylink2 not available. Using mock backend. "
                "Install pylink2 for real hardware access."
            )
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    def connect(self) -> bool:
        """Connect to J-Link debugger.
        
        Returns:
            True if connected successfully
        """
        if not HAS_PYLINK:
            logger.error("cannot_connect_pylink2_not_installed")
            return False
        
        try:
            self._jlink = pylink2.JLink()
            
            if self._serial:
                self._jlink.open(serial_no=self._serial)
            else:
                self._jlink.open()
            
            # Configure interface
            if self._interface == 1:  # SWD
                self._jlink.set_tif(pylink2.enums.JLinkInterfaces.SWD)
            else:  # JTAG
                self._jlink.set_tif(pylink2.enums.JLinkInterfaces.JTAG)
            
            # Set speed
            self._jlink.set_speed(self._speed_khz)
            
            # Connect to target
            self._jlink.connect(device="Cortex-M4", verbose=False)
            
            self._connected = True
            logger.info(
                "jlink_connected",
                serial=self._serial,
                interface="SWD" if self._interface == 1 else "JTAG",
                speed=self._speed_khz,
            )
            return True
            
        except Exception as e:
            logger.error("jlink_connection_failed", error=str(e))
            self._connected = False
            return False
    
    def disconnect(self) -> None:
        """Disconnect from J-Link."""
        if self._jlink:
            try:
                self._jlink.close()
            except Exception:
                pass
            self._jlink = None
        self._connected = False
        logger.info("jlink_disconnected")
    
    def read_bytes(self, address: int, size: int) -> bytes:
        """Read memory from target.
        
        Args:
            address: Memory address to read
            size: Number of bytes to read
            
        Returns:
            Bytes read from memory
        """
        if not self._connected or not self._jlink:
            raise RuntimeError("J-Link not connected")
        
        try:
            data = self._jlink.memory_read(address, size)
            return bytes(data)
        except Exception as e:
            logger.error(
                "jlink_read_failed",
                address=f"0x{address:08X}",
                size=size,
                error=str(e),
            )
            raise
    
    def write_bytes(self, address: int, data: bytes) -> None:
        """Write memory to target.
        
        Args:
            address: Memory address to write
            data: Bytes to write
        """
        if not self._connected or not self._jlink:
            raise RuntimeError("J-Link not connected")
        
        try:
            self._jlink.memory_write(address, list(data))
            logger.debug(
                "jlink_write",
                address=f"0x{address:08X}",
                size=len(data),
            )
        except Exception as e:
            logger.error(
                "jlink_write_failed",
                address=f"0x{address:08X}",
                size=len(data),
                error=str(e),
            )
            raise
    
    def read_register(self, reg_name: str) -> int:
        """Read ARM register.
        
        Args:
            reg_name: Register name (r0-r15, sp, lr, pc, xpsr)
            
        Returns:
            Register value
        """
        if not self._connected or not self._jlink:
            raise RuntimeError("J-Link not connected")
        
        # Map register names to J-Link indices
        reg_map = {
            "r0": 0, "r1": 1, "r2": 2, "r3": 3,
            "r4": 4, "r5": 5, "r6": 6, "r7": 7,
            "r8": 8, "r9": 9, "r10": 10, "r11": 11, "r12": 12,
            "sp": 13, "r13": 13, "lr": 14, "r14": 14,
            "pc": 15, "r15": 15,
        }
        
        reg_index = reg_map.get(reg_name.lower())
        if reg_index is None:
            raise ValueError(f"Unknown register: {reg_name}")
        
        try:
            # J-Link SDK uses different register indices
            # Core registers: 0-15
            value = self._jlink.register_read(reg_index)
            return value
        except Exception as e:
            logger.error(
                "jlink_register_read_failed",
                register=reg_name,
                error=str(e),
            )
            raise
    
    def write_register(self, reg_name: str, value: int) -> None:
        """Write ARM register.
        
        Args:
            reg_name: Register name
            value: Value to write
        """
        if not self._connected or not self._jlink:
            raise RuntimeError("J-Link not connected")
        
        reg_map = {
            "r0": 0, "r1": 1, "r2": 2, "r3": 3,
            "r4": 4, "r5": 5, "r6": 6, "r7": 7,
            "r8": 8, "r9": 9, "r10": 10, "r11": 11, "r12": 12,
            "sp": 13, "r13": 13, "lr": 14, "r14": 14,
            "pc": 15, "r15": 15,
        }
        
        reg_index = reg_map.get(reg_name.lower())
        if reg_index is None:
            raise ValueError(f"Unknown register: {reg_name}")
        
        try:
            self._jlink.register_write(reg_index, value)
            logger.debug("jlink_register_write", register=reg_name, value=value)
        except Exception as e:
            logger.error(
                "jlink_register_write_failed",
                register=reg_name,
                value=value,
                error=str(e),
            )
            raise
    
    def halt(self) -> None:
        """Halt the CPU."""
        if self._jlink:
            self._jlink.halt()
    
    def resume(self) -> None:
        """Resume CPU execution."""
        if self._jlink:
            self._jlink.resume()
    
    def step(self) -> None:
        """Step one instruction."""
        if self._jlink:
            self._jlink.step()
    
    def reset(self, halt: bool = True) -> None:
        """Reset the target.
        
        Args:
            halt: Halt CPU after reset
        """
        if self._jlink:
            self._jlink.reset(halt=halt)
    
    def flash_write(self, address: int, data: bytes, erase: bool = True) -> bool:
        """Flash memory at address.
        
        Args:
            address: Flash base address
            data: Data to flash
            erase: Erase flash before writing
            
        Returns:
            True if successful
        """
        if not self._connected or not self._jlink:
            raise RuntimeError("J-Link not connected")
        
        try:
            if erase:
                # Auto-erase handled by flash_write
                pass
            
            self._jlink.flash_write(address, list(data))
            logger.info(
                "jlink_flash_write",
                address=f"0x{address:08X}",
                size=len(data),
            )
            return True
        except Exception as e:
            logger.error(
                "jlink_flash_write_failed",
                address=f"0x{address:08X}",
                size=len(data),
                error=str(e),
            )
            return False
    
    def flash_verify(self, address: int, expected: bytes) -> bool:
        """Verify flash contents.
        
        Args:
            address: Flash base address
            expected: Expected data
            
        Returns:
            True if verification passes
        """
        try:
            actual = self.read_bytes(address, len(expected))
            return actual == expected
        except Exception:
            return False
    
    def get_idcode(self) -> int | None:
        """Get device IDCODE.
        
        Returns:
            IDCODE value or None
        """
        if not self._connected or not self._jlink:
            return None
        
        try:
            return self._jlink.idcode()
        except Exception:
            return None
    
    def read_core_state(self) -> dict[str, Any]:
        """Read complete core state for crash analysis.
        
        Returns:
            Dict with registers and status
        """
        state = {
            "pc": self.read_register("pc"),
            "sp": self.read_register("sp"),
            "lr": self.read_register("lr"),
            "registers": {},
        }
        
        for reg in ["r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", 
                    "r8", "r9", "r10", "r11", "r12"]:
            try:
                state["registers"][reg] = self.read_register(reg)
            except Exception:
                pass
        
        return state


# Backwards compatibility alias
JLinkRealBackend = PylinkBackend


if __name__ == "__main__":
    print("Pylink2 J-Link Backend")
    print("=" * 40)
    
    if HAS_PYLINK:
        print("pylink2 is installed. Real hardware access available.")
        
        # Example usage
        backend = PylinkBackend(serial=None, interface=1, speed_khz=4000)
        if backend.connect():
            print("Connected to J-Link")
            
            # Read IDCODE
            idcode = backend.get_idcode()
            print(f"IDCODE: 0x{idcode:08X}")
            
            # Read core state
            state = backend.read_core_state()
            print(f"PC: 0x{state['pc']:08X}")
            print(f"SP: 0x{state['sp']:08X}")
            
            backend.disconnect()
        else:
            print("Failed to connect to J-Link")
    else:
        print("pylink2 NOT installed.")
        print("Install with: pip install pylink2")
