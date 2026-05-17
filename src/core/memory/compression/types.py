"""Type definitions for the compression module."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class CompressionStrategyType(str, Enum):
    """Available compression strategy types."""
    TRUNCATION = "truncation"
    EXTRACTIVE = "extractive"
    KEYVALUE = "kv_compact"
    ADAPTIVE = "adaptive_prune"


@dataclass
class CompressionMetadata:
    """Metadata stored with compressed content for reversible decompression."""
    
    strategy: str
    strategy_version: str = "1.0"  # For migration compatibility
    params: dict[str, Any] = field(default_factory=dict)
    model_version: Optional[str] = None
    original_hash: Optional[str] = None
    is_lossless: bool = False  # Only True for lossless strategies (e.g., gzip)
    selected_indices: Optional[list[int]] = None
    kept_fields: Optional[list[str]] = None
    start_truncate: int = 0
    end_truncate: int = 0
    semantic_similarity: float = 0.85
    compressed_at: int = field(default_factory=lambda: int(time.time()))
    error: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON storage."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompressionMetadata:
        """Create from dictionary."""
        if isinstance(data, str):
            data = json.loads(data)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())


@dataclass
class CompressionResult:
    """Result of a compression operation."""
    
    success: bool
    compressed_content: Optional[str] = None
    metadata: Optional[CompressionMetadata] = None
    original_length: int = 0
    compressed_length: int = 0
    error: Optional[str] = None
    version_mismatch: bool = False
    
    @property
    def compression_ratio(self) -> float:
        """Calculate compression ratio."""
        if self.compressed_length == 0:
            return 1.0
        return self.original_length / self.compressed_length
    
    @property
    def space_saved(self) -> int:
        """Calculate bytes saved."""
        return self.original_length - self.compressed_length


@dataclass
class MemoryItem:
    """A memory item with compression fields."""
    
    id: str
    type: str
    content: str
    session_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: int = field(default_factory=lambda: int(time.time()))
    chunk_index: int = 0
    chunk_total: int = 1
    parent_id: str = ""
    
    # Compression fields
    compressed: bool = False
    compression_type: Optional[str] = None
    compression_metadata: Optional[CompressionMetadata] = None
    original_length: int = 0
    compressed_length: int = 0
    semantic_similarity: float = 0.0
    last_compressed_at: Optional[int] = None
    compression_attempt_count: int = 0
    no_compress: bool = False
    deleted: bool = False
    deleted_at: Optional[int] = None
    cold_storage_ref: Optional[str] = None
    
    # Versioning
    last_updated: int = field(default_factory=lambda: int(time.time()))
    version: int = 1
    original_content_hash: Optional[str] = None
    
    # Access tracking
    access_count: int = 0
    last_accessed: Optional[int] = None
    
    # No-compress TTL (item can be re-evaluated after this timestamp)
    no_compress_until: Optional[int] = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database storage."""
        data = asdict(self)
        if self.compression_metadata:
            data["compression_metadata"] = self.compression_metadata.to_json()
        return data
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryItem:
        """Create from database row."""
        if "compression_metadata" in data and data["compression_metadata"]:
            if isinstance(data["compression_metadata"], str):
                data["compression_metadata"] = CompressionMetadata.from_dict(
                    data["compression_metadata"]
                )
            elif isinstance(data["compression_metadata"], dict):
                data["compression_metadata"] = CompressionMetadata.from_dict(
                    data["compression_metadata"]
                )
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class CacheItem:
    """A cache item with compression fields."""
    
    id: str
    cache_key: str
    content: str
    tool_name: str = ""
    args_hash: str = ""
    created_at: int = field(default_factory=lambda: int(time.time()))
    expires_at: int = 0
    access_count: int = 0
    last_accessed: Optional[int] = None
    
    # Compression fields
    compressed: bool = False
    compression_type: Optional[str] = None
    compression_metadata: Optional[CompressionMetadata] = None
    original_length: int = 0
    compressed_length: int = 0
    semantic_similarity: float = 0.0
    last_compressed_at: Optional[int] = None
    compression_attempt_count: int = 0
    no_compress: bool = False
    deleted: bool = False
    deleted_at: Optional[int] = None
    cold_storage_ref: Optional[str] = None
    
    # Versioning
    last_updated: int = field(default_factory=lambda: int(time.time()))
    version: int = 1
    original_content_hash: Optional[str] = None
    
    # No-compress TTL (item can be re-evaluated after this timestamp)
    no_compress_until: Optional[int] = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database storage."""
        data = asdict(self)
        if self.compression_metadata:
            data["compression_metadata"] = self.compression_metadata.to_json()
        return data
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CacheItem:
        """Create from database row."""
        if "compression_metadata" in data and data["compression_metadata"]:
            if isinstance(data["compression_metadata"], str):
                data["compression_metadata"] = CompressionMetadata.from_dict(
                    data["compression_metadata"]
                )
            elif isinstance(data["compression_metadata"], dict):
                data["compression_metadata"] = CompressionMetadata.from_dict(
                    data["compression_metadata"]
                )
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class OriginalBlob:
    """Original content stored for fallback decompression."""
    
    id: int = 0
    item_id: str = ""
    content: str = ""
    content_hash: str = ""
    item_type: str = ""
    compressed_at: Optional[int] = None
    deleted_at: Optional[int] = None


@dataclass
class CompressionStats:
    """Statistics for compression operations."""
    
    items_compressed: int = 0
    items_failed: int = 0
    items_skipped_version_mismatch: int = 0
    items_skipped_age: int = 0
    items_skipped_flag: int = 0
    
    compression_ratio_sum: float = 0.0
    semantic_similarity_sum: float = 0.0
    count: int = 0
    
    worker_latency_ms_sum: float = 0.0
    worker_latency_count: int = 0
    
    decompression_cache_hits: int = 0
    decompression_cache_misses: int = 0
    
    soft_deleted_count: int = 0
    permanent_purged_count: int = 0
    
    # Phase 4E: Issue #6 - Integrity scanner metrics
    integrity_scan_passed: int = 0
    integrity_scan_failed: int = 0
    integrity_scan_repaired: int = 0
    
    # Phase 4E: Issue #6 - Migration metrics
    migration_migrated: int = 0
    migration_failed: int = 0
    
    def update_compression(self, ratio: float, similarity: float) -> None:
        """Update compression statistics."""
        self.compression_ratio_sum += ratio
        self.semantic_similarity_sum += similarity
        self.count += 1
    
    def update_worker_latency(self, latency_ms: float) -> None:
        """Update worker latency statistics."""
        self.worker_latency_ms_sum += latency_ms
        self.worker_latency_count += 1
    
    @property
    def avg_compression_ratio(self) -> float:
        """Average compression ratio."""
        if self.count == 0:
            return 1.0
        return self.compression_ratio_sum / self.count
    
    @property
    def avg_semantic_similarity(self) -> float:
        """Average semantic similarity."""
        if self.count == 0:
            return 0.0
        return self.semantic_similarity_sum / self.count
    
    @property
    def avg_worker_latency_ms(self) -> float:
        """Average worker latency in milliseconds."""
        if self.worker_latency_count == 0:
            return 0.0
        return self.worker_latency_ms_sum / self.worker_latency_count
    
    @property
    def decompression_cache_hit_rate(self) -> float:
        """Cache hit rate."""
        total = self.decompression_cache_hits + self.decompression_cache_misses
        if total == 0:
            return 0.0
        return self.decompression_cache_hits / total
    
    def update_integrity_scan(self, passed: int = 0, failed: int = 0, repaired: int = 0) -> None:
        """Phase 4E: Issue #6 - Update integrity scan statistics."""
        self.integrity_scan_passed += passed
        self.integrity_scan_failed += failed
        self.integrity_scan_repaired += repaired
    
    def update_migration(self, migrated: int = 0, failed: int = 0) -> None:
        """Phase 4E: Issue #6 - Update migration statistics."""
        self.migration_migrated += migrated
        self.migration_failed += failed
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "items_compressed": self.items_compressed,
            "items_failed": self.items_failed,
            "items_skipped_version_mismatch": self.items_skipped_version_mismatch,
            "items_skipped_age": self.items_skipped_age,
            "items_skipped_flag": self.items_skipped_flag,
            "compression_ratio_avg": self.avg_compression_ratio,
            "semantic_similarity_avg": self.avg_semantic_similarity,
            "worker_latency_ms_avg": self.avg_worker_latency_ms,
            "decompression_cache_hit_rate": self.decompression_cache_hit_rate,
            "soft_deleted_count": self.soft_deleted_count,
            "permanent_purged_count": self.permanent_purged_count,
            # Phase 4E: Issue #6 - Integrity and migration metrics
            "integrity_scan_passed": self.integrity_scan_passed,
            "integrity_scan_failed": self.integrity_scan_failed,
            "integrity_scan_repaired": self.integrity_scan_repaired,
            "migration_migrated": self.migration_migrated,
            "migration_failed": self.migration_failed,
        }
