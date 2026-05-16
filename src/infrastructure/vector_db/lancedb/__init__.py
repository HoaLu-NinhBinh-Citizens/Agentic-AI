"""Lancedb vector store module."""

from typing import Any


class LanceDBVectorStore:
    """LanceDB vector store implementation."""
    
    def __init__(self, path: str):
        self._path = path
    
    async def add(self, id: str, vector: list[float], metadata: dict[str, Any]) -> None:
        """Add vector."""
        pass
    
    async def search(self, query: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        """Search vectors."""
        return []
