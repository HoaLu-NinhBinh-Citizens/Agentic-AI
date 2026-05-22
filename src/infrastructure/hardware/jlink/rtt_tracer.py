"""Real-time tracing via RTT (Phase 6.3)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from src.domain.hardware.probe import RegisterValue

from .rtt import RTTReader
from .rtt import RTTChannelConfig, RTTControlBlock

logger = logging.getLogger(__name__)

DEFAULT_TRACE_BUFFER_LINES = 500
DEFAULT_POLL_INTERVAL_S = 0.1


class WatchpointKind(Enum):
    """Memory watch trigger type."""

    READ = "read"
    WRITE = "write"
    CHANGE = "change"


@dataclass(frozen=True)
class MemoryWatchpoint:
    """Memory region to poll for changes."""

    address: int
    size: int
    kind: WatchpointKind = WatchpointKind.CHANGE
    label: str = ""


@dataclass
class TraceBufferConfig:
    """Trace ring buffer settings."""

    max_entries: int = DEFAULT_TRACE_BUFFER_LINES
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S


@dataclass
class TraceEntry:
    """Single trace log line."""

    timestamp: float
    source: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


class RealTimeTracer:
    """Live register/memory/RTT tracing."""

    def __init__(
        self,
        probe: Any,
        rtt_reader: RTTReader | None = None,
        config: TraceBufferConfig | None = None,
    ) -> None:
        self._probe = probe
        self._rtt = rtt_reader
        self._config = config or TraceBufferConfig()
        self._buffer: deque[TraceEntry] = deque(maxlen=self._config.max_entries)
        self._watchpoints: list[MemoryWatchpoint] = []
        self._last_memory: dict[int, bytes] = {}
        self._register_names: list[str] = []
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._on_entry: Callable[[TraceEntry], None] | None = None

    @property
    def entries(self) -> list[TraceEntry]:
        return list(self._buffer)

    def set_callback(self, handler: Callable[[TraceEntry], None]) -> None:
        self._on_entry = handler

    def add_watchpoint(self, wp: MemoryWatchpoint) -> None:
        self._watchpoints.append(wp)

    def track_registers(self, names: list[str]) -> None:
        self._register_names = [n.lower() for n in names]

    async def sample_registers(self) -> list[RegisterValue]:
        """Read tracked registers once."""
        results: list[RegisterValue] = []
        for name in self._register_names:
            try:
                reg = await self._probe.read_register(name)
                results.append(reg)
                self._append("register", f"{reg.name}=0x{reg.value:08X}", {"register": reg.name})
            except Exception as exc:
                logger.debug("register read %s: %s", name, exc)
        return results

    async def sample_watchpoints(self) -> int:
        """Poll watchpoints; return number of changes detected."""
        changes = 0
        for wp in self._watchpoints:
            result = await self._probe.read_memory(wp.address, wp.size)
            if not result.success:
                continue
            prev = self._last_memory.get(wp.address)
            self._last_memory[wp.address] = result.data
            if prev is None:
                continue
            if prev != result.data:
                changes += 1
                label = wp.label or f"0x{wp.address:08X}"
                self._append("watchpoint", f"{label} changed", {"address": wp.address})
        return changes

    def _append(self, source: str, message: str, data: dict[str, Any] | None = None) -> None:
        entry = TraceEntry(time.time(), source, message, data or {})
        self._buffer.append(entry)
        if self._on_entry:
            self._on_entry(entry)

    async def _trace_loop(self) -> None:
        while self._running:
            await self.sample_registers()
            await self.sample_watchpoints()
            if self._rtt:
                ch = self._rtt.get_channel(0)
                if ch and ch.bytes_available:
                    data = ch.read(512)
                    if data:
                        text = data.decode("utf-8", errors="replace").strip()
                        if text:
                            self._append("rtt", text, {"bytes": len(data)})
            await asyncio.sleep(self._config.poll_interval_s)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._trace_loop())

    async def stop(self) -> None:
        self._running = False
        if self._rtt:
            self._rtt.stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    @classmethod
    def create_with_rtt(
        cls,
        probe: Any,
        rtt_base: int = 0x20000000,
        buffer_config: TraceBufferConfig | None = None,
    ) -> RealTimeTracer:
        """Factory with default RTT control block."""
        cb = RTTControlBlock(
            base_address=rtt_base,
            channels=[RTTChannelConfig()],
        )
        reader = RTTReader(cb)
        return cls(probe, rtt_reader=reader, config=buffer_config)
