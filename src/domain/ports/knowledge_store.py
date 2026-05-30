"""Port interface for knowledge store - dependency inversion for vector DB.

This module defines the abstraction that domain layer (KnowledgeBase) depends on,
allowing infrastructure implementations (ChromaDB, LanceDB, in-memory) to be
swapped without changing domain logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.domain.knowledge.kb import KBEntry


class KnowledgeStore(ABC):
    """Abstract interface for knowledge base storage backends.

    Implements Dependency Inversion Principle: domain layer defines this
    interface, infrastructure implements it.

    The KnowledgeBase class depends on this abstraction, not on ChromaDB.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the store (e.g., connect to database)."""
        pass

    @abstractmethod
    async def add_entry(self, entry: KBEntry) -> None:
        """Add a knowledge base entry to the store.

        Args:
            entry: KBEntry to store (must have id, embedding, and metadata)
        """
        pass

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        """Search for similar entries.

        Args:
            query_embedding: Query vector for similarity search
            top_k: Maximum number of results to return
            filter_metadata: Optional metadata filters

        Returns:
            List of (id, score, metadata) tuples sorted by relevance.
            Score is similarity (higher is better, range 0-1).
        """
        pass

    @abstractmethod
    async def get_entry(self, entry_id: str) -> KBEntry | None:
        """Retrieve an entry by ID.

        Args:
            entry_id: Unique entry identifier

        Returns:
            KBEntry if found, None otherwise.
        """
        pass

    @abstractmethod
    async def delete_entry(self, entry_id: str) -> None:
        """Delete an entry by ID.

        Args:
            entry_id: Unique entry identifier
        """
        pass

    @abstractmethod
    async def count(self) -> int:
        """Get total number of entries in the store.

        Returns:
            Total entry count.
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all entries from the store."""
        pass
