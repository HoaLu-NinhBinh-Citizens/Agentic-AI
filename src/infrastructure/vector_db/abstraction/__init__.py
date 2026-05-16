"""Vector DB abstraction stub."""

from typing import Any


class VectorDB:
    """Abstract vector database interface."""
    
    def __init__(self):
        self._vectors: dict[str, list[float]] = {}
    
    async def add(self, id: str, vector: list[float], metadata: dict[str, Any]) -> None:
        """Add a vector."""
        self._vectors[id] = vector
    
    async def search(self, query: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        """Search for similar vectors."""
        return []
    
    async def delete(self, id: str) -> None:
        """Delete a vector."""
        if id in self._vectors:
            del self._vectors[id]
