"""Chromadb vector store module."""

from src.infrastructure.vector_db.chromadb.knowledge_store import ChromaDBKnowledgeStore
from typing import Any


class ChromaDBVectorStore:
    """ChromaDB vector store implementation."""
    
    def __init__(self, path: str):
        self._path = path
    
    async def add(self, id: str, vector: list[float], metadata: dict[str, Any]) -> None:
        """Add vector."""
        pass
    
    async def search(self, query: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        """Search vectors."""
        return []
