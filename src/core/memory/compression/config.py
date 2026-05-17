"""Configuration for the compression module - Phase 4E Production Fixes."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TruncationConfig:
    """Configuration for truncation compression."""
    
    max_chars: int = 2000
    keep_both_ends: bool = True


@dataclass
class ExtractiveConfig:
    """Configuration for extractive summarization."""
    
    top_k_ratio: float = 0.3
    diversity_lambda: float = 0.5
    model_version: str = "bge-m3:latest"
    # Phase 4E: Issue #8 - Prevent O(n²) blowup
    max_sentences: int = 200  # Hard cap
    use_approximate_mmr: bool = True  # Fast approximate MMR


@dataclass
class KeyValueConfig:
    """Configuration for key-value compaction."""
    
    keep_fields_ratio: float = 0.5


@dataclass
class AdaptivePruneConfig:
    """Configuration for adaptive pruning."""
    
    prune_after_days: int = 30
    min_access_count: int = 2
    soft_delete: bool = True
    permanent_delete_days: int = 7


@dataclass
class StrategyConfig:
    """Configuration for compression strategies."""
    
    default: str = "extractive"
    truncation: TruncationConfig = field(default_factory=TruncationConfig)
    extractive: ExtractiveConfig = field(default_factory=ExtractiveConfig)
    kv_compact: KeyValueConfig = field(default_factory=KeyValueConfig)
    adaptive_prune: AdaptivePruneConfig = field(default_factory=AdaptivePruneConfig)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "default": self.default,
            "truncation": self.truncation.__dict__,
            "extractive": self.extractive.__dict__,
            "kv_compact": self.kv_compact.__dict__,
            "adaptive_prune": self.adaptive_prune.__dict__,
        }


@dataclass
class WorkerConfig:
    """Configuration for the background worker."""
    
    interval_seconds: int = 3600
    batch_size: int = 50
    rate_limit_items_per_second: float = 10.0
    max_attempts: int = 3
    min_age_days: int = 7
    optimistic_lock: bool = True
    cooldown_seconds: float = 0.1
    dry_run: bool = False
    worker_id: str = "worker_1"  # Phase 4E: Issue #19 - Correlation IDs


@dataclass
class QualityConfig:
    """Configuration for compression quality validation."""
    
    min_similarity: float = 0.85
    validate_before_commit: bool = True
    # Phase 4E: Issue #9 - Similarity validation sampling
    validation_sampling_rate: float = 1.0  # 1.0 = 100%, 0.1 = 10%
    validate_always_if_ratio_below: float = 0.3
    validate_always_if_suspicious: bool = True
    # Phase 4E: Issue #15 - Compression ratio guard
    min_compression_ratio: float = 0.95  # compressed must be < 95% of original
    absolute_min_savings_bytes: int = 100  # But at least save 100 bytes


@dataclass
class DecompressionCacheConfig:
    """Configuration for decompression cache."""
    
    enabled: bool = True
    maxsize: int = 1000
    ttl_seconds: int = 300  # Phase 4D: Reduced from 3600s to 300s
    # Phase 4E: Issue #18 - Memory-based limits
    max_memory_mb: int = 100  # Memory-based limit


@dataclass
class FeedbackConfig:
    """Configuration for agent feedback handling."""
    
    auto_disable_on_report: bool = True
    rollback_and_mark_no_compress: bool = True


# Phase 4E: Issue #14 - Cold storage deduplication
@dataclass
class ColdStorageConfig:
    """Configuration for cold storage (original blobs)."""
    
    enabled: bool = True
    threshold_days: int = 7
    blob_retention_days: int = 30
    keep_latest_blob_only: bool = True
    deduplicate_by_hash: bool = True


# Phase 4E: Issues #2-4 - Redis lock with token ownership + heartbeat
@dataclass
class DistributedLockConfig:
    """Configuration for distributed locking with token ownership."""
    
    enabled: bool = False  # Disabled by default, use Redis for production
    lock_timeout_seconds: float = 30.0
    retry_interval_seconds: float = 1.0
    use_token_ownership: bool = True  # Phase 4E: Issue #3 - UUID token for safe release
    heartbeat_interval_seconds: float = 10.0  # Phase 4E: Issue #4 - Lock renewal
    fallback_to_inmemory: bool = True


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    
    enabled: bool = False
    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0
    half_open_requests: int = 3


@dataclass
class LimitsConfig:
    """Configuration for size limits."""
    
    max_item_size_mb: int = 10
    max_embedding_chars: int = 50000
    max_compression_ratio: float = 0.1  # Reject if compressed too aggressively
    large_item_strategy: str = "skip"  # "skip" | "truncate"


# Phase 4E: Issue #11 - No-compress TTL
@dataclass
class NoCompressConfig:
    """Configuration for no_compress TTL."""
    
    disable_hours: int = 24  # Hours to disable compression after issue reported
    retry_after_hours: int = 24  # Items can be re-evaluated after this


# Phase 4E: Issue #7 - CPU/Resource Guards
@dataclass
class ResourceLimitsConfig:
    """Configuration for per-item resource limits."""
    
    max_cpu_time_ms: int = 5000  # 5 seconds max per item
    max_sentences: int = 500  # Cap for extractive summarizer
    max_json_fields: int = 100  # Max fields for KV compaction
    max_embedding_batch_size: int = 100  # Max sentences per embedding batch
    max_characters: int = 100000  # 100K chars input limit


# Phase 4E: Issue #17 - Integrity scanner
@dataclass
class IntegrityScannerConfig:
    """Configuration for integrity scanner."""
    
    enabled: bool = False
    interval_hours: int = 24
    sample_rate: float = 0.01  # 1% of items per scan
    min_samples: int = 10
    max_samples: int = 100


# Phase 4E: Issue #16 - Priority scheduling
@dataclass
class PrioritySchedulingConfig:
    """Configuration for priority scheduling."""
    
    enabled: bool = True
    savings_weight: float = 0.4
    coldness_weight: float = 0.3
    size_weight: float = 0.3


# Phase 4E: Issue #13 - Batch processing
@dataclass
class BatchProcessingConfig:
    """Configuration for batch processing."""
    
    batch_size: int = 50
    savepoint_per_item: bool = True  # Phase 4E: Issue #12 - Per-item isolation
    rollback_on_failure: bool = False  # Continue on partial failure


@dataclass
class CompressionConfig:
    """Main configuration for compression module."""
    
    enabled: bool = True
    
    worker: WorkerConfig = field(default_factory=WorkerConfig)
    strategies: StrategyConfig = field(default_factory=StrategyConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    decompression_cache: DecompressionCacheConfig = field(
        default_factory=DecompressionCacheConfig
    )
    feedback: FeedbackConfig = field(default_factory=FeedbackConfig)
    cold_storage: ColdStorageConfig = field(default_factory=ColdStorageConfig)
    distributed_lock: DistributedLockConfig = field(
        default_factory=DistributedLockConfig
    )
    circuit_breaker: CircuitBreakerConfig = field(
        default_factory=CircuitBreakerConfig
    )
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    no_compress: NoCompressConfig = field(default_factory=NoCompressConfig)
    resource_limits: ResourceLimitsConfig = field(
        default_factory=ResourceLimitsConfig
    )
    integrity_scanner: IntegrityScannerConfig = field(
        default_factory=IntegrityScannerConfig
    )
    priority_scheduling: PrioritySchedulingConfig = field(
        default_factory=PrioritySchedulingConfig
    )
    batch_processing: BatchProcessingConfig = field(
        default_factory=BatchProcessingConfig
    )
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompressionConfig:
        """Create from dictionary."""
        config = cls()
        
        if "worker" in data:
            config.worker = WorkerConfig(**data["worker"])
        if "strategies" in data:
            strat_data = data["strategies"]
            config.strategies = StrategyConfig(
                default=strat_data.get("default", "extractive"),
                truncation=TruncationConfig(**strat_data.get("truncation", {})),
                extractive=ExtractiveConfig(**strat_data.get("extractive", {})),
                kv_compact=KeyValueConfig(**strat_data.get("kv_compact", {})),
                adaptive_prune=AdaptivePruneConfig(**strat_data.get("adaptive_prune", {})),
            )
        if "quality" in data:
            config.quality = QualityConfig(**data["quality"])
        if "decompression_cache" in data:
            config.decompression_cache = DecompressionCacheConfig(
                **data["decompression_cache"]
            )
        if "feedback" in data:
            config.feedback = FeedbackConfig(**data["feedback"])
        if "cold_storage" in data:
            config.cold_storage = ColdStorageConfig(**data["cold_storage"])
        if "distributed_lock" in data:
            config.distributed_lock = DistributedLockConfig(**data["distributed_lock"])
        if "circuit_breaker" in data:
            config.circuit_breaker = CircuitBreakerConfig(**data["circuit_breaker"])
        if "limits" in data:
            config.limits = LimitsConfig(**data["limits"])
        if "no_compress" in data:
            config.no_compress = NoCompressConfig(**data["no_compress"])
        if "resource_limits" in data:
            config.resource_limits = ResourceLimitsConfig(**data["resource_limits"])
        if "integrity_scanner" in data:
            config.integrity_scanner = IntegrityScannerConfig(**data["integrity_scanner"])
        if "priority_scheduling" in data:
            config.priority_scheduling = PrioritySchedulingConfig(**data["priority_scheduling"])
        if "batch_processing" in data:
            config.batch_processing = BatchProcessingConfig(**data["batch_processing"])
        
        return config
    
    @classmethod
    def from_yaml(cls, yaml_path: str) -> CompressionConfig:
        """Load configuration from YAML file."""
        try:
            import yaml
            with open(yaml_path, "r") as f:
                data = yaml.safe_load(f)
            if data and "compression" in data:
                return cls.from_dict(data["compression"])
        except ImportError:
            pass
        except FileNotFoundError:
            pass
        return cls()
    
    @classmethod
    def from_env(cls) -> CompressionConfig:
        """Create configuration from environment variables."""
        return cls(
            enabled=os.getenv("COMPRESSION_ENABLED", "true").lower() == "true",
            worker=WorkerConfig(
                interval_seconds=int(os.getenv("COMPRESSION_INTERVAL", "3600")),
                batch_size=int(os.getenv("COMPRESSION_BATCH_SIZE", "50")),
                rate_limit_items_per_second=float(
                    os.getenv("COMPRESSION_RATE_LIMIT", "10")
                ),
                max_attempts=int(os.getenv("COMPRESSION_MAX_ATTEMPTS", "3")),
                min_age_days=int(os.getenv("COMPRESSION_MIN_AGE_DAYS", "7")),
            ),
            quality=QualityConfig(
                min_similarity=float(os.getenv("COMPRESSION_MIN_SIMILARITY", "0.85")),
                validate_before_commit=os.getenv(
                    "COMPRESSION_VALIDATE", "true"
                ).lower() == "true",
            ),
            decompression_cache=DecompressionCacheConfig(
                enabled=os.getenv("DECOMPRESSION_CACHE_ENABLED", "true").lower() == "true",
                maxsize=int(os.getenv("DECOMPRESSION_CACHE_MAXSIZE", "1000")),
                ttl_seconds=int(os.getenv("DECOMPRESSION_CACHE_TTL", "300")),
            ),
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "worker": self.worker.__dict__,
            "strategies": self.strategies.to_dict(),
            "quality": self.quality.__dict__,
            "decompression_cache": self.decompression_cache.__dict__,
            "feedback": self.feedback.__dict__,
            "cold_storage": self.cold_storage.__dict__,
            "distributed_lock": self.distributed_lock.__dict__,
            "circuit_breaker": self.circuit_breaker.__dict__,
            "limits": self.limits.__dict__,
            "no_compress": self.no_compress.__dict__,
            "resource_limits": self.resource_limits.__dict__,
            "integrity_scanner": self.integrity_scanner.__dict__,
            "priority_scheduling": self.priority_scheduling.__dict__,
            "batch_processing": self.batch_processing.__dict__,
        }
