"""GDB Client - GDB remote protocol client for ARM debugging.

Phase 6.4: GDB Client
- Connect to GDB server (gdbserver, J-Link GDB Server)
- Read/write registers
- Read/write memory
- Set breakpoints
- Stack backtrace
- Variable inspection
"""

from __future__ import annotations

import asyncio
import re
import socket
import struct
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator

logger = __import__("structlog").get_logger(__name__)


class GDBError(Exception):
    """GDB protocol error."""
    pass


class BreakpointType(Enum):
    """GDB breakpoint types."""
    SOFTWARE = "software"
    HARDWARE = "hardware"
    WRITE_WATCH = "write_watch"
    READ_WATCH = "read_watch"
    ACCESS_WATCH = "access_watch"


@dataclass
class GDBRegister:
    """GDB register representation."""
    
    number: int
    name: str
    value: int = 0
    size: int = 4  # bytes
    
    def to_hex(self) -> str:
        """Convert value to hex string."""
        return f"{self.value:0{self.size * 2}x}"


@dataclass
class GDBBreakpoint:
    """GDB breakpoint."""
    
    address: int
    breakpoint_type: BreakpointType = BreakpointType.SOFTWARE
    enabled: bool = True
    original_bytes: bytes = field(default_factory=bytes)
    breakpoint_id: int | None = None


@dataclass
class GDBStackFrame:
    """Stack frame from backtrace."""
    
    level: int
    pc: int
    sp: int
    fp: int  # Frame pointer
    function: str = ""
    source_file: str = ""
    source_line: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "pc": f"0x{self.pc:08X}",
            "sp": f"0x{self.sp:08X}",
            "fp": f"0x{self.fp:08X}",
            "function": self.function,
            "source": f"{self.source_file}:{self.source_line}" if self.source_file else "",
        }


@dataclass
class GDBVariable:
    """Local or global variable."""
    
    name: str
    value: Any
    type_name: str = ""
    address: int = 0
    is_local: bool = True
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": str(self.value),
            "type": self.type_name,
            "address": f"0x{self.address:08X}" if self.address else "",
            "scope": "local" if self.is_local else "global",
        }


@dataclass
class GDBThread:
    """GDB thread information."""
    
    thread_id: int
    target_id: str = ""
    name: str = ""
    state: str = "stopped"  # stopped, running, exit
    frame: GDBStackFrame | None = None


@dataclass 
class GDBTargetInfo:
    """Target information from GDB."""
    
    endian: str = "little"
    arch: str = "arm"
    osabi: str = ""
    pointer_size: int = 4
    registers: list[GDBRegister] = field(default_factory=list)


class GDBClient:
    """GDB Remote Serial Protocol (RSP) client.
    
    Features:
    - Connect to GDB server via TCP
    - Read/write registers
    - Read/write memory
    - Set/clear breakpoints
    - Stack backtrace
    - Variable inspection
    - Continue/step execution
    """
    
    # GDB RSP packet constants
    ACK = b"+"
    NACK = b"-"
    PACKET_START = b"$"
    PACKET_END = b"#"
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 3333,
        timeout: float = 5.0,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._sequence_id = 0
        
        # Target state
        self._registers: dict[int, GDBRegister] = {}
        self._breakpoints: dict[int, GDBBreakpoint] = {}
        self._last_signal: int = 0
        
        # Symbol table cache
        self._symbol_cache: dict[str, int] = {}
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to GDB server."""
        return self._connected
    
    async def connect(self) -> bool:
        """Connect to GDB server.
        
        Returns:
            True if connection successful.
        """
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout,
            )
            self._connected = True
            
            # Read initial ack
            await self._read_ack()
            
            logger.info("gdb_connected", host=self.host, port=self.port)
            return True
            
        except asyncio.TimeoutError:
            logger.error("gdb_connect_timeout", host=self.host, port=self.port)
            return False
        except Exception as e:
            logger.error("gdb_connect_error", error=str(e))
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from GDB server."""
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
        self._connected = False
        logger.info("gdb_disconnected")
    
    async def _read_ack(self) -> bool:
        """Read ACK/NACK from GDB."""
        try:
            data = await asyncio.wait_for(
                self._reader.read(1),
                timeout=1.0,
            )
            return data == self.ACK
        except asyncio.TimeoutError:
            return True  # Assume ack if timeout
        except Exception:
            return False
    
    async def _send_ack(self) -> None:
        """Send ACK to GDB."""
        if self._writer:
            self._writer.write(self.ACK)
            await self._writer.drain()
    
    async def _send_packet(self, command: str) -> str:
        """Send GDB RSP packet and receive response.
        
        Args:
            command: GDB protocol command
            
        Returns:
            Response data (without packet wrapper)
        """
        if not self._connected:
            raise GDBError("Not connected to GDB server")
        
        # Build packet
        self._sequence_id = (self._sequence_id + 1) % 256
        packet_data = command.encode("ascii")
        
        # Calculate checksum
        checksum = sum(packet_data) % 256
        packet = self.PACKET_START + packet_data + self.PACKET_END + f"{checksum:02x}".encode()
        
        # Send
        self._writer.write(packet)
        await self._writer.drain()
        
        # Read response
        return await self._receive_packet()
    
    async def _receive_packet(self) -> str:
        """Receive GDB RSP packet.

        Every read is bounded by self.timeout and checked for EOF: a server
        that dies mid-packet previously left the read-until-# loop spinning
        forever (no EOF check), hanging the caller indefinitely.
        """
        # Read until $
        while True:
            data = await asyncio.wait_for(self._reader.read(1), timeout=self.timeout)
            if data == self.PACKET_START:
                break
            if not data:
                raise GDBError("Connection closed")

        # Read until #
        packet_data = b""
        while True:
            data = await asyncio.wait_for(self._reader.read(1), timeout=self.timeout)
            if data == self.PACKET_END:
                break
            if not data:
                raise GDBError("Connection closed mid-packet")
            packet_data += data

        # Read checksum
        checksum = await asyncio.wait_for(self._reader.read(2), timeout=self.timeout)
        if not checksum or len(checksum) < 2:
            raise GDBError("Connection closed reading checksum")
        
        # Verify checksum
        calc_sum = sum(packet_data) % 256
        recv_sum = int(checksum.decode(), 16)
        
        if calc_sum != recv_sum:
            self._writer.write(self.NACK)
            raise GDBError(f"Checksum mismatch: {calc_sum} != {recv_sum}")
        
        # Send ACK
        self._writer.write(self.ACK)
        await self._writer.drain()
        
        # Decode response
        return self._decode_data(packet_data.decode())
    
    def _decode_data(self, data: str) -> str:
        """Decode GDB escape sequences in data."""
        # Handle #xx escapes
        result = []
        i = 0
        while i < len(data):
            if data[i] == "}" and i + 1 < len(data):
                # Escape sequence
                result.append(chr(ord(data[i+1]) ^ 0x20))
                i += 2
            else:
                result.append(data[i])
                i += 1
        return "".join(result)
    
    def _encode_data(self, data: str) -> str:
        """Encode data with GDB escape sequences."""
        result = []
        for c in data:
            code = ord(c)
            if code < 0x20 or code > 0x7E or code in (0x23, 0x24, 0x7D):  # #, $, }
                result.append("}" + chr(code ^ 0x20))
            else:
                result.append(c)
        return "".join(result)
    
    # =========================================================================
    # Target Operations
    # =========================================================================
    
    async def get_target_info(self) -> GDBTargetInfo | None:
        """Get target information."""
        try:
            response = await self._send_packet("?")
            
            # Parse signal info (e.g., "S05" = SIGTRAP)
            if response and response[0] == "S":
                self._last_signal = int(response[1:3], 16)
            
            # TODO: Parse target info from qSupported and qC
            return GDBTargetInfo()
            
        except Exception as e:
            logger.error("gdb_get_target_info", error=str(e))
            return None
    
    async def halt(self) -> bool:
        """Halt the target."""
        try:
            await self._send_packet("\x03")  # Ctrl+C
            await self._read_stop_reply()
            return True
        except Exception as e:
            logger.error("gdb_halt", error=str(e))
            return False
    
    async def resume(self, action: str = "c") -> bool:
        """Resume target execution.
        
        Args:
            action: 'c' = continue, 's' = step
        """
        try:
            response = await self._send_packet(action)
            return await self._read_stop_reply()
        except Exception as e:
            logger.error("gdb_resume", action=action, error=str(e))
            return False
    
    async def step(self) -> bool:
        """Step one instruction."""
        return await self.resume("s")
    
    async def continue_exec(self) -> bool:
        """Continue execution."""
        return await self.resume("c")
    
    async def _read_stop_reply(self) -> bool:
        """Read and parse stop reply packet."""
        try:
            response = await self._receive_packet()
            
            if response.startswith("T"):
                # Stopped with signal
                self._last_signal = int(response[1:3], 16)
                return True
            elif response.startswith("W"):
                # Process exited
                return False
            elif response == "OK":
                return True
            
            return True
            
        except Exception as e:
            logger.error("gdb_stop_reply", error=str(e))
            return False
    
    # =========================================================================
    # Register Operations
    # =========================================================================
    
    async def read_register(self, reg_num: int) -> int | None:
        """Read a single register.
        
        Args:
            reg_num: Register number (0-25 for ARM)
            
        Returns:
            Register value or None on error
        """
        try:
            response = await self._send_packet(f"p{reg_num:x}")
            
            # Parse hex response
            if response and response != "":
                return int(response, 16)
            return None
            
        except Exception as e:
            logger.error("gdb_read_register", reg=reg_num, error=str(e))
            return None
    
    async def read_all_registers(self) -> dict[int, int]:
        """Read all registers.
        
        Returns:
            Dictionary of register number to value
        """
        try:
            response = await self._send_packet("g")
            
            # Parse hex response (each register is 4 bytes = 8 hex chars)
            registers = {}
            for i in range(25):  # R0-R15
                offset = i * 8
                if offset + 8 <= len(response):
                    value = int(response[offset:offset+8], 16)
                    registers[i] = value
                    self._registers[i] = GDBRegister(number=i, value=value)
            
            return registers
            
        except Exception as e:
            logger.error("gdb_read_all_registers", error=str(e))
            return {}
    
    async def write_register(self, reg_num: int, value: int) -> bool:
        """Write a single register.
        
        Args:
            reg_num: Register number
            value: Value to write
            
        Returns:
            True on success
        """
        try:
            response = await self._send_packet(f"P{reg_num:x}={value:08x}")
            return response == "OK"
        except Exception as e:
            logger.error("gdb_write_register", reg=reg_num, error=str(e))
            return False
    
    # =========================================================================
    # Memory Operations
    # =========================================================================
    
    async def read_memory(self, address: int, size: int) -> bytes | None:
        """Read memory.
        
        Args:
            address: Memory address
            size: Number of bytes to read
            
        Returns:
            Memory contents or None on error
        """
        try:
            response = await self._send_packet(f"m{address:x},{size:x}")
            
            # Parse hex response
            if response and response != "":
                return bytes.fromhex(response)
            return None
            
        except Exception as e:
            logger.error("gdb_read_memory", address=hex(address), size=size, error=str(e))
            return None
    
    async def write_memory(self, address: int, data: bytes) -> bool:
        """Write memory.
        
        Args:
            address: Memory address
            data: Data to write
            
        Returns:
            True on success
        """
        try:
            hex_data = data.hex()
            response = await self._send_packet(f"M{address:x},{len(data):x}:{hex_data}")
            return response == "OK"
        except Exception as e:
            logger.error("gdb_write_memory", address=hex(address), error=str(e))
            return False
    
    # =========================================================================
    # Breakpoint Operations
    # =========================================================================
    
    async def set_breakpoint(
        self,
        address: int,
        breakpoint_type: BreakpointType = BreakpointType.SOFTWARE,
        length: int = 4,
    ) -> GDBBreakpoint | None:
        """Set a breakpoint.
        
        Args:
            address: Breakpoint address
            breakpoint_type: Type of breakpoint
            length: Instruction length (4 for ARM)
            
        Returns:
            GDBBreakpoint object or None on error
        """
        try:
            # Read original bytes
            original = await self.read_memory(address, length)
            
            # Z0 = software breakpoint
            # Z1 = hardware breakpoint
            # Z2 = write watchpoint
            # Z3 = read watchpoint
            # Z4 = access watchpoint
            z_type = {
                BreakpointType.SOFTWARE: 0,
                BreakpointType.HARDWARE: 1,
                BreakpointType.WRITE_WATCH: 2,
                BreakpointType.READ_WATCH: 3,
                BreakpointType.ACCESS_WATCH: 4,
            }.get(breakpoint_type, 0)
            
            response = await self._send_packet(f"Z{z_type},{address:x},{length:x}")
            
            if response == "OK":
                bp = GDBBreakpoint(
                    address=address,
                    breakpoint_type=breakpoint_type,
                    original_bytes=original or b"\x00" * length,
                )
                self._breakpoints[address] = bp
                return bp
            
            return None
            
        except Exception as e:
            logger.error("gdb_set_breakpoint", address=hex(address), error=str(e))
            return None
    
    async def clear_breakpoint(self, address: int) -> bool:
        """Clear a breakpoint.
        
        Args:
            address: Breakpoint address
            
        Returns:
            True on success
        """
        try:
            if address not in self._breakpoints:
                return False
            
            bp = self._breakpoints[address]
            z_type = {
                BreakpointType.SOFTWARE: 0,
                BreakpointType.HARDWARE: 1,
            }.get(bp.breakpoint_type, 0)
            
            response = await self._send_packet(f"z{z_type},{address:x},4")
            
            if response == "OK":
                del self._breakpoints[address]
                return True
            
            return False
            
        except Exception as e:
            logger.error("gdb_clear_breakpoint", address=hex(address), error=str(e))
            return False
    
    # =========================================================================
    # Stack Trace
    # =========================================================================
    
    async def get_backtrace(self, max_frames: int = 20) -> list[GDBStackFrame]:
        """Get stack backtrace.
        
        Args:
            max_frames: Maximum number of frames to retrieve
            
        Returns:
            List of GDBStackFrame objects
        """
        frames = []
        
        try:
            # Read current frame info
            registers = await self.read_all_registers()
            
            if not registers:
                return frames
            
            # PC at index 15, SP at 13, LR at 14
            pc = registers.get(15, 0)
            sp = registers.get(13, 0)
            lr = registers.get(14, 0)
            fp = registers.get(11, 0)  # R11 = FP
            
            # Add first frame
            frame = GDBStackFrame(
                level=0,
                pc=pc,
                sp=sp,
                fp=fp,
                function=self._lookup_symbol(pc),
            )
            frames.append(frame)
            
            # Try to unwind stack
            for level in range(1, max_frames):
                try:
                    # Read return address from stack
                    return_addr = await self.read_memory(sp + 4, 4)
                    if not return_addr or len(return_addr) < 4:
                        break
                    
                    return_value = struct.unpack("<I", return_addr)[0]
                    
                    # Try to read next frame pointer
                    fp_data = await self.read_memory(fp, 4)
                    if not fp_data or len(fp_data) < 4:
                        break
                    
                    next_fp = struct.unpack("<I", fp_data)[0]
                    next_sp = fp + 4  # Typical ARM frame
                    
                    frame = GDBStackFrame(
                        level=level,
                        pc=return_value,
                        sp=next_sp,
                        fp=next_fp,
                        function=self._lookup_symbol(return_value),
                    )
                    frames.append(frame)
                    
                    # Update for next iteration
                    sp = next_sp
                    fp = next_fp
                    
                except Exception:
                    break
            
        except Exception as e:
            logger.error("gdb_backtrace", error=str(e))
        
        return frames
    
    async def get_stack_variables(self, frame_level: int = 0) -> list[GDBVariable]:
        """Get local variables for a stack frame.
        
        Args:
            frame_level: Stack frame level (0 = current)
            
        Returns:
            List of GDBVariable objects
        """
        variables = []
        
        try:
            # Use -stack-list-variables
            response = await self._send_packet("-stack-list-variables 1")
            
            # Parse response (format varies by GDB version)
            # Example: {name="var1",value="10"} {name="var2",value="0x1234"}
            pattern = r'name="([^"]+)",value="([^"]+)"'
            for match in re.finditer(pattern, response):
                variables.append(GDBVariable(
                    name=match.group(1),
                    value=match.group(2),
                    is_local=True,
                ))
            
        except Exception as e:
            logger.error("gdb_stack_variables", error=str(e))
        
        return variables
    
    # =========================================================================
    # Symbol Operations
    # =========================================================================
    
    def _lookup_symbol(self, address: int) -> str:
        """Look up symbol for address from cache."""
        # Check cache
        for sym_addr, sym_name in self._symbol_cache.items():
            if abs(sym_addr - address) < 0x100:
                offset = address - sym_addr
                if offset > 0:
                    return f"{sym_name}+0x{offset:x}"
                return sym_name
        
        return ""
    
    async def lookup_symbol(self, name: str) -> int | None:
        """Look up symbol address.
        
        Args:
            name: Symbol name
            
        Returns:
            Symbol address or None
        """
        try:
            response = await self._send_packet(f"qSymbol:{name.encode().hex()}")
            
            # Response format: "NAME=ADDR" or ""
            if "=" in response:
                addr_str = response.split("=")[1]
                addr = int(addr_str, 16)
                self._symbol_cache[addr] = name
                return addr
            
            return None
            
        except Exception as e:
            logger.error("gdb_lookup_symbol", name=name, error=str(e))
            return None
    
    # =========================================================================
    # Thread Operations
    # =========================================================================
    
    async def list_threads(self) -> list[GDBThread]:
        """List all threads."""
        threads = []
        
        try:
            response = await self._send_packet("qfThreadInfo")
            
            if response.startswith("m"):
                thread_ids = response[1:].split("m")
                for tid in thread_ids:
                    if tid:
                        threads.append(GDBThread(
                            thread_id=int(tid, 16),
                        ))
                
                # Get remaining threads
                while True:
                    response = await self._send_packet("qsThreadInfo")
                    if response == "l":
                        break
                    if response.startswith("m"):
                        for tid in response[1:].split("m"):
                            if tid:
                                threads.append(GDBThread(
                                    thread_id=int(tid, 16),
                                ))
            
        except Exception as e:
            logger.error("gdb_list_threads", error=str(e))
        
        return threads
    
    async def select_thread(self, thread_id: int) -> bool:
        """Select a thread."""
        try:
            response = await self._send_packet(f"Hg{thread_id:x}")
            return response == "OK"
        except Exception:
            return False
    
    # =========================================================================
    # Context Manager
    # =========================================================================
    
    async def __aenter__(self) -> GDBClient:
        """Context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        await self.disconnect()
