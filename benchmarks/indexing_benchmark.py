#!/usr/bin/env python3
"""Benchmark script for indexing performance.

Run from repository root:
    python benchmarks/indexing_benchmark.py
    python benchmarks/indexing_benchmark.py --files 1000 --workers 8
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.indexing.hash_utils import compute_short_hash


# =============================================================================
# LRU CACHED HASH FUNCTIONS
# =============================================================================


@lru_cache(maxsize=10000)
def cached_content_hash(content: str) -> str:
    """LRU-cached content hash for repeated lookups."""
    return compute_short_hash(content)


def compute_file_hash_parallel(
    files: list[Path],
    max_workers: int = 4,
) -> dict[str, tuple[str, float]]:
    """Compute content hashes for multiple files in parallel."""
    results: dict[str, tuple[str, float]] = {}
    
    def hash_one(path: Path) -> tuple[str, tuple[str, float]]:
        try:
            mtime = path.stat().st_mtime
            content = path.read_text(encoding="utf-8", errors="replace")
            content_hash = cached_content_hash(content)
            return str(path), (content_hash, mtime)
        except OSError:
            return str(path), ("", 0.0)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(hash_one, f): f for f in files}
        for future in as_completed(futures):
            try:
                path_str, (content_hash, mtime) = future.result()
                results[path_str] = (content_hash, mtime)
            except Exception:
                pass
    
    return results


# =============================================================================
# INDEXED EXTENSIONS
# =============================================================================

INDEXED_EXTENSIONS = {
    ".py", ".c", ".h", ".cpp", ".hpp", ".cc", ".cxx",
    ".rs", ".go", ".java", ".ts", ".tsx", ".js", ".jsx",
    ".yaml", ".yml", ".toml", ".json", ".md",
}

EXCLUDE_PATTERNS = {
    "node_modules", ".git", "__pycache__", ".pytest_cache",
    "build", "dist", ".venv", "venv", ".tox", ".mypy_cache",
    "*.pyc", "*.pyo", ".DS_Store",
}


def is_indexable(file_path: Path) -> bool:
    """Return True if file should be indexed based on extension and exclusions."""
    if file_path.suffix.lower() not in INDEXED_EXTENSIONS:
        return False
    name = file_path.name
    if name in EXCLUDE_PATTERNS or name.startswith("."):
        return False
    for part in file_path.parts:
        if part in EXCLUDE_PATTERNS:
            return False
    return True


def discover_files(root: Path) -> list[Path]:
    """Walk `root` and return all indexable files."""
    files = []
    for path in root.rglob("*"):
        if path.is_file() and is_indexable(path):
            files.append(path)
    return files


# =============================================================================
# STATE DB (simplified for benchmark)
# =============================================================================

import sqlite3


@dataclass(slots=True)
class FileState:
    """State record for one tracked file."""
    path: str
    mtime: float
    content_hash: str
    indexed_at: float | None


class IndexStateDB:
    """SQLite-backed file state tracker for incremental indexing."""

    def __init__(self, db_path: Path | str = ".ai_support/index_state.db"):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS file_index_state (
                path       TEXT    PRIMARY KEY,
                mtime      REAL    NOT NULL,
                content_hash TEXT  NOT NULL,
                indexed_at REAL
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_indexed_at
            ON file_index_state (indexed_at)
        """)
        self._conn.commit()

    def get(self, path: str) -> FileState | None:
        row = self._conn.execute(
            "SELECT path, mtime, content_hash, indexed_at FROM file_index_state WHERE path=?",
            (path,),
        ).fetchone()
        return FileState(*row) if row else None

    def upsert(self, state: FileState) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO file_index_state
               (path, mtime, content_hash, indexed_at) VALUES (?,?,?,?)""",
            (state.path, state.mtime, state.content_hash, state.indexed_at),
        )
        self._conn.commit()


@dataclass
class IndexerStats:
    """Statistics from an indexing run."""
    total_files: int = 0
    changed_files: int = 0
    indexed_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    elapsed_seconds: float = 0.0


def create_test_files(tmp_dir: Path, count: int, content_size: str = "small") -> list[Path]:
    """Create test files with varying content sizes.
    
    Args:
        tmp_dir: Directory to create files in
        count: Number of files to create
        content_size: "small", "medium", or "large"
    """
    files = []
    content_templates = {
        "small": "def func_{i}(): return {i}\n",
        "medium": "class Class{i}:\n    def method_{i}(self):\n        return {i}\n",
        "large": """
class Class{i}:
    \"\"\"A sample class for benchmarking.\"\"\"
    
    def __init__(self):
        self.value = {i}
    
    def method_{i}(self):
        return self.value * 2
    
    @staticmethod
    def static_method():
        return "static"
    
    @classmethod
    def class_method(cls):
        return cls.__name__
    
    def _private_method(self):
        return self.value
""",
    }
    
    template = content_templates.get(content_size, content_templates["small"])
    
    for i in range(count):
        content = template.format(i=i) * (3 if content_size == "small" else 1)
        file_path = tmp_dir / f"benchmark_file_{i:04d}.py"
        file_path.write_text(content)
        files.append(file_path)
    
    return files


def benchmark_file_discovery(root: Path) -> dict:
    """Benchmark file discovery performance."""
    start = time.perf_counter()
    files = discover_files(root)
    elapsed = time.perf_counter() - start
    
    return {
        "operation": "file_discovery",
        "file_count": len(files),
        "elapsed_seconds": elapsed,
        "throughput": len(files) / elapsed if elapsed > 0 else 0,
    }


def benchmark_parallel_hashing(files: list[Path], workers: int = 4) -> dict:
    """Benchmark parallel file hashing."""
    # Clear cache
    cached_content_hash.cache_clear()
    
    start = time.perf_counter()
    results = compute_file_hash_parallel(files, max_workers=workers)
    elapsed = time.perf_counter() - start
    
    return {
        "operation": "parallel_hash",
        "file_count": len(files),
        "workers": workers,
        "elapsed_seconds": elapsed,
        "throughput": len(files) / elapsed if elapsed > 0 else 0,
    }


def benchmark_cached_hashing(contents: list[str], iterations: int = 3) -> dict:
    """Benchmark LRU cached hashing."""
    results = []
    
    # Clear cache
    cached_content_hash.cache_clear()
    
    for i in range(iterations):
        start = time.perf_counter()
        hashes = [cached_content_hash(c) for c in contents]
        elapsed = time.perf_counter() - start
        results.append({
            "iteration": i + 1,
            "elapsed_seconds": elapsed,
            "throughput": len(contents) / elapsed if elapsed > 0 else 0,
        })
    
    # Calculate average
    avg_elapsed = sum(r["elapsed_seconds"] for r in results) / len(results)
    
    return {
        "operation": "cached_hash",
        "content_count": len(contents),
        "iterations": iterations,
        "avg_elapsed_seconds": avg_elapsed,
        "avg_throughput": len(contents) / avg_elapsed if avg_elapsed > 0 else 0,
        "per_iteration": results,
    }


def benchmark_index_state_db(tmp_path: Path, file_count: int) -> dict:
    """Benchmark index state database operations."""
    db_path = tmp_path / "benchmark_index.db"
    db = IndexStateDB(db_path)
    db.connect()
    
    # Benchmark insert
    states = [
        FileState(
            path=f"/test/file_{i}.py",
            mtime=1234567890.0 + i,
            content_hash=f"hash_{i:06d}",
            indexed_at=1234567891.0 + i,
        )
        for i in range(file_count)
    ]
    
    start = time.perf_counter()
    for state in states:
        db.upsert(state)
    insert_elapsed = time.perf_counter() - start
    
    # Benchmark query
    start = time.perf_counter()
    for i in range(file_count):
        db.get(f"/test/file_{i}.py")
    query_elapsed = time.perf_counter() - start
    
    db.close()
    
    return {
        "operation": "index_state_db",
        "file_count": file_count,
        "insert_elapsed_seconds": insert_elapsed,
        "insert_throughput": file_count / insert_elapsed if insert_elapsed > 0 else 0,
        "query_elapsed_seconds": query_elapsed,
        "query_throughput": file_count / query_elapsed if query_elapsed > 0 else 0,
    }


async def benchmark_full_indexing_cycle(
    tmp_path: Path,
    file_count: int,
    workers: int = 4,
) -> dict:
    """Benchmark a full indexing cycle.
    
    Note: This requires importing from the main codebase.
    Returns a placeholder result for now.
    """
    # Import lazily to avoid slots issues
    try:
        from src.infrastructure.indexing.incremental import IncrementalIndexer
    except (TypeError, ImportError):
        return {
            "operation": "full_indexing",
            "file_count": file_count,
            "workers": workers,
            "elapsed_seconds": 0.0,
            "throughput": 0.0,
            "note": "Skipped due to import error",
            "stats": {
                "total_files": 0,
                "indexed_files": 0,
                "changed_files": 0,
                "failed_files": 0,
            },
        }
    
    # Create test files
    files = create_test_files(tmp_path, file_count, "medium")
    
    # Mock KB and embed service
    class MockKB:
        async def upsert_entries(self, chunks, embeddings):
            await asyncio.sleep(0.001)  # Simulate async
    
    class MockEmbed:
        async def embed_batch(self, texts):
            return [[0.1] * 384 for _ in texts]
    
    # Create indexer
    indexer = IncrementalIndexer(
        kb=MockKB(),
        embed_svc=MockEmbed(),
        state_db=tmp_path / "index_state.db",
        concurrency=4,
        hash_workers=workers,
    )
    indexer.connect()
    
    # Run indexing
    start = time.perf_counter()
    stats = await indexer.sync(tmp_path)
    elapsed = time.perf_counter() - start
    
    indexer.close()
    
    return {
        "operation": "full_indexing",
        "file_count": file_count,
        "workers": workers,
        "elapsed_seconds": elapsed,
        "throughput": file_count / elapsed if elapsed > 0 else 0,
        "stats": {
            "total_files": stats.total_files,
            "indexed_files": stats.indexed_files,
            "changed_files": stats.changed_files,
            "failed_files": stats.failed_files,
        },
    }


def print_benchmark_result(name: str, result: dict) -> None:
    """Print benchmark result in a formatted way."""
    print(f"\n{'='*60}")
    print(f"BENCHMARK: {name}")
    print(f"{'='*60}")
    
    for key, value in result.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        elif isinstance(value, dict):
            print(f"  {key}:")
            for k, v in value.items():
                if isinstance(v, float):
                    print(f"    {k}: {v:.4f}")
                else:
                    print(f"    {k}: {v}")
        else:
            print(f"  {key}: {value}")


def main():
    parser = argparse.ArgumentParser(description="Indexing Performance Benchmark")
    parser.add_argument("--files", type=int, default=100, help="Number of test files")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers")
    parser.add_argument("--content", choices=["small", "medium", "large"], 
                       default="small", help="Content size")
    parser.add_argument("--skip-full", action="store_true", help="Skip full indexing benchmark")
    args = parser.parse_args()
    
    print(f"\n{'#'*60}")
    print(f"# INDEXING PERFORMANCE BENCHMARK")
    print(f"# Files: {args.files}, Workers: {args.workers}, Content: {args.content}")
    print(f"{'#'*60}")
    
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        
        # Create test files
        print(f"\nCreating {args.files} test files...")
        files = create_test_files(tmp_path, args.files, args.content)
        print(f"Created {len(files)} files")
        
        # Benchmark file discovery
        result = benchmark_file_discovery(tmp_path)
        print_benchmark_result("File Discovery", result)
        
        # Benchmark parallel hashing
        result = benchmark_parallel_hashing(files, args.workers)
        print_benchmark_result("Parallel Hashing", result)
        
        # Benchmark cached hashing
        contents = [f"def func_{i}(): return {i}" * 50 for i in range(args.files)]
        result = benchmark_cached_hashing(contents)
        print_benchmark_result("LRU Cached Hashing", result)
        
        # Benchmark index state DB
        result = benchmark_index_state_db(tmp_path, args.files)
        print_benchmark_result("Index State DB", result)
        
        # Benchmark full indexing cycle (if not skipped)
        if not args.skip_full and args.files <= 200:
            print(f"\nRunning full indexing benchmark (this may take a moment)...")
            result = asyncio.run(benchmark_full_indexing_cycle(tmp_path, args.files, args.workers))
            print_benchmark_result("Full Indexing Cycle", result)
        elif args.skip_full:
            print("\n[Skipped: Full indexing benchmark]")
        else:
            print(f"\n[Skipped: Full indexing benchmark for {args.files} files]")
        
        # Summary
        print(f"\n{'='*60}")
        print(f"SUMMARY")
        print(f"{'='*60}")
        print(f"Test configuration:")
        print(f"  - File count: {args.files}")
        print(f"  - Worker threads: {args.workers}")
        print(f"  - Content size: {args.content}")


if __name__ == "__main__":
    main()
