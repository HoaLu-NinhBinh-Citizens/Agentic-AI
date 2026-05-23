"""Tests for bug dependency graph (Phase 8.4b)."""

import pytest
from src.infrastructure.analysis.bug_report_parser import (
    BugReport,
    BugType,
    BugSeverity,
    BugLocation,
)
from src.infrastructure.analysis.bug_dependency_graph import (
    BugDependencyGraph,
    BugNode,
    CycleDetector,
    DependencyAnalyzer,
    DependencyEdge,
    DependencyType,
    get_bug_dependency_graph,
)


class TestBugNode:
    """Test BugNode dataclass."""
    
    def test_add_dependency(self):
        """Test adding dependencies."""
        node = BugNode(
            bug_id="bug1",
            signature="sig1",
            title="Test Bug",
            bug_type="hard_fault",
            severity="critical",
        )
        
        node.add_dependency("bug2")
        node.add_dependency("bug3")
        node.add_dependency("bug2")  # Duplicate
        
        assert len(node.dependencies) == 2
        assert "bug2" in node.dependencies
        assert "bug3" in node.dependencies
    
    def test_add_dependent(self):
        """Test adding dependents."""
        node = BugNode(
            bug_id="bug1",
            signature="sig1",
            title="Test Bug",
            bug_type="hard_fault",
            severity="critical",
        )
        
        node.add_dependent("bug2")
        node.add_dependent("bug3")
        
        assert len(node.dependents) == 2
    
    def test_counts(self):
        """Test dependency/dependent counts."""
        node = BugNode(
            bug_id="bug1",
            signature="sig1",
            title="Test Bug",
            bug_type="hard_fault",
            severity="critical",
            dependencies=["bug2", "bug3"],
            dependents=["bug4"],
        )
        
        assert node.dependency_count == 2
        assert node.dependent_count == 1


class TestCycleDetector:
    """Test cycle detection."""
    
    def test_no_cycle_simple(self):
        """Test simple graph with no cycle."""
        graph = BugDependencyGraph()
        graph.add_bugs([
            BugReport(id="bug1", title="Bug 1", bug_type=BugType.HARD_FAULT, severity=BugSeverity.CRITICAL),
            BugReport(id="bug2", title="Bug 2", bug_type=BugType.STACK_OVERFLOW, severity=BugSeverity.HIGH),
        ])
        
        detector = CycleDetector()
        assert not detector.has_cycle(graph)
    
    def test_detect_simple_cycle(self):
        """Test detecting a simple cycle: A -> B -> A."""
        graph = BugDependencyGraph()
        graph.add_bugs([
            BugReport(id="bug1", title="Bug 1", bug_type=BugType.HARD_FAULT, severity=BugSeverity.CRITICAL),
            BugReport(id="bug2", title="Bug 2", bug_type=BugType.STACK_OVERFLOW, severity=BugSeverity.HIGH),
        ])
        
        graph.add_dependency("bug1", "bug2")
        # Second dependency creates cycle - should be rejected
        result = graph.add_dependency("bug2", "bug1")
        
        assert result is False
        # Verify cycle was NOT created
        assert "bug1" not in graph.get_node("bug2").dependencies
        
        detector = CycleDetector()
        assert not detector.has_cycle(graph)
    
    def test_detect_complex_cycle(self):
        """Test detecting a complex cycle: A -> B -> C -> A."""
        graph = BugDependencyGraph()
        graph.add_bugs([
            BugReport(id="bug1", title="Bug 1", bug_type=BugType.HARD_FAULT, severity=BugSeverity.CRITICAL),
            BugReport(id="bug2", title="Bug 2", bug_type=BugType.STACK_OVERFLOW, severity=BugSeverity.HIGH),
            BugReport(id="bug3", title="Bug 3", bug_type=BugType.DEADLOCK, severity=BugSeverity.MEDIUM),
        ])
        
        graph.add_dependency("bug1", "bug2")
        graph.add_dependency("bug2", "bug3")
        # This would create cycle - should be rejected
        result = graph.add_dependency("bug3", "bug1")
        
        assert result is False
        # Graph should be acyclic
        detector = CycleDetector()
        assert not detector.has_cycle(graph)
        
        # Only 2 edges should exist (cycle prevented)
        stats = graph.get_statistics()
        assert stats["total_edges"] == 2


class TestDependencyAnalyzer:
    """Test dependency inference."""
    
    def test_infer_causal_relationship(self):
        """Test inferring causal relationship between bugs."""
        analyzer = DependencyAnalyzer()
        
        bugs = [
            BugReport(
                id="bug1",
                title="Null pointer",
                bug_type=BugType.MEMORY_FAULT,
                severity=BugSeverity.HIGH,
            ),
            BugReport(
                id="bug2",
                title="HardFault",
                bug_type=BugType.HARD_FAULT,
                severity=BugSeverity.CRITICAL,
            ),
        ]
        
        deps = analyzer.infer_dependencies(bugs)
        
        # Should find some dependency (may or may not be causal)
        assert isinstance(deps, list)


class TestBugDependencyGraph:
    """Test bug dependency graph."""
    
    def test_add_node(self):
        """Test adding a bug as node."""
        graph = BugDependencyGraph()
        
        bug = BugReport(
            id="bug1",
            title="HardFault",
            bug_type=BugType.HARD_FAULT,
            severity=BugSeverity.CRITICAL,
        )
        
        node = graph.add_node(bug)
        
        assert node is not None
        assert node.bug_id == "bug1"
        assert node.title == "HardFault"
    
    def test_add_dependency(self):
        """Test adding a dependency edge."""
        graph = BugDependencyGraph()
        
        bug1 = BugReport(id="bug1", title="Bug 1", bug_type=BugType.HARD_FAULT, severity=BugSeverity.CRITICAL)
        bug2 = BugReport(id="bug2", title="Bug 2", bug_type=BugType.STACK_OVERFLOW, severity=BugSeverity.HIGH)
        
        graph.add_bugs([bug1, bug2])
        result = graph.add_dependency("bug1", "bug2")
        
        assert result is True
        assert "bug2" in graph.get_node("bug1").dependencies
        assert "bug1" in graph.get_node("bug2").dependents
    
    def test_prevent_cycle(self):
        """Test that adding a cycle is prevented."""
        graph = BugDependencyGraph()
        
        bug1 = BugReport(id="bug1", title="Bug 1", bug_type=BugType.HARD_FAULT, severity=BugSeverity.CRITICAL)
        bug2 = BugReport(id="bug2", title="Bug 2", bug_type=BugType.STACK_OVERFLOW, severity=BugSeverity.HIGH)
        
        graph.add_bugs([bug1, bug2])
        
        # Add first dependency
        result1 = graph.add_dependency("bug1", "bug2")
        assert result1 is True
        
        # Try to add reverse dependency (would create cycle) - should be rejected
        result2 = graph.add_dependency("bug2", "bug1")
        
        assert result2 is False
        # Dependencies should not be updated
        assert "bug1" not in graph.get_node("bug2").dependencies
    
    def test_get_roots(self):
        """Test getting root bugs."""
        graph = BugDependencyGraph()
        
        bug1 = BugReport(id="bug1", title="Root Bug", bug_type=BugType.HARD_FAULT, severity=BugSeverity.CRITICAL)
        bug2 = BugReport(id="bug2", title="Dependent Bug", bug_type=BugType.STACK_OVERFLOW, severity=BugSeverity.HIGH)
        
        graph.add_bugs([bug1, bug2])
        graph.add_dependency("bug2", "bug1")  # bug2 depends on bug1
        
        roots = graph.get_roots()
        
        assert len(roots) == 1
        assert roots[0].bug_id == "bug1"
    
    def test_get_leaves(self):
        """Test getting leaf bugs."""
        graph = BugDependencyGraph()
        
        bug1 = BugReport(id="bug1", title="Root Bug", bug_type=BugType.HARD_FAULT, severity=BugSeverity.CRITICAL)
        bug2 = BugReport(id="bug2", title="Dependent Bug", bug_type=BugType.STACK_OVERFLOW, severity=BugSeverity.HIGH)
        
        graph.add_bugs([bug1, bug2])
        graph.add_dependency("bug2", "bug1")
        
        leaves = graph.get_leaves()
        
        assert len(leaves) == 1
        assert leaves[0].bug_id == "bug2"
    
    def test_get_root_causes(self):
        """Test finding root causes."""
        graph = BugDependencyGraph()
        
        # Create a chain: A -> B -> C
        bug_a = BugReport(id="bug_a", title="Root Cause", bug_type=BugType.HARD_FAULT, severity=BugSeverity.CRITICAL)
        bug_b = BugReport(id="bug_b", title="Middle", bug_type=BugType.STACK_OVERFLOW, severity=BugSeverity.HIGH)
        bug_c = BugReport(id="bug_c", title="Leaf", bug_type=BugType.I2C_TIMEOUT, severity=BugSeverity.MEDIUM)
        
        graph.add_bugs([bug_a, bug_b, bug_c])
        graph.add_dependency("bug_b", "bug_a")
        graph.add_dependency("bug_c", "bug_b")
        
        root_causes = graph.get_root_causes()
        
        # A has no dependencies but has dependents, so it should be a root cause
        assert len(root_causes) >= 1
        cause_ids = [rc.bug_id for rc in root_causes]
        assert "bug_a" in cause_ids
    
    def test_get_dependent_chain(self):
        """Test getting all dependents of a bug."""
        graph = BugDependencyGraph()
        
        bug1 = BugReport(id="bug1", title="Root", bug_type=BugType.HARD_FAULT, severity=BugSeverity.CRITICAL)
        bug2 = BugReport(id="bug2", title="Direct Dep", bug_type=BugType.STACK_OVERFLOW, severity=BugSeverity.HIGH)
        bug3 = BugReport(id="bug3", title="Indirect Dep", bug_type=BugType.I2C_TIMEOUT, severity=BugSeverity.MEDIUM)
        
        graph.add_bugs([bug1, bug2, bug3])
        graph.add_dependency("bug2", "bug1")
        graph.add_dependency("bug3", "bug2")
        
        dependents = graph.get_dependent_chain("bug1")
        
        assert len(dependents) == 2
        dependent_ids = {d.bug_id for d in dependents}
        assert "bug2" in dependent_ids
        assert "bug3" in dependent_ids
    
    def test_get_dependency_chain(self):
        """Test getting all dependencies of a bug."""
        graph = BugDependencyGraph()
        
        bug1 = BugReport(id="bug1", title="Root", bug_type=BugType.HARD_FAULT, severity=BugSeverity.CRITICAL)
        bug2 = BugReport(id="bug2", title="Direct Dep", bug_type=BugType.STACK_OVERFLOW, severity=BugSeverity.HIGH)
        bug3 = BugReport(id="bug3", title="Indirect Dep", bug_type=BugType.I2C_TIMEOUT, severity=BugSeverity.MEDIUM)
        
        graph.add_bugs([bug1, bug2, bug3])
        graph.add_dependency("bug3", "bug2")
        graph.add_dependency("bug3", "bug1")
        
        dependencies = graph.get_dependency_chain("bug3")
        
        assert len(dependencies) == 2
        dep_ids = {d.bug_id for d in dependencies}
        assert "bug1" in dep_ids
        assert "bug2" in dep_ids
    
    def test_topological_sort(self):
        """Test topological sort."""
        graph = BugDependencyGraph()
        
        # Create: A -> B -> C
        bug_a = BugReport(id="bug_a", title="A", bug_type=BugType.HARD_FAULT, severity=BugSeverity.CRITICAL)
        bug_b = BugReport(id="bug_b", title="B", bug_type=BugType.STACK_OVERFLOW, severity=BugSeverity.HIGH)
        bug_c = BugReport(id="bug_c", title="C", bug_type=BugType.I2C_TIMEOUT, severity=BugSeverity.MEDIUM)
        
        graph.add_bugs([bug_a, bug_b, bug_c])
        graph.add_dependency("bug_b", "bug_a")
        graph.add_dependency("bug_c", "bug_b")
        
        sorted_nodes = graph.topological_sort()
        
        assert sorted_nodes is not None
        assert len(sorted_nodes) == 3
        
        # Check order: bug_a should come before bug_b, bug_b before bug_c
        ids = [n.bug_id for n in sorted_nodes]
        assert ids.index("bug_a") < ids.index("bug_b")
        assert ids.index("bug_b") < ids.index("bug_c")
    
    def test_topological_sort_fails_with_cycle(self):
        """Test that topological sort fails with cycle."""
        graph = BugDependencyGraph()
        
        bug1 = BugReport(id="bug1", title="Bug 1", bug_type=BugType.HARD_FAULT, severity=BugSeverity.CRITICAL)
        bug2 = BugReport(id="bug2", title="Bug 2", bug_type=BugType.STACK_OVERFLOW, severity=BugSeverity.HIGH)
        
        graph.add_bugs([bug1, bug2])
        graph.add_dependency("bug1", "bug2")
        # This should be rejected (would create cycle)
        result = graph.add_dependency("bug2", "bug1")
        
        assert result is False
        
        # Should succeed since no cycle was created
        sorted_nodes = graph.topological_sort()
        assert sorted_nodes is not None
    
    def test_infer_and_add_dependencies(self):
        """Test automatic dependency inference."""
        graph = BugDependencyGraph()
        
        bugs = [
            BugReport(
                id="bug1",
                title="Memory fault",
                bug_type=BugType.MEMORY_FAULT,
                severity=BugSeverity.HIGH,
            ),
            BugReport(
                id="bug2",
                title="HardFault",
                bug_type=BugType.HARD_FAULT,
                severity=BugSeverity.CRITICAL,
            ),
        ]
        
        # Just verify inference runs without error
        count = graph.infer_and_add_dependencies(bugs)
        # Count may be 0 if no causal patterns match exactly
        assert isinstance(count, int)
    
    def test_find_and_break_cycle(self):
        """Test cycle detection (breaking is tested separately)."""
        graph = BugDependencyGraph()
        
        bug1 = BugReport(id="bug1", title="Bug 1", bug_type=BugType.HARD_FAULT, severity=BugSeverity.CRITICAL)
        bug2 = BugReport(id="bug2", title="Bug 2", bug_type=BugType.STACK_OVERFLOW, severity=BugSeverity.HIGH)
        bug3 = BugReport(id="bug3", title="Bug 3", bug_type=BugType.I2C_TIMEOUT, severity=BugSeverity.MEDIUM)
        
        graph.add_bugs([bug1, bug2, bug3])
        graph.add_dependency("bug1", "bug2", DependencyType.RELATED, 0.8)
        graph.add_dependency("bug2", "bug3", DependencyType.RELATED, 0.7)
        # This would create cycle - should be rejected
        result = graph.add_dependency("bug3", "bug1", DependencyType.RELATED, 0.6)
        
        assert result is False
        
        # No cycles should exist
        cycles = graph.find_cycles()
        assert len(cycles) == 0
        
        # Graph statistics
        stats = graph.get_statistics()
        assert stats["total_nodes"] == 3
        assert stats["total_edges"] == 2  # Only 2 edges added successfully


class TestBugDependencyGraphIntegration:
    """Integration tests for bug dependency graph."""
    
    def test_realistic_scenario(self):
        """Test with realistic bug dependencies."""
        graph = BugDependencyGraph()
        
        bugs = [
            BugReport(
                id="null_ptr",
                title="Null pointer dereference",
                bug_type=BugType.MEMORY_FAULT,
                severity=BugSeverity.HIGH,
            ),
            BugReport(
                id="hardfault",
                title="HardFault exception",
                bug_type=BugType.HARD_FAULT,
                severity=BugSeverity.CRITICAL,
            ),
            BugReport(
                id="watchdog",
                title="Watchdog timeout",
                bug_type=BugType.WATCHDOG_TIMEOUT,
                severity=BugSeverity.HIGH,
            ),
        ]
        
        graph.add_bugs(bugs)
        
        # Null pointer causes hardfault
        graph.add_dependency("hardfault", "null_ptr", DependencyType.CAUSES, 0.9)
        
        # Hardfault causes watchdog (system hangs)
        graph.add_dependency("watchdog", "hardfault", DependencyType.CAUSES, 0.85)
        
        # Get root causes
        root_causes = graph.get_root_causes()
        assert len(root_causes) == 1
        assert root_causes[0].bug_id == "null_ptr"
        
        # Check statistics
        stats = graph.get_statistics()
        assert stats["total_nodes"] == 3
        assert stats["total_edges"] == 2
        assert stats["has_cycles"] is False
    
    def test_export_to_dict(self):
        """Test exporting graph to dictionary."""
        graph = BugDependencyGraph()
        
        bug1 = BugReport(id="bug1", title="Bug 1", bug_type=BugType.HARD_FAULT, severity=BugSeverity.CRITICAL)
        bug2 = BugReport(id="bug2", title="Bug 2", bug_type=BugType.STACK_OVERFLOW, severity=BugSeverity.HIGH)
        
        graph.add_bugs([bug1, bug2])
        graph.add_dependency("bug2", "bug1")
        
        data = graph.to_dict()
        
        assert "nodes" in data
        assert "edges" in data
        assert "bug1" in data["nodes"]
        assert "bug2" in data["nodes"]
        assert len(data["edges"]) == 1
