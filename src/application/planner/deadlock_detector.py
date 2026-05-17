"""Deadlock detection for DAG validation - Phase 5B."""

from __future__ import annotations

from collections import deque
from typing import Optional

from .types import DeadlockReport, PlanGraph, PlanNode, ValidationResult


class DeadlockDetector:
    """Detects deadlocks in conditional DAGs.
    
    Performs three types of validation:
    1. Cycle detection (acyclic check)
    2. Join reachability validation
    3. Orphan task detection
    """
    
    def __init__(self, auto_reject: bool = True):
        self._auto_reject = auto_reject
    
    async def detect_deadlock(self, plan: PlanGraph) -> DeadlockReport:
        """Run all deadlock detection checks.
        
        Args:
            plan: The plan graph to validate
            
        Returns:
            DeadlockReport with all detected issues
        """
        cycles = await self.validate_acyclic(plan)
        unreachable_joins = await self.validate_join_reachability(plan)
        orphan_tasks = await self.detect_orphan_tasks(plan)
        
        has_deadlock = bool(cycles or unreachable_joins or orphan_tasks)
        
        return DeadlockReport(
            has_deadlock=has_deadlock,
            cycles=cycles,
            unreachable_joins=unreachable_joins,
            orphan_tasks=orphan_tasks,
        )
    
    async def validate_acyclic(self, plan: PlanGraph) -> list[list[str]]:
        """Check for cycles in the DAG.
        
        Uses DFS to detect cycles and returns the cycle path if found.
        
        Args:
            plan: The plan graph to validate
            
        Returns:
            List of cycles (each cycle is a list of node IDs)
        """
        if not plan.nodes:
            return []
        
        nodes_map = {n.node_id: n for n in plan.nodes}
        
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n.node_id: WHITE for n in plan.nodes}
        parent = {n.node_id: None for n in plan.nodes}
        cycles = []
        
        def dfs(node_id: str, path: list[str]) -> bool:
            color[node_id] = GRAY
            path.append(node_id)
            
            node = nodes_map.get(node_id)
            if node:
                for dep_id in node.depends_on:
                    if dep_id not in nodes_map:
                        continue
                    
                    if color[dep_id] == GRAY:
                        cycle_start = path.index(dep_id)
                        cycle = path[cycle_start:] + [dep_id]
                        cycles.append(cycle)
                    
                    elif color[dep_id] == WHITE:
                        parent[dep_id] = node_id
                        if dfs(dep_id, path):
                            return True
            
            path.pop()
            color[node_id] = BLACK
            return False
        
        for node in plan.nodes:
            if color[node.node_id] == WHITE:
                if dfs(node.node_id, []):
                    break
        
        return cycles
    
    async def validate_join_reachability(self, plan: PlanGraph) -> list[str]:
        """Ensure all join nodes are reachable from start.
        
        Args:
            plan: The plan graph to validate
            
        Returns:
            List of unreachable join node IDs
        """
        if not plan.root_node_id:
            return []
        
        unreachable = []
        nodes_map = {n.node_id: n for n in plan.nodes}
        
        join_nodes = [
            n.node_id for n in plan.nodes
            if n.join_policy is not None
        ]
        
        reachable = self._get_reachable_nodes(plan, plan.root_node_id)
        
        for join_id in join_nodes:
            if join_id not in reachable:
                unreachable.append(join_id)
        
        return unreachable
    
    async def detect_orphan_tasks(self, plan: PlanGraph) -> list[str]:
        """Find tasks not reachable from start or not leading to terminal.
        
        Args:
            plan: The plan graph to validate
            
        Returns:
            List of orphan task IDs
        """
        if not plan.nodes:
            return []
        
        nodes_map = {n.node_id: n for n in plan.nodes}
        
        if plan.root_node_id:
            reachable_from_start = self._get_reachable_nodes(plan, plan.root_node_id)
        else:
            reachable_from_start = set(n.node_id for n in plan.nodes)
        
        reachable_to_terminal = self._get_reachable_to_terminal(plan)
        
        orphans = []
        
        for node in plan.nodes:
            if node.node_id not in reachable_from_start:
                orphans.append(node.node_id)
            elif node.node_id not in reachable_to_terminal:
                orphans.append(node.node_id)
        
        return orphans
    
    def _get_reachable_nodes(
        self,
        plan: PlanGraph,
        start_id: str,
    ) -> set[str]:
        """Get all nodes reachable from a start node."""
        reachable = set()
        queue = deque([start_id])
        nodes_map = {n.node_id: n for n in plan.nodes}
        
        while queue:
            node_id = queue.popleft()
            
            if node_id in reachable:
                continue
            
            reachable.add(node_id)
            
            node = nodes_map.get(node_id)
            if node:
                for dep_id in node.depends_on:
                    if dep_id not in reachable:
                        queue.append(dep_id)
        
        return reachable
    
    def _get_reachable_to_terminal(self, plan: PlanGraph) -> set[str]:
        """Get all nodes that can reach a terminal node.
        
        A terminal node is one that has no outgoing edges.
        """
        if not plan.nodes:
            return set()
        
        outgoing = {n.node_id: set() for n in plan.nodes}
        incoming = {n.node_id: set() for n in plan.nodes}
        
        for node in plan.nodes:
            for dep_id in node.depends_on:
                if dep_id in outgoing:
                    outgoing[dep_id].add(node.node_id)
                    incoming[node.node_id].add(dep_id)
        
        terminal_nodes = {
            node_id for node_id, edges in outgoing.items()
            if not edges
        }
        
        if not terminal_nodes:
            return set(n.node_id for n in plan.nodes)
        
        can_reach_terminal = set()
        queue = deque(terminal_nodes)
        
        while queue:
            node_id = queue.popleft()
            
            if node_id in can_reach_terminal:
                continue
            
            can_reach_terminal.add(node_id)
            
            for predecessor in incoming[node_id]:
                if predecessor not in can_reach_terminal:
                    queue.append(predecessor)
        
        return can_reach_terminal
    
    async def validate_plan(self, plan: PlanGraph) -> ValidationResult:
        """Validate plan for deadlocks and return detailed report.
        
        Args:
            plan: The plan graph to validate
            
        Returns:
            ValidationResult with deadlock check results
        """
        report = await self.detect_deadlock(plan)
        
        errors = []
        warnings = []
        
        for cycle in report.cycles:
            errors.append(f"Cycle detected: {' -> '.join(cycle)}")
        
        for join_id in report.unreachable_joins:
            errors.append(f"Join node unreachable: {join_id}")
        
        for orphan_id in report.orphan_tasks:
            warnings.append(f"Orphan task: {orphan_id}")
        
        return ValidationResult(
            is_valid=not report.has_deadlock,
            errors=errors,
            warnings=warnings,
            details={
                "cycles": report.cycles,
                "unreachable_joins": report.unreachable_joins,
                "orphan_tasks": report.orphan_tasks,
            },
        )


class ConditionalDeadlockDetector(DeadlockDetector):
    """Extended deadlock detector for conditional DAGs.
    
    Handles conditional branches and optional dependencies.
    """
    
    async def detect_deadlock_with_conditions(
        self,
        plan: PlanGraph,
        condition_results: dict[str, bool],
    ) -> DeadlockReport:
        """Detect deadlocks considering conditional branch outcomes.
        
        Args:
            plan: The plan graph
            condition_results: Map of node_id to condition outcome
            
        Returns:
            DeadlockReport considering active paths only
        """
        if not plan.root_node_id:
            return DeadlockReport(has_deadlock=False)
        
        active_nodes = self._get_active_nodes(plan, condition_results)
        
        filtered_plan = self._filter_plan(plan, active_nodes)
        
        return await self.detect_deadlock(filtered_plan)
    
    def _get_active_nodes(
        self,
        plan: PlanGraph,
        condition_results: dict[str, bool],
    ) -> set[str]:
        """Get nodes that are active given condition outcomes."""
        nodes_map = {n.node_id: n for n in plan.nodes}
        active = set()
        
        if not plan.root_node_id:
            return set(n.node_id for n in plan.nodes)
        
        queue = deque([plan.root_node_id])
        
        while queue:
            node_id = queue.popleft()
            
            if node_id in active:
                continue
            
            active.add(node_id)
            
            node = nodes_map.get(node_id)
            if not node:
                continue
            
            if node.condition_expr:
                if not condition_results.get(node_id, False):
                    continue
            
            for dep_id in node.depends_on:
                if dep_id not in active:
                    queue.append(dep_id)
        
        return active
    
    def _filter_plan(
        self,
        plan: PlanGraph,
        active_nodes: set[str],
    ) -> PlanGraph:
        """Create a filtered plan with only active nodes."""
        from .types import PlanGraph as PlanGraphType
        
        filtered_nodes = [
            n for n in plan.nodes
            if n.node_id in active_nodes
        ]
        
        for node in filtered_nodes:
            node.depends_on = [
                d for d in node.depends_on
                if d in active_nodes
            ]
        
        return PlanGraphType(
            plan_id=plan.plan_id,
            goal=plan.goal,
            nodes=filtered_nodes,
            root_node_id=plan.root_node_id if plan.root_node_id in active_nodes else None,
        )
