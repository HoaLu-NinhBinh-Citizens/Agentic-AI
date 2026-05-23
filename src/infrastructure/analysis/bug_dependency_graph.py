"""Bug dependency graph (Phase 8.4b).

Provides:
- Dependency tracking between bugs
- Cycle detection in bug dependencies
- Root cause analysis
- Dependency traversal algorithms
"""

from __future__ import annotations

import hashlib
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from src.infrastructure.analysis.bug_report_parser import BugReport

logger = logging.getLogger(__name__)


class DependencyType(Enum):
    """Type of dependency relationship."""
    CAUSES = "causes"           # A causes B
    BLOCKS = "blocks"           # A blocks B
    DUPLICATES = "duplicates"    # A is duplicate of B
    RELATED = "related"         # A is related to B
    DEPENDS_ON = "depends_on"   # A depends on B
    CORRELATED = "correlated"   # A correlates with B


@dataclass
class BugNode:
    """Node in the bug dependency graph."""
    bug_id: str
    signature: str
    title: str
    bug_type: str
    severity: str
    dependencies: list[str] = field(default_factory=list)  # IDs of bugs this depends on
    dependents: list[str] = field(default_factory=list)     # IDs of bugs that depend on this
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    is_root_cause: bool = False
    is_leaf: bool = False  # No bugs depend on this
    
    def add_dependency(self, dep_id: str) -> None:
        """Add a dependency."""
        if dep_id not in self.dependencies:
            self.dependencies.append(dep_id)
    
    def add_dependent(self, dep_id: str) -> None:
        """Add a dependent."""
        if dep_id not in self.dependents:
            self.dependents.append(dep_id)
    
    @property
    def dependency_count(self) -> int:
        return len(self.dependencies)
    
    @property
    def dependent_count(self) -> int:
        return len(self.dependents)


@dataclass
class DependencyEdge:
    """Edge in the bug dependency graph."""
    source_id: str
    target_id: str
    dep_type: DependencyType
    confidence: float = 1.0
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class CycleDetector:
    """Detect cycles in bug dependency graph.
    
    Uses Tarjan's algorithm for cycle detection.
    """
    
    def __init__(self) -> None:
        self._visited: set[str] = set()
        self._recursion_stack: set[str] = set()
        self._cycles: list[list[str]] = []
    
    def find_all_cycles(self, graph: BugDependencyGraph) -> list[list[str]]:
        """Find all cycles in the graph."""
        self._visited.clear()
        self._recursion_stack.clear()
        self._cycles.clear()
        
        for node_id in graph.get_node_ids():
            if node_id not in self._visited:
                self._dfs(node_id, graph, [])
        
        return self._cycles
    
    def _dfs(self, node_id: str, graph: BugDependencyGraph, path: list[str]) -> None:
        """DFS traversal with cycle detection."""
        self._visited.add(node_id)
        self._recursion_stack.add(node_id)
        path.append(node_id)
        
        node = graph.get_node(node_id)
        if node:
            for dep_id in node.dependencies:
                if dep_id not in self._visited:
                    self._dfs(dep_id, graph, path)
                elif dep_id in self._recursion_stack:
                    # Found cycle - extract it
                    cycle_start = path.index(dep_id)
                    cycle = path[cycle_start:] + [dep_id]
                    if cycle not in self._cycles:
                        self._cycles.append(cycle)
        
        path.pop()
        self._recursion_stack.remove(node_id)
    
    def has_cycle(self, graph: BugDependencyGraph) -> bool:
        """Check if graph has any cycles."""
        return len(self.find_all_cycles(graph)) > 0


class DependencyAnalyzer:
    """Analyze bug dependencies to infer relationships."""
    
    # Patterns that suggest cause-effect relationships
    CAUSAL_PATTERNS = {
        # Null pointer dereference can cause hardfault
        ("NULL_POINTER", "HARD_FAULT"): 0.9,
        ("STACK_OVERFLOW", "HARD_FAULT"): 0.85,
        ("BUS_FAULT", "HARD_FAULT"): 0.8,
        ("HEAP_EXHAUSTION", "NULL_POINTER"): 0.7,
        ("DEADLOCK", "WATCHDOG_TIMEOUT"): 0.6,
        ("RACE_CONDITION", "DEADLOCK"): 0.5,
        ("CLOCK_ERROR", "PERIPHERAL_ERROR"): 0.7,
        ("POWER_ERROR", "RESET"): 0.8,
    }
    
    def infer_dependencies(
        self,
        bugs: list[BugReport],
    ) -> list[tuple[str, str, DependencyType, float]]:
        """Infer dependencies between bugs based on patterns.
        
        Returns:
            List of (source_id, target_id, dep_type, confidence) tuples
        """
        dependencies: list[tuple[str, str, DependencyType, float]] = []
        
        for i, bug1 in enumerate(bugs):
            for bug2 in bugs[i + 1:]:
                # Check causal patterns
                dep = self._check_causal_pattern(bug1, bug2)
                if dep:
                    dependencies.append(dep)
        
        return dependencies
    
    def _check_causal_pattern(
        self,
        bug1: BugReport,
        bug2: BugReport,
    ) -> tuple[str, str, DependencyType, float] | None:
        """Check if two bugs match a known causal pattern."""
        pattern_key = (bug1.bug_type.value.upper(), bug2.bug_type.value.upper())
        
        if pattern_key in self.CAUSAL_PATTERNS:
            confidence = self.CAUSAL_PATTERNS[pattern_key]
            return (
                bug1.id or bug1.compute_signature(),
                bug2.id or bug2.compute_signature(),
                DependencyType.CAUSES,
                confidence,
            )
        
        # Check for common root causes
        if set(bug1.root_causes) & set(bug2.root_causes):
            return (
                bug1.id or bug1.compute_signature(),
                bug2.id or bug2.compute_signature(),
                DependencyType.CORRELATED,
                0.6,
            )
        
        return None


class BugDependencyGraph:
    """Directed acyclic graph (DAG) of bug dependencies.
    
    Phase 8.4b: Bug dependency graph
    - Bug A depends on Bug B
    - Detects and breaks cycles
    - Supports root cause analysis
    """
    
    def __init__(self) -> None:
        self._nodes: dict[str, BugNode] = {}
        self._edges: list[DependencyEdge] = []
        self._cycle_detector = CycleDetector()
        self._dependency_analyzer = DependencyAnalyzer()
    
    def add_node(self, bug: BugReport) -> BugNode:
        """Add a bug as a node in the graph."""
        bug_id = bug.id or bug.compute_signature()
        
        if bug_id in self._nodes:
            return self._nodes[bug_id]
        
        node = BugNode(
            bug_id=bug_id,
            signature=bug.compute_signature(),
            title=bug.title,
            bug_type=bug.bug_type.value,
            severity=bug.severity.value,
        )
        self._nodes[bug_id] = node
        return node
    
    def add_dependency(
        self,
        source_id: str,
        target_id: str,
        dep_type: DependencyType = DependencyType.CAUSES,
        confidence: float = 1.0,
        reason: str = "",
    ) -> bool:
        """Add a dependency edge between two bugs.
        
        Args:
            source_id: ID of the source bug
            target_id: ID of the target bug (source depends on target)
            
        Returns:
            True if dependency was added, False if it would create a cycle
        """
        if source_id == target_id:
            return False
        
        # Get or create nodes
        if source_id not in self._nodes:
            return False
        if target_id not in self._nodes:
            return False
        
        source = self._nodes[source_id]
        target = self._nodes[target_id]
        
        # Add edge
        source.add_dependency(target_id)
        target.add_dependent(source_id)
        
        self._edges.append(DependencyEdge(
            source_id=source_id,
            target_id=target_id,
            dep_type=dep_type,
            confidence=confidence,
            reason=reason,
        ))
        
        # Check for cycles
        if self._cycle_detector.has_cycle(self):
            # Revert
            source.dependencies.remove(target_id)
            target.dependents.remove(source_id)
            self._edges.pop()
            logger.warning("Dependency would create cycle, skipped", extra={"source": source_id, "target": target_id})
            return False
        
        return True
    
    def add_bugs(self, bugs: list[BugReport]) -> None:
        """Add multiple bugs as nodes."""
        for bug in bugs:
            self.add_node(bug)
    
    def infer_and_add_dependencies(self, bugs: list[BugReport]) -> int:
        """Infer dependencies between bugs and add them.
        
        Returns:
            Number of dependencies added
        """
        # Add nodes
        self.add_bugs(bugs)
        
        # Infer dependencies
        inferred = self._dependency_analyzer.infer_dependencies(bugs)
        
        count = 0
        for source_id, target_id, dep_type, confidence in inferred:
            if self.add_dependency(source_id, target_id, dep_type, confidence):
                count += 1
        
        return count
    
    def get_node(self, bug_id: str) -> BugNode | None:
        """Get a node by ID."""
        return self._nodes.get(bug_id)
    
    def get_node_ids(self) -> list[str]:
        """Get all node IDs."""
        return list(self._nodes.keys())
    
    def get_roots(self) -> list[BugNode]:
        """Get root bugs (no dependencies)."""
        return [n for n in self._nodes.values() if len(n.dependencies) == 0]
    
    def get_leaves(self) -> list[BugNode]:
        """Get leaf bugs (no dependents)."""
        return [n for n in self._nodes.values() if len(n.dependents) == 0]
    
    def get_root_causes(self) -> list[BugNode]:
        """Get bugs that are root causes (affect many others but are not caused by others)."""
        root_causes = []
        for node in self._nodes.values():
            if len(node.dependencies) == 0 and len(node.dependents) > 0:
                root_causes.append(node)
        return sorted(root_causes, key=lambda n: len(n.dependents), reverse=True)
    
    def get_dependent_chain(self, bug_id: str) -> list[BugNode]:
        """Get all bugs that depend on this bug (directly or indirectly)."""
        if bug_id not in self._nodes:
            return []
        
        visited: set[str] = set()
        result: list[BugNode] = []
        queue = deque([bug_id])
        
        while queue:
            current_id = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)
            
            node = self._nodes.get(current_id)
            if node:
                for dep_id in node.dependents:
                    if dep_id not in visited:
                        dep_node = self._nodes.get(dep_id)
                        if dep_node:
                            result.append(dep_node)
                        queue.append(dep_id)
        
        return result
    
    def get_dependency_chain(self, bug_id: str) -> list[BugNode]:
        """Get all bugs that this bug depends on (directly or indirectly)."""
        if bug_id not in self._nodes:
            return []
        
        visited: set[str] = set()
        result: list[BugNode] = []
        queue = deque([bug_id])
        
        while queue:
            current_id = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)
            
            node = self._nodes.get(current_id)
            if node:
                for dep_id in node.dependencies:
                    if dep_id not in visited:
                        dep_node = self._nodes.get(dep_id)
                        if dep_node:
                            result.append(dep_node)
                        queue.append(dep_id)
        
        return result
    
    def topological_sort(self) -> list[BugNode] | None:
        """Return nodes in topological order (dependencies first).
        
        Returns None if graph has cycles.
        """
        if self._cycle_detector.has_cycle(self):
            return None
        
        in_degree = {node_id: 0 for node_id in self._nodes}
        for node in self._nodes.values():
            for dep_id in node.dependencies:
                if dep_id in in_degree:
                    pass  # in_degree counts dependencies
        
        # Calculate in-degrees
        in_degree = {node_id: 0 for node_id in self._nodes}
        for node in self._nodes.values():
            for dep_id in node.dependencies:
                if dep_id in in_degree:
                    pass
        
        # Actually count how many deps each node has
        for node_id in self._nodes:
            node = self._nodes[node_id]
            in_degree[node_id] = len(node.dependencies)
        
        # Kahn's algorithm
        queue = deque([node_id for node_id, degree in in_degree.items() if degree == 0])
        result: list[BugNode] = []
        
        while queue:
            current_id = queue.popleft()
            current = self._nodes[current_id]
            result.append(current)
            
            for dep_id in current.dependents:
                in_degree[dep_id] -= 1
                if in_degree[dep_id] == 0:
                    queue.append(dep_id)
        
        if len(result) != len(self._nodes):
            return None  # Has cycle
        
        return result
    
    def find_cycles(self) -> list[list[str]]:
        """Find all cycles in the graph."""
        return self._cycle_detector.find_all_cycles(self)
    
    def break_cycle(self, cycle: list[str]) -> str | None:
        """Break a cycle by removing the weakest dependency.
        
        Returns:
            ID of the removed dependency
        """
        if len(cycle) < 2:
            return None
        
        # Find weakest edge (lowest confidence)
        weakest_edge = None
        weakest_confidence = 1.0
        
        for i, source_id in enumerate(cycle[:-1]):
            target_id = cycle[i + 1]
            for edge in self._edges:
                if edge.source_id == source_id and edge.target_id == target_id:
                    if edge.confidence < weakest_confidence:
                        weakest_confidence = edge.confidence
                        weakest_edge = edge
        
        if weakest_edge:
            # Remove edge
            self._edges.remove(weakest_edge)
            
            # Update nodes
            source = self._nodes.get(weakest_edge.source_id)
            target = self._nodes.get(weakest_edge.target_id)
            if source:
                source.dependencies.remove(weakest_edge.target_id)
            if target:
                target.dependents.remove(weakest_edge.source_id)
            
            return weakest_edge.target_id
        
        return None
    
    def get_statistics(self) -> dict[str, Any]:
        """Get graph statistics."""
        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "root_causes": len(self.get_root_causes()),
            "leaves": len(self.get_leaves()),
            "has_cycles": self._cycle_detector.has_cycle(self),
            "cycles": len(self.find_cycles()),
        }
    
    def to_dict(self) -> dict[str, Any]:
        """Export graph as dictionary."""
        return {
            "nodes": {
                node_id: {
                    "bug_id": node.bug_id,
                    "title": node.title,
                    "bug_type": node.bug_type,
                    "severity": node.severity,
                    "dependencies": node.dependencies,
                    "dependents": node.dependents,
                }
                for node_id, node in self._nodes.items()
            },
            "edges": [
                {
                    "source": edge.source_id,
                    "target": edge.target_id,
                    "type": edge.dep_type.value,
                    "confidence": edge.confidence,
                    "reason": edge.reason,
                }
                for edge in self._edges
            ],
        }


# Global singleton
_graph: BugDependencyGraph | None = None


def get_bug_dependency_graph() -> BugDependencyGraph:
    """Get global bug dependency graph instance."""
    global _graph
    if _graph is None:
        _graph = BugDependencyGraph()
    return _graph


# CLI for testing
if __name__ == "__main__":
    from src.infrastructure.analysis.bug_report_parser import (
        BugReport,
        BugType,
        BugSeverity,
        BugLocation,
    )
    
    graph = BugDependencyGraph()
    
    # Create sample bugs with relationships
    bugs = [
        BugReport(
            id="bug1",
            title="Null pointer dereference",
            bug_type=BugType.MEMORY_FAULT,
            severity=BugSeverity.HIGH,
            confidence=0.9,
        ),
        BugReport(
            id="bug2",
            title="HardFault",
            bug_type=BugType.HARD_FAULT,
            severity=BugSeverity.CRITICAL,
            confidence=0.95,
        ),
        BugReport(
            id="bug3",
            title="Stack overflow",
            bug_type=BugType.STACK_OVERFLOW,
            severity=BugSeverity.CRITICAL,
            confidence=0.9,
        ),
    ]
    
    print("Testing bug dependency graph:")
    print("-" * 50)
    
    # Add bugs
    graph.add_bugs(bugs)
    print(f"Added {len(bugs)} bugs")
    
    # Add dependencies
    graph.add_dependency("bug1", "bug2", DependencyType.CAUSES, 0.9, "Null ptr can cause hardfault")
    graph.add_dependency("bug3", "bug2", DependencyType.CAUSES, 0.85, "Stack overflow can cause hardfault")
    print("Added 2 dependencies")
    
    # Analyze
    stats = graph.get_statistics()
    print(f"\nStatistics: {stats}")
    
    # Find root causes
    roots = graph.get_root_causes()
    print(f"\nRoot causes ({len(roots)}):")
    for root in roots:
        print(f"  - {root.title} ({root.bug_type}) affects {len(root.dependents)} bugs")
    
    # Check for cycles
    cycles = graph.find_cycles()
    print(f"\nCycles found: {len(cycles)}")
    
    # Topological sort
    sorted_nodes = graph.topological_sort()
    if sorted_nodes:
        print("\nTopological order:")
        for node in sorted_nodes:
            print(f"  - {node.title}")
