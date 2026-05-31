"""Incremental indexing benchmark and verification tests.

Tests that validate the incremental indexing guarantees:
- Only changed files are re-indexed
- Unchanged files are skipped
- Deleted files are cleaned up
- Re-indexed files are logged
"""

from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


class IncrementalIndexingBenchmark:
    """Benchmark for incremental indexing operations."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.results: list[dict] = []

    def record(self, operation: str, elapsed: float, details: dict) -> None:
        """Record a benchmark result."""
        self.results.append({
            "operation": operation,
            "elapsed_ms": elapsed * 1000,
            "details": details,
        })

    def summary(self) -> dict:
        """Get benchmark summary."""
        if not self.results:
            return {}
        total_ms = sum(r["elapsed_ms"] for r in self.results)
        return {
            "total_operations": len(self.results),
            "total_ms": round(total_ms, 2),
            "avg_ms": round(total_ms / len(self.results), 2) if self.results else 0,
            "results": self.results,
        }


@pytest.fixture
def incremental_benchmark():
    """Create an incremental indexing benchmark instance."""
    return IncrementalIndexingBenchmark(Path("."))


@pytest.mark.asyncio
async def test_only_changed_file_is_reindexed(
    tmp_path: Path,
    incremental_benchmark: IncrementalIndexingBenchmark,
):
    """Test that only changed files are re-indexed, not the entire project.

    This is the critical test for incremental indexing verification.
    """
    from src.infrastructure.indexing.incremental import (
        IncrementalIndexer,
        IndexStateDB,
        FileState,
    )

    # Setup: Create a project with multiple files
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create 20 test files
    file_count = 20
    files = []
    for i in range(file_count):
        f = project_root / f"module_{i}.py"
        f.write_text(f"def func_{i}(): return {i}\n")
        files.append(f)

    # Mock KB and embed service
    class MockKB:
        upsert_calls: list = []

        async def upsert_entries(self, chunks, embeddings):
            self.upsert_calls.append(len(chunks))
            await asyncio.sleep(0.001)

        async def delete_by_source(self, path):
            pass

    class MockEmbed:
        async def embed_batch(self, texts):
            return [[0.1] * 384 for _ in texts]

    # First sync: index all files
    db_path = tmp_path / "index_state.db"
    indexer = IncrementalIndexer(
        kb=MockKB(),
        embed_svc=MockEmbed(),
        state_db=db_path,
        concurrency=4,
        hash_workers=2,
    )
    indexer.connect()

    start = time.perf_counter()
    stats = await indexer.sync(project_root)
    first_sync_elapsed = time.perf_counter() - start

    assert stats.total_files == file_count, f"Expected {file_count} files, got {stats.total_files}"
    assert stats.indexed_files == file_count, f"Expected {file_count} indexed, got {stats.indexed_files}"
    assert stats.changed_files == file_count, f"Expected {file_count} changed, got {stats.changed_files}"

    # Record first sync
    incremental_benchmark.record(
        "first_sync_full",
        first_sync_elapsed,
        {"files": file_count, "indexed": stats.indexed_files}
    )

    # Second sync: only 1 file changed
    # Modify just one file
    files[0].write_text(f"def modified_func(): return 'changed'\n")

    kb_calls_before = len(MockKB().upsert_calls) if hasattr(MockKB, 'upsert_calls') else 0
    mock_kb = MockKB()
    mock_kb.upsert_calls = []  # Reset

    indexer._kb = mock_kb

    start = time.perf_counter()
    stats = await indexer.sync(project_root)
    second_sync_elapsed = time.perf_counter() - start

    # Verify only 1 file was re-indexed
    assert stats.changed_files == 1, f"Expected 1 changed file, got {stats.changed_files}"
    assert stats.indexed_files == 1, f"Expected 1 indexed, got {stats.indexed_files}"
    assert stats.skipped_files == file_count - 1, f"Expected {file_count - 1} skipped, got {stats.skipped_files}"

    # Record second sync
    incremental_benchmark.record(
        "second_sync_incremental",
        second_sync_elapsed,
        {"changed": stats.changed_files, "skipped": stats.skipped_files}
    )

    # Verify speedup: incremental should be much faster
    # Allow for variance in test environments
    speedup_threshold = 3.0  # At least 3x speedup expected
    speedup = first_sync_elapsed / second_sync_elapsed if second_sync_elapsed > 0 else float('inf')
    assert speedup > speedup_threshold, f"Incremental sync should be >{speedup_threshold}x faster, got {speedup:.1f}x"

    incremental_benchmark.record(
        "incremental_speedup",
        speedup,
        {"first_ms": first_sync_elapsed * 1000, "second_ms": second_sync_elapsed * 1000}
    )

    indexer.close()

    # Print benchmark results
    summary = incremental_benchmark.summary()
    print(f"\n[Benchmark] Incremental Indexing Verification:")
    print(f"  First sync (full): {first_sync_elapsed * 1000:.1f}ms for {file_count} files")
    print(f"  Second sync (1 changed): {second_sync_elapsed * 1000:.1f}ms")
    print(f"  Speedup: {speedup:.1f}x")


@pytest.mark.asyncio
async def test_reindexed_files_are_logged(
    tmp_path: Path,
):
    """Test that re-indexed files are exposed via an API."""
    from src.infrastructure.indexing.incremental import (
        IncrementalIndexer,
    )

    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create files
    for i in range(5):
        (project_root / f"file_{i}.py").write_text(f"x = {i}\n")

    class MockKB:
        async def upsert_entries(self, chunks, embeddings):
            await asyncio.sleep(0.001)

        async def delete_by_source(self, path):
            pass

    class MockEmbed:
        async def embed_batch(self, texts):
            return [[0.1] * 384 for _ in texts]

    # Track which files are actually indexed
    indexed_paths: list[str] = []

    class TrackingKB(MockKB):
        async def upsert_entries(self, chunks, embeddings):
            for chunk in chunks:
                if chunk.get("source") and chunk["source"] not in indexed_paths:
                    indexed_paths.append(chunk["source"])
            await super().upsert_entries(chunks, embeddings)

    db_path = tmp_path / "index_state.db"
    indexer = IncrementalIndexer(
        kb=TrackingKB(),
        embed_svc=MockEmbed(),
        state_db=db_path,
    )
    indexer.connect()

    # First sync
    await indexer.sync(project_root)
    first_indexed = indexed_paths.copy()
    assert len(first_indexed) == 5, f"Expected 5 files indexed, got {len(first_indexed)}"

    # Modify 2 files
    (project_root / "file_0.py").write_text("y = 100\n")
    (project_root / "file_2.py").write_text("z = 200\n")

    indexed_paths.clear()
    await indexer.sync(project_root)
    second_indexed = indexed_paths.copy()

    # Verify only the changed files were re-indexed
    assert len(second_indexed) == 2, f"Expected 2 files re-indexed, got {len(second_indexed)}"
    assert "file_0.py" in second_indexed[0] or "file_0" in str(second_indexed)
    assert "file_2.py" in second_indexed[1] or "file_2" in str(second_indexed)

    indexer.close()

    print(f"\n[Verified] Re-indexed files API:")
    print(f"  First run: {len(first_indexed)} files indexed")
    print(f"  Second run: {len(second_indexed)} files re-indexed (only changed)")


@pytest.mark.asyncio
async def test_deleted_files_cleaned_up(
    tmp_path: Path,
):
    """Test that deleted files are cleaned from the index."""
    from src.infrastructure.indexing.incremental import (
        IncrementalIndexer,
        IndexStateDB,
    )

    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create files
    for i in range(5):
        (project_root / f"file_{i}.py").write_text(f"x = {i}\n")

    class MockKB:
        deleted_sources: list[str] = []

        async def upsert_entries(self, chunks, embeddings):
            await asyncio.sleep(0.001)

        async def delete_by_source(self, path):
            self.deleted_sources.append(path)

    class MockEmbed:
        async def embed_batch(self, texts):
            return [[0.1] * 384 for _ in texts]

    db_path = tmp_path / "index_state.db"
    indexer = IncrementalIndexer(
        kb=MockKB(),
        embed_svc=MockEmbed(),
        state_db=db_path,
    )
    indexer.connect()

    # First sync
    await indexer.sync(project_root)

    # Delete 2 files
    (project_root / "file_0.py").unlink()
    (project_root / "file_2.py").unlink()

    MockKB.deleted_sources.clear()
    stats = await indexer.sync(project_root)

    # Verify deleted files were cleaned up
    assert len(MockKB.deleted_sources) == 2, f"Expected 2 deletions, got {len(MockKB.deleted_sources)}"

    indexer.close()

    print(f"\n[Verified] Deleted files cleanup:")
    print(f"  Deleted {len(MockKB.deleted_sources)} files from index")


@pytest.mark.asyncio
async def test_parallel_hash_performance(
    tmp_path: Path,
):
    """Benchmark parallel hashing vs sequential hashing."""
    from src.infrastructure.indexing.incremental import compute_file_hash_parallel

    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create 100 test files
    for i in range(100):
        (project_root / f"file_{i}.py").write_text(f"def func_{i}(): return {i}\n" * 10)

    files = list(project_root.glob("*.py"))

    # Benchmark sequential (1 worker)
    start1 = time.perf_counter()
    results1 = compute_file_hash_parallel(files, max_workers=1)
    time1 = time.perf_counter() - start1

    # Benchmark parallel (4 workers)
    start4 = time.perf_counter()
    results4 = compute_file_hash_parallel(files, max_workers=4)
    time4 = time.perf_counter() - start4

    # Parallel should be faster or similar
    assert len(results1) == len(results4) == 100

    print(f"\n[Benchmark] Parallel Hashing:")
    print(f"  1 worker: {time1 * 1000:.1f}ms")
    print(f"  4 workers: {time4 * 1000:.1f}ms")
    print(f"  Speedup: {time1 / time4:.1f}x" if time4 > 0 else "  Same speed")


@pytest.mark.asyncio
async def test_index_state_db_performance(
    tmp_path: Path,
):
    """Benchmark index state DB operations."""
    from src.infrastructure.indexing.incremental import (
        IndexStateDB,
        FileState,
    )

    db_path = tmp_path / "index_state.db"
    db = IndexStateDB(db_path)
    db.connect()

    # Benchmark bulk insert
    file_count = 1000
    states = [
        FileState(
            path=f"/test/file_{i}.py",
            mtime=1234567890.0 + i,
            content_hash=f"hash_{i:06d}",
            indexed_at=1234567891.0 + i,
        )
        for i in range(file_count)
    ]

    start_insert = time.perf_counter()
    for state in states:
        db.upsert(state)
    insert_time = time.perf_counter() - start_insert

    # Benchmark query
    start_query = time.perf_counter()
    for i in range(file_count):
        db.get(f"/test/file_{i}.py")
    query_time = time.perf_counter() - start_query

    db.close()

    print(f"\n[Benchmark] Index State DB:")
    print(f"  {file_count} inserts: {insert_time * 1000:.1f}ms ({file_count/insert_time:.0f}/sec)")
    print(f"  {file_count} queries: {query_time * 1000:.1f}ms ({file_count/query_time:.0f}/sec)")


@pytest.mark.asyncio
async def test_incremental_indexing_scales(
    tmp_path: Path,
):
    """Test that incremental indexing scales better than full indexing."""
    from src.infrastructure.indexing.incremental import IncrementalIndexer

    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create 50 files
    file_count = 50
    for i in range(file_count):
        (project_root / f"module_{i}.py").write_text(f"def func_{i}(): return {i}\n")

    class MockKB:
        upsert_count = 0

        async def upsert_entries(self, chunks, embeddings):
            self.upsert_count += len(chunks)
            await asyncio.sleep(0.001)

        async def delete_by_source(self, path):
            pass

    class MockEmbed:
        async def embed_batch(self, texts):
            return [[0.1] * 384 for _ in texts]

    db_path = tmp_path / "index_state.db"
    indexer = IncrementalIndexer(
        kb=MockKB(),
        embed_svc=MockEmbed(),
        state_db=db_path,
        concurrency=4,
    )
    indexer.connect()

    # Full sync
    stats1 = await indexer.sync(project_root)
    full_sync_time = stats1.elapsed_seconds

    # Modify 5 files (10% change)
    for i in range(5):
        (project_root / f"module_{i}.py").write_text(f"def updated_{i}(): return 'updated'\n")

    MockKB.upsert_count = 0
    stats2 = await indexer.sync(project_root)
    incremental_time = stats2.elapsed_seconds

    assert stats2.changed_files == 5
    assert stats2.skipped_files == file_count - 5

    indexer.close()

    speedup = full_sync_time / incremental_time if incremental_time > 0 else float('inf')
    print(f"\n[Benchmark] Incremental Scaling:")
    print(f"  Full sync: {full_sync_time * 1000:.1f}ms for {file_count} files")
    print(f"  Incremental (10% change): {incremental_time * 1000:.1f}ms")
    print(f"  Speedup: {speedup:.1f}x")

    # Incremental should be significantly faster
    assert speedup > 3, f"Expected >3x speedup, got {speedup:.1f}x"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
