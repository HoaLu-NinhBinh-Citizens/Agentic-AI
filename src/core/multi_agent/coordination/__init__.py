"""
Multi-Agent Coordination Layer

Enterprise-grade multi-agent coordination with:
- Two-way circuit breaker
- Federated health propagation
- Schema evolution
- Batch idempotency
- Tenant isolation
- Agent resource quota
- Leader election
- Backpressure control
- Dead letter alerts

Phase 5F: Reliability, Governance & Safety:
- Saga atomic compensation
- Circuit error classification
- Sliding log rate limiting
- Policy cache invalidation
- Sandbox egress policy
- Prompt injection explainability
- Fair share quota (DRF)
- Error budget policy
- Chaos steady-state baseline
- Secrets audit log
- Break-glass alerting
- DR metrics (RTO/RPO)
- Cost chargeback
"""

from src.core.multi_agent.coordination.types import (
    AgentQuota,
    TenantConfig,
    SchemaDefinition,
    SchemaMigration,
    HealthStatus,
    SubAgentStatus,
    FederatedHealthReport,
    BatchItem,
    BatchResult,
    DeadLetterItem,
    DeadLetterAlertConfig,
    BackpressureResponse,
    LeaderInfo,
)

from src.core.multi_agent.coordination.config import (
    MultiAgentCoordinationConfig,
    CircuitBreakerConfig,
    FederatedHealthConfig,
    SchemaEvolutionConfig,
    BatchIdempotencyConfig,
    QuotaConfig,
    LeaderElectionConfig,
    BackpressureConfig,
    DeadLetterAlertConfig,
    TenantIsolationConfig,
)

from src.core.multi_agent.coordination.circuit_breaker import (
    TwoWayCircuitBreaker,
    CircuitBreakerDirection,
)

from src.core.multi_agent.coordination.health import (
    FederatedHealthPropagator,
)

from src.core.multi_agent.coordination.schema_evolution import (
    SchemaEvolutionEngine,
    CompatibilityPolicy,
)

from src.core.multi_agent.coordination.batch_idempotency import (
    BatchIdempotencyStore,
)

from src.core.multi_agent.coordination.tenant_isolation import (
    TenantIsolationLayer,
)

from src.core.multi_agent.coordination.quota import (
    QuotaEnforcer,
    QuotaExceededError,
)

from src.core.multi_agent.coordination.leader_election import (
    LeaderElector,
)

from src.core.multi_agent.coordination.backpressure import (
    BackpressureController,
)

from src.core.multi_agent.coordination.dead_letter_alert import (
    DeadLetterAlert,
)

from src.core.multi_agent.coordination.coordinator import (
    MultiAgentCoordinator,
)

from src.core.multi_agent.coordination.rate_limiter import (
    SlidingLogRateLimiter,
    RateLimitResult,
)

from src.core.multi_agent.coordination.policy_cache import (
    PolicyCacheInvalidator,
    SandboxEgressPolicy,
    Policy,
)

from src.core.multi_agent.coordination.fair_share_quota import (
    FairShareQuota,
    ErrorBudgetPolicy,
    AllocationResult,
    ErrorBudgetStatus,
)

from src.core.multi_agent.coordination.governance import (
    BreakGlassAlert,
    DRMetrics,
    ChargebackReporter,
)

__all__ = [
    # Types
    "AgentQuota",
    "TenantConfig",
    "SchemaDefinition",
    "SchemaMigration",
    "HealthStatus",
    "SubAgentStatus",
    "FederatedHealthReport",
    "BatchItem",
    "BatchResult",
    "DeadLetterItem",
    "DeadLetterAlertConfig",
    "BackpressureResponse",
    "LeaderInfo",
    # Phase 5F Types
    "BreakGlassAction",
    "ExperimentStatus",
    "ErrorType",
    "ResourceType",
    "SecretsAuditRecord",
    "BreakGlassEvent",
    "BreakGlassToken",
    "DRRestoreRecord",
    "CostRecord",
    "BaselineMetrics",
    "ExperimentResult",
    # Config
    "MultiAgentCoordinationConfig",
    "CircuitBreakerConfig",
    "FederatedHealthConfig",
    "SchemaEvolutionConfig",
    "BatchIdempotencyConfig",
    "QuotaConfig",
    "LeaderElectionConfig",
    "BackpressureConfig",
    "DeadLetterAlertConfig",
    "TenantIsolationConfig",
    # Phase 5F Components
    "SlidingLogRateLimiter",
    "RateLimitResult",
    "PolicyCacheInvalidator",
    "SandboxEgressPolicy",
    "Policy",
    "FairShareQuota",
    "ErrorBudgetPolicy",
    "AllocationResult",
    "ErrorBudgetStatus",
    "BreakGlassAlert",
    "DRMetrics",
    "ChargebackReporter",
    # Components
    "TwoWayCircuitBreaker",
    "CircuitBreakerDirection",
    "FederatedHealthPropagator",
    "SchemaEvolutionEngine",
    "CompatibilityPolicy",
    "BatchIdempotencyStore",
    "TenantIsolationLayer",
    "QuotaEnforcer",
    "QuotaExceededError",
    "LeaderElector",
    "BackpressureController",
    "DeadLetterAlert",
    "MultiAgentCoordinator",
]
