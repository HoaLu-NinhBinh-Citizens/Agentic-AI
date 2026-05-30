"""
Parallel processing for large codebases.
Uses multiprocessing and async I/O for optimal performance.
"""

import asyncio
import hashlib
import json
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional, Callable, Any
import os


@dataclass
class ProcessingStats:
    """Statistics for parallel processing operations."""
    files_processed: int = 0
    files_failed: int = 0
    total_bytes: int = 0
    duration_seconds: float = 0.0
    throughput_mbps: float = 0.0


class ParallelProcessor:
    """
    Process large codebases in parallel.
    Uses both multiprocessing (CPU-bound) and threading (I/O-bound).
    """

    def __init__(
        self,
        max_workers: Optional[int] = None,
        chunk_size: int = 100
    ):
        self.max_workers = max_workers or os.cpu_count()
        self.chunk_size = chunk_size
        self._stats = ProcessingStats()

    def process_files(
        self,
        files: list[Path],
        processor: Callable[[Path], Any],
        use_multiprocessing: bool = True
    ) -> list[Any]:
        """
        Process multiple files in parallel.

        Args:
            files: List of files to process
            processor: Function to process each file
            use_multiprocessing: Use multiprocessing (True) or threading (False)

        Returns:
            List of results from each file
        """
        if use_multiprocessing:
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                results = list(executor.map(processor, files, chunksize=self.chunk_size))
        else:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                results = list(executor.map(processor, files))

        return results

    async def process_files_async(
        self,
        files: list[Path],
        processor: Callable[[Path], Any]
    ) -> list[Any]:
        """
        Process files asynchronously with rate limiting.
        """
        semaphore = asyncio.Semaphore(self.max_workers)

        async def process_with_limit(file: Path) -> Any:
            async with semaphore:
                return processor(file)

        tasks = [process_with_limit(f) for f in files]
        return await asyncio.gather(*tasks)

    def process_streaming(
        self,
        files: list[Path],
        processor: Callable[[Path], Iterator[Any]]
    ) -> Iterator[Any]:
        """
        Process files in streaming mode for memory efficiency.
        Yields results as they come in.
        """
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(processor, f) for f in files]

            for future in futures:
                for result in future.result():
                    yield result

    def process_batch(
        self,
        files: list[Path],
        batch_processor: Callable[[list[Path]], list[Any]],
        batch_size: int = 50
    ) -> list[Any]:
        """
        Process files in batches for better memory management.
        """
        results = []

        for i in range(0, len(files), batch_size):
            batch = files[i:i + batch_size]
            batch_results = batch_processor(batch)
            results.extend(batch_results)

        return results


class IncrementalProcessor:
    """
    Process only changed files since last run.
    Uses content hashing to detect changes.
    """

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file = cache_dir / "file_hashes.json"
        self._file_hashes: dict[str, str] = self._load_cache()

    def _load_cache(self) -> dict[str, str]:
        """Load cached file hashes."""
        if self._cache_file.exists():
            return json.loads(self._cache_file.read_text(encoding="utf-8"))
        return {}

    def _save_cache(self):
        """Save file hashes to cache."""
        self._cache_file.write_text(json.dumps(self._file_hashes, indent=2), encoding="utf-8")

    def get_changed_files(
        self,
        files: list[Path]
    ) -> tuple[list[Path], list[Path]]:
        """
        Get files that have changed since last run.

        Returns:
            (changed_files, unchanged_files)
        """
        changed = []
        unchanged = []

        for f in files:
            try:
                content = f.read_bytes()
                file_hash = hashlib.sha256(content).hexdigest()

                key = str(f)
                if key not in self._file_hashes or self._file_hashes[key] != file_hash:
                    changed.append(f)
                    self._file_hashes[key] = file_hash
                else:
                    unchanged.append(f)
            except Exception:
                changed.append(f)

        self._save_cache()
        return changed, unchanged

    def process_incremental(
        self,
        files: list[Path],
        processor: Callable[[Path], Any]
    ) -> dict[str, Any]:
        """
        Process only changed files, use cached results for unchanged.
        """
        changed, unchanged = self.get_changed_files(files)

        results = {}

        for f in changed:
            try:
                results[str(f)] = processor(f)
            except Exception as e:
                results[str(f)] = {"error": str(e)}

        for f in unchanged:
            cached = self._get_cached_result(f)
            if cached:
                results[str(f)] = cached

        return results

    def _get_cached_result(self, file: Path) -> Optional[Any]:
        """Get cached result for a file."""
        cache_file = self.cache_dir / f"{file.stem}_{file.suffix.lstrip('.')}.json"

        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))

        return None

    def _cache_result(self, file: Path, result: Any):
        """Cache result for a file."""
        cache_file = self.cache_dir / f"{file.stem}_{file.suffix.lstrip('.')}.json"
        cache_file.write_text(json.dumps(result), encoding="utf-8")
