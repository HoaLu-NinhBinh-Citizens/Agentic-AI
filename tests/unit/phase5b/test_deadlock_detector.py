"""Unit tests for deadlock detector.

Tests cover:
- test_detect_cycle: Detects cycles in conditional DAG
- test_detect_orphan_task: Detects tasks not reachable from start
- test_detect_unreachable_join: Detects join nodes that can't be reached
"""

from __future__ import annotations

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from application.planner.deadlock_detector import (
    DeadlockDetector,
    ConditionalDeadlockDetector,
)
from application.planner.types import (
    PlanGraph,
    PlanNode,
    DeadlockReport,
)


# ============================================================================
# DeadlockDetector Tests
# ============================================================================

class TestDeadlockDetector:
    """Test deadlock detection in DAGs."""

    @pytest.fixture
    def detector(self):
        """Create deadlock detector."""
        return DeadlockDetector()

    @pytest.fixture
    def valid_dag(self):
        """Create a valid DAG."""
        return PlanGraph(
            plan_id="valid-001",
            goal="Build API",
            nodes=[
                PlanNode(
                    node_id="root",
                    task_type="task",
                    description="Start",
                    depends_on=[],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
                PlanNode(
                    node_id="step1",
                    task_type="task",
                    description="Step 1",
                    depends_on=["root"],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=2.0,
                    estimated_duration=20.0,
                ),
                PlanNode(
                    node_id="step2",
                    task_type="task",
                    description="Step 2",
                    depends_on=["step1"],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=2.0,
                    estimated_duration=20.0,
                ),
            ],
            root_node_id="root",
        )

    @pytest.fixture
    def cyclic_dag(self):
        """Create a DAG with cycle."""
        return PlanGraph(
            plan_id="cyclic-001",
            goal="Cyclic Plan",
            nodes=[
                PlanNode(
                    node_id="a",
                    task_type="task",
                    description="Task A",
                    depends_on=["c"],  # Cycle: a -> c -> b -> a
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
                PlanNode(
                    node_id="b",
                    task_type="task",
                    description="Task B",
                    depends_on=["a"],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
                PlanNode(
                    node_id="c",
                    task_type="task",
                    description="Task C",
                    depends_on=["b"],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
            ],
            root_node_id="a",
        )

    @pytest.fixture
    def orphan_dag(self):
        """Create a DAG with orphan tasks."""
        return PlanGraph(
            plan_id="orphan-001",
            goal="Orphan Plan",
            nodes=[
                PlanNode(
                    node_id="root",
                    task_type="task",
                    description="Root",
                    depends_on=[],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
                PlanNode(
                    node_id="orphan",
                    task_type="task",
                    description="Orphan Task",
                    depends_on=[],  # No dependency, orphan
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
            ],
            root_node_id="root",
        )

    @pytest.fixture
    def unreachable_join_dag(self):
        """Create a DAG with unreachable join."""
        return PlanGraph(
            plan_id="unreachable-join-001",
            goal="Unreachable Join Plan",
            nodes=[
                PlanNode(
                    node_id="root",
                    task_type="task",
                    description="Root",
                    depends_on=[],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
                PlanNode(
                    node_id="join1",
                    task_type="join",
                    description="Join (unreachable)",
                    depends_on=["orphan_task"],  # Not reachable from root
                    branch_options=[],
                    condition_expr=None,
                    join_policy="ALL_COMPLETE",
                    estimated_cost=0.0,
                    estimated_duration=0.0,
                ),
                PlanNode(
                    node_id="orphan_task",
                    task_type="task",
                    description="Orphan Task",
                    depends_on=[],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
            ],
            root_node_id="root",
        )

    @pytest.mark.asyncio
    async def test_detect_cycle_none_in_valid_dag(self, detector, valid_dag):
        """Test that valid DAG has no cycles."""
        cycles = await detector.validate_acyclic(valid_dag)
        
        assert len(cycles) == 0

    @pytest.mark.asyncio
    async def test_detect_cycle_found_in_cyclic_dag(self, detector, cyclic_dag):
        """Test that cyclic DAG is detected."""
        cycles = await detector.validate_acyclic(cyclic_dag)
        
        assert len(cycles) > 0

    @pytest.mark.asyncio
    async def test_detect_orphan_task_none_in_valid_dag(self, detector, valid_dag):
        """Test that valid DAG has no orphans."""
        orphans = await detector.detect_orphan_tasks(valid_dag)
        
        assert len(orphans) == 0

    @pytest.mark.asyncio
    async def test_detect_orphan_task_found(self, detector, orphan_dag):
        """Test that orphan tasks are detected."""
        orphans = await detector.detect_orphan_tasks(orphan_dag)
        
        assert "orphan" in orphans

    @pytest.mark.asyncio
    async def test_detect_unreachable_join(self, detector, unreachable_join_dag):
        """Test that unreachable join nodes are detected."""
        unreachable = await detector.validate_join_reachability(unreachable_join_dag)
        
        assert "join1" in unreachable

    @pytest.mark.asyncio
    async def test_detect_deadlock_comprehensive(self, detector, cyclic_dag):
        """Test comprehensive deadlock detection."""
        report = await detector.detect_deadlock(cyclic_dag)
        
        assert report.has_deadlock is True
        assert len(report.cycles) > 0

    @pytest.mark.asyncio
    async def test_validate_plan_valid(self, detector, valid_dag):
        """Test plan validation for valid DAG."""
        result = await detector.validate_plan(valid_dag)
        
        assert result.is_valid is True
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_validate_plan_with_cycle(self, detector, cyclic_dag):
        """Test plan validation catches cycle."""
        result = await detector.validate_plan(cyclic_dag)
        
        assert result.is_valid is False
        assert any("Cycle" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_empty_plan(self, detector):
        """Test handling of empty plan."""
        empty_plan = PlanGraph(
            plan_id="empty",
            goal="Empty",
            nodes=[],
            root_node_id=None,
        )
        
        report = await detector.detect_deadlock(empty_plan)
        
        assert report.has_deadlock is False

    @pytest.mark.asyncio
    async def test_single_node_plan(self, detector):
        """Test single node plan (no dependencies)."""
        single = PlanGraph(
            plan_id="single",
            goal="Single",
            nodes=[
                PlanNode(
                    node_id="only",
                    task_type="task",
                    description="Only",
                    depends_on=[],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
            ],
            root_node_id="only",
        )
        
        report = await detector.detect_deadlock(single)
        
        assert report.has_deadlock is False


# ============================================================================
# ConditionalDeadlockDetector Tests
# ============================================================================

class TestConditionalDeadlockDetector:
    """Test conditional deadlock detection."""

    @pytest.fixture
    def detector(self):
        """Create conditional deadlock detector."""
        return ConditionalDeadlockDetector()

    @pytest.mark.asyncio
    async def test_detect_deadlock_with_conditions(self, detector):
        """Test deadlock detection with conditional outcomes."""
        # Create a plan where one branch leads to cycle
        plan = PlanGraph(
            plan_id="conditional-001",
            goal="Conditional Plan",
            nodes=[
                PlanNode(
                    node_id="root",
                    task_type="task",
                    description="Root",
                    depends_on=[],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
                PlanNode(
                    node_id="branch_a",
                    task_type="task",
                    description="Branch A",
                    depends_on=["root"],
                    branch_options=["cond1"],
                    condition_expr="cond1 == True",
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
                PlanNode(
                    node_id="branch_b",
                    task_type="task",
                    description="Branch B",
                    depends_on=["root"],
                    branch_options=["cond1"],
                    condition_expr="cond1 == False",
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
            ],
            root_node_id="root",
        )
        
        # When cond1 is False, branch_a is not active
        condition_results = {"branch_a": False, "branch_b": True}
        
        report = await detector.detect_deadlock_with_conditions(plan, condition_results)
        
        # Should not detect deadlock since inactive branch doesn't matter
        assert report.has_deadlock is False

    @pytest.mark.asyncio
    async def test_active_nodes_filtering(self, detector):
        """Test that inactive nodes are filtered."""
        plan = PlanGraph(
            plan_id="filter-001",
            goal="Filter Test",
            nodes=[
                PlanNode(
                    node_id="root",
                    task_type="task",
                    description="Root",
                    depends_on=[],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
                PlanNode(
                    node_id="active",
                    task_type="task",
                    description="Active Task",
                    depends_on=["root"],
                    branch_options=["cond"],
                    condition_expr="cond == True",
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
                PlanNode(
                    node_id="inactive",
                    task_type="task",
                    description="Inactive Task",
                    depends_on=["root"],
                    branch_options=["cond"],
                    condition_expr="cond == False",
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
            ],
            root_node_id="root",
        )
        
        conditions = {"active": True, "inactive": False}
        
        active = detector._get_active_nodes(plan, conditions)
        
        assert "root" in active
        assert "active" in active
        assert "inactive" not in active

    @pytest.mark.asyncio
    async def test_get_active_nodes_no_conditions(self, detector):
        """Test active nodes when no conditions are false."""
        plan = PlanGraph(
            plan_id="no-cond-001",
            goal="No Conditions",
            nodes=[
                PlanNode(
                    node_id="root",
                    task_type="task",
                    description="Root",
                    depends_on=[],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
                PlanNode(
                    node_id="child",
                    task_type="task",
                    description="Child",
                    depends_on=["root"],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
            ],
            root_node_id="root",
        )
        
        active = detector._get_active_nodes(plan, {})
        
        assert len(active) == 2
        assert "root" in active
        assert "child" in active


# ============================================================================
# Parallel Branch Tests
# ============================================================================

class TestParallelBranchDeadlock:
    """Test deadlock detection in parallel branches."""

    @pytest.fixture
    def detector(self):
        """Create deadlock detector."""
        return DeadlockDetector()

    @pytest.mark.asyncio
    async def test_parallel_branches_valid(self, detector):
        """Test valid parallel branch structure."""
        plan = PlanGraph(
            plan_id="parallel-001",
            goal="Parallel Plan",
            nodes=[
                PlanNode(
                    node_id="root",
                    task_type="task",
                    description="Root",
                    depends_on=[],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
                PlanNode(
                    node_id="parallel1",
                    task_type="task",
                    description="Parallel 1",
                    depends_on=["root"],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
                PlanNode(
                    node_id="parallel2",
                    task_type="task",
                    description="Parallel 2",
                    depends_on=["root"],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
                PlanNode(
                    node_id="join",
                    task_type="join",
                    description="Join",
                    depends_on=["parallel1", "parallel2"],
                    branch_options=[],
                    condition_expr=None,
                    join_policy="ALL_COMPLETE",
                    estimated_cost=0.0,
                    estimated_duration=0.0,
                ),
            ],
            root_node_id="root",
        )
        
        report = await detector.detect_deadlock(plan)
        
        assert report.has_deadlock is False

    @pytest.mark.asyncio
    async def test_missing_dependency(self, detector):
        """Test detection of missing dependency (orphan)."""
        plan = PlanGraph(
            plan_id="missing-dep-001",
            goal="Missing Dependency",
            nodes=[
                PlanNode(
                    node_id="root",
                    task_type="task",
                    description="Root",
                    depends_on=[],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
                PlanNode(
                    node_id="dependent",
                    task_type="task",
                    description="Dependent (missing dep)",
                    depends_on=["nonexistent"],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
            ],
            root_node_id="root",
        )
        
        orphans = await detector.detect_orphan_tasks(plan)
        
        # dependent references nonexistent, so it's effectively orphaned
        assert "dependent" in orphans
