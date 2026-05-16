"""Knowledge chunking domain module."""

from typing import Any


class KnowledgeChunking:
    """Chunk knowledge for retrieval."""
    
    def chunk(self, text: str, chunk_size: int = 512) -> list[str]:
        """Split text into chunks."""
        words = text.split()
        return [" ".join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]
