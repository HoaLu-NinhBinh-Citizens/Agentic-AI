"""Unit tests for planner expansion guard.

Tests cover:
- test_beam_search_max_states: Limits search states, doesn't exceed
- test_plan_expansion_guard: Exceeds max_nodes -> PlannerExpansionError
"""

from __future__ import annotations

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from application.planner.expansion_guard import (
    PlannerExpansionGuard,
    PlannerExpansionError,
    ExpansionMetrics,
)
from application.planner.types import PlanGraph, PlanNode, ValidationResult


# ============================================================================
# PlannerExpansionGuard Tests
# ============================================================================

class TestPlannerExpansionGuard:
    """Test planner expansion guard."""

    @pytest.fixture
    def guard(self):
        """Create guard with test limits."""
        return PlannerExpansionGuard(
            max_plan_nodes=10,
            max_branch_factor=3,
            max_search_states=100,
            max_generation_depth=5,
            planning_timeout_seconds=10.0,
        )

    @pytest.fixture
    def valid_plan(self):
        """Create a valid plan within limits."""
        return PlanGraph(
            plan_id="valid-001",
            goal="Small Plan",
            nodes=[
                PlanNode(
                    node_id=f"node_{i}",
                    task_type="task",
                    description=f"Node {i}",
                    depends_on=[] if i == 0 else [f"node_{i-1}"],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                )
                for i in range(5)
            ],
            root_node_id="node_0",
        )

    @pytest.fixture
    def large_plan(self):
        """Create a plan exceeding node limit."""
        return PlanGraph(
            plan_id="large-001",
            goal="Large Plan",
            nodes=[
                PlanNode(
                    node_id=f"node_{i}",
                    task_type="task",
                    description=f"Node {i}",
                    depends_on=[] if i == 0 else [f"node_{i-1}"],
                    branch_options=[],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                )
                for i in range(15)  # Over 10 node limit
            ],
            root_node_id="node_0",
        )

    @pytest.fixture
    def deep_plan(self):
        """Create a plan exceeding depth limit."""
        nodes = []
        for i in range(10):  # Over 5 depth limit
            nodes.append(PlanNode(
                node_id=f"depth_{i}",
                task_type="task",
                description=f"Depth {i}",
                depends_on=[] if i == 0 else [f"depth_{i-1}"],
                branch_options=[],
                condition_expr=None,
                join_policy=None,
                estimated_cost=1.0,
                estimated_duration=10.0,
            ))
        
        return PlanGraph(
            plan_id="deep-001",
            goal="Deep Plan",
            nodes=nodes,
            root_node_id="depth_0",
        )

    @pytest.fixture
    def high_branch_plan(self):
        """Create a plan with high branch factor."""
        return PlanGraph(
            plan_id="branch-001",
            goal="High Branch Plan",
            nodes=[
                PlanNode(
                    node_id="root",
                    task_type="task",
                    description="Root",
                    depends_on=[],
                    branch_options=["a", "b", "c", "d"],  # Over 3 limit
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                ),
            ],
            root_node_id="root",
        )

    def test_validate_plan_within_limits(self, guard, valid_plan):
        """Test validation passes for valid plan."""
        result = guard.validate_plan(valid_plan)
        
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_plan_exceeds_nodes(self, guard, large_plan):
        """Test validation catches node limit exceeded."""
        result = guard.validate_plan(large_plan)
        
        assert result.is_valid is False
        assert any("nodes" in e.lower() for e in result.errors)

    def test_validate_plan_exceeds_depth(self, guard, deep_plan):
        """Test validation catches depth exceeded."""
        result = guard.validate_plan(deep_plan)
        
        assert result.is_valid is False
        assert any("depth" in e.lower() for e in result.errors)

    def test_validate_plan_exceeds_branch(self, guard, high_branch_plan):
        """Test validation catches branch factor exceeded."""
        result = guard.validate_plan(high_branch_plan)
        
        assert result.is_valid is False
        assert any("branch" in e.lower() for e in result.errors)

    def test_enforce_plan_limit_raises(self, guard, large_plan):
        """Test enforce_plan_limit raises on violation."""
        with pytest.raises(PlannerExpansionError) as exc_info:
            guard.enforce_plan_limit(large_plan)
        
        assert "max_plan_nodes" in exc_info.value.limit_type

    def test_enforce_plan_limit_passes(self, guard, valid_plan):
        """Test enforce_plan_limit passes for valid plan."""
        # Should not raise
        guard.enforce_plan_limit(valid_plan)

    def test_validate_decomposition(self, guard):
        """Test validating task decomposition."""
        result = guard.validate_decomposition("parent", 2, 3)
        
        assert result.is_valid is True

    def test_validate_decomposition_exceeds_branch(self, guard):
        """Test decomposition exceeds branch limit."""
        result = guard.validate_decomposition("parent", 10, 2)  # 10 branches
        
        assert result.is_valid is False
        assert any("branches" in e.lower() for e in result.errors)

    def test_validate_decomposition_exceeds_depth(self, guard):
        """Test decomposition exceeds depth limit."""
        result = guard.validate_decomposition("parent", 2, 10)  # 10 depth
        
        assert result.is_valid is False
        assert any("depth" in e.lower() for e in result.errors)

    def test_validate_search_states_within_limit(self, guard):
        """Test search states within limit."""
        result = guard.validate_search_states(50)
        
        assert result.is_valid is True

    def test_validate_search_states_exceeds_limit(self, guard):
        """Test search states exceeds limit."""
        result = guard.validate_search_states(150)  # Over 100
        
        assert result.is_valid is False
        assert any("states" in e.lower() for e in result.errors)

    def test_beam_search_max_states(self, guard):
        """Test that beam search respects max states limit."""
        # Simulate beam search tracking
        current_states = 0
        for i in range(200):
            result = guard.validate_search_states(current_states)
            
            if not result.is_valid:
                # Would stop beam search here
                break
            
            # Expand states (simulated)
            if current_states < guard._max_states:
                current_states += 10

    def test_plan_expansion_guard(self, guard, large_plan):
        """Test that exceeding max_nodes raises PlannerExpansionError."""
        with pytest.raises(PlannerExpansionError) as exc_info:
            guard.enforce_plan_limit(large_plan)
        
        assert exc_info.value.limit_type == "max_plan_nodes"

    def test_timeout_check(self, guard):
        """Test timeout checking."""
        assert guard.check_timeout(5.0) is False  # Under 10s
        assert guard.check_timeout(10.0) is False  # Exactly 10s
        assert guard.check_timeout(11.0) is True   # Over 10s

    def test_timeout_remaining(self, guard):
        """Test remaining time calculation."""
        assert guard.get_timeout_remaining(2.0) == 8.0
        assert guard.get_timeout_remaining(12.0) == 0.0

    def test_limits_property(self, guard):
        """Test limits property returns config."""
        limits = guard.limits
        
        assert limits["max_plan_nodes"] == 10
        assert limits["max_branch_factor"] == 3
        assert limits["max_search_states"] == 100
        assert limits["max_generation_depth"] == 5


# ============================================================================
# ExpansionMetrics Tests
# ============================================================================

class TestExpansionMetrics:
    """Test expansion metrics tracking."""

    @pytest.fixture
    def metrics(self):
        """Create expansion metrics."""
        return ExpansionMetrics()

    @pytest.fixture
    def sample_plan(self):
        """Create a sample plan for metrics."""
        return PlanGraph(
            plan_id="sample",
            goal="Sample",
            nodes=[
                PlanNode(
                    node_id=f"n{i}",
                    task_type="task",
                    description=f"Node {i}",
                    depends_on=[],
                    branch_options=["a", "b"] if i == 0 else [],
                    condition_expr=None,
                    join_policy=None,
                    estimated_cost=1.0,
                    estimated_duration=10.0,
                )
                for i in range(5)
            ],
            root_node_id="n0",
        )

    def test_record_plan(self, metrics, sample_plan):
        """Test recording plan metrics."""
        metrics.record_plan(sample_plan)
        
        stats = metrics.get_stats()
        
        assert stats["total_plans"] == 1
        assert stats["max_nodes_observed"] == 5

    def test_record_rejection(self, metrics):
        """Test recording plan rejection."""
        metrics.record_rejection()
        metrics.record_rejection()
        
        stats = metrics.get_stats()
        
        assert stats["rejections"] == 2

    def test_stats_with_no_records(self, metrics):
        """Test stats with no recorded plans."""
        stats = metrics.get_stats()
        
        assert stats["total_plans"] == 0
        assert stats["rejections"] == 0
        assert stats["avg_nodes"] == 0

    def test_multiple_plans(self, metrics, sample_plan):
        """Test recording multiple plans."""
        for _ in range(3):
            metrics.record_plan(sample_plan)
        
        stats = metrics.get_stats()
        
        assert stats["total_plans"] == 3
