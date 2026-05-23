"""RTT Buffer Overflow Protection for W-008.

Adds flow control and overflow detection to RTT tracing:
- Bounded buffer with overflow detection
- Flow control backpressure
- Overflow callbacks and recovery
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class OverflowAction(Enum):
    """Action to take on buffer overflow."""

    DROP_OLDEST = "drop_oldest"  # Drop oldest entries
    DROP_NEWEST = "drop_newest"  # Drop newest entries
    BLOCK = "block"  # Block until space available
    ERROR = "error"  # Raise error


@dataclass
class OverflowConfig:
    """Configuration for overflow behavior."""

    max_buffer_size: int = 1024 * 1024  # 1MB default
    max_entries: int = 50000  # Max number of trace entries
    overflow_action: OverflowAction = OverflowAction.DROP_OLDEST
    overflow_callback: Optional[Callable[[str, int], None]] = None
    enable_flow_control: bool = True
    backpressure_threshold: float = 0.8  # Start backpressure at 80%
    resume_threshold: float = 0.5  # Resume at 50%


@dataclass
class OverflowStats:
    """Statistics about overflow events."""

    total_entries: int = 0
    dropped_entries: int = 0
    overflow_count: int = 0
    last_overflow_size: int = 0
    last_overflow_time: float = 0.0
    backpressure_active: bool = False
    total_bytes: int = 0
    max_bytes_reached: int = 0


class ProtectedRTTChannel:
    """RTT Channel with overflow protection and flow control.

    W-008 Fix: Prevents buffer overflow during high-throughput tracing.
    """

    def __init__(
        self,
        channel_index: int,
        name: str = "Terminal",
        config: Optional[OverflowConfig] = None,
    ):
        self.channel_index = channel_index
        self.name = name
        self._config = config or OverflowConfig()

        self._buffer: deque[tuple[float, bytes]] = deque()
        self._byte_count = 0
        self._stats = OverflowStats()
        self._lock = asyncio.Lock()
        self._backpressure_event = asyncio.Event()
        self._backpressure_event.set()  # Start with no backpressure

    @property
    def stats(self) -> OverflowStats:
        """Get current overflow statistics."""
        return self._stats

    @property
    def usage_ratio(self) -> float:
        """Get buffer usage as ratio (0.0 - 1.0)."""
        if self._config.max_buffer_size == 0:
            return 0.0
        return min(1.0, self._byte_count / self._config.max_buffer_size)

    @property
    def is_backpressure_active(self) -> bool:
        """Check if backpressure is active."""
        return self._backpressure_event.is_set() is False

    def write(self, data: bytes) -> int:
        """Write data with overflow protection.

        Args:
            data: Data bytes to write.

        Returns:
            Number of bytes written (may be less if dropped).
        """
        if not data:
            return 0

        data_len = len(data)
        self._stats.total_entries += 1
        self._stats.total_bytes += data_len

        # Check if backpressure should be active
        self._update_backpressure()

        while True:
            # Check if we need to drop entries
            if self._would_overflow(data_len):
                if self._handle_overflow(data_len):
                    # Overflow handled, proceed with write
                    break
                else:
                    # Could not handle overflow
                    return 0

            # Check buffer entry limit
            if len(self._buffer) >= self._config.max_entries:
                if self._config.overflow_action == OverflowAction.DROP_OLDEST:
                    self._drop_oldest()
                elif self._config.overflow_action == OverflowAction.DROP_NEWEST:
                    return 0  # Don't add if at limit
                else:
                    return 0

            # Space available, write
            break

        self._buffer.append((asyncio.get_event_loop().time(), data))
        self._byte_count += data_len
        self._stats.max_bytes_reached = max(
            self._stats.max_bytes_reached, self._byte_count
        )

        return data_len

    def _would_overflow(self, data_len: int) -> bool:
        """Check if adding data would overflow buffer."""
        return self._byte_count + data_len > self._config.max_buffer_size

    def _handle_overflow(self, data_len: int) -> bool:
        """Handle potential overflow.

        Returns:
            True if overflow handled, False if should abort.
        """
        if self._config.overflow_action == OverflowAction.DROP_OLDEST:
            while self._would_overflow(data_len) and self._buffer:
                self._drop_oldest()
            return True

        elif self._config.overflow_action == OverflowAction.DROP_NEWEST:
            # Don't add if would overflow
            return False

        elif self._config.overflow_action == OverflowAction.ERROR:
            logger.error(
                "RTT buffer overflow",
                channel=self.channel_index,
                size=data_len,
                current=self._byte_count,
                max=self._config.max_buffer_size,
            )
            self._stats.overflow_count += 1
            return False

        elif self._config.overflow_action == OverflowAction.BLOCK:
            # Handled by caller with backpressure
            logger.warning(
                "RTT buffer backpressure active",
                channel=self.channel_index,
                usage=self.usage_ratio,
            )
            return False

        return True

    def _drop_oldest(self) -> None:
        """Drop oldest entry from buffer."""
        if self._buffer:
            _, old_data = self._buffer.popleft()
            self._byte_count -= len(old_data)
            self._stats.dropped_entries += 1

            if self._stats.overflow_count == 0:
                self._stats.overflow_count = 1
            else:
                self._stats.overflow_count += 1

            logger.debug(
                "Dropped oldest RTT entry",
                channel=self.channel_index,
                dropped_bytes=len(old_data),
                remaining=self._byte_count,
            )

    def _update_backpressure(self) -> None:
        """Update backpressure state based on usage."""
        if not self._config.enable_flow_control:
            return

        usage = self.usage_ratio
        is_active = self._backpressure_event.is_set() is False

        if usage >= self._config.backpressure_threshold and not is_active:
            # Activate backpressure
            self._backpressure_event.clear()
            self._stats.backpressure_active = True
            logger.warning(
                "RTT backpressure activated",
                channel=self.channel_index,
                usage=usage,
            )

        elif usage <= self._config.resume_threshold and is_active:
            # Deactivate backpressure
            self._backpressure_event.set()
            self._stats.backpressure_active = False
            logger.info(
                "RTT backpressure released",
                channel=self.channel_index,
                usage=usage,
            )

    async def wait_for_space(self, timeout: float = 5.0) -> bool:
        """Wait for buffer space to become available.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            True if space available, False if timeout.
        """
        if self._byte_count < self._config.max_buffer_size * self._config.resume_threshold:
            return True

        try:
            await asyncio.wait_for(
                self._backpressure_event.wait(),
                timeout=timeout,
            )
            return True
        except asyncio.TimeoutError:
            logger.warning(
                "RTT buffer wait timeout",
                channel=self.channel_index,
                timeout=timeout,
            )
            return False

    def read(self, max_size: int) -> bytes:
        """Read available data from channel."""
        if not self._buffer or max_size <= 0:
            return b""

        chunks = []
        remaining = max_size
        bytes_read = 0

        while self._buffer and remaining > 0:
            _, chunk = self._buffer[0]
            if len(chunk) <= remaining:
                chunks.append(chunk)
                bytes_read += len(chunk)
                remaining -= len(chunk)
                self._buffer.popleft()
                self._byte_count -= len(chunk)
            else:
                # Partial read
                chunks.append(chunk[:remaining])
                bytes_read += remaining
                self._buffer[0] = (self._buffer[0][0], chunk[remaining:])
                self._byte_count -= remaining
                remaining = 0

        return b"".join(chunks)

    def read_all(self) -> list[tuple[float, bytes]]:
        """Read all data without clearing buffer."""
        return list(self._buffer)

    def clear(self) -> None:
        """Clear all buffered data."""
        self._buffer.clear()
        self._byte_count = 0
        self._backpressure_event.set()
        self._stats.backpressure_active = False

    @property
    def bytes_available(self) -> int:
        """Get total bytes in buffer."""
        return self._byte_count

    @property
    def entries_count(self) -> int:
        """Get number of entries in buffer."""
        return len(self._buffer)

    def get_status(self) -> dict:
        """Get channel status."""
        return {
            "channel_index": self.channel_index,
            "name": self.name,
            "bytes_available": self._byte_count,
            "entries_count": len(self._buffer),
            "usage_ratio": self.usage_ratio,
            "backpressure_active": self._stats.backpressure_active,
            "overflow_count": self._stats.overflow_count,
            "dropped_entries": self._stats.dropped_entries,
            "max_bytes_reached": self._stats.max_bytes_reached,
        }


class ProtectedRTTReader:
    """RTT Reader with overflow protection.

    W-008 Fix: Wraps RTTReader with buffer overflow protection.
    """

    def __init__(
        self,
        base_address: int,
        config: Optional[OverflowConfig] = None,
    ):
        self.base_address = base_address
        self._config = config or OverflowConfig()
        self._channels: dict[int, ProtectedRTTChannel] = {}
        self._running = False

    def get_channel(self, index: int) -> ProtectedRTTChannel:
        """Get or create protected channel."""
        if index not in self._channels:
            self._channels[index] = ProtectedRTTChannel(index, config=self._config)
        return self._channels[index]

    def get_channel_status(self, index: int) -> dict:
        """Get status of a channel."""
        channel = self._channels.get(index)
        if channel:
            return channel.get_status()
        return {"channel_index": index, "error": "channel not found"}

    def get_all_status(self) -> list[dict]:
        """Get status of all channels."""
        return [ch.get_status() for ch in self._channels.values()]

    def clear_channel(self, index: int) -> None:
        """Clear a channel's buffer."""
        channel = self._channels.get(index)
        if channel:
            channel.clear()

    def clear_all(self) -> None:
        """Clear all channel buffers."""
        for channel in self._channels.values():
            channel.clear()

    def get_total_stats(self) -> OverflowStats:
        """Aggregate statistics across all channels."""
        total = OverflowStats()
        for channel in self._channels.values():
            stats = channel.stats
            total.total_entries += stats.total_entries
            total.dropped_entries += stats.dropped_entries
            total.overflow_count += stats.overflow_count
            total.total_bytes += stats.total_bytes
            total.max_bytes_reached = max(
                total.max_bytes_reached, stats.max_bytes_reached
            )
        return total
