"""Streaming Flash - Remote firmware streaming support.

Phase 6.2: Implements streaming flash from remote sources:
- HTTP/HTTPS with Range requests
- S3-compatible object storage
- Local file streaming
- Backpressure support
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


@dataclass
class AsyncFirmwareStream:
    """Async iterator for firmware from remote sources.
    
    Supports:
    - HTTP/HTTPS with Range requests
    - S3-compatible object storage
    - Local file streaming
    - Resume from offset
    """
    
    source: str
    total_size: int | None = None
    
    _chunk_size: int = 4096
    _current_offset: int = 0
    _headers: dict[str, str] = field(default_factory=dict)
    
    def __init__(
        self,
        source: str,
        chunk_size: int = 4096,
        total_size: int | None = None,
    ) -> None:
        self.source = source
        self._chunk_size = chunk_size
        self.total_size = total_size
        self._current_offset = 0
    
    async def stream(
        self,
        start_offset: int = 0,
    ) -> AsyncIterator[bytes]:
        """Stream firmware data in chunks.
        
        Args:
            start_offset: Starting offset for resume support
        
        Yields:
            Chunks of firmware data
        """
        self._current_offset = start_offset
        
        if self.source.startswith("http://") or self.source.startswith("https://"):
            async for chunk in self._stream_http(start_offset):
                yield chunk
        elif self.source.startswith("s3://"):
            async for chunk in self._stream_s3(start_offset):
                yield chunk
        else:
            async for chunk in self._stream_file(start_offset):
                yield chunk
    
    async def _stream_http(
        self,
        start_offset: int,
    ) -> AsyncIterator[bytes]:
        """Stream from HTTP source with Range support."""
        try:
            import aiohttp
        except ImportError:
            logger.error("aiohttp_not_installed")
            return
        
        headers = {}
        if start_offset > 0:
            headers["Range"] = f"bytes={start_offset}-"
        
        timeout = aiohttp.ClientTimeout(total=3600)  # 1 hour for large files
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.get(self.source, headers=headers) as response:
                    if response.status == 206:
                        self.total_size = int(response.headers.get("Content-Length", 0)) + start_offset
                    elif response.status == 200:
                        self.total_size = int(response.headers.get("Content-Length", 0))
                    
                    async for chunk in response.content.iter_chunked(self._chunk_size):
                        self._current_offset += len(chunk)
                        yield chunk
            except aiohttp.ClientError as e:
                logger.error("http_stream_error", error=str(e))
    
    async def _stream_s3(
        self,
        start_offset: int,
    ) -> AsyncIterator[bytes]:
        """Stream from S3-compatible storage."""
        try:
            import aiobotocore.session
        except ImportError:
            logger.error("aiobotocore_not_installed")
            return
        
        parts = self.source[5:].split("/", 1)
        if len(parts) < 2:
            logger.error("invalid_s3_uri", source=self.source)
            return
        
        bucket, key = parts[0], parts[1]
        
        session = aiobotocore.session.get_session()
        async with session.create_client("s3") as client:
            kwargs = {"Bucket": bucket, "Key": key}
            
            if start_offset > 0:
                kwargs["Range"] = f"bytes={start_offset}-"
            
            try:
                response = await client.get_object(**kwargs)
                async with response["Body"] as body:
                    async for chunk in body.iter_chunks(chunk_size=self._chunk_size):
                        self._current_offset += len(chunk)
                        yield chunk
            except Exception as e:
                logger.error("s3_stream_error", error=str(e))
    
    async def _stream_file(
        self,
        start_offset: int,
    ) -> AsyncIterator[bytes]:
        """Stream from local file."""
        try:
            import aiofiles
        except ImportError:
            logger.error("aiofiles_not_installed")
            return
        
        async with aiofiles.open(self.source, "rb") as f:
            if start_offset > 0:
                await f.seek(start_offset)
            
            while True:
                chunk = await f.read(self._chunk_size)
                if not chunk:
                    break
                self._current_offset += len(chunk)
                yield chunk
    
    async def get_total_size(self) -> int | None:
        """Get total firmware size without downloading."""
        if self.total_size is not None:
            return self.total_size
        
        if self.source.startswith("http"):
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.head(self.source) as response:
                        self.total_size = int(response.headers.get("Content-Length", 0))
                        return self.total_size
            except Exception:
                pass
        
        return None


@dataclass
class StreamingFlashEngine:
    """Flash engine that streams firmware from remote sources.
    
    Combines AsyncFirmwareStream with flash writing.
    Supports backpressure when flash is slower than stream.
    """
    
    probe: Any  # ProbeInterface
    resume_state_path: str
    
    _backpressure_timeout: float = 30.0
    
    async def flash_from_stream(
        self,
        stream: AsyncFirmwareStream,
        partition_start: int,
        partition_size: int,
        sector_size: int,
        transaction_id: str,
        resume_state: Any = None,
        progress_callback: Any = None,
    ) -> Any:
        """Flash firmware from stream.
        
        Args:
            stream: Firmware stream
            partition_start: Start address
            partition_size: Partition size
            sector_size: Sector size
            transaction_id: Transaction ID for resume
            resume_state: Resume state (if continuing)
            progress_callback: Progress callback
        
        Returns:
            FlashResult
        """
        import time
        from .flash_resume import FlashResult, FlashResumeState
        
        from .flash_resume import FlashResumeState
        
        state = resume_state or FlashResumeState(
            transaction_id=transaction_id,
            firmware_hash="",
            firmware_size=await stream.get_total_size() or 0,
        )
        
        bytes_written = state.total_bytes_written
        start_offset = state.last_sector_written * sector_size + state.last_offset_in_sector
        total_size = stream.total_size or state.firmware_size
        
        hash_ctx = hashlib.sha256()
        
        try:
            current_sector_data = bytearray()
            sector_idx = state.last_sector_written
            
            async for chunk in stream.stream(start_offset):
                hash_ctx.update(chunk)
                current_sector_data.extend(chunk)
                
                while len(current_sector_data) >= sector_size:
                    sector_to_write = bytes(current_sector_data[:sector_size])
                    current_sector_data = current_sector_data[sector_size:]
                    
                    sector_addr = partition_start + (sector_idx * sector_size)
                    await self.probe.write_memory(sector_addr, sector_to_write)
                    
                    verify_data = await self.probe.read_memory(sector_addr, sector_size)
                    if verify_data != sector_to_write:
                        return FlashResult(
                            success=False,
                            error_code="VERIFY_FAILED",
                            error_message=f"Sector {sector_idx} verification failed",
                            resume_state=state,
                        )
                    
                    state.verified_sectors[sector_idx] = hashlib.sha256(sector_to_write).hexdigest()
                    bytes_written += sector_size
                    state.total_bytes_written = bytes_written
                    state.last_sector_written = sector_idx
                    
                    await self._save_state(state)
                    
                    sector_idx += 1
                    
                    if progress_callback:
                        await progress_callback(bytes_written, total_size)
            
            if current_sector_data:
                sector_addr = partition_start + (sector_idx * sector_size)
                padded = bytes(current_sector_data) + b'\xff' * (sector_size - len(current_sector_data))
                await self.probe.write_memory(sector_addr, padded)
                
                state.last_sector_written = sector_idx
                state.total_bytes_written = bytes_written
            
            state.firmware_hash = hash_ctx.hexdigest()
            await self._clear_state(transaction_id)
            
            return FlashResult(
                success=True,
                bytes_written=bytes_written,
                sectors_erased=state.last_sector_written + 1,
            )
            
        except Exception as e:
            state.last_offset_in_sector = len(current_sector_data)
            await self._save_state(state)
            
            return FlashResult(
                success=False,
                error_code="STREAM_ERROR",
                error_message=str(e),
                resume_state=state,
            )
    
    async def _save_state(self, state: Any) -> None:
        """Save resume state."""
        import os
        os.makedirs(self.resume_state_path, exist_ok=True)
        
        from .flash_resume import FlashResumeState
        
        path = os.path.join(self.resume_state_path, f"{state.transaction_id}.resume")
        with open(path, "w") as f:
            f.write(state.to_json())
    
    async def _clear_state(self, transaction_id: str) -> None:
        """Clear resume state."""
        import os
        path = os.path.join(self.resume_state_path, f"{transaction_id}.resume")
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
