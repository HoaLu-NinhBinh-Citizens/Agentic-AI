"""Core memory module exports."""

from .semantic_memory import SemanticMemory, MemoryRecord, MemoryResult
from .chunker import Chunker, Chunk
from .deduplication import DeduplicationEngine

__all__ = [
    "SemanticMemory",
    "MemoryRecord",
    "MemoryResult",
    "Chunker",
    "Chunk",
    "DeduplicationEngine",
]
