"""Planner facade - Phase 5B Enterprise.

Main entry point that integrates all planner components.
"""

from __future__ import annotations

import uuid
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .types import (
    PlanOptions,
    PlanGraph,
    PlanNode,
    PlanState,
    BranchDecision,
    PlanInterrupt,
    PlannerEvent,
    PlanSnapshot,
    ValidationResult,
    DeadlockReport,
    CostForecastReport,
    JoinPolicy,
    JoinResult,
    InterruptStatus,
    ExpirationPolicy,
    HumanAction,
    PlannerEventType,
    Plan,
)
from .condition_evaluator import ConditionEvaluator, BranchConditionEvaluator
from .schema_validator import SchemaValidator, SchemaRegistry
from .branch_recorder import BranchDecisionRecorder, InMemoryBranchDecisionStore
from .resume_idempotency import ResumeIdempotency, InMemoryPlanInterruptStore
from .retry_manager import PlanRetryManager, InMemoryPlanRetryStore
from .semantic_retriever import SemanticPlanRetriever, InMemoryPlanHistoryStore
from .interrupt_handler import InterruptHandler
from .join_policy import JoinPolicyEngine, JoinTaskTracker
from .expansion_guard import PlannerExpansionGuard, PlannerExpansionError
from .deadlock_detector import DeadlockDetector, ConditionalDeadlockDetector
from .event_sourced_state import EventSourcedPlannerState, InMemoryPlannerEventStore
from .snapshot_manager import PlanSnapshotManager, InMemoryPlanSnapshotStore
from .audit_trail import HumanAuditTrail, InMemoryHumanAuditStore
from .cost_forecast import CostForecastEngine
from .metrics import PlannerMetrics, MetricsCollector


@dataclass
class PlannerConfig:
    """Configuration for the planner."""
    max_plan_nodes: int = 500
    max_branch_factor: int = 5
    max_search_states: int = 10000
    max_generation_depth: int = 10
    planning_timeout_seconds: float = 30.0
    default_join_policy: JoinPolicy = JoinPolicy.ALL_SUCCESS
    default_expiration_policy: ExpirationPolicy = ExpirationPolicy.AUTO_CANCEL
    resume_timeout_seconds: int = 300
    semantic_retrieval_min_quality: float = 0.8
    semantic_retrieval_require_verified: bool = True
    semantic_retrieval_max_failure_rate: float = 0.2
    event_sourcing_enabled: bool = True
    audit_log_enabled: bool = True


class PlannerFacade:
    """Enterprise planner facade integrating all Phase 5B components.
    
    This is the main entry point for planning operations.
    """
    
    def __init__(self, config: Optional[PlannerConfig] = None):
        self._config = config or PlannerConfig()
        
        self._setup_components()
    
    def _setup_components(self) -> None:
        """Initialize all planner components."""
        self._metrics = PlannerMetrics()
        
        self._event_store = InMemoryPlannerEventStore()
        self._event_state = EventSourcedPlannerState(self._event_store)
        
        self._schema_registry = SchemaRegistry()
        self._schema_validator = SchemaValidator(self._schema_registry)
        
        self._branch_store = InMemoryBranchDecisionStore()
        self._branch_recorder = BranchDecisionRecorder(self._branch_store)
        
        self._condition_evaluator = BranchConditionEvaluator(
            max_ast_depth=10,
            max_expression_length=500,
        )
        
        self._interrupt_store = InMemoryPlanInterruptStore()
        self._resume_idempotency = ResumeIdempotency(
            self._interrupt_store,
            self._config.resume_timeout_seconds,
        )
        
        self._interrupt_handler = InterruptHandler(
            expiration_policy=self._config.default_expiration_policy,
        )
        
        self._retry_store = InMemoryPlanRetryStore()
        self._retry_manager = PlanRetryManager(
            self._retry_store,
            snapshot_before_first_run=True,
        )
        
        self._history_store = InMemoryPlanHistoryStore()
        self._semantic_retriever = SemanticPlanRetriever(
            self._history_store,
            min_quality_score=self._config.semantic_retrieval_min_quality,
            require_human_verified=self._config.semantic_retrieval_require_verified,
            max_failure_rate=self._config.semantic_retrieval_max_failure_rate,
        )
        
        self._join_engine = JoinPolicyEngine()
        
        self._expansion_guard = PlannerExpansionGuard(
            max_plan_nodes=self._config.max_plan_nodes,
            max_branch_factor=self._config.max_branch_factor,
            max_search_states=self._config.max_search_states,
            max_generation_depth=self._config.max_generation_depth,
            planning_timeout_seconds=self._config.planning_timeout_seconds,
        )
        
        self._deadlock_detector = DeadlockDetector()
        self._conditional_deadlock_detector = ConditionalDeadlockDetector()
        
        self._snapshot_store = InMemoryPlanSnapshotStore()
        self._snapshot_manager = PlanSnapshotManager(self._snapshot_store)
        
        self._audit_store = InMemoryHumanAuditStore()
        self._audit_trail = HumanAuditTrail(
            self._audit_store,
            include_source_ip=True,
        )
        
        self._cost_forecast = CostForecastEngine()
    
    async def plan(
        self,
        goal: str,
        context: Optional[dict] = None,
        options: Optional[PlanOptions] = None,
    ) -> Plan:
        """Create execution plan from goal.
        
        Args:
            goal: The planning goal
            context: Planning context
            options: Planning options
            
        Returns:
            Generated plan
        """
        session_id = await self._event_state.create_session()
        
        await self._event_state.emit_decompose_start(goal, session_id)
        
        await self._event_state.emit_beam_search_step(1, 10, session_id)
        
        plan_id = str(uuid.uuid4())
        
        plan_graph = PlanGraph(
            plan_id=plan_id,
            goal=goal,
            nodes=[],
        )
        
        root_node = PlanNode(
            node_id=str(uuid.uuid4()),
            task_type="root",
            description=goal,
        )
        plan_graph.add_node(root_node)
        plan_graph.root_node_id = root_node.node_id
        
        await self._event_state.emit_decompose_complete(
            task_count=len(plan_graph.nodes),
            session_id=session_id,
        )
        
        if options and options.enable_semantic_retrieval:
            template = await self._semantic_retriever.retrieve_for_template(goal)
            if template:
                await self._event_state.emit_retrieved_template(
                    template.plan_id,
                    template.quality_score,
                    session_id,
                )
        
        validation = await self.validate_plan_graph(plan_graph)
        if not validation.is_valid:
            raise ValueError(f"Plan validation failed: {validation.errors}")
        
        await self._event_state.emit_plan_selected(
            plan_id,
            "beam_search_completed",
            session_id,
        )
        
        snapshot = await self._snapshot_manager.create_snapshot(
            plan_id=plan_id,
            definition_version="1.0",
            plan_graph=plan_graph,
        )
        
        self._metrics.record_plan_created()
        self._metrics.record_checkpoint(len(str(snapshot)))
        
        return Plan(
            plan_id=plan_id,
            goal=goal,
            graph=plan_graph,
            created_at=int(datetime.utcnow().timestamp()),
        )
    
    async def resume_plan(
        self,
        interrupt_id: str,
        user_input: dict,
        token: str,
        approved_by: str = "system",
        reason: Optional[str] = None,
        source_ip: Optional[str] = None,
    ) -> bool:
        """Resume an interrupted plan.
        
        Args:
            interrupt_id: The interrupt to resume
            user_input: User input to continue
            token: Resume token
            approved_by: User performing resume
            reason: Optional reason
            source_ip: Optional source IP
            
        Returns:
            True if resume successful
        """
        start_time = time.time()
        
        result = await self._resume_idempotency.resume(
            interrupt_id, user_input, token
        )
        
        if result.success:
            await self._audit_trail.log_resume(
                plan_id=result.interrupt_id if hasattr(result, 'interrupt_id') else "",
                approved_by=approved_by,
                interrupt_id=interrupt_id,
                reason=reason,
                source_ip=source_ip,
            )
            
            self._metrics.record_interrupt_resume(time.time() - start_time)
        else:
            if result.invalid_token:
                raise ValueError("Invalid resume token")
            if result.already_resumed:
                return False
        
        return result.success
    
    async def create_interrupt(
        self,
        plan_id: str,
        task_id: str,
        timeout_seconds: Optional[int] = None,
    ) -> PlanInterrupt:
        """Create an interrupt for human input.
        
        Args:
            plan_id: Plan identifier
            task_id: Task requiring input
            timeout_seconds: Optional timeout
            
        Returns:
            Created interrupt with resume token
        """
        interrupt = await self._resume_idempotency.create_interrupt(
            plan_id, task_id, timeout_seconds
        )
        
        return interrupt
    
    async def get_planner_events(
        self,
        session_id: str,
    ) -> list[PlannerEvent]:
        """Get events for a planning session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of planner events
        """
        return await self._event_state.get_session_events(session_id)
    
    async def validate_plan_graph(
        self,
        plan_graph: PlanGraph,
    ) -> ValidationResult:
        """Validate plan graph for deadlocks and expansion limits.
        
        Args:
            plan_graph: Plan to validate
            
        Returns:
            Validation report
        """
        errors = []
        warnings = []
        
        expansion_result = self._expansion_guard.validate_plan(plan_graph)
        if not expansion_result.is_valid:
            errors.extend(expansion_result.errors)
            for _ in expansion_result.errors:
                self._metrics.record_expansion_rejection()
        
        deadlock_result = await self._deadlock_detector.validate_plan(plan_graph)
        if not deadlock_result.is_valid:
            errors.extend(deadlock_result.errors)
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details={
                "expansion": expansion_result.details if expansion_result.details else {},
                "deadlock": deadlock_result.details if deadlock_result.details else {},
            },
        )
    
    async def get_snapshot(
        self,
        plan_id: str,
    ) -> Optional[PlanSnapshot]:
        """Get immutable plan snapshot.
        
        Args:
            plan_id: Plan identifier
            
        Returns:
            Snapshot if exists
        """
        return await self._snapshot_manager.get_snapshot(plan_id)
    
    async def forecast_cost(
        self,
        plan: PlanGraph,
        historical_data: Optional[dict] = None,
    ) -> CostForecastReport:
        """Generate cost forecast for a plan.
        
        Args:
            plan: Plan to forecast
            historical_data: Optional historical data
            
        Returns:
            Cost forecast report
        """
        return await self._cost_forecast.forecast(plan, historical_data)
    
    async def evaluate_condition(
        self,
        expr: str,
        context: dict,
    ) -> tuple[bool, Optional[str]]:
        """Evaluate a condition expression safely.
        
        Args:
            expr: Condition expression
            context: Evaluation context
            
        Returns:
            Tuple of (result, error)
        """
        return self._condition_evaluator.evaluate(expr, context)
    
    async def record_branch_decision(
        self,
        workflow_id: str,
        task_id: str,
        selected_branch: str,
        condition_expr: str,
    ) -> BranchDecision:
        """Record a branch decision for replay.
        
        Args:
            workflow_id: Workflow identifier
            task_id: Task identifier
            selected_branch: Selected branch
            condition_expr: Original expression
            
        Returns:
            Recorded decision
        """
        decision = await self._branch_recorder.record(
            workflow_id, task_id, selected_branch, condition_expr
        )
        self._metrics.record_branch_decision()
        return decision
    
    async def get_branch_decision(
        self,
        workflow_id: str,
        task_id: str,
    ) -> Optional[BranchDecision]:
        """Get recorded branch decision for replay.
        
        Args:
            workflow_id: Workflow identifier
            task_id: Task identifier
            
        Returns:
            Recorded decision if exists
        """
        decision = await self._branch_recorder.get_decision(workflow_id, task_id)
        if decision:
            self._metrics.record_branch_decision(cache_hit=True)
        return decision
    
    async def validate_schema(
        self,
        task_id: str,
        schema_version: str,
        data: dict,
    ) -> ValidationResult:
        """Validate data against schema.
        
        Args:
            task_id: Task identifier
            schema_version: Schema version
            data: Data to validate
            
        Returns:
            Validation result
        """
        result = await self._schema_validator.validate_input(
            task_id, schema_version, data
        )
        
        if result.is_valid:
            self._metrics.record_schema_validation(True)
        else:
            self._metrics.record_schema_validation(False)
        
        return result
    
    async def migrate_schema(
        self,
        task_id: str,
        from_version: str,
        to_version: str,
        data: dict,
    ) -> dict:
        """Migrate data between schema versions.
        
        Args:
            task_id: Task identifier
            from_version: Source version
            to_version: Target version
            data: Data to migrate
            
        Returns:
            Migrated data
        """
        migrated = await self._schema_validator.migrate_input(
            task_id, from_version, to_version, data
        )
        self._metrics.record_schema_migration()
        return migrated
    
    async def create_retry_snapshot(
        self,
        plan_id: str,
        state: PlanState,
    ) -> None:
        """Create snapshot before retry.
        
        Args:
            plan_id: Plan identifier
            state: Current state
        """
        await self._retry_manager.create_snapshot(plan_id, state)
        self._metrics.record_plan_retry(False)
    
    async def restore_retry_snapshot(
        self,
        plan_id: str,
    ) -> Optional[PlanState]:
        """Restore state from retry snapshot.
        
        Args:
            plan_id: Plan identifier
            
        Returns:
            Restored state or None
        """
        state = await self._retry_manager.restore_snapshot(plan_id)
        if state:
            self._metrics.record_plan_retry(True)
        return state
    
    async def check_interrupt_expiration(
        self,
        interrupt_id: str,
    ) -> bool:
        """Check and handle interrupt expiration.
        
        Args:
            interrupt_id: Interrupt to check
            
        Returns:
            True if expired and handled
        """
        interrupt = await self._resume_idempotency.get_interrupt(interrupt_id)
        if not interrupt:
            return False
        
        result = await self._interrupt_handler.check_expiration(interrupt)
        
        if result.is_expired:
            await self._resume_idempotency.expire(interrupt_id)
            await self._interrupt_handler.execute_policy(interrupt)
            self._metrics.record_interrupt_expiration()
            return True
        
        return False
    
    async def evaluate_join(
        self,
        join_task_id: str,
        policy: JoinPolicy,
        branch_results: dict,
        quorum_count: int = 1,
    ) -> JoinResult:
        """Evaluate a join condition.
        
        Args:
            join_task_id: Join task identifier
            policy: Join policy
            branch_results: Branch results
            quorum_count: Required for QUORUM policy
            
        Returns:
            Join result
        """
        return await self._join_engine.evaluate_join(
            join_task_id, policy, branch_results, quorum_count
        )
    
    async def get_plan_audit_trail(
        self,
        plan_id: str,
    ) -> list:
        """Get audit trail for a plan.
        
        Args:
            plan_id: Plan identifier
            
        Returns:
            List of audit entries
        """
        return await self._audit_trail.get_plan_audit_trail(plan_id)
    
    def get_metrics(self) -> dict:
        """Get current planner metrics.
        
        Returns:
            Metrics summary
        """
        return self._metrics.get_summary()
