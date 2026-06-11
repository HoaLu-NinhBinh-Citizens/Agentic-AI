"""Integration tests for IndexingService lifecycle (watcher + indexer + KB).

Uses the real KnowledgeBase + InMemoryKnowledgeStore + real IncrementalIndexer;
only the network-backed embedding service is faked.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.domain.knowledge.kb import KnowledgeBase
from src.domain.ports.in_memory_knowledge_store import InMemoryKnowledgeStore
from src.infrastructure.indexing.file_watcher import FileChange
from src.infrastructure.indexing.service import IndexingService


class FakeEmbedService:
    DIM = 8

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.5] * self.DIM for _ in texts]

    async def embed(self, text: str) -> list[float]:
        return [0.5] * self.DIM


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "alpha.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    (ws / "beta.py").write_text("def beta():\n    return 2\n", encoding="utf-8")
    return ws


@pytest.fixture
def service(workspace: Path, tmp_path: Path) -> IndexingService:
    kb = KnowledgeBase(store=InMemoryKnowledgeStore())
    return IndexingService(
        workspace=workspace,
        kb=kb,
        embed_service=FakeEmbedService(),
        state_db=tmp_path / "state.db",
    )


class TestIndexingServiceLifecycle:
    @pytest.mark.asyncio
    async def test_start_runs_initial_sync_into_kb(self, service: IndexingService):
        await service.start()
        try:
            assert service._sync_task is not None
            await service._sync_task  # wait for background sync to finish
            stats = await service.kb.get_stats()
            assert stats["total_entries"] >= 2
        finally:
            await service.stop()

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self, service: IndexingService):
        await service.start()
        await service.stop()
        await service.stop()  # second stop must not raise

    @pytest.mark.asyncio
    async def test_watcher_change_triggers_reindex(
        self, service: IndexingService, workspace: Path
    ):
        await service.start()
        try:
            await service._sync_task
            baseline = (await service.kb.get_stats())["total_entries"]

            new_file = workspace / "gamma.py"
            new_file.write_text("def gamma():\n    return 3\n", encoding="utf-8")

            # Simulate the watchdog-thread callback directly
            service._on_watcher_change(
                FileChange(path=new_file, event_type="created")
            )
            # call_soon_threadsafe + create_task need loop turns to run
            for _ in range(50):
                await asyncio.sleep(0.02)
                count = (await service.kb.get_stats())["total_entries"]
                if count > baseline:
                    break

            assert (await service.kb.get_stats())["total_entries"] > baseline
        finally:
            await service.stop()

    @pytest.mark.asyncio
    async def test_non_indexable_changes_are_ignored(
        self, service: IndexingService, workspace: Path
    ):
        await service.start()
        try:
            await service._sync_task
            baseline = (await service.kb.get_stats())["total_entries"]

            binary = workspace / "image.png"
            binary.write_bytes(b"\x89PNG")
            service._on_watcher_change(
                FileChange(path=binary, event_type="created")
            )
            await asyncio.sleep(0.1)

            assert (await service.kb.get_stats())["total_entries"] == baseline
        finally:
            await service.stop()
