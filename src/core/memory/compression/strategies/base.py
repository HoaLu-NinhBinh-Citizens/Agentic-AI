"""Base compression strategy protocol."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..types import CompressionMetadata, CompressionResult


class CompressionStrategy(ABC):
    """Abstract base class for compression strategies.
    
    All compression strategies must implement the compress method.
    Strategies should be stateless and thread-safe.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the strategy name."""
        pass
    
    @abstractmethod
    async def compress(self, content: str) -> tuple[str, "CompressionMetadata"]:
        """Compress content and return (compressed_content, metadata).
        
        Args:
            content: The content to compress.
            
        Returns:
            Tuple of (compressed_content, CompressionMetadata).
            If compression is not applicable, return original content.
        """
        pass
    
    @abstractmethod
    async def decompress(
        self, content: str, metadata: "CompressionMetadata"
    ) -> str:
        """Decompress content using metadata.
        
        Args:
            content: The compressed content.
            metadata: The compression metadata.
            
        Returns:
            Original content.
            
        Raises:
            DecompressionError: If decompression fails.
        """
        pass


class CompressionError(Exception):
    """Base exception for compression errors."""
    
    def __init__(self, message: str, strategy: str | None = None):
        super().__init__(message)
        self.strategy = strategy


class DecompressionError(CompressionError):
    """Exception raised when decompression fails."""
    
    def __init__(self, message: str, strategy: str | None = None):
        super().__init__(message, strategy)


class StrategyNotFoundError(CompressionError):
    """Exception raised when strategy is not found."""
    
    def __init__(self, strategy: str):
        super().__init__(f"Compression strategy not found: {strategy}", strategy=strategy)
