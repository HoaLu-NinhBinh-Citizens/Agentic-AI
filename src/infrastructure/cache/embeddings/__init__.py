"""Embedding cache module."""

from typing import Any


class EmbeddingCache:
    """Cache for embeddings."""
    
    def __init__(self):
        self._cache: dict[str, list[float]] = {}
    
    def get(self, key: str) -> list[float] | None:
        """Get cached embedding."""
        return self._cache.get(key)
    
    def set(self, key: str, embedding: list[float]) -> None:
        """Cache embedding."""
        self._cache[key] = embedding
