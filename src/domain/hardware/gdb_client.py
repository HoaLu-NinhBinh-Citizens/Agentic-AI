"""GDB Remote Serial Protocol (RSP) client implementation."""

from __future__ import annotations

import asyncio
import re
import socket
import struct
from dataclasses import dataclass, field
from typing import Callable

from .embedded_target import (
    BreakpointType,
    GDBFrame,
    GDBBreakpoint,
    GDBRegister,
    StackFrame,
)


# GDB RSP packet constants
GDB_ACK = b"+"
GDB_NAK = b"-"
GDB_INTERRUPT = b"\x03"
GDB_PACKET_START = b"$"
GDB_PACKET_END = b"#"
GDB_CHECKSUM_HEX = 2  # 2 hex digits for checksum


class GDBError(Exception):
    """GDB client errors."""
    pass


class GDBChecksumError(GDBError):
    """Checksum mismatch error."""
    pass


@dataclass
class GDBConnectionInfo:
    """GDB connection information."""
    
    host: str
    port: int
    connected_at: float = 0.0


class GDBClient:
    """GDB Remote Serial Protocol client."""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 3333,
        timeout: float = 10.0,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._breakpoint_count = 0
        self._breakpoints: dict[int, int] = {}  # address -> breakpoint number
        self._last_signal: int | None = None
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to GDB server."""
        return self._connected
    
    async def connect(self) -> None:
        """Connect to GDB server."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout,
            )
            self._connected = True
            
            # Enable acknowledgment packets
            await self._send_raw(b"+")
            
            # Get initial target info
            await self._send_command(b"?")

        except asyncio.TimeoutError:
            raise GDBError(f"Connection timeout to {self.host}:{self.port}")
        except Exception as e:
            raise GDBError(f"Failed to connect: {e}")
    
    async def disconnect(self) -> None:
        """Disconnect from GDB server."""
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
        self._connected = False
        self._reader = None
        self._writer = None
    
    async def _send_raw(self, data: bytes) -> None:
        """Send raw data."""
        if self._writer:
            self._writer.write(data)
            await self._writer.drain()
    
    async def _recv_packet(self) -> bytes:
        """Receive a GDB RSP packet."""
        if not self._reader:
            raise GDBError("Not connected")
        
        # Read until packet start
        byte = await self._reader.read(1)
        while byte and byte != GDB_PACKET_START:
            byte = await self._reader.read(1)
            if not byte:
                raise GDBError("Connection closed")
        
        # Read until packet end
        data = byte
        while True:
            byte = await self._reader.read(1)
            if not byte:
                raise GDBError("Connection closed")
            if byte == GDB_PACKET_END:
                break
            data += byte
        
        # Read checksum
        checksum_data = await self._reader.readexact(GDB_CHECKSUM_HEX)
        checksum = int(checksum_data.decode(), 16)
        
        # Verify checksum
        computed = sum(data[1:]) & 0xFF
        if computed != checksum:
            await self._send_raw(GDB_NAK)
            raise GDBChecksumError(
                f"Checksum mismatch: expected {checksum}, got {computed}"
            )
        
        await self._send_raw(GDB_ACK)
        return data[1:]  # Remove start byte
    
    async def _send_packet(self, data: bytes) -> bytes:
        """Send a GDB RSP packet and receive response."""
        if not self._writer or not self._reader:
            raise GDBError("Not connected")
        
        # Build packet with checksum
        checksum = sum(data) & 0xFF
        packet = GDB_PACKET_START + data + GDB_PACKET_END + f"{checksum:02x}".encode()
        
        await self._send_raw(packet)
        
        # Wait for acknowledgment
        ack = await self._reader.read(1)
        if ack == GDB_NAK:
            # Resend once
            await self._send_raw(packet)
            ack = await self._reader.read(1)
        
        # Receive response
        response = await self._recv_packet()
        
        return response
    
    async def _send_command(self, cmd: bytes) -> str:
        """Send command and get response as string."""
        response = await self._send_packet(cmd)
        return response.decode("ascii", errors="replace")
    
    async def read_registers(self) -> dict[str, int]:
        """Read all core registers."""
        response = await self._send_command(b"g")
        
        if response.startswith(b"E"):
            raise GDBError(f"Failed to read registers: {response}")
        
        return self._parse_register_response(response)
    
    def _parse_register_response(self, data: bytes) -> dict[str, int]:
        """Parse register response."""
        registers: dict[str, int] = {}
        
        # ARM registers are sent as sequences of 8 hex chars (32-bit)
        reg_names = [
            "r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7",
            "r8", "r9", "r10", "r11", "r12", "sp", "lr", "pc",
            "xpsr", "msp", "psp", "primask", "faultmask", "basepri", "control",
        ]
        
        hex_str = data.decode("ascii")
        for i, name in enumerate(reg_names):
            if i * 8 < len(hex_str):
                try:
                    value = int(hex_str[i * 8:(i + 1) * 8], 16)
                    registers[name] = value
                except ValueError:
                    pass
        
        return registers
    
    async def read_register(self, name: str) -> int:
        """Read a specific register."""
        reg_map = {
            "pc": "15", "sp": "13", "lr": "14",
            "r0": "0", "r1": "1", "r2": "2", "r3": "3",
        }
        
        reg_num = reg_map.get(name, name)
        response = await self._send_command(f"p{reg_num}".encode())
        
        if response.startswith(b"E"):
            raise GDBError(f"Failed to read register {name}: {response}")
        
        return int(response.decode("ascii"), 16)
    
    async def write_register(self, name: str, value: int) -> None:
        """Write a register."""
        reg_map = {
            "pc": "15", "sp": "13", "lr": "14",
        }
        
        reg_num = reg_map.get(name, name)
        hex_value = f"{value:08x}"
        response = await self._send_command(f"P{reg_num}={hex_value}".encode())
        
        if response.startswith(b"E"):
            raise GDBError(f"Failed to write register {name}: {response}")
    
    async def read_memory(self, addr: int, length: int) -> bytes:
        """Read memory."""
        response = await self._send_command(f"m{addr:x},{length:x}".encode())
        
        if response.startswith(b"E"):
            raise GDBError(f"Failed to read memory at 0x{addr:x}: {response}")
        
        return bytes.fromhex(response.decode("ascii"))
    
    async def write_memory(self, addr: int, data: bytes) -> None:
        """Write memory."""
        hex_data = data.hex()
        response = await self._send_command(
            f"M{addr:x},{len(data):x}:{hex_data}".encode()
        )
        
        if response.startswith(b"E"):
            raise GDBError(f"Failed to write memory at 0x{addr:x}: {response}")
    
    async def set_breakpoint(
        self,
        addr: int,
        bp_type: BreakpointType = BreakpointType.SOFTWARE,
    ) -> int:
        """Set a breakpoint."""
        bp_type_map = {
            BreakpointType.SOFTWARE: "software",
            BreakpointType.HARDWARE: "hardware",
            BreakpointType.FLASH: "flash",
        }
        
        bp_str = bp_type_map.get(bp_type, "software")
        response = await self._send_command(
            f"Z0,{addr:x},1:{bp_str}".encode()
        )
        
        if response == b"OK":
            self._breakpoint_count += 1
            self._breakpoints[addr] = self._breakpoint_count
            return self._breakpoint_count
        
        raise GDBError(f"Failed to set breakpoint at 0x{addr:x}: {response}")
    
    async def remove_breakpoint(self, addr: int) -> None:
        """Remove a breakpoint."""
        if addr not in self._breakpoints:
            return
        
        bp_num = self._breakpoints[addr]
        response = await self._send_command(f"z0,{addr:x},1".encode())
        
        if response == b"OK":
            del self._breakpoints[addr]
        else:
            raise GDBError(f"Failed to remove breakpoint: {response}")
    
    async def continue_(self) -> int:
        """Continue execution. Returns signal received."""
        response = await self._send_command(b"c")
        
        # Parse signal
        if response.startswith(b"S"):
            signal = int(response[1:], 16)
            self._last_signal = signal
            return signal
        elif response.startswith(b"T"):
            # Stopped with signal and register info
            self._last_signal = int(response[1:3], 16)
            return self._last_signal
        
        return 0
    
    async def interrupt(self) -> None:
        """Send interrupt to halt target."""
        await self._send_raw(GDB_INTERRUPT)
    
    async def step(self) -> int:
        """Single step. Returns signal received."""
        response = await self._send_command(b"s")
        
        if response.startswith(b"S"):
            signal = int(response[1:], 16)
            self._last_signal = signal
            return signal
        
        return 0
    
    async def halt(self) -> int:
        """Halt target. Returns signal."""
        await self.interrupt()
        
        # Read response
        response = await self._recv_packet()
        
        if response.startswith(b"S"):
            signal = int(response[1:], 16)
            self._last_signal = signal
            return signal
        
        return 0
    
    async def reset(self) -> None:
        """Reset target."""
        response = await self._send_command(b"rst")
        
        if response.startswith(b"E"):
            raise GDBError(f"Failed to reset: {response}")
    
    async def backtrace(self) -> list[GDBFrame]:
        """Get backtrace."""
        frames: list[GDBFrame] = []
        
        # Get current PC
        pc_registers = await self.read_registers()
        
        # Use 'bt' command for backtrace
        response = await self._send_command(b"bt")
        
        # Parse backtrace response
        # Format: level=addr ...
        lines = response.decode("ascii").strip().split("\n")
        
        for line in lines:
            if not line.strip():
                continue
            
            # Parse frame
            match = re.match(r"#(\d+)\s+.*?at\s+(.*?):(\d+)", line)
            if match:
                level = int(match.group(1))
                file_line = match.group(2)
                line_num = int(match.group(3))
                
                # Get PC for this frame
                pc = pc_registers.get("pc", 0)
                
                frames.append(GDBFrame(
                    level=level,
                    pc=pc,
                    file=file_line,
                    line=line_num,
                ))
        
        return frames
    
    async def get_current_pc(self) -> int:
        """Get current program counter."""
        return await self.read_register("pc")
    
    async def get_current_stack_pointer(self) -> int:
        """Get current stack pointer."""
        return await self.read_register("sp")
    
    async def get_current_lr(self) -> int:
        """Get current link register."""
        return await self.read_register("lr")
    
    async def get_thread_info(self) -> dict:
        """Get thread information."""
        response = await self._send_command(b"qfThreadInfo")
        
        if response == b"l":
            return {"threads": []}
        
        # Parse thread IDs
        response = await self._send_command(b"qsThreadInfo")
        
        return {"threads": []}
    
    async def select_thread(self, thread_id: int) -> None:
        """Select thread."""
        response = await self._send_command(f"T{thread_id}".encode())
        
        if response.startswith(b"E"):
            raise GDBError(f"Failed to select thread {thread_id}: {response}")
    
    async def query_supported(self) -> dict[str, bool]:
        """Query supported features."""
        response = await self._send_command(b"qSupported")
        
        features: dict[str, bool] = {}
        for feat in response.decode().split(";"):
            if "=" in feat:
                key, value = feat.split("=")
                features[key] = bool(int(value))
            else:
                features[feat] = True
        
        return features


class GDBSession:
    """GDB debugging session with convenience methods."""
    
    def __init__(self, client: GDBClient):
        self.client = client
        self._breakpoints: list[int] = []
        self._watchpoints: list[int] = []
    
    async def __aenter__(self) -> "GDBSession":
        await self.client.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        # Clean up breakpoints
        for addr in self._breakpoints:
            try:
                await self.client.remove_breakpoint(addr)
            except Exception:
                pass
        
        await self.client.disconnect()
    
    async def halt_and_examine(self) -> dict:
        """Halt target and get current state."""
        signal = await self.client.halt()
        
        registers = await self.client.read_registers()
        pc = registers.get("pc", 0)
        sp = registers.get("sp", 0)
        lr = registers.get("lr", 0)
        
        backtrace = await self.client.backtrace()
        
        return {
            "signal": signal,
            "pc": pc,
            "sp": sp,
            "lr": lr,
            "registers": registers,
            "backtrace": backtrace,
        }
    
    async def step_until(self, addr: int, max_steps: int = 10000) -> bool:
        """Step until reaching address."""
        for _ in range(max_steps):
            pc = await self.client.get_current_pc()
            
            if pc == addr:
                return True
            
            await self.client.step()
        
        return False
    
    async def run_to_breakpoint(self, addr: int) -> int:
        """Run to breakpoint."""
        bp_num = await self.client.set_breakpoint(addr)
        self._breakpoints.append(addr)
        
        signal = await self.client.continue_()
        
        return signal
    
    async def read_struct(self, addr: int, fmt: str) -> tuple:
        """Read structured data from memory."""
        # Calculate size from format
        size = struct.calcsize(fmt)
        data = await self.client.read_memory(addr, size)
        return struct.unpack(fmt, data)
