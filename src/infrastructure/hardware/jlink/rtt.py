"""SEGGER RTT channel support (Phase 6.1 / 6.3)."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator

from .config import DEFAULT_RTT_BUFFER_SIZE, DEFAULT_RTT_UP_CHANNEL

logger = logging.getLogger(__name__)

RTT_MAGIC = b"SEGGER RTT"
RTT_CB_SIZE = 24


class RTTDirection(Enum):
    """RTT buffer direction."""

    UP = "up"
    DOWN = "down"


@dataclass
class RTTChannelConfig:
    """Configuration for one RTT channel."""

    index: int = DEFAULT_RTT_UP_CHANNEL
    name: str = "Terminal"
    buffer_size: int = DEFAULT_RTT_BUFFER_SIZE
    direction: RTTDirection = RTTDirection.UP


@dataclass
class RTTControlBlock:
    """Parsed RTT control block metadata."""

    base_address: int
    num_up_channels: int = 1
    num_down_channels: int = 1
    channels: list[RTTChannelConfig] = field(default_factory=list)


@dataclass
class RTTChannel:
    """Runtime RTT channel with ring buffer."""

    config: RTTChannelConfig
    _buffer: deque[bytes] = field(default_factory=deque)
    _write_index: int = 0
    _read_index: int = 0

    def write(self, data: bytes) -> int:
        """Append data (target → host up-channel simulation)."""
        if not data:
            return 0
        self._buffer.append(data)
        self._write_index += len(data)
        while len(self._buffer) > self.config.buffer_size:
            self._buffer.popleft()
        return len(data)

    def read(self, max_size: int) -> bytes:
        """Read available data from channel."""
        if not self._buffer or max_size <= 0:
            return b""
        chunks: list[bytes] = []
        remaining = max_size
        while self._buffer and remaining > 0:
            chunk = self._buffer.popleft()
            if len(chunk) <= remaining:
                chunks.append(chunk)
                remaining -= len(chunk)
            else:
                chunks.append(chunk[:remaining])
                self._buffer.appendleft(chunk[remaining:])
                remaining = 0
        data = b"".join(chunks)
        self._read_index += len(data)
        return data

    @property
    def bytes_available(self) -> int:
        return sum(len(c) for c in self._buffer)


class RTTReader:
    """Async RTT up-channel reader."""

    def __init__(
        self,
        control_block: RTTControlBlock,
        poll_interval_s: float = 0.05,
    ) -> None:
        self._cb = control_block
        self._poll_interval_s = poll_interval_s
        self._channels: dict[int, RTTChannel] = {}
        self._running = False
        for cfg in control_block.channels or [RTTChannelConfig()]:
            self._channels[cfg.index] = RTTChannel(config=cfg)

    def get_channel(self, index: int) -> RTTChannel | None:
        return self._channels.get(index)

    def inject(self, index: int, data: bytes) -> int:
        """Inject data (mock / test hook)."""
        ch = self._channels.get(index)
        if ch is None:
            return 0
        return ch.write(data)

    async def read_stream(
        self,
        channel_index: int = DEFAULT_RTT_UP_CHANNEL,
        chunk_size: int = 256,
    ) -> AsyncIterator[bytes]:
        """Yield RTT data until stopped."""
        self._running = True
        ch = self._channels.get(channel_index)
        if ch is None:
            self._running = False
            return
        try:
            while self._running:
                data = ch.read(chunk_size)
                if data:
                    yield data
                else:
                    await asyncio.sleep(self._poll_interval_s)
        finally:
            self._running = False

    def stop(self) -> None:
        self._running = False
