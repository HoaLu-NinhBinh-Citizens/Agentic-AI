"""
Configuration classes for Multi-Agent Coordination Layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5
    window_seconds: float = 60.0
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1
    transient_error_codes: List[str] = field(default_factory=lambda: [
        "MCP_ERROR",
        "TIMEOUT",
        "CONNECTION_REFUSED",
        "CONNECTION_ERROR",
    ])


@dataclass
class FederatedHealthConfig:
    """Federated health propagation configuration."""
    health_interval_seconds: int = 10
    offline_threshold_seconds: int = 30
    max_sub_agents: int = 100


@dataclass
class SchemaEvolutionConfig:
    """Schema evolution configuration."""
    compatibility_policy: str = "backward"  # backward, forward, full
    default_version: str = "1"
    current_version: str = "1"
    migration_cache_ttl_seconds: int = 3600


@dataclass
class BatchIdempotencyConfig:
    """Batch idempotency configuration."""
    ttl_seconds: int = 86400  # 24 hours
    cleanup_interval_seconds: int = 3600
    max_batch_size: int = 1000


@dataclass
class QuotaConfig:
    """Agent quota configuration."""
    max_concurrent_tasks: int = 10
    max_message_rate: int = 100  # per second
    max_workspace_bytes: int = 10 * 1024 * 1024  # 10MB


@dataclass
class LeaderElectionConfig:
    """Leader election configuration."""
    lock_key: str = "coordinator:leader"
    heartbeat_interval_seconds: int = 10
    lock_ttl_seconds: int = 30
    redis_url: Optional[str] = None
    max_retry_attempts: int = 3
    retry_delay_seconds: float = 1.0


@dataclass
class BackpressureConfig:
    """Backpressure control configuration."""
    rate_limit_per_agent: int = 200
    window_seconds: int = 10
    enable_per_tenant: bool = False
    default_retry_after_seconds: int = 5


@dataclass
class DeadLetterAlertConfig:
    """Dead letter alert configuration."""
    threshold: int = 1000
    webhook_url: str = ""
    webhook_method: str = "POST"
    webhook_headers: Dict[str, str] = field(default_factory=dict)
    check_interval_seconds: int = 60
    enabled: bool = True


@dataclass
class TenantIsolationConfig:
    """Tenant isolation configuration."""
    jwt_secret: str = ""
    admin_roles: List[str] = field(default_factory=lambda: ["admin", "super_admin"])
    require_tenant_header: bool = True
    allow_cross_tenant_audit: bool = True
    session_timeout_seconds: int = 3600


@dataclass
class MultiRegionConfig:
    """Multi-region failover configuration."""
    regions: List[str] = field(default_factory=lambda: ["primary", "secondary"])
    health_check_interval_seconds: int = 30
    failover_timeout_seconds: int = 60
    prefer_primary: bool = True


@dataclass
class MultiAgentCoordinationConfig:
    """Main configuration for multi-agent coordination."""
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    federated_health: FederatedHealthConfig = field(default_factory=FederatedHealthConfig)
    schema_evolution: SchemaEvolutionConfig = field(default_factory=SchemaEvolutionConfig)
    batch_idempotency: BatchIdempotencyConfig = field(default_factory=BatchIdempotencyConfig)
    quota: QuotaConfig = field(default_factory=QuotaConfig)
    leader_election: LeaderElectionConfig = field(default_factory=LeaderElectionConfig)
    backpressure: BackpressureConfig = field(default_factory=BackpressureConfig)
    dead_letter_alert: DeadLetterAlertConfig = field(default_factory=DeadLetterAlertConfig)
    tenant_isolation: TenantIsolationConfig = field(default_factory=TenantIsolationConfig)
    multi_region: MultiRegionConfig = field(default_factory=MultiRegionConfig)
    
    # Global settings
    enable_metrics: bool = True
    metrics_prefix: str = "multi_agent"
    log_level: str = "INFO"
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MultiAgentCoordinationConfig":
        """Create config from dictionary."""
        config = cls()
        
        if "circuit_breaker" in data:
            cb = data["circuit_breaker"]
            config.circuit_breaker = CircuitBreakerConfig(
                failure_threshold=cb.get("failure_threshold", 5),
                window_seconds=cb.get("window_seconds", 60.0),
                recovery_timeout=cb.get("recovery_timeout", 30.0),
                half_open_max_calls=cb.get("half_open_max_calls", 1),
                transient_error_codes=cb.get("transient_error_codes", []),
            )
        
        if "federated_health" in data:
            fh = data["federated_health"]
            config.federated_health = FederatedHealthConfig(
                health_interval_seconds=fh.get("health_interval", 10),
                offline_threshold_seconds=fh.get("offline_threshold", 30),
                max_sub_agents=fh.get("max_sub_agents", 100),
            )
        
        if "schema_evolution" in data:
            se = data["schema_evolution"]
            config.schema_evolution = SchemaEvolutionConfig(
                compatibility_policy=se.get("evolution", "backward"),
                default_version=se.get("default_version", "1"),
                current_version=se.get("current_version", "1"),
            )
        
        if "batch_idempotency" in data:
            bi = data["batch_idempotency"]
            config.batch_idempotency = BatchIdempotencyConfig(
                ttl_seconds=bi.get("ttl", 86400),
                cleanup_interval_seconds=bi.get("cleanup_interval", 3600),
                max_batch_size=bi.get("max_batch_size", 1000),
            )
        
        if "quota" in data:
            q = data["quota"]
            config.quota = QuotaConfig(
                max_concurrent_tasks=q.get("default", {}).get("max_concurrent_tasks", 10),
                max_message_rate=q.get("default", {}).get("max_message_rate", 100),
                max_workspace_bytes=q.get("default", {}).get("max_workspace_bytes", 10 * 1024 * 1024),
            )
        
        if "leader_election" in data:
            le = data["leader_election"]
            config.leader_election = LeaderElectionConfig(
                lock_key=le.get("lock_key", "coordinator:leader"),
                heartbeat_interval_seconds=le.get("heartbeat_interval", 10),
                lock_ttl_seconds=le.get("lock_ttl", 30),
                redis_url=le.get("redis_url"),
            )
        
        if "backpressure" in data:
            bp = data["backpressure"]
            config.backpressure = BackpressureConfig(
                rate_limit_per_agent=bp.get("rate_limit_per_agent", 200),
                window_seconds=bp.get("window_seconds", 10),
                default_retry_after_seconds=bp.get("default_retry_after", 5),
            )
        
        if "dead_letter_alert" in data:
            dla = data["dead_letter_alert"]
            config.dead_letter_alert = DeadLetterAlertConfig(
                threshold=dla.get("threshold", 1000),
                webhook_url=dla.get("webhook_url", ""),
                webhook_method=dla.get("webhook_method", "POST"),
                webhook_headers=dla.get("webhook_headers", {}),
                check_interval_seconds=dla.get("check_interval", 60),
                enabled=dla.get("enabled", True),
            )
        
        if "tenant_isolation" in data:
            ti = data["tenant_isolation"]
            config.tenant_isolation = TenantIsolationConfig(
                jwt_secret=ti.get("jwt_secret", ""),
                admin_roles=ti.get("admin_roles", ["admin", "super_admin"]),
                require_tenant_header=ti.get("require_tenant_header", True),
                allow_cross_tenant_audit=ti.get("allow_cross_tenant_audit", True),
            )
        
        if "multi_region" in data:
            mr = data["multi_region"]
            config.multi_region = MultiRegionConfig(
                regions=mr.get("regions", ["primary", "secondary"]),
                health_check_interval_seconds=mr.get("health_check_interval", 30),
                failover_timeout_seconds=mr.get("failover_timeout", 60),
                prefer_primary=mr.get("prefer_primary", True),
            )
        
        config.enable_metrics = data.get("enable_metrics", True)
        config.metrics_prefix = data.get("metrics_prefix", "multi_agent")
        config.log_level = data.get("log_level", "INFO")
        
        return config
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "circuit_breaker": {
                "failure_threshold": self.circuit_breaker.failure_threshold,
                "window_seconds": self.circuit_breaker.window_seconds,
                "recovery_timeout": self.circuit_breaker.recovery_timeout,
                "half_open_max_calls": self.circuit_breaker.half_open_max_calls,
                "transient_error_codes": self.circuit_breaker.transient_error_codes,
            },
            "federated_health": {
                "health_interval": self.federated_health.health_interval_seconds,
                "offline_threshold": self.federated_health.offline_threshold_seconds,
                "max_sub_agents": self.federated_health.max_sub_agents,
            },
            "schema_evolution": {
                "evolution": self.schema_evolution.compatibility_policy,
                "default_version": self.schema_evolution.default_version,
                "current_version": self.schema_evolution.current_version,
            },
            "batch_idempotency": {
                "ttl": self.batch_idempotency.ttl_seconds,
                "cleanup_interval": self.batch_idempotency.cleanup_interval_seconds,
                "max_batch_size": self.batch_idempotency.max_batch_size,
            },
            "quota": {
                "default": {
                    "max_concurrent_tasks": self.quota.max_concurrent_tasks,
                    "max_message_rate": self.quota.max_message_rate,
                    "max_workspace_bytes": self.quota.max_workspace_bytes,
                }
            },
            "leader_election": {
                "lock_key": self.leader_election.lock_key,
                "heartbeat_interval": self.leader_election.heartbeat_interval_seconds,
                "lock_ttl": self.leader_election.lock_ttl_seconds,
                "redis_url": self.leader_election.redis_url,
            },
            "backpressure": {
                "rate_limit_per_agent": self.backpressure.rate_limit_per_agent,
                "window_seconds": self.backpressure.window_seconds,
                "default_retry_after": self.backpressure.default_retry_after_seconds,
            },
            "dead_letter_alert": {
                "threshold": self.dead_letter_alert.threshold,
                "webhook_url": self.dead_letter_alert.webhook_url,
                "webhook_method": self.dead_letter_alert.webhook_method,
                "webhook_headers": self.dead_letter_alert.webhook_headers,
                "check_interval": self.dead_letter_alert.check_interval_seconds,
                "enabled": self.dead_letter_alert.enabled,
            },
            "tenant_isolation": {
                "jwt_secret": "***" if self.tenant_isolation.jwt_secret else "",
                "admin_roles": self.tenant_isolation.admin_roles,
                "require_tenant_header": self.tenant_isolation.require_tenant_header,
            },
            "multi_region": {
                "regions": self.multi_region.regions,
                "health_check_interval": self.multi_region.health_check_interval_seconds,
                "failover_timeout": self.multi_region.failover_timeout_seconds,
                "prefer_primary": self.multi_region.prefer_primary,
            },
            "enable_metrics": self.enable_metrics,
            "metrics_prefix": self.metrics_prefix,
            "log_level": self.log_level,
        }
