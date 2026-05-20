"""Serial/UART monitor for embedded target output."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Generator

from .embedded_target import SerialConfig


class SerialError(Exception):
    """Serial monitor errors."""
    pass


@dataclass
class SerialLine:
    """Serial line data."""
    
    text: str
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "target"  # target, host
    raw: bytes = b""


@dataclass
class PatternMatch:
    """Pattern match result."""
    
    pattern: str
    match: re.Match
    line: SerialLine
    group_values: dict[str, str] = field(default_factory=dict)


class SerialMonitor:
    """UART/Serial port monitor."""
    
    def __init__(self, config: SerialConfig | None = None):
        self.config = config or SerialConfig()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._running = False
        self._pattern_handlers: list[tuple[re.Pattern, Callable[[PatternMatch], None]]] = []
        self._line_buffer: asyncio.Queue[SerialLine] = asyncio.Queue()
        self._task: asyncio.Task | None = None
    
    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected
    
    async def connect(self, config: SerialConfig | None = None) -> None:
        """Connect to serial port."""
        import serial_asyncio
        
        if config:
            self.config = config
        
        if not self.config.port:
            raise SerialError("No port specified")
        
        try:
            protocol_factory = lambda: asyncio.Protocol()
            self._reader, self._writer = await serial_asyncio.open_serial_connection(
                url=self.config.port,
                baudrate=self.config.baudrate,
                bytesize=self.config.bytesize,
                parity=self.config.parity,
                stopbits=self.config.stopbits,
                timeout=self.config.timeout,
            )
            self._connected = True
            
            # Start read task
            self._running = True
            self._task = asyncio.create_task(self._read_loop())
            
        except Exception as e:
            raise SerialError(f"Failed to connect to {self.config.port}: {e}")
    
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
        
        self._connected = False
        self._reader = None
        self._writer = None
    
    async def _read_loop(self) -> None:
        """Read loop."""
        buffer = b""
        
        while self._running and self._reader:
            try:
                data = await asyncio.wait_for(
                    self._reader.read(1024),
                    timeout=0.1,
                )
                
                if not data:
                    break
                
                buffer += data
                
                # Process complete lines
                while b"\n" in buffer or b"\r" in buffer:
                    # Find line ending
                    if b"\r\n" in buffer:
                        line_end = buffer.index(b"\r\n")
                        line_data = buffer[:line_end]
                        buffer = buffer[line_end + 2:]
                    elif b"\n" in buffer:
                        line_end = buffer.index(b"\n")
                        line_data = buffer[:line_end]
                        buffer = buffer[line_end + 1:]
                    elif b"\r" in buffer:
                        line_end = buffer.index(b"\r")
                        line_data = buffer[:line_end]
                        buffer = buffer[line_end + 1:]
                    else:
                        break
                    
                    if line_data:
                        text = line_data.decode("utf-8", errors="replace")
                        line = SerialLine(text=text, raw=line_data)
                        
                        await self._line_buffer.put(line)
                        self._check_patterns(line)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                if self._running:
                    print(f"Serial read error: {e}")
                break
    
    def _check_patterns(self, line: SerialLine) -> None:
        """Check line against registered patterns."""
        for pattern, handler in self._pattern_handlers:
            match = pattern.search(line.text)
            if match:
                group_dict = match.groupdict() if match.groupdict() else {}
                pattern_match = PatternMatch(
                    pattern=pattern.pattern,
                    match=match,
                    line=line,
                    group_values=group_dict,
                )
                try:
                    handler(pattern_match)
                except Exception as e:
                    print(f"Pattern handler error: {e}")
    
    def add_pattern_handler(
        self,
        pattern: str,
        handler: Callable[[PatternMatch], None],
    ) -> None:
        """Add a pattern match handler."""
        compiled = re.compile(pattern)
        self._pattern_handlers.append((compiled, handler))
    
    def remove_pattern_handler(self, pattern: str) -> None:
        """Remove a pattern handler."""
        for i, (p, _) in enumerate(self._pattern_handlers):
            if p.pattern == pattern:
                del self._pattern_handlers[i]
                break
    
    async def read_line(self, timeout: float = 1.0) -> SerialLine | None:
        """Read one line."""
        try:
            return await asyncio.wait_for(
                self._line_buffer.get(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return None
    
    async def read_lines(
        self,
        count: int,
        timeout: float = 1.0,
    ) -> list[SerialLine]:
        """Read multiple lines."""
        lines = []
        for _ in range(count):
            line = await self.read_line(timeout=timeout)
            if line is None:
                break
            lines.append(line)
        return lines
    
    async def read_until(
        self,
        pattern: str,
        timeout: float = 5.0,
    ) -> tuple[list[SerialLine], PatternMatch | None]:
        """Read until pattern matches."""
        compiled = re.compile(pattern)
        lines: list[SerialLine] = []
        start_time = asyncio.get_event_loop().time()
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            remaining = timeout - elapsed
            
            if remaining <= 0:
                break
            
            line = await self.read_line(timeout=remaining)
            if line is None:
                break
            
            lines.append(line)
            
            match = compiled.search(line.text)
            if match:
                pattern_match = PatternMatch(
                    pattern=pattern,
                    match=match,
                    line=line,
                    group_values=match.groupdict() or {},
                )
                return lines, pattern_match
        
        return lines, None
    
    async def write(self, data: str) -> None:
        """Write to serial port."""
        if not self._writer:
            raise SerialError("Not connected")
        
        self._writer.write(data.encode("utf-8"))
        await self._writer.drain()
        
        # Add to buffer for tracking
        line = SerialLine(text=data, source="host")
        await self._line_buffer.put(line)
    
    async def writeline(self, data: str) -> None:
        """Write line to serial port."""
        await self.write(data + "\n")
    
    def lines(self, timeout: float = 1.0) -> Generator[SerialLine, None, None]:
        """Generator for reading lines."""
        while self._connected:
            try:
                line = asyncio.get_event_loop().run_until_complete(
                    self.read_line(timeout=timeout)
                )
                if line is None:
                    break
                yield line
            except RuntimeError:
                break
    
    async def detect_baudrate(self) -> int:
        """Auto-detect baudrate."""
        # TODO: Implement baudrate detection
        # Send break, measure response timing
        return self.config.baudrate
    
    async def flush(self) -> None:
        """Flush input buffer."""
        while not self._line_buffer.empty():
            try:
                self._line_buffer.get_nowait()
            except asyncio.QueueEmpty:
                break
    
    async def get_buffer_stats(self) -> dict:
        """Get buffer statistics."""
        return {
            "connected": self._connected,
            "buffer_size": self._line_buffer.qsize(),
            "pattern_handlers": len(self._pattern_handlers),
        }


class LogCapture:
    """Capture serial output for analysis."""
    
    def __init__(self, monitor: SerialMonitor):
        self.monitor = monitor
        self._captured: list[SerialLine] = []
        self._capturing = False
    
    async def start_capture(self) -> None:
        """Start capturing."""
        self._capturing = True
        self._captured.clear()
    
    async def capture(
        self,
        duration: float,
    ) -> list[SerialLine]:
        """Capture for duration."""
        await self.start_capture()
        
        end_time = asyncio.get_event_loop().time() + duration
        
        while asyncio.get_event_loop().time() < end_time:
            line = await self.monitor.read_line(timeout=1.0)
            if line:
                self._captured.append(line)
        
        await self.stop_capture()
        return self._captured
    
    async def stop_capture(self) -> list[SerialLine]:
        """Stop capturing."""
        self._capturing = False
        return self._captured
    
    def get_lines(self) -> list[SerialLine]:
        """Get captured lines."""
        return self._captured.copy()
    
    def filter_lines(
        self,
        pattern: str | None = None,
        source: str | None = None,
    ) -> list[SerialLine]:
        """Filter captured lines."""
        lines = self._captured
        
        if pattern:
            compiled = re.compile(pattern)
            lines = [l for l in lines if compiled.search(l.text)]
        
        if source:
            lines = [l for l in lines if l.source == source]
        
        return lines
    
    def get_text(self) -> str:
        """Get captured text."""
        return "\n".join(line.text for line in self._captured)
    
    def clear(self) -> None:
        """Clear captured lines."""
        self._captured.clear()
