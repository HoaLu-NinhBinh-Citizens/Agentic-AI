"""Incremental Indexer — only re-index changed files since last run."""

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
    "IncrementalIndexer",
    "IndexStateDB",
    "IndexerStats",
    "FileState",
    "discover_files",
    "is_indexable",
    "INDEXED_EXTENSIONS",
    "EXCLUDE_PATTERNS",
]
