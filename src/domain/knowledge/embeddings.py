"""Knowledge embeddings domain module."""

from typing import Any


class KnowledgeEmbeddings:
    """Embeddings for knowledge."""
    
    def __init__(self):
        self._embeddings: dict[str, list[float]] = {}
    
    def add(self, key: str, embedding: list[float]) -> None:
        """Add embedding."""
        self._embeddings[key] = embedding
