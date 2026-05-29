"""Knowledge Base - semantic retrieval system for embedded engineering.

Integrates:
- ChromaDB for vector storage and similarity search
- EmbeddingService for semantic embeddings (Ollama bge-m3)
- Citation tracking for hardware evidence
- Hardware-aware chunking for code/RM documents

Architecture:
    Ingest → Chunk → Embed → Index → Retrieve → Citation → LLM Context
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import structlog

from src.domain.knowledge.chunking import HardwareChunker
from src.domain.knowledge.citation import Citation, SourceType
from src.domain.knowledge.embeddings import KnowledgeEmbeddings

logger = structlog.get_logger(__name__)


class KBEntryType(Enum):
    """Type of knowledge base entry."""
    REGISTER_SPEC = "register_spec"
    PERIPHERAL_SPEC = "peripheral_spec"
    INTERRUPT_SPEC = "interrupt_spec"
    CLOCK_SPEC = "clock_spec"
    CODE_SNIPPET = "code_snippet"
    FIRMWARE_PATTERN = "firmware_pattern"
    HARDWARE_CONSTRAINT = "hardware_constraint"
    ERROR_ANALYSIS = "error_analysis"
    RM_EXCERPT = "rm_excerpt"


@dataclass
class KBEntry:
    """A single knowledge base entry."""
    id: str
    type: KBEntryType
    title: str
    content: str
    source: str                    # File, RM section, SVD name
    source_type: SourceType
    chip_family: str | None        # e.g. "STM32F4", "STM32H7"
    peripheral: str | None        # e.g. "CAN1", "SPI2"
    register: str | None          # e.g. "CAN_MCR", "SPI_CR1"
    tags: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    embedding: list[float] | None = None
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "source": self.source,
            "chip_family": self.chip_family,
            "peripheral": self.peripheral,
            "register": self.register,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class KBQuery:
    """Query for knowledge base search."""
    text: str
    chip_family: str | None = None
    peripheral: str | None = None
    entry_types: list[KBEntryType] | None = None
    top_k: int = 5
    include_content: bool = True


@dataclass
class KBSearchResult:
    """Result of a knowledge base query."""
    entry: KBEntry
    score: float                   # Similarity score (0-1)
    matched_on: list[str]          # Which fields matched
    citations: list[Citation] = field(default_factory=list)

    def to_context(self) -> str:
        """Format as LLM context string."""
        ctx = f"[{self.entry.source}] {self.entry.title}\n{self.entry.content}"
        if self.citations:
            ctx += "\n" + "\n".join(f"  -> {c.text}" for c in self.citations[:3])
        return ctx


class ChromaDBStore:
    """
    ChromaDB-backed vector store.

    Wraps the ChromaDB Python client for persistence and similarity search.
    Falls back to in-memory if ChromaDB is unavailable.
    """

    def __init__(self, persist_directory: str | None = None):
        self._persist_directory = persist_directory
        self._collection_name = "ai_support_kb"
        self._client = None
        self._collection = None
        self._memory_store: dict[str, KBEntry] = {}
        self._embedding_map: dict[str, list[float]] = {}
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
                path=self._persist_directory or "./.kb_chroma",
                settings=client_settings,
            )
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._initialized = True
            logger.info("ChromaDB initialized at %s", self._persist_directory or "./.kb_chroma")
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

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        """
        Search vector store.

        Returns:
            List of (id, score, metadata) tuples.
        """
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

        return []

    async def get_entry(self, entry_id: str) -> KBEntry | None:
        """Get entry by ID."""
        await self.initialize()
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

    async def count(self) -> int:
        """Get total entry count."""
        await self.initialize()
        if self._collection is not None:
            try:
                return self._collection.count()
            except Exception:
                pass
        return len(self._memory_store)


class KnowledgeBase:
    """
    Full knowledge base with semantic retrieval.

    Integrates ChromaDB vector store with Ollama embeddings for
    hardware-aware semantic search.

    Usage:
        kb = KnowledgeBase()
        await kb.add_rm_excerpt(
            chip_family="STM32F407",
            peripheral="CAN1",
            content="CAN_MCR: INRQ (Initialization Request)...",
            source="RM0090 p.980",
        )
        results = await kb.query("CAN initialization sequence")
    """

    def __init__(
        self,
        persist_directory: str | None = None,
        embed_service=None,
    ):
        self._store = ChromaDBStore(persist_directory=persist_directory)
        self._embeddings = KnowledgeEmbeddings()
        self._chunker = HardwareChunker()
        self._embed_service = embed_service

    def set_embed_service(self, embed_service) -> None:
        """Set the embedding service (e.g. EmbeddingService from infrastructure)."""
        self._embed_service = embed_service

    async def _embed(self, text: str) -> list[float]:
        """Generate embedding for text."""
        # Try Ollama EmbeddingService first
        if self._embed_service is not None:
            try:
                result = await self._embed_service.embed(text)
                if result:
                    return result
            except Exception as e:
                logger.warning("Embed service failed: %s", e)

        # Fallback: generate deterministic embedding from text hash
        # This provides consistent but non-semantic embeddings
        return self._embeddings.fallback_embedding(text)

    # ─── Ingestion ─────────────────────────────────────────────────────

    async def add_entry(
        self,
        entry_type: KBEntryType,
        title: str,
        content: str,
        source: str,
        source_type: SourceType = SourceType.RM,
        chip_family: str | None = None,
        peripheral: str | None = None,
        register: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> KBEntry:
        """Add a single entry to the knowledge base."""
        import uuid
        entry_id = str(uuid.uuid4())[:12]

        # Chunk if content is too long
        if len(content) > 2000:
            chunks = await self._chunker.chunk(content, entry_type.value)
        else:
            chunks = [{"id": entry_id, "content": content}]

        entry = KBEntry(
            id=entry_id,
            type=entry_type,
            title=title,
            content=chunks[0]["content"],
            source=source,
            source_type=source_type,
            chip_family=chip_family,
            peripheral=peripheral,
            register=register,
            tags=tags or [],
            metadata=metadata or {},
        )

        # Generate embedding
        embed_text = f"{title}\n{content}"
        entry.embedding = await self._embed(embed_text)

        await self._store.add_entry(entry)
        logger.debug("kb_entry_added", id=entry_id, type=entry_type.value, title=title)

        return entry

    async def add_rm_excerpt(
        self,
        chip_family: str,
        peripheral: str,
        content: str,
        source: str,
        register: str | None = None,
    ) -> KBEntry:
        """Add Reference Manual excerpt."""
        return await self.add_entry(
            entry_type=KBEntryType.RM_EXCERPT,
            title=f"{peripheral} - {register or 'Overview'}",
            content=content,
            source=source,
            source_type=SourceType.RM,
            chip_family=chip_family,
            peripheral=peripheral,
            register=register,
            tags=[chip_family, peripheral, "reference-manual"],
        )

    async def add_svd_peripheral(
        self,
        chip_family: str,
        peripheral: str,
        base_address: str,
        registers: list[dict[str, Any]],
        interrupts: list[dict[str, Any]],
    ) -> KBEntry:
        """Add SVD-defined peripheral."""
        content_lines = [
            f"Base Address: {base_address}",
            "Registers:",
        ]
        for reg in registers:
            content_lines.append(f"  - {reg.get('name', '?')}: {reg.get('description', '')}")
        content_lines.append("Interrupts:")
        for irq in interrupts:
            content_lines.append(f"  - {irq.get('name', '?')}: IRQ {irq.get('value', '?')}")

        return await self.add_entry(
            entry_type=KBEntryType.PERIPHERAL_SPEC,
            title=f"{peripheral} (SVD)",
            content="\n".join(content_lines),
            source=f"{chip_family}.svd",
            source_type=SourceType.SVD,
            chip_family=chip_family,
            peripheral=peripheral,
            tags=[chip_family, peripheral, "svd", "hardware-model"],
        )

    async def add_code_pattern(
        self,
        pattern_name: str,
        code: str,
        language: str,
        peripheral: str | None = None,
        chip_family: str | None = None,
        description: str | None = None,
    ) -> KBEntry:
        """Add a code pattern/snippet."""
        content = f"Language: {language}\n"
        if description:
            content += f"Description: {description}\n"
        content += f"\n```\n{code}\n```"

        return await self.add_entry(
            entry_type=KBEntryType.CODE_SNIPPET,
            title=pattern_name,
            content=content,
            source=f"{pattern_name}.{language}",
            source_type=SourceType.CODE,
            chip_family=chip_family,
            peripheral=peripheral,
            tags=[language, peripheral or "general", "pattern"],
        )

    async def add_constraint(
        self,
        constraint_type: str,
        description: str,
        severity: str,
        chip_family: str | None = None,
        peripheral: str | None = None,
    ) -> KBEntry:
        """Add a hardware constraint rule."""
        return await self.add_entry(
            entry_type=KBEntryType.HARDWARE_CONSTRAINT,
            title=f"[{severity.upper()}] {constraint_type}",
            content=description,
            source="hardware-constraints",
            source_type=SourceType.HARDWARE_MODEL,
            chip_family=chip_family,
            peripheral=peripheral,
            tags=[constraint_type, severity, "constraint"],
        )

    async def add_error_analysis(
        self,
        error_code: str,
        analysis: str,
        fix_suggestion: str,
        related_constraints: list[str] | None = None,
    ) -> KBEntry:
        """Add error analysis from past failures."""
        content = f"Error Code: {error_code}\n\nAnalysis:\n{analysis}\n\nFix Suggestion:\n{fix_suggestion}"
        if related_constraints:
            content += "\n\nRelated Constraints:\n" + "\n".join(f"  - {c}" for c in related_constraints)

        return await self.add_entry(
            entry_type=KBEntryType.ERROR_ANALYSIS,
            title=f"Error Analysis: {error_code}",
            content=content,
            source="error-analysis",
            source_type=SourceType.ERROR_LOG,
            tags=["error-analysis", error_code],
        )

    # ─── Query ────────────────────────────────────────────────────────

    async def query(self, query: KBQuery) -> list[KBSearchResult]:
        """
        Query the knowledge base with semantic search.

        W-012 Fix: Removed global _lock to allow concurrent queries.
        ChromaDB is thread-safe; the in-memory fallback uses a dict which
        is safe for concurrent reads (writes are only on add/delete).

        Args:
            query: KBQuery with text, filters, and top_k

        Returns:
            List of KBSearchResult sorted by relevance
        """
        # Build filter
        filter_meta: dict[str, Any] = {}
        if query.chip_family:
            filter_meta["chip_family"] = query.chip_family
        if query.peripheral:
            filter_meta["peripheral"] = query.peripheral
        if query.entry_types:
            filter_meta["type"] = {"$in": [t.value for t in query.entry_types]}

        # Generate query embedding
        query_embedding = await self._embed(query.text)

        # Search vector store
        raw_results = await self._store.search(
            query_embedding=query_embedding,
            top_k=query.top_k,
            filter_metadata=filter_meta if filter_meta else None,
        )

        results: list[KBSearchResult] = []
        for entry_id, score, metadata in raw_results:
            entry = await self._store.get_entry(entry_id)
            if entry is None:
                continue

            # Build matched_on list
            matched_on: list[str] = []
            if query.chip_family and metadata.get("chip_family") == query.chip_family:
                matched_on.append("chip_family")
            if query.peripheral and metadata.get("peripheral") == query.peripheral:
                matched_on.append("peripheral")
            if score > 0.7:
                matched_on.append("semantic_similarity")

            results.append(KBSearchResult(
                entry=entry,
                score=score,
                matched_on=matched_on if matched_on else ["semantic_similarity"],
                citations=entry.citations,
            ))

        return results

    async def query_by_text(
        self,
        text: str,
        chip_family: str | None = None,
        peripheral: str | None = None,
        top_k: int = 5,
    ) -> list[KBSearchResult]:
        """Simple text query."""
        query = KBQuery(
            text=text,
            chip_family=chip_family,
            peripheral=peripheral,
            top_k=top_k,
        )
        return await self.query(query)

    async def query_by_type(
        self,
        entry_type: KBEntryType,
        chip_family: str | None = None,
        peripheral: str | None = None,
        top_k: int = 10,
    ) -> list[KBSearchResult]:
        """Query by entry type."""
        query = KBQuery(
            text="",
            chip_family=chip_family,
            peripheral=peripheral,
            entry_types=[entry_type],
            top_k=top_k,
        )
        return await self.query(query)

    # ─── Context Building ─────────────────────────────────────────────

    async def build_context(
        self,
        query: KBQuery,
        max_chars: int = 4000,
    ) -> str:
        """
        Build LLM context string from knowledge base results.

        Args:
            query: Query to search for
            max_chars: Maximum context length

        Returns:
            Formatted context string for LLM
        """
        results = await self.query(query)
        if not results:
            return ""

        context_parts: list[str] = []
        total_chars = 0

        for result in results:
            ctx = result.to_context()
            if total_chars + len(ctx) > max_chars:
                break
            context_parts.append(ctx)
            total_chars += len(ctx)

        header = (
            f"[Knowledge Base — {len(results)} result(s) for: {query.text}]\n"
            f"{'='*60}\n"
        )
        return header + "\n\n".join(context_parts)

    async def build_citation_context(
        self,
        query: str,
        chip_family: str,
        peripheral: str,
    ) -> str:
        """Build context specifically for hardware citation."""
        results = await self.query_by_text(
            text=query,
            chip_family=chip_family,
            peripheral=peripheral,
            top_k=3,
        )

        if not results:
            return ""

        lines = [
            f"[Hardware Evidence for {peripheral} on {chip_family}]",
            "",
        ]
        for r in results:
            lines.append(f"Source: {r.entry.source}")
            lines.append(f"Type: {r.entry.type.value}")
            lines.append(f"Content:\n{r.entry.content}")
            if r.entry.citations:
                lines.append("Citations:")
                for c in r.entry.citations[:2]:
                    lines.append(f"  - {c.source} p.{c.page}: {c.text[:100]}")
            lines.append("")

        return "\n".join(lines)

    # ─── Management ───────────────────────────────────────────────────

    async def get_stats(self) -> dict[str, Any]:
        """Get knowledge base statistics."""
        return {
            "total_entries": await self._store.count(),
            "embed_service": (
                self._embed_service.__class__.__name__
                if self._embed_service else "fallback"
            ),
        }

    async def clear(self) -> None:
        """Clear all entries."""
        self._store = ChromaDBStore(
            persist_directory=getattr(self._store, "_persist_directory", None)
        )
        logger.info("knowledge_base_cleared")
