"""Integration contract tests between IncrementalIndexer and KnowledgeBase.

These tests intentionally use the REAL KnowledgeBase (with the in-memory
store) instead of a mock. Before `upsert_entries`/`delete_by_source` were
added to KnowledgeBase, the indexer crashed with AttributeError on its very
first `_index_file` call — but unit tests passed because they mocked the KB
with methods the real class did not have. This suite pins the contract.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.domain.knowledge.kb import KnowledgeBase
from src.domain.ports.in_memory_knowledge_store import InMemoryKnowledgeStore
from src.infrastructure.indexing.incremental import IncrementalIndexer


class FakeEmbedService:
    """Local fake for the network-backed EmbeddingService (no Ollama needed)."""

    DIM = 8

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    async def embed(self, text: str) -> list[float]:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        # Deterministic, content-dependent vector
        seed = sum(ord(c) for c in text) or 1
        return [((seed * (i + 1)) % 97) / 97.0 for i in range(FakeEmbedService.DIM)]


@pytest.fixture
def kb() -> KnowledgeBase:
    return KnowledgeBase(store=InMemoryKnowledgeStore())


@pytest.fixture
def indexer(kb: KnowledgeBase, tmp_path: Path) -> IncrementalIndexer:
    idx = IncrementalIndexer(
        kb=kb,
        embed_svc=FakeEmbedService(),
        state_db=tmp_path / "index_state.db",
    )
    idx.connect()
    yield idx
    idx.close()


class TestKnowledgeBaseIndexerContract:
    async def test_upsert_entries_stores_chunks(self, kb: KnowledgeBase):
        chunks = [
            {"text": "def foo():\n    return 1", "source": "a.py", "type": "code"},
            {"text": "def bar():\n    return 2", "source": "a.py", "type": "code"},
        ]
        embeddings = [[0.1] * 8, [0.2] * 8]

        entries = await kb.upsert_entries(chunks, embeddings)

        assert len(entries) == 2
        stats = await kb.get_stats()
        assert stats["total_entries"] == 2
        assert all(e.source == "a.py" for e in entries)

    async def test_reupsert_same_source_replaces_not_duplicates(self, kb: KnowledgeBase):
        chunks = [{"text": "v1", "source": "a.py", "type": "code"}]
        await kb.upsert_entries(chunks, [[0.1] * 8])
        # Re-index same file with different content and chunk count
        chunks_v2 = [
            {"text": "v2 part 1", "source": "a.py", "type": "code"},
            {"text": "v2 part 2", "source": "a.py", "type": "code"},
        ]
        await kb.upsert_entries(chunks_v2, [[0.2] * 8, [0.3] * 8])

        stats = await kb.get_stats()
        assert stats["total_entries"] == 2  # replaced, not 3

    async def test_delete_by_source_removes_only_that_source(self, kb: KnowledgeBase):
        await kb.upsert_entries(
            [
                {"text": "x", "source": "a.py", "type": "code"},
                {"text": "y", "source": "b.py", "type": "code"},
            ],
            [[0.1] * 8, [0.2] * 8],
        )

        deleted = await kb.delete_by_source("a.py")

        assert deleted == 1
        stats = await kb.get_stats()
        assert stats["total_entries"] == 1

    async def test_upsert_without_embeddings_falls_back(self, kb: KnowledgeBase):
        # No embeddings supplied and no embed service: deterministic fallback path
        entries = await kb.upsert_entries(
            [{"text": "hello world", "source": "c.py", "type": "code"}]
        )
        assert len(entries) == 1
        assert entries[0].embedding is not None
        assert len(entries[0].embedding) > 0


class TestIncrementalIndexerWithRealKB:
    """Exercise the previously-crashing production path end-to-end."""

    async def test_index_file_populates_real_kb(
        self, indexer: IncrementalIndexer, kb: KnowledgeBase, tmp_path: Path
    ):
        src_file = tmp_path / "sample.py"
        src_file.write_text(
            "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n",
            encoding="utf-8",
        )

        await indexer._index_file(src_file, content_hash="deadbeef")

        stats = await kb.get_stats()
        assert stats["total_entries"] > 0

    async def test_delete_from_kb_after_file_removed(
        self, indexer: IncrementalIndexer, kb: KnowledgeBase, tmp_path: Path
    ):
        src_file = tmp_path / "gone.py"
        src_file.write_text("def f():\n    pass\n", encoding="utf-8")
        await indexer._index_file(src_file, content_hash="cafebabe")
        assert (await kb.get_stats())["total_entries"] > 0

        await indexer._delete_from_kb(str(src_file))

        assert (await kb.get_stats())["total_entries"] == 0

    async def test_sync_indexes_tmp_project(
        self, indexer: IncrementalIndexer, kb: KnowledgeBase, tmp_path: Path
    ):
        project = tmp_path / "proj"
        project.mkdir()
        (project / "m1.py").write_text("def a():\n    return 1\n", encoding="utf-8")
        (project / "m2.py").write_text("def b():\n    return 2\n", encoding="utf-8")

        stats = await indexer.sync(project)

        assert stats.indexed_files == 2
        assert stats.failed_files == 0
        assert (await kb.get_stats())["total_entries"] >= 2
