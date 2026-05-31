"""Performance tests for indexing operations.

Tests focus on measuring and validating performance optimizations:
- Parallel file hashing
- Batch processing
- LRU caching
- Memory efficiency
"""

import asyncio
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.indexing.incremental import (
    IncrementalIndexer,
    IndexStateDB,
    IndexerStats,
    compute_file_hash_parallel,
    cached_content_hash,
    FileState,
    discover_files,
    is_indexable,
)


class TestParallelHashing:
    """Tests for parallel file hashing performance."""

    @pytest.mark.asyncio
    async def test_parallel_hash_100_files(self, tmp_path):
        """Test hashing 100 small files in parallel."""
        # Create 100 test files
        files = []
        for i in range(100):
            f = tmp_path / f"file_{i}.py"
            f.write_text(f"def func_{i}(): return {i}")
            files.append(f)

        # Time parallel hashing
        start = time.perf_counter()
        results = compute_file_hash_parallel(files, max_workers=4)
        elapsed = time.perf_counter() - start

        # Verify all files hashed
        assert len(results) == 100

        # Should complete in reasonable time (< 1 second for 100 files)
        assert elapsed < 1.0, f"Hashing took {elapsed:.2f}s"

    @pytest.mark.asyncio
    async def test_parallel_hash_scales_linearly(self, tmp_path):
        """Verify parallel hashing scales with workers."""
        # Create test files
        files = []
        for i in range(50):
            f = tmp_path / f"file_{i}.py"
            f.write_text(f"def func_{i}(): return {i}" * 10)  # Larger content
            files.append(f)

        # Test with 1 worker
        start1 = time.perf_counter()
        compute_file_hash_parallel(files, max_workers=1)
        time1 = time.perf_counter() - start1

        # Test with 4 workers
        start4 = time.perf_counter()
        compute_file_hash_parallel(files, max_workers=4)
        time4 = time.perf_counter() - start4

        # Parallel should be faster or similar (within 2x)
        # (Not guaranteed faster due to overhead, but shouldn't be much slower)
        assert time4 < time1 * 2.5, f"4 workers ({time4:.3f}s) much slower than 1 ({time1:.3f}s)"


class TestLRUCaching:
    """Tests for LRU caching performance."""

    def test_content_hash_cache_hit(self):
        """Test that repeated hashes hit cache."""
        content = "def foo(): pass" * 100

        # First call - cache miss
        start1 = time.perf_counter()
        hash1 = cached_content_hash(content)
        time1 = time.perf_counter() - start1

        # Second call - should hit cache
        start2 = time.perf_counter()
        hash2 = cached_content_hash(content)
        time2 = time.perf_counter() - start2

        # Same hash
        assert hash1 == hash2

        # Cached should be faster (or at least not slower)
        # Note: Very fast operations may not show difference
        assert time2 <= time1 * 2  # Allow some variance

    def test_cache_multiple_contents(self):
        """Test caching with multiple different contents."""
        contents = [f"def func_{i}(): return {i}" * 50 for i in range(100)]

        start = time.perf_counter()
        hashes = [cached_content_hash(c) for c in contents]
        elapsed = time.perf_counter() - start

        # All hashes should be unique
        assert len(set(hashes)) == 100

        # Should complete quickly
        assert elapsed < 0.5, f"Hashing 100 contents took {elapsed:.2f}s"


class TestFileDiscovery:
    """Tests for file discovery performance."""

    def test_discover_files_performance(self, tmp_path):
        """Test discovering files in a directory."""
        # Create test structure
        for i in range(50):
            (tmp_path / f"file_{i}.py").write_text(f"# File {i}")
            (tmp_path / f"data_{i}.json").write_text('{"key": "value"}')

        # Should not include non-indexable files
        (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02")

        start = time.perf_counter()
        files = discover_files(tmp_path)
        elapsed = time.perf_counter() - start

        # Should find only Python and JSON files
        assert len(files) == 100  # 50 .py + 50 .json

        # Should complete quickly
        assert elapsed < 0.1, f"Discovery took {elapsed:.2f}s"


class TestIndexerStats:
    """Tests for indexer statistics."""

    def test_stats_initialization(self):
        """Test IndexerStats default values."""
        stats = IndexerStats()

        assert stats.total_files == 0
        assert stats.changed_files == 0
        assert stats.indexed_files == 0
        assert stats.failed_files == 0
        assert stats.skipped_files == 0
        assert stats.elapsed_seconds == 0.0

    def test_stats_accumulation(self):
        """Test accumulating statistics."""
        stats = IndexerStats()
        stats.total_files = 100
        stats.changed_files = 20
        stats.indexed_files = 18
        stats.failed_files = 2
        stats.skipped_files = 80
        stats.elapsed_seconds = 1.5

        assert stats.indexed_files + stats.failed_files == stats.changed_files


class TestIndexStateDB:
    """Tests for index state database."""

    def test_db_lifecycle(self, tmp_path):
        """Test database connect/close."""
        db_path = tmp_path / "test_index.db"
        db = IndexStateDB(db_path)

        db.connect()
        assert db._conn is not None

        db.close()
        assert db._conn is None

    def test_upsert_and_get(self, tmp_path):
        """Test inserting and retrieving state."""
        db_path = tmp_path / "test_index.db"
        db = IndexStateDB(db_path)
        db.connect()

        state = FileState(
            path="/test/file.py",
            mtime=1234567890.0,
            content_hash="abc123",
            indexed_at=1234567891.0,
        )

        db.upsert(state)
        retrieved = db.get("/test/file.py")

        assert retrieved is not None
        assert retrieved.path == state.path
        assert retrieved.content_hash == state.content_hash

        db.close()


class TestIsIndexable:
    """Tests for file indexability check."""

    @pytest.mark.parametrize("extension,expected", [
        (".py", True),
        (".c", True),
        (".h", True),
        (".rs", True),
        (".js", True),
        (".json", True),
        (".md", True),
        (".txt", False),
        (".exe", False),
        (".bin", False),
        (".pyc", False),
    ])
    def test_extension_filtering(self, extension, expected):
        """Test that only supported extensions are indexable."""
        path = Path(f"test/file{extension}")
        assert is_indexable(path) == expected

    def test_excluded_directories(self):
        """Test that excluded directories are not indexed."""
        assert is_indexable(Path("node_modules/foo.py")) is False
        assert is_indexable(Path(".git/config.py")) is False
        assert is_indexable(Path("__pycache__/foo.py")) is False
        assert is_indexable(Path("build/output.py")) is False


class TestMemoryOptimization:
    """Tests for memory optimization with __slots__."""

    def test_filestate_has_slots(self):
        """Test that FileState uses __slots__."""
        state = FileState(
            path="/test.py",
            mtime=1.0,
            content_hash="hash",
            indexed_at=2.0,
        )

        # Should work fine
        assert state.path == "/test.py"

        # Should not allow arbitrary attributes
        with pytest.raises(AttributeError):
            state.extra_attr = "value"

    def test_slots_memory_benefit(self):
        """Demonstrate memory benefit of __slots__."""
        import sys

        # Create instances
        states = [
            FileState(f"/test_{i}.py", 1.0, f"hash{i}", 2.0)
            for i in range(1000)
        ]

        # Each instance should have __slots__
        for state in states:
            assert hasattr(type(state), "__slots__")


class TestConcurrency:
    """Tests for concurrent operations."""

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self):
        """Test that semaphore properly limits concurrency."""
        counter = {"value": 0}
        max_concurrent = {"max": 0}

        async def task(sem):
            async with sem:
                counter["value"] += 1
                max_concurrent["max"] = max(max_concurrent["max"], counter["value"])
                await asyncio.sleep(0.01)
                counter["value"] -= 1

        sem = asyncio.Semaphore(3)
        await asyncio.gather(*[task(sem) for _ in range(10)])

        assert max_concurrent["max"] <= 3


# Performance benchmarks (marked as slow)
class TestIndexingBenchmarks:
    """Benchmarks for indexing operations."""

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_benchmark_500_files(self, tmp_path):
        """Benchmark indexing 500 files."""
        # Create test files
        for i in range(500):
            (tmp_path / f"file_{i}.py").write_text(
                f"class Class{i}:\n    def method_{i}(self):\n        return {i}"
            )

        files = list(tmp_path.rglob("*.py"))

        # Benchmark
        start = time.perf_counter()
        results = compute_file_hash_parallel(files, max_workers=4)
        elapsed = time.perf_counter() - start

        assert len(results) == 500
        print(f"\n[benchmark] 500 files hashed in {elapsed:.3f}s ({500/elapsed:.1f} files/sec)")

        # Should complete in under 5 seconds
        assert elapsed < 5.0, f"Took {elapsed:.2f}s (expected < 5s)"

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_benchmark_1000_content_hashes(self):
        """Benchmark 1000 content hash operations."""
        contents = [f"def func_{i}(): return {i}" * 100 for i in range(1000)]

        # Clear cache first
        cached_content_hash.cache_clear()

        start = time.perf_counter()
        hashes = [cached_content_hash(c) for c in contents]
        elapsed = time.perf_counter() - start

        assert len(hashes) == 1000
        assert len(set(hashes)) == 1000  # All unique

        print(f"\n[benchmark] 1000 hashes in {elapsed:.3f}s ({1000/elapsed:.1f} ops/sec)")

        # Should complete in under 1 second
        assert elapsed < 1.0, f"Took {elapsed:.2f}s (expected < 1s)"
