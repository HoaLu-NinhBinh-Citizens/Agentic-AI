"""Incremental Indexer — only re-index changed files since last run."""

from src.infrastructure.indexing.hash_utils import (
    compute_content_hash,
    compute_file_hash,
    compute_short_hash,
)
from src.infrastructure.indexing.incremental import (
    EXCLUDE_PATTERNS,
    INDEXED_EXTENSIONS,
    FileState,
    IndexStateDB,
    IndexerStats,
    IncrementalIndexer,
    discover_files,
    is_indexable,
)

__all__ = [
    # Hash utilities
    "compute_content_hash",
    "compute_file_hash",
    "compute_short_hash",
    # Incremental indexer
    "IncrementalIndexer",
    "IndexStateDB",
    "IndexerStats",
    "FileState",
    "discover_files",
    "is_indexable",
    "INDEXED_EXTENSIONS",
    "EXCLUDE_PATTERNS",
]
