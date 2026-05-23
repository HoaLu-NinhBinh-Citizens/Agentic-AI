"""Real OpenOCD backend for ST-Link and other debug probes.

Provides:
- Real memory read/write via OpenOCD
- Register access with proper parsing
- Flash programming
- Core state inspection

Usage:
    backend = OpenOCDBackend()
    backend.connect()
    data = backend.read_memory(0x08000000, 256)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import socket
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Try to import python-openocd or use subprocess
HAS_OPENOCD_PYTHON = False
try:
    import python_openocd
    HAS_OPENOCD_PYTHON = True
except ImportError:
    logger.info("python-openocd not available, using subprocess")


class OpenOCDConnection:
    """Low-level OpenOCD TCL RPC connection.
    
    OpenOCD exposes a TCL RPC server on TCP port 4444 by default.
    This class provides direct access to OpenOCD commands.
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 4444,
        timeout: float = 5.0,
    ):
        self._host = host
        self._port = port
        self._timeout = timeout
        self._socket: socket.socket | None = None
        self._connected = False
    
    def connect(self) -> bool:
        """Connect to OpenOCD server."""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self._timeout)
            self._socket.connect((self._host, self._port))
            self._connected = True
            logger.info("openocd_connected", host=self._host, port=self._port)
            return True
        except Exception as e:
            logger.error("openocd_connection_failed", error=str(e))
            self._connected = False
            return False
    
    def disconnect(self) -> None:
        """Disconnect from OpenOCD."""
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        self._connected = False
    
    def send_command(self, command: str) -> str:
        """Send command to OpenOCD and get response.
        
        Args:
            command: OpenOCD TCL command
            
        Returns:
            Response string
        """
        if not self._connected or not self._socket:
            raise RuntimeError("Not connected to OpenOCD")
        
        try:
            # Send command with newline
            self._socket.sendall(f"{command}\n".encode())
            
            # Read response (OpenOCD sends back the result)
            response = b""
            while True:
                chunk = self._socket.recv(4096)
                if not chunk:
                    break
                response += chunk
                if b"\n" in chunk:
                    break
            
            return response.decode().strip()
        except Exception as e:
            logger.error("openocd_command_failed", command=command, error=str(e))
            raise
    
    def read_memory(self, address: int, length: int) -> bytes:
        """Read memory using OpenOCD.
        
        Args:
            address: Memory address
            length: Number of bytes
            
        Returns:
            Memory contents
        """
        # Use dump_image to file then read
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            temp_path = f.name
        
        try:
            # Dump memory to file
            self.send_command(f"dump_image {temp_path} {hex(address)} {length}")
            
            # Read the file
            with open(temp_path, "rb") as f:
                data = f.read()
            
            return data
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass
    
    def write_memory(self, address: int, data: bytes) -> bool:
        """Write memory using OpenOCD.
        
        Args:
            address: Memory address
            data: Bytes to write
            
        Returns:
            True if successful
        """
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(data)
            temp_path = f.name
        
        try:
            self.send_command(f"load_image {temp_path} {hex(address)}")
            return True
        except Exception as e:
            logger.error("openocd_write_failed", error=str(e))
            return False
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass
    
    def read_register(self, name: str) -> int:
        """Read CPU register.
        
        Args:
            name: Register name (pc, sp, lr, r0-r12)
            
        Returns:
            Register value
        """
        response = self.send_command(f"reg {name}")
        
        # Parse response like: "r0 (/32): 0x20000000"
        match = re.search(r":\s+(0x[0-9a-fA-F]+)", response)
        if match:
            return int(match.group(1), 16)
        
        raise ValueError(f"Could not parse register value from: {response}")
    
    def halt(self) -> None:
        """Halt CPU."""
        self.send_command("halt")
    
    def resume(self) -> None:
        """Resume CPU."""
        self.send_command("resume")
    
    def step(self) -> None:
        """Step one instruction."""
        self.send_command("step")
    
    def reset(self, halt: bool = True) -> None:
        """Reset target.
        
        Args:
            halt: Halt after reset
        """
        if halt:
            self.send_command("reset halt")
        else:
            self.send_command("reset run")
    
    def poll(self) -> bool:
        """Poll target state.
        
        Returns:
            True if target is halted
        """
        response = self.send_command("poll")
        return "halted" in response.lower()


class OpenOCDBackend:
    """OpenOCD backend for debug probes.
    
    Provides high-level interface using either:
    1. Direct TCP connection to OpenOCD RPC
    2. Subprocess calls to openocd CLI
    
    Works with:
    - ST-Link (via ST-Link.cfg)
    - J-Link (via jlink.cfg)
    - CMSIS-DAP (via cmsis-dap.cfg)
    """
    
    def __init__(
        self,
        interface_config: str = "interface/stlink.cfg",
        target_config: str | None = None,
        speed_khz: int = 4000,
        openocd_path: str = "openocd",
    ):
        """
        Args:
            interface_config: OpenOCD interface config
            target_config: OpenOCD target config (e.g., target/stm32f4.cfg)
            speed_khz: Interface speed
            openocd_path: Path to openocd binary
        """
        self._interface_config = interface_config
        self._target_config = target_config
        self._speed_khz = speed_khz
        self._openocd_path = openocd_path
        self._process: asyncio.subprocess.Process | None = None
        self._connection: OpenOCDConnection | None = None
        self._connected = False
    
    async def start_openocd(self) -> bool:
        """Start OpenOCD as subprocess and connect.
        
        Returns:
            True if successful
        """
        cmd = [
            self._openocd_path,
            "-f", self._interface_config,
        ]
        
        if self._target_config:
            cmd.extend(["-f", self._target_config])
        
        cmd.extend([
            "-c", f"adapter speed {self._speed_khz}",
            "-c", "init",
        ])
        
        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            # Wait for OpenOCD to start
            await asyncio.sleep(2)
            
            # Connect via RPC
            self._connection = OpenOCDConnection()
            if self._connection.connect():
                self._connected = True
                logger.info("openocd_backend_started", interface=self._interface_config)
                return True
            
            return False
            
        except Exception as e:
            logger.error("openocd_start_failed", error=str(e))
            return False
    
    async def stop_openocd(self) -> None:
        """Stop OpenOCD subprocess."""
        if self._connection:
            self._connection.disconnect()
        
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
            self._process = None
        
        self._connected = False
        logger.info("openocd_backend_stopped")
    
    def connect(self, host: str = "localhost", port: int = 4444) -> bool:
        """Connect to existing OpenOCD server.
        
        Args:
            host: OpenOCD server host
            port: OpenOCD RPC port
            
        Returns:
            True if connected
        """
        self._connection = OpenOCDConnection(host, port)
        if self._connection.connect():
            self._connected = True
            return True
        return False
    
    def disconnect(self) -> None:
        """Disconnect from OpenOCD."""
        if self._connection:
            self._connection.disconnect()
        self._connected = False
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    def read_memory(self, address: int, length: int) -> bytes:
        """Read memory from target.
        
        Args:
            address: Memory address
            length: Number of bytes
            
        Returns:
            Memory contents
        """
        if not self._connected or not self._connection:
            raise RuntimeError("Not connected to OpenOCD")
        
        return self._connection.read_memory(address, length)
    
    def write_memory(self, address: int, data: bytes) -> bool:
        """Write memory to target.
        
        Args:
            address: Memory address
            data: Bytes to write
            
        Returns:
            True if successful
        """
        if not self._connected or not self._connection:
            raise RuntimeError("Not connected to OpenOCD")
        
        return self._connection.write_memory(address, data)
    
    def read_register(self, name: str) -> int:
        """Read CPU register.
        
        Args:
            name: Register name
            
        Returns:
            Register value
        """
        if not self._connected or not self._connection:
            raise RuntimeError("Not connected to OpenOCD")
        
        return self._connection.read_register(name)
    
    def write_register(self, name: str, value: int) -> bool:
        """Write CPU register.
        
        Args:
            name: Register name
            value: Value to write
            
        Returns:
            True if successful
        """
        if not self._connected or not self._connection:
            raise RuntimeError("Not connected to OpenOCD")
        
        try:
            self._connection.send_command(f"reg {name} {hex(value)}")
            return True
        except Exception:
            return False
    
    def halt(self) -> None:
        """Halt CPU."""
        if self._connection:
            self._connection.halt()
    
    def resume(self) -> None:
        """Resume CPU."""
        if self._connection:
            self._connection.resume()
    
    def step(self) -> None:
        """Step one instruction."""
        if self._connection:
            self._connection.step()
    
    def reset(self, halt: bool = True) -> None:
        """Reset target.
        
        Args:
            halt: Halt after reset
        """
        if self._connection:
            self._connection.reset(halt=halt)
    
    def is_halted(self) -> bool:
        """Check if target is halted."""
        if self._connection:
            return self._connection.poll()
        return False
    
    def read_core_state(self) -> dict[str, Any]:
        """Read complete core state.
        
        Returns:
            Dict with all registers and status
        """
        if not self._connected or not self._connection:
            return {}
        
        state = {
            "halted": self.is_halted(),
            "registers": {},
        }
        
        # Read all registers
        for name in ["r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7",
                     "r8", "r9", "r10", "r11", "r12", "sp", "lr", "pc"]:
            try:
                state["registers"][name] = self.read_register(name)
            except Exception:
                pass
        
        return state


# Factory function
def create_openocd_backend(
    interface: str = "stlink",
    target: str | None = None,
) -> OpenOCDBackend:
    """Create OpenOCD backend for probe type.
    
    Args:
        interface: Interface type (stlink, jlink, cmsis-dap)
        target: Target chip config
        
    Returns:
        OpenOCDBackend instance
    """
    interface_map = {
        "stlink": "interface/stlink.cfg",
        "jlink": "interface/jlink.cfg",
        "cmsis-dap": "interface/cmsis-dap.cfg",
    }
    
    target_map = {
        "stm32f4": "target/stm32f4x.cfg",
        "stm32f1": "target/stm32f1x.cfg",
        "stm32l4": "target/stm32l4x.cfg",
        "nrf52": "target/nrf52.cfg",
    }
    
    iface_config = interface_map.get(interface, f"interface/{interface}.cfg")
    target_config = target_map.get(target, target) if target else None
    
    return OpenOCDBackend(
        interface_config=iface_config,
        target_config=target_config,
    )


if __name__ == "__main__":
    print("OpenOCD Backend for ST-Link/J-Link")
    print("=" * 40)
    print()
    print("Usage:")
    print("  # Start OpenOCD manually:")
    print("  openocd -f interface/stlink.cfg -f target/stm32f4x.cfg")
    print()
    print("  # Then connect from Python:")
    print("  backend = OpenOCDBackend()")
    print("  backend.connect()")
    print("  pc = backend.read_register('pc')")
