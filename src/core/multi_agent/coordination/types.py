"""
Shared types for Multi-Agent Coordination Layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


class HealthStatus(str, Enum):
    """Health status enum."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    OFFLINE = "offline"


class CircuitBreakerState(str, Enum):
    """Circuit breaker state enum."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerDirection(str, Enum):
    """Direction of circuit breaker call."""
    COORDINATOR_TO_AGENT = "coordinator_to_agent"
    AGENT_TO_COORDINATOR = "agent_to_coordinator"


class CompatibilityPolicy(str, Enum):
    """Schema evolution compatibility policy."""
    BACKWARD = "backward"   # New code reads old data
    FORWARD = "forward"     # Old code reads new data
    FULL = "full"           # Both directions


@dataclass
class AgentQuota:
    """Agent resource quota configuration."""
    agent_id: str
    max_concurrent_tasks: int = 10
    max_message_rate: int = 100  # messages per second
    max_workspace_bytes: int = 10 * 1024 * 1024  # 10MB
    
    # Current usage (runtime state)
    current_concurrent: int = 0
    current_message_rate: float = 0.0
    current_workspace_bytes: int = 0
    
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "max_message_rate": self.max_message_rate,
            "max_workspace_bytes": self.max_workspace_bytes,
            "current_concurrent": self.current_concurrent,
            "current_message_rate": self.current_message_rate,
            "current_workspace_bytes": self.current_workspace_bytes,
        }


@dataclass
class TenantConfig:
    """Tenant configuration."""
    tenant_id: str
    name: str
    quota_multiplier: float = 1.0
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "name": self.name,
            "quota_multiplier": self.quota_multiplier,
            "enabled": self.enabled,
            "metadata": self.metadata,
        }


@dataclass
class SchemaField:
    """Schema field definition."""
    name: str
    type: str
    required: bool = False
    default: Any = None
    description: str = ""


@dataclass
class SchemaDefinition:
    """Schema version definition."""
    message_type: str
    version: str
    fields: List[SchemaField]
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_type": self.message_type,
            "version": self.version,
            "fields": [
                {"name": f.name, "type": f.type, "required": f.required}
                for f in self.fields
            ],
        }


SchemaMigration = Callable[[Dict[str, Any]], Dict[str, Any]]


@dataclass
class SubAgentStatus:
    """Sub-agent health status."""
    agent_id: str
    status: HealthStatus
    last_heartbeat: datetime
    error_count: int = 0
    task_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_offline(self) -> bool:
        return self.status == HealthStatus.OFFLINE
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "status": self.status.value,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "error_count": self.error_count,
            "task_count": self.task_count,
        }


@dataclass
class FederatedHealthReport:
    """Federated health report from federated agent."""
    federated_agent_id: str
    sub_agents: List[SubAgentStatus]
    timestamp: datetime = field(default_factory=datetime.now)
    health_score: float = 1.0  # 0.0 to 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "federated_agent_id": self.federated_agent_id,
            "sub_agents": [sa.to_dict() for sa in self.sub_agents],
            "timestamp": self.timestamp.isoformat(),
            "health_score": self.health_score,
        }


@dataclass
class BatchItem:
    """Batch operation item."""
    index: int
    idempotency_key: str
    data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchResult:
    """Batch operation result."""
    index: int
    idempotency_key: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    skipped: bool = False  # True if returned cached result


@dataclass
class DeadLetterItem:
    """Dead letter queue item."""
    id: str
    tenant_id: str
    queue_name: str
    message: Dict[str, Any]
    error: str
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = field(default_factory=datetime.now)
    last_retry_at: Optional[datetime] = None
    
    @property
    def is_exhausted(self) -> bool:
        return self.retry_count >= self.max_retries
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "queue_name": self.queue_name,
            "message": self.message,
            "error": self.error,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "is_exhausted": self.is_exhausted,
        }


@dataclass
class DeadLetterAlertConfig:
    """Dead letter alert configuration."""
    tenant_id: str = ""
    queue_name: str = "default"
    threshold: int = 1000
    webhook_url: str = ""
    webhook_method: str = "POST"
    webhook_headers: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class BackpressureResponse:
    """Backpressure check response."""
    is_limited: bool
    retry_after: float = 0.0
    limit: int = 0
    remaining: int = 0
    reset_at: datetime = field(default_factory=datetime.now)
    
    def to_headers(self) -> Dict[str, str]:
        return {
            "Retry-After": str(int(self.retry_after)),
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(int(self.reset_at.timestamp())),
        }


@dataclass
class LeaderInfo:
    """Leader election info."""
    leader_id: str
    elected_at: datetime
    last_heartbeat: datetime
    term: int = 0
    
    def is_expired(self, ttl_seconds: float = 30.0) -> bool:
        elapsed = (datetime.now() - self.last_heartbeat).total_seconds()
        return elapsed > ttl_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "leader_id": self.leader_id,
            "elected_at": self.elected_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "term": self.term,
        }


@dataclass
class CircuitBreakerInfo:
    """Circuit breaker state info."""
    name: str
    direction: CircuitBreakerDirection
    state: CircuitBreakerState
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_state_change: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "direction": self.direction.value,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
        }


@dataclass
class CoordinatorMetrics:
    """Coordinator metrics snapshot."""
    timestamp: datetime = field(default_factory=datetime.now)
    total_agents: int = 0
    healthy_agents: int = 0
    open_circuits: int = 0
    pending_tasks: int = 0
    dead_letter_depth: int = 0
    leader_active: bool = False
    active_region: str = "primary"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_agents": self.total_agents,
            "healthy_agents": self.healthy_agents,
            "open_circuits": self.open_circuits,
            "pending_tasks": self.pending_tasks,
            "dead_letter_depth": self.dead_letter_depth,
            "leader_active": self.leader_active,
            "active_region": self.active_region,
        }


# ============== Phase 5F: Reliability, Governance & Safety ==============

class SecretAction(str, Enum):
    """Secret access actions."""
    READ = "read"
    WRITE = "write"
    ROTATE = "rotate"
    CREATE = "create"
    DELETE = "delete"
    LIST = "list"


class BreakGlassAction(str, Enum):
    """Break-glass actions."""
    CREATED = "created"
    USED = "used"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ExperimentStatus(str, Enum):
    """Status of chaos experiment."""
    PENDING = "pending"
    BASELINE_MEASURED = "baseline_measured"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ErrorType(str, Enum):
    """Circuit breaker error types."""
    TRIP = "trip"  # Serious errors that trip the breaker
    TEMP = "temp"  # Temporary errors that don't trip


class ResourceType(str, Enum):
    """Resource types for quota allocation."""
    TASK = "task"
    CPU = "cpu"
    MEMORY = "memory"
    STORAGE = "storage"
    NETWORK = "network"


@dataclass
class SecretsAuditRecord:
    """Audit record for secret access."""
    secret_name: str
    accessed_by: str
    timestamp: datetime
    source_ip: str
    action: SecretAction
    success: bool
    error: Optional[str] = None


@dataclass
class BreakGlassEvent:
    """Break-glass event data."""
    token_id: str
    requester: str
    reason: str
    action: BreakGlassAction
    duration_seconds: int
    timestamp: datetime
    source_ip: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BreakGlassToken:
    """Break-glass emergency token."""
    token_id: str
    created_by: str
    reason: str
    created_at: datetime
    expires_at: datetime
    revoked: bool = False
    used_count: int = 0


@dataclass
class DRRestoreRecord:
    """Disaster recovery restore record."""
    snapshot_id: str
    start_time: datetime
    end_time: Optional[datetime]
    data_loss_seconds: int
    target_rto_seconds: int
    target_rpo_seconds: int
    status: str  # in_progress, completed, failed
    alert_sent: bool = False


@dataclass
class CostRecord:
    """Cost record for chargeback."""
    tenant_id: str
    team_id: Optional[str]
    project_id: Optional[str]
    cost_usd: float
    resource_type: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BaselineMetrics:
    """Baseline metrics for comparison."""
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    error_rate: float
    throughput_rps: float
    cpu_percent: float
    memory_percent: float
    measured_at: datetime


@dataclass
class ExperimentResult:
    """Result of chaos experiment."""
    experiment_id: str
    status: ExperimentStatus
    baseline: Optional[BaselineMetrics]
    post_experiment: Optional[BaselineMetrics]
    deviations: Dict[str, float]
    passed: bool
    failure_reason: Optional[str]
