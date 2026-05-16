"""
Serial Reader - UART Communication for Hardware Testing

Provides real-time UART reading capabilities for AI agent to:
- Read serial output from STM32 board
- Parse crash logs and error messages
- Detect success/failure patterns
- Support timeout-based reading

Usage:
    reader = SerialReader(port="COM3", baudrate=115200)
    output = reader.read_until("OK", timeout=5.0)
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional

try:
    import serial
    import serial.tools.list_ports
    PYSERIAL_AVAILABLE = True
except ImportError:
    PYSERIAL_AVAILABLE = False
    serial = None

logger = logging.getLogger(__name__)


class ReadStatus(Enum):
    """Serial read operation status."""
    SUCCESS = "success"
    TIMEOUT = "timeout"
    ERROR = "error"
    NO_DATA = "no_data"
    PORT_NOT_OPEN = "port_not_open"


@dataclass
class SerialConfig:
    """Configuration for serial connection."""
    port: str = "COM3"
    baudrate: int = 115200
    timeout: float = 1.0
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1.0
    xonxoff: bool = False
    rtscts: bool = False


@dataclass
class ReadResult:
    """Result of a serial read operation."""
    status: ReadStatus
    data: str = ""
    bytes_read: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    matched_pattern: Optional[str] = None


@dataclass
class CrashLog:
    """Parsed crash log from embedded system."""
    crash_type: str = ""
    pc_address: Optional[int] = None
    lr_address: Optional[int] = None
    stack_frame: List[int] = field(default_factory=list)
    registers: dict = field(default_factory=dict)
    raw_log: str = ""
    timestamp: Optional[float] = None

    def is_valid(self) -> bool:
        return bool(self.crash_type or self.pc_address)


class SerialReader:
    """
    UART Serial Reader for embedded hardware testing.

    Supports:
    - Blocking read with timeout
    - Pattern matching (read until marker)
    - Crash log parsing
    - Async reading for non-blocking operation
    """

    def __init__(self, config: Optional[SerialConfig] = None):
        if not PYSERIAL_AVAILABLE:
            raise ImportError("pyserial is required. Install with: pip install pyserial")

        self.config = config or SerialConfig()
        self._serial: Optional[serial.Serial] = None
        self._is_open: bool = False

    def _get_port(self) -> str:
        """Resolve port from src.core.config or auto-detect."""
        if self.config.port and self.config.port != "auto":
            return self.config.port

        ports = list(serial.tools.list_ports.comports())
        if not ports:
            raise RuntimeError("No serial ports found")

        for port in ports:
            if "STM" in port.description or "STLink" in port.description:
                logger.info(f"Auto-detected STM32 port: {port.device}")
                return port.device

        logger.info(f"Using first available port: {ports[0].device}")
        return ports[0].device

    def open(self) -> bool:
        """Open serial connection."""
        if self._is_open:
            return True

        try:
            port = self._get_port()
            self._serial = serial.Serial(
                port=port,
                baudrate=self.config.baudrate,
                bytesize=self.config.bytesize,
                parity=self.config.parity,
                stopbits=self.config.stopbits,
                timeout=self.config.timeout,
                xonxoff=self.config.xonxoff,
                rtscts=self.config.rtscts,
            )
            self._is_open = True
            logger.info(f"Serial port opened: {port} @ {self.config.baudrate} baud")
            return True
        except Exception as e:
            logger.error(f"Failed to open serial port: {e}")
            self._is_open = False
            return False

    def close(self) -> None:
        """Close serial connection."""
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("Serial port closed")
        self._is_open = False
        self._serial = None

    def is_open(self) -> bool:
        """Check if serial port is open."""
        return self._is_open and self._serial is not None and self._serial.is_open

    def flush_input(self) -> None:
        """Flush input buffer."""
        if self.is_open():
            self._serial.reset_input_buffer()

    def flush_output(self) -> None:
        """Flush output buffer."""
        if self.is_open():
            self._serial.reset_output_buffer()

    def read_available(self, max_bytes: int = 4096) -> str:
        """Read all available bytes from serial port."""
        if not self.is_open():
            return ""

        try:
            if self._serial.in_waiting > 0:
                data = self._serial.read(min(self._serial.in_waiting, max_bytes))
                return data.decode('utf-8', errors='replace')
        except Exception as e:
            logger.error(f"Read error: {e}")
        return ""

    def read_until(
        self,
        marker: str,
        timeout: float = 5.0,
        strip_chars: str = "\r\n",
    ) -> ReadResult:
        """
        Read until marker is found or timeout.

        Args:
            marker: String to wait for
            timeout: Maximum seconds to wait
            strip_chars: Characters to strip from result

        Returns:
            ReadResult with status and data
        """
        if not self.is_open():
            return ReadResult(status=ReadStatus.PORT_NOT_OPEN)

        start = time.time()
        buffer = ""

        while (time.time() - start) < timeout:
            if self._serial.in_waiting > 0:
                try:
                    data = self._serial.read(self._serial.in_waiting)
                    buffer += data.decode('utf-8', errors='replace')

                    if marker in buffer:
                        duration = time.time() - start
                        return ReadResult(
                            status=ReadStatus.SUCCESS,
                            data=buffer.strip(strip_chars),
                            bytes_read=len(buffer),
                            duration_seconds=duration,
                            matched_pattern=marker,
                        )
                except Exception as e:
                    return ReadResult(
                        status=ReadStatus.ERROR,
                        error=str(e),
                        duration_seconds=time.time() - start,
                    )

            time.sleep(0.01)

        return ReadResult(
            status=ReadStatus.TIMEOUT,
            data=buffer.strip(strip_chars),
            bytes_read=len(buffer),
            duration_seconds=timeout,
        )

    def read_for(
        self,
        duration: float,
        strip_chars: str = "\r\n",
    ) -> ReadResult:
        """
        Read for a fixed duration.

        Args:
            duration: Seconds to read
            strip_chars: Characters to strip from result

        Returns:
            ReadResult with all collected data
        """
        if not self.is_open():
            return ReadResult(status=ReadStatus.PORT_NOT_OPEN)

        start = time.time()
        buffer = ""

        while (time.time() - start) < duration:
            if self._serial.in_waiting > 0:
                try:
                    data = self._serial.read(self._serial.in_waiting)
                    buffer += data.decode('utf-8', errors='replace')
                except Exception as e:
                    return ReadResult(
                        status=ReadStatus.ERROR,
                        data=buffer,
                        error=str(e),
                        duration_seconds=time.time() - start,
                    )
            time.sleep(0.01)

        if buffer:
            return ReadResult(
                status=ReadStatus.SUCCESS,
                data=buffer.strip(strip_chars),
                bytes_read=len(buffer),
                duration_seconds=duration,
            )

        return ReadResult(
            status=ReadStatus.NO_DATA,
            duration_seconds=duration,
        )

    def read_line(self, timeout: Optional[float] = None) -> ReadResult:
        """Read one line (until newline)."""
        timeout = timeout or self.config.timeout
        return self.read_until("\n", timeout=timeout)

    def write(self, data: str) -> int:
        """Write string to serial port."""
        if not self.is_open():
            return 0

        try:
            self._serial.write(data.encode('utf-8'))
            return len(data)
        except Exception as e:
            logger.error(f"Write error: {e}")
            return 0

    def parse_crash_log(self, raw_output: str) -> Optional[CrashLog]:
        """
        Parse crash log from raw serial output.

        Supports common crash log formats:
        - HardFault: "HardFault! PC=0x08001234 LR=0x08005678"
        - Assert: "ASSERT failed: file.c:42"
        - Generic error: "ERROR: ..."
        """
        crash = CrashLog(raw_log=raw_output, timestamp=time.time())

        # HardFault pattern
        hf_match = re.search(
            r"HardFault[^\w]*.*?(?:PC=0x([0-9A-Fa-f]+))?.*?(?:LR=0x([0-9A-Fa-f]+))?",
            raw_output,
            re.IGNORECASE
        )
        if hf_match:
            crash.crash_type = "HardFault"
            if hf_match.group(1):
                crash.pc_address = int(hf_match.group(1), 16)
            if hf_match.group(2):
                crash.lr_address = int(hf_match.group(2), 16)

        # Assert pattern
        assert_match = re.search(
            r"ASSERT[^\w]+(?:failed|error)[^\w:]*:\s*(\w+\.c):(\d+)",
            raw_output,
            re.IGNORECASE
        )
        if assert_match:
            crash.crash_type = f"Assert({assert_match.group(1)}:{assert_match.group(2)})"

        # Generic error
        if not crash.crash_type:
            error_match = re.search(r"(?:ERROR|FATAL|FAULT):\s*(.+)", raw_output, re.IGNORECASE)
            if error_match:
                crash.crash_type = f"Error: {error_match.group(1).strip()}"

        # Stack frame addresses
        stack_addrs = re.findall(r"0x([0-9A-Fa-f]{8})", raw_output)
        for addr in stack_addrs:
            try:
                crash.stack_frame.append(int(addr, 16))
            except ValueError:
                pass

        return crash if crash.is_valid() else None

    def detect_success_pattern(
        self,
        output: str,
        patterns: Optional[List[str]] = None,
    ) -> bool:
        """
        Detect success from output patterns.

        Default success patterns:
        - "[OK]", "[SUCCESS]", "[PASSED]"
        - "Init complete", "System ready"
        - No error keywords
        """
        if not output:
            return False

        success_patterns = patterns or [
            r"\[OK\]",
            r"\[SUCCESS\]",
            r"\[PASSED\]",
            r"Init\s+complete",
            r"System\s+ready",
            r"Started",
            r"Ready",
        ]

        error_patterns = [
            r"ERROR",
            r"FAULT",
            r"FAILED",
            r"FAIL",
            r"Hang",
            r"Crash",
            r"Assert",
        ]

        for pattern in error_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                return False

        for pattern in success_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                return True

        return False

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


async def async_read_until(
    reader: SerialReader,
    marker: str,
    timeout: float = 5.0,
) -> ReadResult:
    """Async wrapper for read_until."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, reader.read_until, marker, timeout)


async def async_read_for(
    reader: SerialReader,
    duration: float,
) -> ReadResult:
    """Async wrapper for read_for."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, reader.read_for, duration)


def list_available_ports() -> List[dict]:
    """List all available serial ports."""
    if not PYSERIAL_AVAILABLE:
        return []

    ports = []
    for port in serial.tools.list_ports.comports():
        ports.append({
            "device": port.device,
            "name": port.name,
            "description": port.description,
            "hwid": port.hwid,
        })
    return ports


if __name__ == "__main__":
    print("Available serial ports:")
    for p in list_available_ports():
        print(f"  {p['device']}: {p['description']}")

    print("\nExample usage:")
    print("  reader = SerialReader(port='COM3', baudrate=115200)")
    print("  with SerialReader() as reader:")
    print("      result = reader.read_until('[OK]', timeout=5.0)")
    print("      print(result.data)")
