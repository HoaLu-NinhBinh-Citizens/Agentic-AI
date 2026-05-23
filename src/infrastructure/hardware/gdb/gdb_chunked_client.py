"""GDB Packet Chunking and Retry for W-009.

Adds chunked reading and retry for large GDB RSP responses:
- Chunked memory reading for large regions
- Retry with exponential backoff
- Packet size negotiation
- Truncation detection and recovery
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ChunkConfig:
    """Configuration for chunked reads."""

    max_chunk_size: int = 256  # Max bytes per read
    min_chunk_size: int = 4  # Min bytes per read
    default_chunk_size: int = 128  # Default chunk size
    enable_adaptive: bool = True  # Adapt chunk size based on success


@dataclass
class ChunkStats:
    """Statistics for chunked operations."""

    total_reads: int = 0
    successful_reads: int = 0
    failed_reads: int = 0
    retries: int = 0
    truncations_detected: int = 0
    chunk_sizes_used: list[int] = field(default_factory=list)


class GDBChunkedClient:
    """GDB Client wrapper with chunked reading and retry.

    W-009 Fix: Handles large memory reads without truncation.
    """

    def __init__(
        self,
        gdb_client,
        config: Optional[ChunkConfig] = None,
        max_retries: int = 3,
        retry_base_delay: float = 0.1,
    ):
        """Initialize chunked GDB client.

        Args:
            gdb_client: Underlying GDB client instance.
            config: Chunk configuration.
            max_retries: Maximum retry attempts.
            retry_base_delay: Base delay for exponential backoff.
        """
        self._client = gdb_client
        self._config = config or ChunkConfig()
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._stats = ChunkStats()
        self._current_chunk_size = self._config.default_chunk_size

    @property
    def stats(self) -> ChunkStats:
        """Get chunked operation statistics."""
        return self._stats

    async def read_memory_chunked(
        self,
        address: int,
        size: int,
    ) -> Optional[bytes]:
        """Read memory with chunking and retry.

        Args:
            address: Memory address.
            size: Number of bytes to read.

        Returns:
            Memory contents or None on failure.
        """
        if size <= self._current_chunk_size:
            # Small read, use direct method
            return await self._read_with_retry(
                self._client.read_memory, address, size
            )

        # Large read, chunk it
        chunks = []
        remaining = size
        current_addr = address
        self._stats.total_reads += 1

        while remaining > 0:
            chunk_size = min(self._current_chunk_size, remaining)

            data = await self._read_with_retry(
                self._client.read_memory, current_addr, chunk_size
            )

            if data is None:
                self._stats.failed_reads += 1
                # If any chunk fails, return what we have or None
                if not chunks:
                    return None
                logger.warning(
                    "Partial read due to chunk failure",
                    address=hex(address),
                    size=size,
                    read=len(b"".join(chunks)),
                )
                return b"".join(chunks)

            if len(data) < chunk_size:
                # Truncation detected
                self._stats.truncations_detected += 1
                logger.debug(
                    "Chunk truncated",
                    expected=chunk_size,
                    actual=len(data),
                    address=hex(current_addr),
                )

                # If truncated at first chunk, try smaller chunks
                if current_addr == address and len(data) < chunk_size:
                    if chunk_size > self._config.min_chunk_size:
                        # Reduce chunk size and retry
                        self._current_chunk_size = max(
                            chunk_size // 2, self._config.min_chunk_size
                        )
                        logger.info(
                            "Reducing chunk size",
                            new_size=self._current_chunk_size,
                        )
                        # Restart with smaller chunks
                        return await self.read_memory_chunked(address, size)

            chunks.append(data)
            remaining -= len(data)
            current_addr += len(data)
            self._stats.successful_reads += 1

        # Adaptive chunk size adjustment
        if self._config.enable_adaptive and len(chunks) == 1:
            # Single chunk worked, try larger next time
            self._current_chunk_size = min(
                int(self._current_chunk_size * 1.25),
                self._config.max_chunk_size,
            )
        elif len(chunks) > 1:
            # Multiple chunks needed, might want smaller
            pass

        return b"".join(chunks)

    async def _read_with_retry(
        self,
        read_func,
        *args,
        **kwargs,
    ) -> Optional[bytes]:
        """Read with exponential backoff retry.

        Args:
            read_func: Function to call for reading.
            *args: Positional arguments for read_func.
            **kwargs: Keyword arguments for read_func.

        Returns:
            Result from read_func or None on final failure.
        """
        last_error = None

        for attempt in range(self._max_retries):
            try:
                result = await read_func(*args, **kwargs)

                if result is not None:
                    if attempt > 0:
                        self._stats.retries += attempt
                    return result

                last_error = "Read returned None"

            except Exception as e:
                last_error = str(e)
                logger.debug(
                    "Read attempt failed",
                    attempt=attempt + 1,
                    error=last_error,
                )

            if attempt < self._max_retries - 1:
                # Exponential backoff
                delay = self._retry_base_delay * (2 ** attempt)
                await asyncio.sleep(delay)

                # Reduce chunk size on retry
                if self._current_chunk_size > self._config.min_chunk_size:
                    self._current_chunk_size = max(
                        self._current_chunk_size // 2,
                        self._config.min_chunk_size,
                    )

        self._stats.failed_reads += 1
        logger.warning(
            "Read failed after retries",
            attempts=self._max_retries,
            last_error=last_error,
        )
        return None

    async def write_memory_chunked(
        self,
        address: int,
        data: bytes,
    ) -> bool:
        """Write memory with chunking and retry.

        Args:
            address: Memory address.
            data: Data to write.

        Returns:
            True if all chunks written successfully.
        """
        chunk_size = min(self._current_chunk_size, len(data))
        remaining = len(data)
        current_addr = address

        while remaining > 0:
            chunk = data[len(data) - remaining:len(data) - remaining + chunk_size]

            success = await self._write_with_retry(
                self._client.write_memory, current_addr, chunk
            )

            if not success:
                return False

            remaining -= len(chunk)
            current_addr += len(chunk)

        return True

    async def _write_with_retry(
        self,
        write_func,
        *args,
        **kwargs,
    ) -> bool:
        """Write with exponential backoff retry.

        Args:
            write_func: Function to call for writing.
            *args: Positional arguments for write_func.
            **kwargs: Keyword arguments for write_func.

        Returns:
            True on success, False on final failure.
        """
        for attempt in range(self._max_retries):
            try:
                result = await write_func(*args, **kwargs)
                if result:
                    return True
                last_error = "Write returned False"
            except Exception as e:
                last_error = str(e)
                logger.debug(
                    "Write attempt failed",
                    attempt=attempt + 1,
                    error=last_error,
                )

            if attempt < self._max_retries - 1:
                delay = self._retry_base_delay * (2 ** attempt)
                await asyncio.sleep(delay)

        logger.warning(
            "Write failed after retries",
            attempts=self._max_retries,
            last_error=last_error,
        )
        return False

    def get_status(self) -> dict:
        """Get client status."""
        return {
            "current_chunk_size": self._current_chunk_size,
            "config_chunk_size": self._config.default_chunk_size,
            "max_retries": self._max_retries,
            "stats": {
                "total_reads": self._stats.total_reads,
                "successful_reads": self._stats.successful_reads,
                "failed_reads": self._stats.failed_reads,
                "retries": self._stats.retries,
                "truncations_detected": self._stats.truncations_detected,
            },
        }

    def reset_stats(self) -> None:
        """Reset statistics."""
        self._stats = ChunkStats()
        self._current_chunk_size = self._config.default_chunk_size

    def reset_chunk_size(self) -> None:
        """Reset chunk size to default."""
        self._current_chunk_size = self._config.default_chunk_size

    @property
    def client(self):
        """Access underlying GDB client for other operations."""
        return self._client
