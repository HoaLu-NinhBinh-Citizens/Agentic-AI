"""Planner core types and enums - Phase 5B Enterprise."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum, auto
from typing import Any, Callable, Optional


class JoinPolicy(Enum):
    """Join policy for parallel branches."""
    ALL_SUCCESS = "all_success"
    ANY_SUCCESS = "any_success"
    QUORUM = "quorum"
    ALL_COMPLETED = "all_completed"


class InterruptStatus(Enum):
    """Status of a plan interrupt."""
    PENDING = "pending"
    RESUMED = "resumed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ExpirationPolicy(Enum):
    """Policy for expired interrupts."""
    AUTO_CANCEL = "auto_cancel"
    ESCALATE = "escalate"
    FALLBACK_BRANCH = "fallback_branch"


class HumanAction(Enum):
    """Human-in-the-loop action types."""
    RESUME = "resume"
    CANCEL = "cancel"
    APPROVE = "approve"
    REJECT = "reject"
    ESCALATE = "escalate"


class PlannerEventType(Enum):
    """Planner event types for event sourcing."""
    DECOMPOSE_START = "decompose_start"
    DECOMPOSE_COMPLETE = "decompose_complete"
    BEAM_SEARCH_STEP = "beam_search_step"
    CANDIDATE_EVALUATED = "candidate_evaluated"
    RETRIEVED_TEMPLATE = "retrieved_template"
    PLAN_SELECTED = "plan_selected"
    BRANCH_DECIDED = "branch_decided"
    INTERRUPT_CREATED = "interrupt_created"
    INTERRUPT_RESUMED = "interrupt_resumed"
    INTERRUPT_EXPIRED = "interrupt_expired"
    RETRY_SNAPSHOT_CREATED = "retry_snapshot_created"
    RETRY_SNAPSHOT_RESTORED = "retry_snapshot_restored"
    PLAN_VALIDATED = "plan_validated"
    PLAN_REJECTED = "plan_rejected"
    COST_FORECAST_GENERATED = "cost_forecast_generated"


@dataclass
class PlanOptions:
    """Options for plan creation."""
    max_nodes: int = 500
    max_branch_factor: int = 5
    max_depth: int = 10
    timeout_seconds: float = 30.0
    join_policy: JoinPolicy = JoinPolicy.ALL_SUCCESS
    schema_version: str = "1.0"
    enable_semantic_retrieval: bool = True
    enable_deadlock_detection: bool = True


@dataclass
class PlanNode:
    """A node in the plan graph."""
    node_id: str
    task_type: str
    description: str
    input_schema_version: str = "1.0"
    output_schema_version: str = "1.0"
    depends_on: list[str] = field(default_factory=list)
    condition_expr: Optional[str] = None
    branch_options: list[str] = field(default_factory=list)
    join_policy: Optional[JoinPolicy] = None
    retry_config: Optional[dict] = None
    timeout_seconds: Optional[float] = None
    estimated_cost: float = 0.0
    estimated_duration: float = 0.0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.node_id:
            self.node_id = str(uuid.uuid4())


@dataclass
class PlanGraph:
    """Complete plan graph structure."""
    plan_id: str
    goal: str
    nodes: list[PlanNode] = field(default_factory=list)
    root_node_id: Optional[str] = None
    definition_version: str = "1.0"
    created_at: int = field(default_factory=lambda: int(datetime.now(UTC).timestamp()))
    metadata: dict = field(default_factory=dict)

    def add_node(self, node: PlanNode) -> None:
        """Add a node to the plan."""
        self.nodes.append(node)

    def get_node(self, node_id: str) -> Optional[PlanNode]:
        """Get node by ID."""
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def get_dependencies(self, node_id: str) -> list[str]:
        """Get direct dependencies of a node."""
        node = self.get_node(node_id)
        return node.depends_on if node else []


@dataclass
class BranchDecision:
    """Records a conditional branch decision for replay."""
    workflow_id: str
    task_id: str
    selected_branch: str
    evaluated_at: int
    condition_expr: str


@dataclass
class PlanInterrupt:
    """Represents an interrupted plan waiting for human input."""
    interrupt_id: str
    plan_id: str
    task_id: str
    status: InterruptStatus
    resume_token: str
    user_input: Optional[dict] = None
    created_at: int = field(default_factory=lambda: int(datetime.now(UTC).timestamp()))
    expires_at: Optional[int] = None
    expired_at: Optional[int] = None
    resumed_at: Optional[int] = None


@dataclass
class PlannerEvent:
    """Event for planner event sourcing."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    event_type: PlannerEventType = PlannerEventType.DECOMPOSE_START
    data: dict = field(default_factory=dict)
    timestamp: int = field(default_factory=lambda: int(datetime.now(UTC).timestamp()))


@dataclass
class PlanSnapshot:
    """Immutable plan snapshot for replay."""
    plan_id: str
    definition_version: str
    serialized_graph: dict
    snapshot_events: list[dict]
    created_at: int = field(default_factory=lambda: int(datetime.now(UTC).timestamp()))


@dataclass
class PlanRetrySnapshot:
    """Snapshot of plan state before retry."""
    plan_id: str
    snapshot: dict
    created_at: int = field(default_factory=lambda: int(datetime.now(UTC).timestamp()))


@dataclass
class HumanAuditEntry:
    """Human audit log entry."""
    plan_id: str
    action: HumanAction = HumanAction.RESUME
    approved_by: str = ""
    reason: Optional[str] = None
    source_ip: Optional[str] = None
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    interrupt_id: Optional[str] = None
    approved_at: int = field(default_factory=lambda: int(datetime.now(UTC).timestamp()))


@dataclass
class SchemaDefinition:
    """Schema definition with versioning."""
    schema_id: str
    version: str
    schema_def: dict
    created_at: int = field(default_factory=lambda: int(datetime.now(UTC).timestamp()))


@dataclass
class SchemaMigration:
    """Schema migration function registration."""
    schema_id: str
    from_version: str
    to_version: str
    migrate_fn: Callable[[dict], dict]


@dataclass
class ValidationResult:
    """Result of plan validation."""
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


@dataclass
class DeadlockReport:
    """Report from deadlock detection."""
    has_deadlock: bool
    cycles: list[list[str]] = field(default_factory=list)
    unreachable_joins: list[str] = field(default_factory=list)
    orphan_tasks: list[str] = field(default_factory=list)


@dataclass
class CostForecastReport:
    """Cost forecast with correlation disclaimer."""
    total_cost: float
    task_costs: dict[str, float]
    critical_path: list[str]
    estimated_duration: float
    independence_disclaimer: str = (
        "Giả định các task duration độc lập. "
        "Trong thực tế, có thể có correlation do network, provider. "
        "Hỗ trợ covariance sẽ có trong Phase 5C."
    )
    covariance_available: bool = False
    covariance_matrix: Optional[dict] = None


@dataclass
class ResumeResult:
    """Result of a resume operation."""
    success: bool
    error: Optional[str] = None
    already_resumed: bool = False
    invalid_token: bool = False


@dataclass
class JoinResult:
    """Result of join policy evaluation."""
    can_proceed: bool
    policy: JoinPolicy
    satisfied_branches: list[str] = field(default_factory=list)
    failed_branches: list[str] = field(default_factory=list)
    partial_results: dict = field(default_factory=dict)


@dataclass
class RetrievedPlan:
    """Plan retrieved from semantic search."""
    plan_id: str
    goal_text: str
    plan_graph: PlanGraph
    quality_score: float
    reliability_weight: float
    human_verified: bool
    failure_rate: float
    retrieved_at: int = field(default_factory=lambda: int(datetime.now(UTC).timestamp()))


@dataclass
class ExpirationResult:
    """Result of interrupt expiration check."""
    is_expired: bool
    expired_at: Optional[int] = None
    should_escalate: bool = False
    fallback_available: bool = False


@dataclass
class PlanState:
    """Complete state of a plan for snapshot."""
    plan_id: str
    plan_graph: PlanGraph
    branch_decisions: list[BranchDecision]
    completed_tasks: set[str] = field(default_factory=set)
    task_results: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)
    current_node_id: Optional[str] = None
    created_at: int = field(default_factory=lambda: int(datetime.now(UTC).timestamp()))

    def to_dict(self) -> dict:
        """Serialize state to dict."""
        return {
            "plan_id": self.plan_id,
            "plan_graph": self._serialize_graph(),
            "branch_decisions": [self._serialize_decision(d) for d in self.branch_decisions],
            "completed_tasks": list(self.completed_tasks),
            "task_results": self.task_results,
            "context": self.context,
            "current_node_id": self.current_node_id,
            "created_at": self.created_at,
        }

    def _serialize_graph(self) -> dict:
        """Serialize plan graph."""
        return {
            "plan_id": self.plan_graph.plan_id,
            "goal": self.plan_graph.goal,
            "nodes": [
                {
                    "node_id": n.node_id,
                    "task_type": n.task_type,
                    "description": n.description,
                    "depends_on": n.depends_on,
                }
                for n in self.plan_graph.nodes
            ],
        }

    def _serialize_decision(self, d: BranchDecision) -> dict:
        """Serialize branch decision."""
        return {
            "workflow_id": d.workflow_id,
            "task_id": d.task_id,
            "selected_branch": d.selected_branch,
            "evaluated_at": d.evaluated_at,
            "condition_expr": d.condition_expr,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PlanState:
        """Deserialize state from dict."""
        graph_data = data["plan_graph"]
        nodes = [PlanNode(**n) for n in graph_data["nodes"]]
        plan_graph = PlanGraph(
            plan_id=graph_data["plan_id"],
            goal=graph_data["goal"],
            nodes=nodes,
        )
        decisions = [
            BranchDecision(**d) for d in data["branch_decisions"]
        ]
        return cls(
            plan_id=data["plan_id"],
            plan_graph=plan_graph,
            branch_decisions=decisions,
            completed_tasks=set(data["completed_tasks"]),
            task_results=data["task_results"],
            context=data["context"],
            current_node_id=data.get("current_node_id"),
            created_at=data["created_at"],
        )


@dataclass
class Plan:
    """Represents a complete execution plan."""
    plan_id: str
    goal: str
    graph: PlanGraph
    created_at: int
    status: str = "created"
    metadata: dict = field(default_factory=dict)
