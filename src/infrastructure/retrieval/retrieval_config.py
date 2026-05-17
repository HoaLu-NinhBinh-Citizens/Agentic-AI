"""Phase 5C v12 Configuration Schema.

Configuration schema for Advanced Context & Retrieval Engine features:
- Read isolation (snapshot)
- Replica lag awareness
- Plugin management
- Query budget per type
- Golden set drift detection
- Document-aware cache invalidation
- Explainability size limits
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ============================================================================
# Read Isolation Config
# ============================================================================

@dataclass
class ReadIsolationConfig:
    """Configuration for snapshot isolation."""
    enabled: bool = True
    snapshot_ttl_seconds: int = 3600
    max_snapshots: int = 100


# ============================================================================
# Replica Lag Config
# ============================================================================

@dataclass
class ReplicaLagConfig:
    """Configuration for replica lag awareness."""
    enabled: bool = True
    max_lag_seconds: float = 5.0
    fallback_to_primary: bool = True
    check_interval_seconds: float = 10.0
    primary_fallback_warning: bool = True


# ============================================================================
# Plugin Management Config
# ============================================================================

@dataclass
class PluginManagementConfig:
    """Configuration for plugin version management."""
    enabled: bool = True
    auto_rollback: bool = True
    version_history_size: int = 5
    health_check_timeout: float = 5.0
    rollback_cooldown_seconds: int = 60


# ============================================================================
# Query Budget Config
# ============================================================================

@dataclass
class QueryBudgetConfig:
    """Configuration for query type budget allocation."""
    enabled: bool = True
    per_intent: dict[str, int] = field(default_factory=lambda: {
        "factoid": 4000,
        "reasoning": 8000,
        "code": 16000,
        "instruction": 2000,
        "general": 8192,
    })
    default_max_tokens: int = 8192
    default_max_chunks: int = 10
    default_timeout_seconds: float = 30.0


# ============================================================================
# Golden Set Config
# ============================================================================

@dataclass
class GoldenSetConfig:
    """Configuration for golden set drift detection."""
    enabled: bool = True
    eval_interval_hours: int = 24
    drift_threshold: float = 0.1  # 10% drop
    min_queries_for_eval: int = 10
    alert_webhook: Optional[str] = None
    auto_archive: bool = True
    archive_after_days: int = 30


# ============================================================================
# Cache Config
# ============================================================================

@dataclass
class CacheConfig:
    """Configuration for document-aware cache invalidation."""
    document_aware_invalidation: bool = True
    bloom_filter_enabled: bool = True
    bloom_filter_false_positive: float = 0.01
    mapping_ttl_seconds: int = 86400  # 24 hours
    max_mappings: int = 10000


# ============================================================================
# Explainability Config
# ============================================================================

@dataclass
class ExplainabilityConfig:
    """Configuration for explainability size limits."""
    enabled: bool = True
    max_provenance_entries: int = 100
    max_total_bytes: int = 10240  # 10KB
    min_influence_score: float = 0.1
    include_score_breakdown: bool = True


# ============================================================================
# Phase 5C Full Config
# ============================================================================

@dataclass
class Phase5CConfig:
    """Complete Phase 5C configuration."""
    read_isolation: ReadIsolationConfig = field(default_factory=ReadIsolationConfig)
    replica_lag: ReplicaLagConfig = field(default_factory=ReplicaLagConfig)
    plugin_management: PluginManagementConfig = field(default_factory=PluginManagementConfig)
    query_budget: QueryBudgetConfig = field(default_factory=QueryBudgetConfig)
    golden_set: GoldenSetConfig = field(default_factory=GoldenSetConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    explainability: ExplainabilityConfig = field(default_factory=ExplainabilityConfig)

    @classmethod
    def from_dict(cls, data: dict) -> Phase5CConfig:
        """Create config from dictionary."""
        return cls(
            read_isolation=ReadIsolationConfig(**data.get("read_isolation", {})),
            replica_lag=ReplicaLagConfig(**data.get("replica_lag", {})),
            plugin_management=PluginManagementConfig(**data.get("plugin_management", {})),
            query_budget=QueryBudgetConfig(**data.get("query_budget", {})),
            golden_set=GoldenSetConfig(**data.get("golden_set", {})),
            cache=CacheConfig(**data.get("cache", {})),
            explainability=ExplainabilityConfig(**data.get("explainability", {})),
        )

    def to_dict(self) -> dict:
        """Convert config to dictionary."""
        return {
            "read_isolation": {
                "enabled": self.read_isolation.enabled,
                "snapshot_ttl_seconds": self.read_isolation.snapshot_ttl_seconds,
                "max_snapshots": self.read_isolation.max_snapshots,
            },
            "replica_lag": {
                "enabled": self.replica_lag.enabled,
                "max_lag_seconds": self.replica_lag.max_lag_seconds,
                "fallback_to_primary": self.replica_lag.fallback_to_primary,
                "check_interval_seconds": self.replica_lag.check_interval_seconds,
            },
            "plugin_management": {
                "enabled": self.plugin_management.enabled,
                "auto_rollback": self.plugin_management.auto_rollback,
                "version_history_size": self.plugin_management.version_history_size,
            },
            "query_budget": {
                "enabled": self.query_budget.enabled,
                "per_intent": self.query_budget.per_intent,
                "default_max_tokens": self.query_budget.default_max_tokens,
            },
            "golden_set": {
                "enabled": self.golden_set.enabled,
                "eval_interval_hours": self.golden_set.eval_interval_hours,
                "drift_threshold": self.golden_set.drift_threshold,
                "alert_webhook": self.golden_set.alert_webhook,
            },
            "cache": {
                "document_aware_invalidation": self.cache.document_aware_invalidation,
                "bloom_filter_enabled": self.cache.bloom_filter_enabled,
                "bloom_filter_false_positive": self.cache.bloom_filter_false_positive,
            },
            "explainability": {
                "enabled": self.explainability.enabled,
                "max_provenance_entries": self.explainability.max_provenance_entries,
                "max_total_bytes": self.explainability.max_total_bytes,
            },
        }


# ============================================================================
# Default Config
# ============================================================================

DEFAULT_PHASE5C_CONFIG = Phase5CConfig()


# ============================================================================
# YAML Config Template
# ============================================================================

PHASE5C_YAML_TEMPLATE = """
# Phase 5C v12 - Advanced Context & Retrieval Engine Configuration

retrieval:
  # Read Isolation
  read_isolation:
    enabled: true
    snapshot_ttl_seconds: 3600
    max_snapshots: 100

  # Replica Lag Awareness
  replica_lag:
    enabled: true
    max_lag_seconds: 5
    fallback_to_primary: true
    check_interval_seconds: 10

  # Plugin Management
  plugin_management:
    enabled: true
    auto_rollback: true
    version_history_size: 5

  # Query Budget per Type
  query_budget:
    enabled: true
    per_intent:
      factoid: 4000
      reasoning: 8000
      code: 16000
      instruction: 2000
      general: 8192
    default_max_tokens: 8192

  # Golden Set Drift Detection
  golden_set:
    enabled: true
    eval_interval_hours: 24
    drift_threshold: 0.1  # 10% drop
    alert_webhook: "https://alerts..."

  # Document-Aware Cache
  cache:
    document_aware_invalidation: true
    bloom_filter_enabled: true
    bloom_filter_false_positive: 0.01

  # Explainability Limits
  explainability:
    enabled: true
    max_provenance_entries: 100
    max_total_bytes: 10240  # 10KB
"""
