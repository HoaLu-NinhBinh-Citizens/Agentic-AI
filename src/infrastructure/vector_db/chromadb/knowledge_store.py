"""ChromaDB knowledge store implementation.

Implements KnowledgeStore port interface using ChromaDB for persistence
and similarity search.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import structlog

from src.domain.ports.knowledge_store import KnowledgeStore

if TYPE_CHECKING:
    from src.domain.knowledge.kb import KBEntry

logger = structlog.get_logger(__name__)


class ChromaDBKnowledgeStore(KnowledgeStore):
    """ChromaDB-backed knowledge store implementation.

    Wraps the ChromaDB Python client for persistence and similarity search.
    Falls back to in-memory if ChromaDB is unavailable.
    """

    def __init__(self, persist_directory: str | None = None):
        self._persist_directory = persist_directory or "./.kb_chroma"
        self._collection_name = "ai_support_kb"
        self._client = None
        self._collection = None
        self._memory_store: dict[str, KBEntry] = {}
        self._memory_embeddings: dict[str, list[float]] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize ChromaDB connection."""
        if self._initialized:
            return

        try:
            import chromadb
            from chromadb.config import Settings

            client_settings = Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            )
            self._client = chromadb.PersistentClient(
                path=self._persist_directory,
                settings=client_settings,
            )
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._initialized = True
            logger.info("ChromaDB initialized at %s", self._persist_directory)
        except ImportError:
            logger.warning("ChromaDB not available, using in-memory store")
            self._initialized = True
        except Exception as e:
            logger.warning("ChromaDB init failed, using in-memory store: %s", e)
            self._initialized = True

    async def add_entry(self, entry: KBEntry) -> None:
        """Add entry to the vector store."""
        await self.initialize()

        if self._collection is not None:
            doc = f"{entry.title}\n{entry.content}"
            metadata = {
                "id": entry.id,
                "type": entry.type.value,
                "source": entry.source,
                "chip_family": entry.chip_family or "",
                "peripheral": entry.peripheral or "",
                "register": entry.register or "",
                "tags": ",".join(entry.tags),
            }
            self._collection.add(
                ids=[entry.id],
                documents=[doc],
                embeddings=[entry.embedding] if entry.embedding else None,
                metadatas=[metadata],
            )
        else:
            self._memory_store[entry.id] = entry
            if entry.embedding:
                self._memory_embeddings[entry.id] = entry.embedding

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        """Search vector store."""
        await self.initialize()

        if self._collection is not None:
            try:
                results = self._collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k,
                    where=filter_metadata,
                    include=["metadatas", "distances"],
                )
                ids = results.get("ids", [[]])[0]
                distances = results.get("distances", [[]])[0]
                metadatas = results.get("metadatas", [[]])[0]
                return list(zip(ids, [1 - d for d in distances], metadatas))
            except Exception as e:
                logger.error("ChromaDB query error: %s", e)

        # Fallback to in-memory search
        return await self._memory_search(query_embedding, top_k, filter_metadata)

    async def _memory_search(
        self,
        query_embedding: list[float],
        top_k: int,
        filter_metadata: dict[str, Any] | None,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        """Fallback in-memory search when ChromaDB unavailable."""
        from src.domain.ports.in_memory_knowledge_store import InMemoryKnowledgeStore

        # Temporarily create an in-memory store for search
        temp_store = InMemoryKnowledgeStore()
        temp_store._entries = self._memory_store.copy()
        temp_store._embeddings = self._memory_embeddings.copy()
        temp_store._initialized = True

        return await temp_store.search(query_embedding, top_k, filter_metadata)

    async def get_entry(self, entry_id: str) -> KBEntry | None:
        """Get entry by ID."""
        await self.initialize()

        if self._collection is not None:
            try:
                result = self._collection.get(ids=[entry_id])
                if result and result.get("metadatas") and result["metadatas"]:
                    metadata = result["metadatas"][0]
                    from src.domain.knowledge.kb import KBEntryType, SourceType

                    return KBEntry(
                        id=entry_id,
                        type=KBEntryType(metadata.get("type", "RM_EXCERPT")),
                        title=metadata.get("source", ""),
                        content="",  # Content not stored in ChromaDB metadata
                        source=metadata.get("source", ""),
                        source_type=SourceType.RM,
                        chip_family=metadata.get("chip_family") or None,
                        peripheral=metadata.get("peripheral") or None,
                        register=metadata.get("register") or None,
                        tags=metadata.get("tags", "").split(",") if metadata.get("tags") else [],
                    )
            except Exception:
                pass

        return self._memory_store.get(entry_id)

    async def delete_entry(self, entry_id: str) -> None:
        """Delete entry by ID."""
        await self.initialize()
        if self._collection is not None:
            try:
                self._collection.delete(ids=[entry_id])
            except Exception as e:
                logger.warning("ChromaDB delete error: %s", e)
        self._memory_store.pop(entry_id, None)
        self._memory_embeddings.pop(entry_id, None)

    async def count(self) -> int:
        """Get total entry count."""
        await self.initialize()
        if self._collection is not None:
            try:
                return self._collection.count()
            except Exception:
                pass
        return len(self._memory_store)

    async def clear(self) -> None:
        """Clear all entries."""
        if self._collection is not None:
            try:
                # Get all IDs and delete them
                all_data = self._collection.get()
                if all_data and all_data.get("ids"):
                    self._collection.delete(ids=all_data["ids"])
            except Exception as e:
                logger.warning("ChromaDB clear error: %s", e)
        self._memory_store.clear()
        self._memory_embeddings.clear()
