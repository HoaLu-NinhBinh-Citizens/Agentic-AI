"""Core memory module exports."""

from .semantic_memory import SemanticMemory, MemoryRecord, MemoryResult
from .chunker import Chunker, Chunk
from .deduplication import DeduplicationEngine
from .store import AgentMemory

# Long-horizon memory for agent consistency
from .long_horizon_memory import LongHorizonMemory, MemoryType, MemoryItem

__all__ = [
    "SemanticMemory",
    "MemoryRecord",
    "MemoryResult",
    "Chunker",
    "Chunk",
    "DeduplicationEngine",
    "AgentMemory",
    "LongHorizonMemory",
    "MemoryType",
    "MemoryItem",
]
