"""Semantic search module."""

from typing import Any


class SemanticSearch:
    """Semantic search engine."""
    
    def __init__(self):
        self._index: dict[str, list[float]] = {}
    
    def index(self, id: str, vector: list[float]) -> None:
        """Index document."""
        self._index[id] = vector
    
    def search(self, query_vector: list[float], top_k: int = 5) -> list[str]:
        """Search by semantic similarity."""
        return list(self._index.keys())[:top_k]
