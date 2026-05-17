"""Truncation compression strategy.

Keeps beginning and/or end of content, discarding middle.
Useful for code, logs, and structured text.
"""

from __future__ import annotations

import hashlib
import time
from typing import TYPE_CHECKING

from .base import CompressionStrategy, DecompressionError
from ..types import CompressionMetadata

if TYPE_CHECKING:
    from ..config import TruncationConfig


class TruncationCompressor(CompressionStrategy):
    """Compress by truncating content while keeping head/tail.
    
    If keep_both_ends is True, keeps beginning and end with ellipsis in middle.
    Otherwise, keeps only the beginning.
    """
    
    def __init__(self, config: "TruncationConfig | None" = None):
        if config is None:
            from ..config import TruncationConfig
            config = TruncationConfig()
        
        self._max_chars = config.max_chars
        self._keep_both_ends = config.keep_both_ends
    
    @property
    def name(self) -> str:
        return "truncation"
    
    async def compress(self, content: str) -> tuple[str, CompressionMetadata]:
        """Compress by truncating content."""
        if len(content) <= self._max_chars:
            return content, CompressionMetadata(
                strategy=self.name,
                params={"max_chars": self._max_chars, "keep_both_ends": self._keep_both_ends},
                original_hash=hashlib.sha256(content.encode()).hexdigest(),
            )
        
        original_hash = hashlib.sha256(content.encode()).hexdigest()
        original_length = len(content)
        
        if self._keep_both_ends:
            available = self._max_chars - 3
            head_len = available // 2
            tail_len = available - head_len
            
            truncated = content[:head_len] + "..." + content[-tail_len:]
        else:
            truncated = content[: self._max_chars]
        
        return truncated, CompressionMetadata(
            strategy=self.name,
            params={
                "max_chars": self._max_chars,
                "keep_both_ends": self._keep_both_ends,
            },
            original_hash=original_hash,
            start_truncate=0 if not self._keep_both_ends else self._max_chars // 2,
            end_truncate=original_length - len(truncated),
            compressed_at=int(time.time()),
        )
    
    async def decompress(
        self, content: str, metadata: CompressionMetadata
    ) -> str:
        """Decompress truncation. Note: Middle content is lost."""
        return content
