"""In-memory knowledge store implementation.

Fallback implementation for when vector DB is unavailable.
Provides basic functionality without external dependencies.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import structlog

from src.domain.ports.knowledge_store import KnowledgeStore

if TYPE_CHECKING:
    from src.domain.knowledge.kb import KBEntry

logger = structlog.get_logger(__name__)


class InMemoryKnowledgeStore(KnowledgeStore):
    """In-memory knowledge store fallback.

    Used when ChromaDB is unavailable or for testing.
    Does not persist data across restarts.
    """

    def __init__(self) -> None:
        self._entries: dict[str, KBEntry] = {}
        self._embeddings: dict[str, list[float]] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize in-memory store."""
        if not self._initialized:
            self._initialized = True
            logger.info("In-memory knowledge store initialized")

    async def add_entry(self, entry: KBEntry) -> None:
        """Add entry to in-memory store."""
        await self.initialize()
        self._entries[entry.id] = entry
        if entry.embedding:
            self._embeddings[entry.id] = entry.embedding

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        """Search using cosine similarity."""
        await self.initialize()

        if not self._embeddings:
            return []

        results: list[tuple[str, float, dict[str, Any]]] = []

        for entry_id, embedding in self._embeddings.items():
            entry = self._entries.get(entry_id)
            if entry is None:
                continue

            # Apply metadata filters
            if filter_metadata:
                if filter_metadata.get("chip_family") and entry.chip_family != filter_metadata["chip_family"]:
                    continue
                if filter_metadata.get("peripheral") and entry.peripheral != filter_metadata["peripheral"]:
                    continue
                if filter_metadata.get("type") and entry.type.value != filter_metadata.get("type"):
                    if isinstance(filter_metadata.get("type"), dict) and "$in" in filter_metadata["type"]:
                        if entry.type.value not in filter_metadata["type"]["$in"]:
                            continue

            # Compute cosine similarity
            similarity = self._cosine_similarity(query_embedding, embedding)

            results.append((
                entry_id,
                similarity,
                {
                    "id": entry.id,
                    "type": entry.type.value,
                    "source": entry.source,
                    "chip_family": entry.chip_family or "",
                    "peripheral": entry.peripheral or "",
                    "register": entry.register or "",
                    "tags": ",".join(entry.tags),
                },
            ))

        # Sort by similarity descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    async def get_entry(self, entry_id: str) -> KBEntry | None:
        """Get entry by ID."""
        await self.initialize()
        return self._entries.get(entry_id)

    async def delete_entry(self, entry_id: str) -> None:
        """Delete entry by ID."""
        await self.initialize()
        self._entries.pop(entry_id, None)
        self._embeddings.pop(entry_id, None)

    async def count(self) -> int:
        """Get entry count."""
        await self.initialize()
        return len(self._entries)

    async def clear(self) -> None:
        """Clear all entries."""
        self._entries.clear()
        self._embeddings.clear()

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(a) != len(b) or not a:
            return 0.0

        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)
