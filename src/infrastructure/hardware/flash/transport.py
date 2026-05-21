"""Transport implementations for remote firmware streaming.

Provides HTTP, S3, and local file transports.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


@dataclass
class ChunkInfo:
    """Information about a firmware chunk."""
    
    data: bytes
    offset: int
    size: int
    hash: str
    
    @classmethod
    def from_data(cls, data: bytes, offset: int) -> "ChunkInfo":
        """Create ChunkInfo from data."""
        return cls(
            data=data,
            offset=offset,
            size=len(data),
            hash=hashlib.sha256(data).hexdigest(),
        )


class FirmwareTransport(ABC):
    """Abstract firmware transport."""
    
    @abstractmethod
    async def open(self) -> None:
        """Open transport."""
        ...
    
    @abstractmethod
    async def close(self) -> None:
        """Close transport."""
        ...
    
    @abstractmethod
    async def get_size(self) -> int | None:
        """Get firmware size."""
        ...
    
    @abstractmethod
    async def stream(self, start_offset: int = 0) -> AsyncIterator[ChunkInfo]:
        """Stream firmware chunks."""
        ...


class HTTPFirmwareTransport(FirmwareTransport):
    """HTTP/HTTPS firmware transport with Range support."""
    
    def __init__(
        self,
        url: str,
        chunk_size: int = 8192,
        timeout: float = 300.0,
    ) -> None:
        """Initialize HTTP transport.
        
        Args:
            url: HTTP/HTTPS URL for firmware
            chunk_size: Size of each chunk
            timeout: Request timeout in seconds
        """
        self.url = url
        self.chunk_size = chunk_size
        self.timeout = timeout
        self._session: Any = None
        self._size: int | None = None
    
    async def open(self) -> None:
        """Open HTTP session and get size."""
        import aiohttp
        
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        )
        
        # Get content length
        async with self._session.head(self.url) as response:
            self._size = int(response.headers.get("Content-Length", 0))
    
    async def close(self) -> None:
        """Close HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None
    
    async def get_size(self) -> int | None:
        """Get firmware size."""
        if self._size is None and self._session:
            async with self._session.head(self.url) as response:
                self._size = int(response.headers.get("Content-Length", 0))
        return self._size
    
    async def stream(self, start_offset: int = 0) -> AsyncIterator[ChunkInfo]:
        """Stream firmware from HTTP source."""
        if not self._session:
            await self.open()
        
        headers = {}
        if start_offset > 0:
            headers["Range"] = f"bytes={start_offset}-"
        
        async with self._session.get(self.url, headers=headers) as response:
            if response.status == 206:
                content_range = response.headers.get("Content-Range", "")
                # Parse "bytes start-end/total"
                if "/" in content_range:
                    self._size = int(content_range.split("/")[-1])
            
            offset = start_offset
            async for chunk in response.content.iter_chunked(self.chunk_size):
                yield ChunkInfo.from_data(chunk, offset)
                offset += len(chunk)


class S3FirmwareTransport(FirmwareTransport):
    """S3-compatible firmware transport."""
    
    def __init__(
        self,
        uri: str,
        chunk_size: int = 8192,
    ) -> None:
        """Initialize S3 transport.
        
        Args:
            uri: S3 URI (s3://bucket/key)
            chunk_size: Size of each chunk
        """
        self.uri = uri
        self.chunk_size = chunk_size
        self._client: Any = None
        self._size: int | None = None
        
        # Parse URI
        if not uri.startswith("s3://"):
            raise ValueError("Invalid S3 URI")
        
        parts = uri[5:].split("/", 1)
        if len(parts) < 2:
            raise ValueError("Invalid S3 URI format")
        
        self.bucket = parts[0]
        self.key = parts[1]
    
    async def open(self) -> None:
        """Open S3 client."""
        import aiobotocore.session
        
        session = aiobotocore.session.get_session()
        self._client = await session.create_client("s3")
        
        # Get object size
        try:
            response = await self._client.head_object(
                Bucket=self.bucket,
                Key=self.key,
            )
            self._size = response["ContentLength"]
        except Exception:
            self._size = None
    
    async def close(self) -> None:
        """Close S3 client."""
        if self._client:
            await self._client.close()
            self._client = None
    
    async def get_size(self) -> int | None:
        """Get firmware size."""
        if self._size is None and self._client:
            try:
                response = await self._client.head_object(
                    Bucket=self.bucket,
                    Key=self.key,
                )
                self._size = response["ContentLength"]
            except Exception:
                pass
        return self._size
    
    async def stream(self, start_offset: int = 0) -> AsyncIterator[ChunkInfo]:
        """Stream firmware from S3."""
        if not self._client:
            await self.open()
        
        kwargs: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": self.key,
        }
        
        if start_offset > 0:
            kwargs["Range"] = f"bytes={start_offset}-"
        
        try:
            response = await self._client.get_object(**kwargs)
            async with response["Body"] as body:
                offset = start_offset
                async for chunk in body.iter_chunks(chunk_size=self.chunk_size):
                    yield ChunkInfo.from_data(chunk, offset)
                    offset += len(chunk)
        except Exception as e:
            logger.error("s3_stream_error", error=str(e))
            raise


class LocalFirmwareTransport(FirmwareTransport):
    """Local file firmware transport."""
    
    def __init__(
        self,
        path: str,
        chunk_size: int = 8192,
    ) -> None:
        """Initialize local transport.
        
        Args:
            path: Path to firmware file
            chunk_size: Size of each chunk
        """
        self.path = path
        self.chunk_size = chunk_size
        self._size: int | None = None
        self._file: Any = None
    
    async def open(self) -> None:
        """Open file and get size."""
        import os
        
        self._size = os.path.getsize(self.path)
    
    async def close(self) -> None:
        """Close file."""
        if self._file:
            await self._file.close()
            self._file = None
    
    async def get_size(self) -> int | None:
        """Get firmware size."""
        if self._size is None:
            await self.open()
        return self._size
    
    async def stream(self, start_offset: int = 0) -> AsyncIterator[ChunkInfo]:
        """Stream firmware from local file."""
        import aiofiles
        
        if not self._file:
            self._file = await aiofiles.open(self.path, "rb")
        
        if start_offset > 0:
            await self._file.seek(start_offset)
        
        offset = start_offset
        while True:
            chunk = await self._file.read(self.chunk_size)
            if not chunk:
                break
            yield ChunkInfo.from_data(chunk, offset)
            offset += len(chunk)


def create_firmware_transport(
    source: str,
    chunk_size: int = 8192,
) -> FirmwareTransport:
    """Create appropriate firmware transport.
    
    Args:
        source: Firmware source (URL, S3 URI, or file path)
        chunk_size: Size of each chunk
    
    Returns:
        Appropriate FirmwareTransport instance
    """
    if source.startswith("http://") or source.startswith("https://"):
        return HTTPFirmwareTransport(source, chunk_size)
    elif source.startswith("s3://"):
        return S3FirmwareTransport(source, chunk_size)
    else:
        return LocalFirmwareTransport(source, chunk_size)
