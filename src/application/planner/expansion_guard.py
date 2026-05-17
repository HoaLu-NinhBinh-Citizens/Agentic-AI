"""Planner expansion guard - Phase 5B."""

from __future__ import annotations

from typing import Optional

from .types import PlanGraph, PlanNode, ValidationResult


class PlannerExpansionError(Exception):
    """Raised when plan exceeds expansion limits."""
    
    def __init__(self, message: str, limit_type: str, value: int, max_value: int):
        super().__init__(message)
        self.limit_type = limit_type
        self.value = value
        self.max_value = max_value


class PlannerExpansionGuard:
    """Enforces complexity limits on plan generation.
    
    Prevents runaway plan expansion by validating:
    - Total node count
    - Branch factor at decision points
    - Generation depth
    - Search states in beam search
    - Planning timeout
    """
    
    def __init__(
        self,
        max_plan_nodes: int = 500,
        max_branch_factor: int = 5,
        max_search_states: int = 10000,
        max_generation_depth: int = 10,
        planning_timeout_seconds: float = 30.0,
    ):
        self._max_nodes = max_plan_nodes
        self._max_branch = max_branch_factor
        self._max_states = max_search_states
        self._max_depth = max_generation_depth
        self._timeout = planning_timeout_seconds
    
    @property
    def limits(self) -> dict:
        """Get current limits."""
        return {
            "max_plan_nodes": self._max_nodes,
            "max_branch_factor": self._max_branch,
            "max_search_states": self._max_states,
            "max_generation_depth": self._max_depth,
            "planning_timeout_seconds": self._timeout,
        }
    
    def validate_plan(self, plan: PlanGraph) -> ValidationResult:
        """Validate a complete plan against all limits.
        
        Args:
            plan: The plan graph to validate
            
        Returns:
            ValidationResult with any violations
        """
        errors = []
        warnings = []
        
        node_count = len(plan.nodes)
        if node_count > self._max_nodes:
            errors.append(
                f"Plan has {node_count} nodes, exceeds limit of {self._max_nodes}"
            )
        
        max_branch = self._get_max_branch_factor(plan)
        if max_branch > self._max_branch:
            errors.append(
                f"Max branch factor is {max_branch}, exceeds limit of {self._max_branch}"
            )
        
        max_depth = self._get_max_depth(plan)
        if max_depth > self._max_depth:
            errors.append(
                f"Plan depth is {max_depth}, exceeds limit of {self._max_depth}"
            )
        
        if plan.root_node_id and self._has_unreachable_nodes(plan):
            warnings.append("Some nodes are not reachable from root")
        
        if self._has_orphan_nodes(plan):
            warnings.append("Some nodes do not lead to any terminal")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details={
                "node_count": node_count,
                "max_branch_factor": max_branch,
                "max_depth": max_depth,
                "limits": self.limits,
            },
        )
    
    def validate_decomposition(
        self,
        parent_task: str,
        child_count: int,
        depth: int,
    ) -> ValidationResult:
        """Validate a task decomposition step.
        
        Called during planning to catch expansion early.
        
        Args:
            parent_task: Parent task identifier
            child_count: Number of child tasks
            depth: Current depth in the plan tree
            
        Returns:
            ValidationResult with any violations
        """
        errors = []
        warnings = []
        
        if child_count > self._max_branch:
            errors.append(
                f"Decomposition creates {child_count} branches, "
                f"exceeds limit of {self._max_branch}"
            )
        
        if depth > self._max_depth:
            errors.append(
                f"Decomposition at depth {depth}, exceeds limit of {self._max_depth}"
            )
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )
    
    def validate_search_states(self, state_count: int) -> ValidationResult:
        """Validate beam search state count.
        
        Args:
            state_count: Current number of search states
            
        Returns:
            ValidationResult
        """
        errors = []
        
        if state_count > self._max_states:
            errors.append(
                f"Search has {state_count} states, exceeds limit of {self._max_states}"
            )
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
        )
    
    def check_timeout(self, elapsed_seconds: float) -> bool:
        """Check if planning has exceeded timeout.
        
        Args:
            elapsed_seconds: Time elapsed since planning started
            
        Returns:
            True if timeout exceeded
        """
        return elapsed_seconds >= self._timeout
    
    def get_timeout_remaining(self, elapsed_seconds: float) -> float:
        """Get remaining time before timeout.
        
        Args:
            elapsed_seconds: Time elapsed since planning started
            
        Returns:
            Remaining seconds (0 if already timed out)
        """
        return max(0.0, self._timeout - elapsed_seconds)
    
    def enforce_plan_limit(self, plan: PlanGraph) -> None:
        """Enforce plan limits, raising exception on violation.
        
        Args:
            plan: The plan to validate
            
        Raises:
            PlannerExpansionError: If any limit is exceeded
        """
        result = self.validate_plan(plan)
        
        if not result.is_valid:
            for error in result.errors:
                if "nodes" in error.lower():
                    raise PlannerExpansionError(
                        error, "max_plan_nodes",
                        result.details["node_count"],
                        self._max_nodes,
                    )
                if "branch" in error.lower():
                    raise PlannerExpansionError(
                        error, "max_branch_factor",
                        result.details["max_branch_factor"],
                        self._max_branch,
                    )
                if "depth" in error.lower():
                    raise PlannerExpansionError(
                        error, "max_generation_depth",
                        result.details["max_depth"],
                        self._max_depth,
                    )
    
    def _get_max_branch_factor(self, plan: PlanGraph) -> int:
        """Calculate maximum branch factor in the plan."""
        max_branch = 0
        
        for node in plan.nodes:
            branch_count = len(node.branch_options)
            if branch_count > max_branch:
                max_branch = branch_count
            
            deps_count = len(node.depends_on)
            if deps_count > max_branch:
                max_branch = deps_count
        
        return max_branch
    
    def _get_max_depth(self, plan: PlanGraph) -> int:
        """Calculate maximum depth of the plan tree."""
        if not plan.root_node_id:
            return 0
        
        depths = {plan.root_node_id: 0}
        max_depth = 0
        
        nodes_map = {n.node_id: n for n in plan.nodes}
        
        def calculate_depth(node_id: str, depth: int) -> None:
            nonlocal max_depth
            max_depth = max(max_depth, depth)
            
            node = nodes_map.get(node_id)
            if not node:
                return
            
            for dep in node.depends_on:
                if dep not in depths:
                    depths[dep] = depth + 1
                    calculate_depth(dep, depth + 1)
        
        calculate_depth(plan.root_node_id, 0)
        
        return max_depth
    
    def _has_unreachable_nodes(self, plan: PlanGraph) -> bool:
        """Check if plan has unreachable nodes."""
        if not plan.root_node_id:
            return len(plan.nodes) > 0
        
        reachable = set()
        nodes_map = {n.node_id: n for n in plan.nodes}
        
        def mark_reachable(node_id: str) -> None:
            if node_id in reachable:
                return
            reachable.add(node_id)
            node = nodes_map.get(node_id)
            if node:
                for dep in node.depends_on:
                    mark_reachable(dep)
        
        mark_reachable(plan.root_node_id)
        
        return len(reachable) < len(plan.nodes)
    
    def _has_orphan_nodes(self, plan: PlanGraph) -> bool:
        """Check if plan has orphan nodes (no path to terminal)."""
        if not plan.nodes:
            return False
        
        terminal_nodes = set()
        nodes_map = {n.node_id: n for n in plan.nodes}
        
        for node in plan.nodes:
            is_terminal = True
            for other in plan.nodes:
                if node.node_id in other.depends_on:
                    is_terminal = False
                    break
            if is_terminal:
                terminal_nodes.add(node.node_id)
        
        if not terminal_nodes:
            return len(plan.nodes) > 1
        
        reached_terminal = set()
        
        def can_reach_terminal(node_id: str, visited: set) -> bool:
            if node_id in visited:
                return False
            if node_id in reached_terminal:
                return True
            
            visited.add(node_id)
            
            if node_id in terminal_nodes:
                reached_terminal.add(node_id)
                return True
            
            node = nodes_map.get(node_id)
            if not node:
                return False
            
            for dep in node.depends_on:
                if can_reach_terminal(dep, visited.copy()):
                    return True
            
            return False
        
        for node in plan.nodes:
            if not can_reach_terminal(node.node_id, set()):
                return True
        
        return False


class ExpansionMetrics:
    """Metrics for monitoring plan expansion."""
    
    def __init__(self):
        self._rejections = 0
        self._node_counts = []
        self._depth_counts = []
        self._branch_counts = []
    
    def record_plan(self, plan: PlanGraph) -> None:
        """Record plan metrics."""
        self._node_counts.append(len(plan.nodes))
        
        max_depth = 0
        max_branch = 0
        
        for node in plan.nodes:
            if len(node.depends_on) > max_depth:
                max_depth = len(node.depends_on)
            if len(node.branch_options) > max_branch:
                max_branch = len(node.branch_options)
        
        self._depth_counts.append(max_depth)
        self._branch_counts.append(max_branch)
    
    def record_rejection(self) -> None:
        """Record a plan rejection."""
        self._rejections += 1
    
    def get_stats(self) -> dict:
        """Get expansion statistics."""
        import statistics
        
        return {
            "total_plans": len(self._node_counts),
            "rejections": self._rejections,
            "avg_nodes": statistics.mean(self._node_counts) if self._node_counts else 0,
            "avg_depth": statistics.mean(self._depth_counts) if self._depth_counts else 0,
            "avg_branch_factor": statistics.mean(self._branch_counts) if self._branch_counts else 0,
            "max_nodes_observed": max(self._node_counts) if self._node_counts else 0,
            "max_depth_observed": max(self._depth_counts) if self._depth_counts else 0,
        }
