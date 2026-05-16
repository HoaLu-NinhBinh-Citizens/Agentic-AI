"""
UART Monitor for Hardware-in-the-Loop Testing

Provides real-time serial output monitoring from STM32 devices.
Supports:
- Configurable baudrate, data bits, parity, stop bits
- Non-blocking async reading with buffering
- Line-based parsing with timestamps
- Pattern matching for error detection
- Export to file for analysis
"""

import asyncio
import logging
import re
import serial
import serial.tools.list_ports
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Dict, Any
from threading import Thread
import io

logger = logging.getLogger(__name__)


@dataclass
class UartConfig:
    """UART connection configuration."""
    port: str = "COM3"
    baudrate: int = 115200
    bytesize: int = serial.EIGHTBITS
    parity: str = serial.PARITY_NONE
    stopbits: float = serial.STOPBITS_ONE
    timeout: float = 1.0
    rtscts: bool = False
    xonxoff: bool = False

    def to_serial_kwargs(self) -> Dict[str, Any]:
        """Convert to serial library kwargs."""
        return {
            "baudrate": self.baudrate,
            "bytesize": self.bytesize,
            "parity": self.parity,
            "stopbits": self.stopbits,
            "timeout": self.timeout,
            "rtscts": self.rtscts,
            "xonxoff": self.xonxoff,
        }


@dataclass
class UartMessage:
    """Represents a single UART message/line."""
    timestamp: datetime
    data: str
    raw_bytes: bytes
    source: str
    is_error: bool = False
    is_warning: bool = False
    severity: str = "INFO"

    @classmethod
    def from_line(cls, line: str, raw: bytes, source: str) -> "UartMessage":
        """Parse a UART line and detect severity."""
        line_lower = line.lower()

        is_error = any(kw in line_lower for kw in ["error", "fail", "fault", "critical", "exception"])
        is_warning = any(kw in line_lower for kw in ["warn", "caution", "notice"])

        severity = "ERROR" if is_error else "WARNING" if is_warning else "INFO"

        return cls(
            timestamp=datetime.now(),
            data=line,
            raw_bytes=raw,
            source=source,
            is_error=is_error,
            is_warning=is_warning,
            severity=severity,
        )


class UartMonitor:
    """
    Real-time UART monitoring for hardware testing.

    Features:
    - Async read loop with buffering
    - Pattern matching for log parsing
    - Error/warning detection
    - Export to file
    - Callback-based event handling
    """

    def __init__(self, config: Optional[UartConfig] = None):
        self.config = config or UartConfig()
        self._serial: Optional[serial.Serial] = None
        self._running = False
        self._read_thread: Optional[Thread] = None
        self._buffer: List[UartMessage] = []
        self._max_buffer_size = 10000
        self._lock = asyncio.Lock()

        # Callbacks
        self._on_message: List[Callable[[UartMessage], None]] = []
        self._on_error: List[Callable[[UartMessage], None]] = []
        self._on_warning: List[Callable[[UartMessage], None]] = []

        # Statistics
        self._stats = {
            "bytes_received": 0,
            "lines_received": 0,
            "errors_detected": 0,
            "warnings_detected": 0,
        }

    # -------------------------------------------------------------------------
    # Connection Management
    # -------------------------------------------------------------------------

    async def connect(self) -> bool:
        """Connect to UART port."""
        if self._serial and self._serial.is_open:
            logger.warning("Already connected to %s", self.config.port)
            return True

        try:
            self._serial = serial.Serial(
                port=self.config.port,
                **self.config.to_serial_kwargs()
            )
            logger.info("Connected to UART %s at %d baud", self.config.port, self.config.baudrate)
            return True
        except serial.SerialException as exc:
            logger.error("Failed to connect to %s: %s", self.config.port, exc)
            return False

    async def disconnect(self) -> None:
        """Disconnect from UART port."""
        self._running = False

        if self._read_thread and self._read_thread.is_alive():
            self._read_thread.join(timeout=2.0)

        if self._serial:
            try:
                self._serial.close()
                logger.info("Disconnected from UART")
            except Exception as exc:
                logger.error("Error closing serial: %s", exc)

    async def is_connected(self) -> bool:
        """Check if connected to UART."""
        return self._serial is not None and self._serial.is_open

    # -------------------------------------------------------------------------
    # Monitoring
    # -------------------------------------------------------------------------

    async def start_monitoring(self) -> None:
        """Start monitoring UART in background thread."""
        if self._running:
            logger.warning("Already monitoring")
            return

        if not await self.is_connected():
            if not await self.connect():
                raise RuntimeError("Cannot start monitoring: not connected")

        self._running = True
        self._read_thread = Thread(target=self._read_loop, daemon=True)
        self._read_thread.start()
        logger.info("UART monitoring started")

    async def stop_monitoring(self) -> None:
        """Stop monitoring UART."""
        self._running = False
        if self._read_thread:
            self._read_thread.join(timeout=2.0)
        logger.info("UART monitoring stopped")

    def _read_loop(self) -> None:
        """Background thread for reading serial data."""
        buffer = io.BytesIO()

        while self._running:
            try:
                if self._serial and self._serial.in_waiting > 0:
                    data = self._serial.read(self._serial.in_waiting)
                    self._stats["bytes_received"] += len(data)
                    buffer.write(data)

                    # Process complete lines
                    content = buffer.getvalue()
                    lines = content.split(b'\n')

                    # Keep incomplete last line in buffer
                    if not content.endswith(b'\n'):
                        buffer = io.BytesIO(lines[-1])
                    else:
                        buffer = io.BytesIO()

                    for line_bytes in lines[:-1]:
                        self._process_line(line_bytes + b'\n')

                else:
                    if buffer.getvalue():
                        content = buffer.getvalue()
                        self._process_line(content)
                        buffer = io.BytesIO()
                    asyncio.sleep(0.01)

            except Exception as exc:
                logger.error("UART read error: %s", exc)
                asyncio.sleep(0.1)

    def _process_line(self, raw: bytes) -> None:
        """Process a received line."""
        try:
            text = raw.decode('utf-8', errors='replace').strip()
        except Exception:
            text = raw.decode('latin-1', errors='replace').strip()

        if not text:
            return

        self._stats["lines_received"] += 1
        msg = UartMessage.from_line(text, raw, self.config.port)

        # Update statistics
        if msg.is_error:
            self._stats["errors_detected"] += 1
            for cb in self._on_error:
                try:
                    cb(msg)
                except Exception as exc:
                    logger.error("Error in error callback: %s", exc)
        elif msg.is_warning:
            self._stats["warnings_detected"] += 1
            for cb in self._on_warning:
                try:
                    cb(msg)
                except Exception as exc:
                    logger.error("Error in warning callback: %s", exc)

        for cb in self._on_message:
            try:
                cb(msg)
            except Exception as exc:
                logger.error("Error in message callback: %s", exc)

        # Add to buffer
        self._add_to_buffer(msg)

    def _add_to_buffer(self, msg: UartMessage) -> None:
        """Add message to circular buffer."""
        self._buffer.append(msg)
        if len(self._buffer) > self._max_buffer_size:
            self._buffer.pop(0)

    # -------------------------------------------------------------------------
    # Callbacks
    # -------------------------------------------------------------------------

    def on_message(self, callback: Callable[[UartMessage], None]) -> None:
        """Register message callback."""
        self._on_message.append(callback)

    def on_error(self, callback: Callable[[UartMessage], None]) -> None:
        """Register error callback."""
        self._on_error.append(callback)

    def on_warning(self, callback: Callable[[UartMessage], None]) -> None:
        """Register warning callback."""
        self._on_warning.append(callback)

    # -------------------------------------------------------------------------
    # Query Methods
    # -------------------------------------------------------------------------

    async def get_messages(
        self,
        since: Optional[datetime] = None,
        severity: Optional[str] = None,
        pattern: Optional[str] = None,
        limit: int = 100,
    ) -> List[UartMessage]:
        """Get messages from buffer with filters."""
        async with self._lock:
            messages = list(self._buffer)

        if since:
            messages = [m for m in messages if m.timestamp >= since]

        if severity:
            messages = [m for m in messages if m.severity == severity.upper()]

        if pattern:
            regex = re.compile(pattern, re.IGNORECASE)
            messages = [m for m in messages if regex.search(m.data)]

        return messages[-limit:]

    async def get_errors(self, limit: int = 50) -> List[UartMessage]:
        """Get error messages."""
        return await self.get_messages(severity="ERROR", limit=limit)

    async def get_warnings(self, limit: int = 50) -> List[UartMessage]:
        """Get warning messages."""
        return await self.get_messages(severity="WARNING", limit=limit)

    async def get_stats(self) -> Dict[str, Any]:
        """Get monitoring statistics."""
        return dict(self._stats)

    async def clear_buffer(self) -> None:
        """Clear message buffer."""
        async with self._lock:
            self._buffer.clear()

    # -------------------------------------------------------------------------
    # Export
    # -------------------------------------------------------------------------

    async def export(self, filepath: Path, format: str = "txt") -> bool:
        """
        Export messages to file.

        Args:
            filepath: Output file path
            format: "txt" or "json"
        """
        messages = await self.get_messages(limit=self._max_buffer_size)

        try:
            if format == "json":
                import json
                data = [
                    {
                        "timestamp": m.timestamp.isoformat(),
                        "severity": m.severity,
                        "data": m.data,
                        "source": m.source,
                    }
                    for m in messages
                ]
                filepath.write_text(json.dumps(data, indent=2), encoding='utf-8')
            else:
                lines = []
                for m in messages:
                    ts = m.timestamp.strftime("%H:%M:%S.%f")[:-3]
                    lines.append(f"[{ts}] [{m.severity:7s}] {m.data}")
                filepath.write_text("\n".join(lines), encoding='utf-8')

            logger.info("Exported %d messages to %s", len(messages), filepath)
            return True

        except Exception as exc:
            logger.error("Export failed: %s", exc)
            return False

    # -------------------------------------------------------------------------
    # Utility
    # -------------------------------------------------------------------------

    @staticmethod
    def list_ports() -> List[Dict[str, str]]:
        """List available COM ports."""
        ports = serial.tools.list_ports.comports()
        return [
            {
                "port": p.device,
                "name": p.name,
                "description": p.description,
                "hwid": p.hwid,
            }
            for p in ports
        ]

    @staticmethod
    def auto_detect_port() -> Optional[str]:
        """
        Auto-detect STM32 device port.
        Searches for common STM32 USB VID/PID.
        """
        ports = UartMonitor.list_ports()
        for port in ports:
            desc = port.get("description", "").lower()
            hwid = port.get("hwid", "").lower()
            if any(kw in desc or kw in hwid for kw in ["stm", "stmicro", "usb serial", "virtual com"]):
                logger.info("Auto-detected STM32 on %s", port["port"])
                return port["port"]
        return None
