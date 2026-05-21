"""Serial Monitor - UART log capture and pattern detection.

Phase 6.5: Serial monitor for firmware debugging
- UART log capture with configurable baudrate
- Pattern detection (error keywords, timestamps)
- Log buffering and export
- Non-blocking async streaming
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Callable

import serial_asyncio

logger = __import__("structlog").get_logger(__name__)


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


@dataclass
class LogEntry:
    """Single log entry from serial output."""
    
    timestamp: float
    level: LogLevel
    message: str
    source: str = "UART"
    raw_line: str = ""
    line_number: int = 0
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "level": self.level.value,
            "message": self.message,
            "source": self.source,
            "line_number": self.line_number,
        }


@dataclass
class SerialMonitorConfig:
    """Configuration for serial monitor."""
    
    port: str = "/dev/ttyUSB0"
    baudrate: int = 115200
    bytesize: int = 8
    parity: str = "N"
    stopbits: int = 1
    timeout: float = 1.0
    
    # Buffer settings
    max_buffer_size: int = 10000
    flush_interval_seconds: float = 5.0
    
    # Pattern settings
    error_patterns: list[str] = field(default_factory=lambda: [
        r"(?i)error",
        r"(?i)fail(ed)?",
        r"(?i)exception",
        r"(?i)fault",
        r"(?i)panic",
        r"(?i)assert",
        r"(?i)abort",
        r"(?i)hardfault",
        r"(?i)memfault",
        r"(?i)busfault",
        r"(?i)usagefault",
    ])
    
    warning_patterns: list[str] = field(default_factory=lambda: [
        r"(?i)warning",
        r"(?i)warn",
    ])
    
    timestamp_patterns: list[str] = field(default_factory=lambda: [
        r"^\[?(\d{2}:\d{2}:\d{2})",
        r"^\[?(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})",
        r"^\[?(\d+\.\d+)",
    ])


@dataclass
class SerialMonitorStats:
    """Statistics for serial monitor."""
    
    bytes_received: int = 0
    lines_received: int = 0
    errors_detected: int = 0
    warnings_detected: int = 0
    start_time: float = field(default_factory=time.time)
    last_error_time: float = 0.0
    
    def uptime_seconds(self) -> float:
        return time.time() - self.start_time


class SerialMonitor:
    """Async serial monitor for UART log capture.
    
    Features:
    - Non-blocking async UART reading
    - Pattern detection (errors, warnings, timestamps)
    - Log buffering with configurable size
    - Callback-based event handling
    - Export to file/buffer
    """
    
    def __init__(
        self,
        config: SerialMonitorConfig | None = None,
        on_error: Callable[[LogEntry], None] | None = None,
        on_warning: Callable[[LogEntry], None] | None = None,
        on_line: Callable[[LogEntry], None] | None = None,
    ):
        self.config = config or SerialMonitorConfig()
        self.on_error = on_error
        self.on_warning = on_warning
        self.on_line = on_line
        
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._running = False
        self._task: asyncio.Task | None = None
        
        self._buffer: list[LogEntry] = []
        self._stats = SerialMonitorStats()
        
        # Compile patterns for efficiency
        self._error_patterns = [
            re.compile(p) for p in self.config.error_patterns
        ]
        self._warning_patterns = [
            re.compile(p) for p in self.config.warning_patterns
        ]
        self._timestamp_patterns = [
            re.compile(p) for p in self.config.timestamp_patterns
        ]
    
    @property
    def stats(self) -> SerialMonitorStats:
        """Get current statistics."""
        return self._stats
    
    @property
    def buffer(self) -> list[LogEntry]:
        """Get current log buffer."""
        return self._buffer.copy()
    
    async def connect(self) -> bool:
        """Connect to serial port.
        
        Returns:
            True if connection successful.
        """
        try:
            self._reader, self._writer = await serial_asyncio.open_serial_connection(
                url=self.config.port,
                baudrate=self.config.baudrate,
                bytesize=self.config.bytesize,
                parity=self.config.parity,
                stopbits=self.config.stopbits,
            )
            self._running = True
            logger.info("serial_connected", 
                       port=self.config.port, 
                       baudrate=self.config.baudrate)
            return True
        except Exception as e:
            logger.error("serial_connect_failed", port=self.config.port, error=str(e))
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from serial port."""
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
        
        self._reader = None
        self._writer = None
        logger.info("serial_disconnected", port=self.config.port)
    
    async def start(self) -> None:
        """Start monitoring in background task."""
        if not self._reader:
            if not await self.connect():
                raise RuntimeError(f"Failed to connect to {self.config.port}")
        
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("serial_monitor_started", port=self.config.port)
    
    async def stop(self) -> None:
        """Stop monitoring."""
        await self.disconnect()
        logger.info("serial_monitor_stopped")
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        line_number = 0
        
        try:
            while self._running and self._reader:
                try:
                    line = await asyncio.wait_for(
                        self._reader.readline(),
                        timeout=self.config.timeout
                    )
                    
                    if not line:
                        continue
                    
                    line_number += 1
                    self._stats.bytes_received += len(line)
                    
                    decoded_line = line.decode("utf-8", errors="replace").strip()
                    
                    if decoded_line:
                        entry = self._parse_line(decoded_line, line_number)
                        self._add_to_buffer(entry)
                        self._process_entry(entry)
                        
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error("serial_read_error", error=str(e))
                    await asyncio.sleep(0.1)
                    
        except asyncio.CancelledError:
            pass
    
    def _parse_line(self, line: str, line_number: int) -> LogEntry:
        """Parse a single line into LogEntry."""
        # Detect log level
        level = self._detect_level(line)
        
        # Extract timestamp if present
        timestamp = time.time()
        for pattern in self._timestamp_patterns:
            match = pattern.search(line)
            if match:
                # For now, use current time if timestamp parsing fails
                try:
                    timestamp_str = match.group(1)
                    # Could convert to epoch here if needed
                except (IndexError, ValueError):
                    pass
                break
        
        return LogEntry(
            timestamp=timestamp,
            level=level,
            message=line,
            raw_line=line,
            line_number=line_number,
        )
    
    def _detect_level(self, line: str) -> LogLevel:
        """Detect log level from line content."""
        # Check for error patterns
        for pattern in self._error_patterns:
            if pattern.search(line):
                self._stats.errors_detected += 1
                self._stats.last_error_time = time.time()
                return LogLevel.ERROR
        
        # Check for warning patterns
        for pattern in self._warning_patterns:
            if pattern.search(line):
                self._stats.warnings_detected += 1
                return LogLevel.WARNING
        
        # Check for common log level prefixes
        line_upper = line.upper()
        if "DEBUG" in line_upper:
            return LogLevel.DEBUG
        elif "INFO" in line_upper:
            return LogLevel.INFO
        elif "WARN" in line_upper:
            return LogLevel.WARNING
        elif "ERROR" in line_upper or "ERR" in line_upper:
            return LogLevel.ERROR
        elif "CRITICAL" in line_upper or "CRIT" in line_upper:
            return LogLevel.CRITICAL
        
        return LogLevel.UNKNOWN
    
    def _add_to_buffer(self, entry: LogEntry) -> None:
        """Add entry to buffer with size limit."""
        self._buffer.append(entry)
        self._stats.lines_received += 1
        
        # Trim buffer if needed
        if len(self._buffer) > self.config.max_buffer_size:
            self._buffer = self._buffer[-self.config.max_buffer_size:]
    
    def _process_entry(self, entry: LogEntry) -> None:
        """Process entry via callbacks."""
        if entry.level == LogLevel.ERROR and self.on_error:
            self.on_error(entry)
        elif entry.level == LogLevel.WARNING and self.on_warning:
            self.on_warning(entry)
        if self.on_line:
            self.on_line(entry)
    
    async def write(self, data: str) -> None:
        """Write data to serial port."""
        if self._writer:
            self._writer.write(data.encode("utf-8"))
            await self._writer.drain()
    
    async def lines(self) -> AsyncIterator[LogEntry]:
        """Async iterator for log entries."""
        queue: asyncio.Queue[LogEntry | None] = asyncio.Queue()
        
        def on_line(entry: LogEntry) -> None:
            queue.put_nowait(entry)
        
        original_callback = self.on_line
        self.on_line = on_line
        
        try:
            if not self._running:
                await self.start()
            
            while self._running:
                entry = await queue.get()
                if entry is None:
                    break
                yield entry
        finally:
            self.on_line = original_callback
    
    def export_buffer(self) -> str:
        """Export buffer as formatted string."""
        lines = []
        for entry in self._buffer:
            level_tag = f"[{entry.level.value:8}]"
            lines.append(f"{level_tag} {entry.message}")
        return "\n".join(lines)
    
    def export_json(self) -> list[dict]:
        """Export buffer as JSON-serializable list."""
        return [entry.to_dict() for entry in self._buffer]
    
    def clear_buffer(self) -> None:
        """Clear the log buffer."""
        self._buffer.clear()
    
    def get_errors(self) -> list[LogEntry]:
        """Get all error entries from buffer."""
        return [e for e in self._buffer if e.level == LogLevel.ERROR]
    
    def get_warnings(self) -> list[LogEntry]:
        """Get all warning entries from buffer."""
        return [e for e in self._buffer if e.level == LogLevel.WARNING]
    
    async def __aenter__(self) -> SerialMonitor:
        """Context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        await self.stop()


class MultiSerialMonitor:
    """Monitor multiple serial ports simultaneously."""
    
    def __init__(self, configs: list[SerialMonitorConfig] | None = None):
        self._monitors: dict[str, SerialMonitor] = {}
        self._configs = configs or []
    
    async def add_port(
        self,
        name: str,
        config: SerialMonitorConfig,
        **callbacks,
    ) -> SerialMonitor:
        """Add a serial port to monitor."""
        monitor = SerialMonitor(config, **callbacks)
        await monitor.start()
        self._monitors[name] = monitor
        return monitor
    
    async def remove_port(self, name: str) -> None:
        """Remove a serial port from monitoring."""
        if name in self._monitors:
            await self._monitors[name].stop()
            del self._monitors[name]
    
    def get_monitor(self, name: str) -> SerialMonitor | None:
        """Get monitor by name."""
        return self._monitors.get(name)
    
    def get_all_buffers(self) -> dict[str, list[LogEntry]]:
        """Get buffers from all monitors."""
        return {name: m.buffer for name, m in self._monitors.items()}
    
    async def close_all(self) -> None:
        """Close all monitors."""
        for monitor in self._monitors.values():
            await monitor.stop()
        self._monitors.clear()
