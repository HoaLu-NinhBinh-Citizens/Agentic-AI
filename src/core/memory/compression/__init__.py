"""Compression module for SemanticMemory and ToolCache.

Phase 4E Production Fixes:
- Atomic transactions (save_blob + compress)
- Redis lock with token ownership + heartbeat
- Real LRU cache (OrderedDict)
- CPU/resource guards
- Extractive summarizer sentence cap
- Similarity validation sampling
- SQLite production tuning
- Priority scheduling
- Integrity scanner
- Strategy migration framework
"""

from .types import (
    CompressionMetadata,
    CompressionResult,
    CompressionStrategyType,
    MemoryItem,
    CacheItem,
    CompressionStats,
)
from .config import (
    CompressionConfig,
    WorkerConfig,
    StrategyConfig,
    QualityConfig,
    ExtractiveConfig,
    DistributedLockConfig,
)
from .engine import CompressionEngine, RedisDistributedLock
from .worker import CompressionWorker, BatchResult, PriorityScheduler
from .decompression import DecompressionCache, Decompressor
from .pruner import SoftDeletePruner, PermanentPurgeJob
from .integrity_scanner import IntegrityScanner, IntegrityReport, ScanResult
from .migration import StrategyMigration, StrategyVersion, MigrationReport

__all__ = [
    # Types
    "CompressionMetadata",
    "CompressionResult",
    "CompressionStrategyType",
    "MemoryItem",
    "CacheItem",
    "CompressionStats",
    # Config
    "CompressionConfig",
    "WorkerConfig",
    "StrategyConfig",
    "QualityConfig",
    "ExtractiveConfig",
    "DistributedLockConfig",
    # Engine
    "CompressionEngine",
    "RedisDistributedLock",
    # Worker
    "CompressionWorker",
    "BatchResult",
    "PriorityScheduler",
    # Decompression
    "DecompressionCache",
    "Decompressor",
    # Pruner
    "SoftDeletePruner",
    "PermanentPurgeJob",
    # Integrity Scanner
    "IntegrityScanner",
    "IntegrityReport",
    "ScanResult",
    # Migration
    "StrategyMigration",
    "StrategyVersion",
    "MigrationReport",
]
