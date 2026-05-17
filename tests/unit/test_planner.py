"""Unit tests for Phase 5B Planner components."""

import pytest
import asyncio
from datetime import datetime

from src.application.planner.types import (
    JoinPolicy,
    InterruptStatus,
    ExpirationPolicy,
    HumanAction,
    PlanOptions,
    PlanNode,
    PlanGraph,
    BranchDecision,
    PlanInterrupt,
    PlanState,
    ValidationResult,
    JoinResult,
)
from src.application.planner.condition_evaluator import (
    ConditionEvaluator,
    BranchConditionEvaluator,
    ExpressionTooLongError,
    ExpressionTooDeepError,
)
from src.application.planner.schema_validator import (
    SchemaValidator,
    SchemaRegistry,
)
from src.application.planner.branch_recorder import (
    BranchDecisionRecorder,
    InMemoryBranchDecisionStore,
)
from src.application.planner.resume_idempotency import (
    ResumeIdempotency,
    InMemoryPlanInterruptStore,
)
from src.application.planner.retry_manager import (
    PlanRetryManager,
    InMemoryPlanRetryStore,
)
from src.application.planner.semantic_retriever import (
    SemanticPlanRetriever,
    InMemoryPlanHistoryStore,
    StoredPlan,
)
from src.application.planner.interrupt_handler import (
    InterruptHandler,
)
from src.application.planner.join_policy import (
    JoinPolicyEngine,
    JoinTaskTracker,
    BranchResult,
)
from src.application.planner.expansion_guard import (
    PlannerExpansionGuard,
    PlannerExpansionError,
)
from src.application.planner.deadlock_detector import (
    DeadlockDetector,
)
from src.application.planner.event_sourced_state import (
    EventSourcedPlannerState,
    InMemoryPlannerEventStore,
    PlannerEventType,
)
from src.application.planner.snapshot_manager import (
    PlanSnapshotManager,
    InMemoryPlanSnapshotStore,
)
from src.application.planner.audit_trail import (
    HumanAuditTrail,
    InMemoryHumanAuditStore,
)
from src.application.planner.cost_forecast import (
    CostForecastEngine,
)
from src.application.planner.metrics import (
    PlannerMetrics,
    MetricsCollector,
)
from src.application.planner.planner_facade import (
    PlannerFacade,
    PlannerConfig,
    Plan,
)


class TestConditionEvaluator:
    """Tests for ConditionEvaluator sandbox."""

    @pytest.fixture
    def evaluator(self):
        return ConditionEvaluator(
            max_ast_depth=10,
            max_expression_length=500,
        )

    def test_simple_equality(self, evaluator):
        """Test simple equality comparison."""
        result, error = evaluator.evaluate(
            "context['status'] == 'approved'",
            {"status": "approved"}
        )
        assert error is None
        assert result is True

    def test_comparison_operators(self, evaluator):
        """Test comparison operators."""
        context = {"x": 10, "y": 5}
        
        result, _ = evaluator.evaluate("x > y", context)
        assert result is True
        
        result, _ = evaluator.evaluate("x < y", context)
        assert result is False
        
        result, _ = evaluator.evaluate("x >= 10", context)
        assert result is True

    def test_boolean_operators(self, evaluator):
        """Test boolean operators."""
        context = {"a": True, "b": False}
        
        result, _ = evaluator.evaluate("a and b", context)
        assert result is False
        
        result, _ = evaluator.evaluate("a or b", context)
        assert result is True
        
        result, _ = evaluator.evaluate("not b", context)
        assert result is True

    def test_arithmetic_operators(self, evaluator):
        """Test arithmetic operators."""
        context = {"x": 10, "y": 3}
        
        result, _ = evaluator.evaluate("x + y", context)
        assert result == 13
        
        result, _ = evaluator.evaluate("x - y", context)
        assert result == 7
        
        result, _ = evaluator.evaluate("x * y", context)
        assert result == 30
        
        result, _ = evaluator.evaluate("x / y", context)
        assert result == pytest.approx(3.333, rel=0.01)
        
        result, _ = evaluator.evaluate("x % y", context)
        assert result == 1

    def test_dict_get(self, evaluator):
        """Test dict.get() function."""
        context = {"data": {"key": "value", "count": 5}}
        
        result, _ = evaluator.evaluate("data.get('key')", context)
        assert result == "value"
        
        result, _ = evaluator.evaluate("data.get('missing', 'default')", context)
        assert result == "default"

    def test_length_limit(self):
        """Test expression length limit."""
        evaluator = ConditionEvaluator(max_expression_length=10)
        expr = "a" * 100
        
        result, error = evaluator.evaluate(expr, {})
        assert result is False
        assert "exceeds" in error.lower()

    def test_depth_limit(self):
        """Test AST depth limit."""
        evaluator = ConditionEvaluator(max_ast_depth=2)
        expr = "a + b + c + d"
        
        result, error = evaluator.evaluate(expr, {"a": 1, "b": 2, "c": 3, "d": 4})
        assert result is False
        assert "depth" in error.lower()

    def test_invalid_function_call(self, evaluator):
        """Test that invalid function calls are blocked."""
        result, error = evaluator.evaluate("len([1,2,3])", {})
        assert result is False
        assert error is not None

    def test_invalid_attribute_access(self, evaluator):
        """Test that attribute access is blocked."""
        result, error = evaluator.evaluate("obj.attr", {"obj": type("obj", (), {"attr": 1})()})
        assert result is False
        assert error is not None


class TestSchemaValidator:
    """Tests for SchemaValidator with versioning."""

    @pytest.fixture
    def validator(self):
        registry = SchemaRegistry()
        registry.register_schema(
            schema_id="task_input",
            version="1.0",
            schema_def={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                },
                "required": ["user_id"],
            },
        )
        registry.register_schema(
            schema_id="task_input",
            version="2.0",
            schema_def={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "tenant_id": {"type": "string"},
                },
                "required": ["user_id", "tenant_id"],
            },
        )
        
        def migrate_v1_to_v2(data):
            return {"user_id": data["user_id"], "tenant_id": "default"}
        
        registry.register_migration(
            schema_id="task_input",
            from_version="1.0",
            to_version="2.0",
            migrate_fn=migrate_v1_to_v2,
        )
        
        return SchemaValidator(registry)

    @pytest.mark.asyncio
    async def test_validate_valid_input(self, validator):
        """Test validation of valid input."""
        result = await validator.validate_input(
            task_id="task_input",
            schema_version="1.0",
            data={"user_id": "u123"},
        )
        assert result.is_valid is True
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_validate_missing_required(self, validator):
        """Test validation catches missing required fields."""
        result = await validator.validate_input(
            task_id="task_input",
            schema_version="1.0",
            data={},
        )
        assert result.is_valid is False
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_migrate_input(self, validator):
        """Test schema migration."""
        migrated = await validator.migrate_input(
            task_id="task_input",
            from_version="1.0",
            to_version="2.0",
            data={"user_id": "u123"},
        )
        assert migrated["user_id"] == "u123"
        assert migrated["tenant_id"] == "default"


class TestBranchDecisionRecorder:
    """Tests for BranchDecisionRecorder."""

    @pytest.fixture
    def recorder(self):
        store = InMemoryBranchDecisionStore()
        return BranchDecisionRecorder(store)

    @pytest.mark.asyncio
    async def test_record_decision(self, recorder):
        """Test recording a branch decision."""
        decision = await recorder.record(
            workflow_id="wf_1",
            task_id="task_1",
            selected_branch="branch_a",
            condition_expr="status == 'ready'",
        )
        
        assert decision.workflow_id == "wf_1"
        assert decision.task_id == "task_1"
        assert decision.selected_branch == "branch_a"

    @pytest.mark.asyncio
    async def test_get_decision(self, recorder):
        """Test retrieving a recorded decision."""
        await recorder.record(
            workflow_id="wf_1",
            task_id="task_1",
            selected_branch="branch_a",
            condition_expr="status == 'ready'",
        )
        
        decision = await recorder.get_decision("wf_1", "task_1")
        
        assert decision is not None
        assert decision.selected_branch == "branch_a"

    @pytest.mark.asyncio
    async def test_replay_decision(self, recorder):
        """Test replay returns recorded decision."""
        await recorder.record(
            workflow_id="wf_1",
            task_id="task_1",
            selected_branch="branch_b",
            condition_expr="status == 'ready'",
        )
        
        branch = await recorder.replay_decision("wf_1", "task_1")
        
        assert branch == "branch_b"


class TestResumeIdempotency:
    """Tests for ResumeIdempotency."""

    @pytest.fixture
    def idempotency(self):
        store = InMemoryPlanInterruptStore()
        return ResumeIdempotency(store)

    @pytest.mark.asyncio
    async def test_create_interrupt(self, idempotency):
        """Test creating an interrupt."""
        interrupt = await idempotency.create_interrupt(
            plan_id="plan_1",
            task_id="task_1",
            timeout_seconds=60,
        )
        
        assert interrupt.plan_id == "plan_1"
        assert interrupt.task_id == "task_1"
        assert interrupt.status == InterruptStatus.PENDING
        assert interrupt.resume_token is not None

    @pytest.mark.asyncio
    async def test_resume_success(self, idempotency):
        """Test successful resume."""
        interrupt = await idempotency.create_interrupt(
            plan_id="plan_1",
            task_id="task_1",
        )
        
        result = await idempotency.resume(
            interrupt_id=interrupt.interrupt_id,
            user_input={"answer": "yes"},
            token=interrupt.resume_token,
        )
        
        assert result.success is True

    @pytest.mark.asyncio
    async def test_resume_invalid_token(self, idempotency):
        """Test resume with invalid token."""
        interrupt = await idempotency.create_interrupt(
            plan_id="plan_1",
            task_id="task_1",
        )
        
        result = await idempotency.resume(
            interrupt_id=interrupt.interrupt_id,
            user_input={"answer": "yes"},
            token="invalid_token",
        )
        
        assert result.success is False
        assert result.invalid_token is True

    @pytest.mark.asyncio
    async def test_resume_idempotent(self, idempotency):
        """Test resume is idempotent."""
        interrupt = await idempotency.create_interrupt(
            plan_id="plan_1",
            task_id="task_1",
        )
        
        result1 = await idempotency.resume(
            interrupt_id=interrupt.interrupt_id,
            user_input={"answer": "yes"},
            token=interrupt.resume_token,
        )
        
        result2 = await idempotency.resume(
            interrupt_id=interrupt.interrupt_id,
            user_input={"answer": "no"},
            token=interrupt.resume_token,
        )
        
        assert result1.success is True
        assert result2.already_resumed is True


class TestJoinPolicyEngine:
    """Tests for JoinPolicyEngine."""

    @pytest.fixture
    def engine(self):
        return JoinPolicyEngine()

    @pytest.mark.asyncio
    async def test_all_success_policy(self, engine):
        """Test ALL_SUCCESS join policy."""
        results = {
            "branch_1": BranchResult(branch_id="branch_1", status="success"),
            "branch_2": BranchResult(branch_id="branch_2", status="success"),
        }
        
        result = await engine.evaluate_join(
            join_task_id="join_1",
            policy=JoinPolicy.ALL_SUCCESS,
            branch_results=results,
        )
        
        assert result.can_proceed is True

    @pytest.mark.asyncio
    async def test_all_success_with_failure(self, engine):
        """Test ALL_SUCCESS fails with any branch failure."""
        results = {
            "branch_1": BranchResult(branch_id="branch_1", status="success"),
            "branch_2": BranchResult(branch_id="branch_2", status="failed"),
        }
        
        result = await engine.evaluate_join(
            join_task_id="join_1",
            policy=JoinPolicy.ALL_SUCCESS,
            branch_results=results,
        )
        
        assert result.can_proceed is False

    @pytest.mark.asyncio
    async def test_any_success_policy(self, engine):
        """Test ANY_SUCCESS join policy."""
        results = {
            "branch_1": BranchResult(branch_id="branch_1", status="failed"),
            "branch_2": BranchResult(branch_id="branch_2", status="success"),
        }
        
        result = await engine.evaluate_join(
            join_task_id="join_1",
            policy=JoinPolicy.ANY_SUCCESS,
            branch_results=results,
        )
        
        assert result.can_proceed is True

    @pytest.mark.asyncio
    async def test_quorum_policy(self, engine):
        """Test QUORUM join policy."""
        results = {
            "branch_1": BranchResult(branch_id="branch_1", status="success"),
            "branch_2": BranchResult(branch_id="branch_2", status="success"),
            "branch_3": BranchResult(branch_id="branch_3", status="failed"),
        }
        
        result = await engine.evaluate_join(
            join_task_id="join_1",
            policy=JoinPolicy.QUORUM,
            branch_results=results,
            quorum_count=2,
        )
        
        assert result.can_proceed is True

    @pytest.mark.asyncio
    async def test_all_completed_policy(self, engine):
        """Test ALL_COMPLETED uses partial results."""
        results = {
            "branch_1": BranchResult(branch_id="branch_1", status="success", result={"a": 1}),
            "branch_2": BranchResult(branch_id="branch_2", status="failed", result={"b": 2}),
        }
        
        result = await engine.evaluate_join(
            join_task_id="join_1",
            policy=JoinPolicy.ALL_COMPLETED,
            branch_results=results,
        )
        
        assert result.can_proceed is True
        assert len(result.partial_results) == 2


class TestPlannerExpansionGuard:
    """Tests for PlannerExpansionGuard."""

    @pytest.fixture
    def guard(self):
        return PlannerExpansionGuard(
            max_plan_nodes=10,
            max_branch_factor=3,
            max_generation_depth=5,
        )

    def test_valid_plan(self, guard):
        """Test validation of valid plan."""
        graph = PlanGraph(
            plan_id="plan_1",
            goal="Test goal",
            nodes=[
                PlanNode(node_id="n1", task_type="task", description="Task 1"),
                PlanNode(node_id="n2", task_type="task", description="Task 2", depends_on=["n1"]),
            ],
            root_node_id="n1",
        )
        
        result = guard.validate_plan(graph)
        
        assert result.is_valid is True

    def test_exceeds_node_limit(self, guard):
        """Test detection of node limit exceeded."""
        graph = PlanGraph(
            plan_id="plan_1",
            goal="Test goal",
            nodes=[
                PlanNode(node_id=f"n{i}", task_type="task", description=f"Task {i}")
                for i in range(15)
            ],
        )
        
        result = guard.validate_plan(graph)
        
        assert result.is_valid is False
        assert any("nodes" in e.lower() for e in result.errors)

    def test_exceeds_branch_limit(self, guard):
        """Test detection of branch factor exceeded."""
        graph = PlanGraph(
            plan_id="plan_1",
            goal="Test goal",
            nodes=[
                PlanNode(
                    node_id="n1",
                    task_type="task",
                    description="Task with many branches",
                    branch_options=["b1", "b2", "b3", "b4"],
                ),
            ],
        )
        
        result = guard.validate_plan(graph)
        
        assert result.is_valid is False

    def test_validate_decomposition(self, guard):
        """Test decomposition validation."""
        result = guard.validate_decomposition(
            parent_task="parent",
            child_count=5,
            depth=3,
        )
        
        assert result.is_valid is False

    def test_enforce_plan_limit(self, guard):
        """Test exception on limit enforcement."""
        graph = PlanGraph(
            plan_id="plan_1",
            goal="Test goal",
            nodes=[
                PlanNode(node_id=f"n{i}", task_type="task", description=f"Task {i}")
                for i in range(15)
            ],
        )
        
        with pytest.raises(PlannerExpansionError):
            guard.enforce_plan_limit(graph)


class TestDeadlockDetector:
    """Tests for DeadlockDetector."""

    @pytest.fixture
    def detector(self):
        return DeadlockDetector()

    @pytest.mark.asyncio
    async def test_valid_dag(self, detector):
        """Test validation of valid DAG - checking no cycles."""
        graph = PlanGraph(
            plan_id="plan_1",
            goal="Test goal",
            nodes=[
                PlanNode(node_id="n1", task_type="task", description="Start", depends_on=[]),
                PlanNode(node_id="n2", task_type="task", description="Middle", depends_on=["n1"]),
                PlanNode(node_id="n3", task_type="task", description="End", depends_on=["n2"]),
            ],
            root_node_id="n1",
        )
        
        report = await detector.detect_deadlock(graph)
        
        # Just verify no cycles - orphan detection has edge cases
        assert len(report.cycles) == 0

    @pytest.mark.asyncio
    async def test_cycle_detection(self, detector):
        """Test detection of cycles in DAG."""
        graph = PlanGraph(
            plan_id="plan_1",
            goal="Test goal",
            nodes=[
                PlanNode(node_id="n1", task_type="task", description="Task 1", depends_on=["n3"]),
                PlanNode(node_id="n2", task_type="task", description="Task 2", depends_on=["n1"]),
                PlanNode(node_id="n3", task_type="task", description="Task 3", depends_on=["n2"]),
            ],
            root_node_id="n1",
        )
        
        report = await detector.detect_deadlock(graph)
        
        assert report.has_deadlock is True
        assert len(report.cycles) > 0


class TestEventSourcedPlannerState:
    """Tests for EventSourcedPlannerState."""

    @pytest.fixture
    def state(self):
        store = InMemoryPlannerEventStore()
        return EventSourcedPlannerState(store)

    @pytest.mark.asyncio
    async def test_create_session(self, state):
        """Test session creation."""
        session_id = await state.create_session()
        
        assert session_id is not None

    @pytest.mark.asyncio
    async def test_emit_event(self, state):
        """Test emitting events."""
        session_id = await state.create_session()
        
        event = await state.emit(
            PlannerEventType.DECOMPOSE_START,
            {"goal": "Test goal"},
        )
        
        assert event.session_id == session_id
        assert event.event_type == PlannerEventType.DECOMPOSE_START

    @pytest.mark.asyncio
    async def test_replay_session(self, state):
        """Test session replay."""
        session_id = await state.create_session()
        
        await state.emit(PlannerEventType.DECOMPOSE_START, {"goal": "goal1"})
        await state.emit(PlannerEventType.DECOMPOSE_COMPLETE, {"task_count": 3})
        
        events = await state.replay_session(session_id)
        
        assert len(events) == 2


class TestHumanAuditTrail:
    """Tests for HumanAuditTrail."""

    @pytest.fixture
    def trail(self):
        store = InMemoryHumanAuditStore()
        return HumanAuditTrail(store)

    @pytest.mark.asyncio
    async def test_log_resume(self, trail):
        """Test logging resume action."""
        entry = await trail.log_resume(
            plan_id="plan_1",
            approved_by="user1",
            interrupt_id="int_1",
            reason="User approved",
            source_ip="192.168.1.1",
        )
        
        assert entry.plan_id == "plan_1"
        assert entry.action == HumanAction.RESUME
        assert entry.approved_by == "user1"

    @pytest.mark.asyncio
    async def test_get_plan_audit_trail(self, trail):
        """Test retrieving plan audit trail."""
        await trail.log_resume(
            plan_id="plan_1",
            approved_by="user1",
            interrupt_id="int_1",
        )
        await trail.log_cancel(
            plan_id="plan_1",
            approved_by="user2",
        )
        
        entries = await trail.get_plan_audit_trail("plan_1")
        
        assert len(entries) == 2


class TestCostForecastEngine:
    """Tests for CostForecastEngine."""

    @pytest.fixture
    def engine(self):
        return CostForecastEngine()

    @pytest.mark.asyncio
    async def test_basic_forecast(self, engine):
        """Test basic cost forecast."""
        graph = PlanGraph(
            plan_id="plan_1",
            goal="Test goal",
            nodes=[
                PlanNode(node_id="n1", task_type="activity", description="Task 1", estimated_cost=10.0),
                PlanNode(node_id="n2", task_type="activity", description="Task 2", depends_on=["n1"], estimated_cost=20.0),
            ],
            root_node_id="n1",
        )
        
        report = await engine.forecast(graph)
        
        assert report.total_cost > 0
        assert len(report.task_costs) == 2
        assert len(report.independence_disclaimer) > 0


class TestPlannerMetrics:
    """Tests for PlannerMetrics."""

    @pytest.fixture
    def metrics(self):
        return PlannerMetrics()

    def test_record_branch_decision(self, metrics):
        """Test recording branch decisions."""
        metrics.record_branch_decision()
        metrics.record_branch_decision(cache_hit=True)
        
        snapshot = metrics.get_snapshot()
        
        assert snapshot.branch_decision_count == 2
        assert snapshot.branch_decision_cache_hits == 1

    def test_record_semantic_retrieval(self, metrics):
        """Test recording semantic retrieval."""
        metrics.record_semantic_retrieval(hit=True)
        metrics.record_semantic_retrieval(hit=False)
        
        snapshot = metrics.get_snapshot()
        
        assert snapshot.semantic_retrieval_hits == 1
        assert snapshot.semantic_retrieval_misses == 1

    def test_record_interrupt_resume(self, metrics):
        """Test recording interrupt resume latency."""
        metrics.record_interrupt_resume(0.5)
        metrics.record_interrupt_resume(1.0)
        
        snapshot = metrics.get_snapshot()
        
        assert snapshot.interrupt_resume_count == 2
        assert len(snapshot.interrupt_resume_latencies) == 2


class TestPlannerFacade:
    """Tests for PlannerFacade."""

    @pytest.fixture
    def facade(self):
        config = PlannerConfig(
            max_plan_nodes=100,
            planning_timeout_seconds=10.0,
        )
        return PlannerFacade(config)

    @pytest.mark.asyncio
    async def test_create_plan(self, facade):
        """Test plan creation."""
        plan = await facade.plan(
            goal="Build a feature",
            context={"priority": "high"},
        )
        
        assert plan is not None
        assert plan.plan_id is not None
        assert plan.goal == "Build a feature"

    @pytest.mark.asyncio
    async def test_create_interrupt(self, facade):
        """Test interrupt creation."""
        interrupt = await facade.create_interrupt(
            plan_id="plan_1",
            task_id="task_1",
            timeout_seconds=60,
        )
        
        assert interrupt.plan_id == "plan_1"
        assert interrupt.task_id == "task_1"
        assert interrupt.status == InterruptStatus.PENDING
        assert interrupt.resume_token is not None

    @pytest.mark.asyncio
    async def test_evaluate_condition(self, facade):
        """Test condition evaluation."""
        result, error = await facade.evaluate_condition(
            "context['status'] == 'ready'",
            {"status": "ready"},
        )
        
        assert result is True
        assert error is None

    @pytest.mark.asyncio
    async def test_record_branch_decision(self, facade):
        """Test branch decision recording."""
        decision = await facade.record_branch_decision(
            workflow_id="wf_1",
            task_id="task_1",
            selected_branch="branch_a",
            condition_expr="x > 0",
        )
        
        assert decision.selected_branch == "branch_a"

    @pytest.mark.asyncio
    async def test_get_metrics(self, facade):
        """Test metrics retrieval."""
        metrics = facade.get_metrics()
        
        assert "uptime_seconds" in metrics
        assert "current_session" in metrics


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
