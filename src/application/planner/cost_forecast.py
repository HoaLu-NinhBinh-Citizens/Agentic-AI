"""Cost forecast engine - Phase 5B."""

from __future__ import annotations

from typing import Optional

from .types import CostForecastReport, PlanGraph, PlanNode


class CostForecastEngine:
    """Estimates cost and duration for plan execution.
    
    Provides correlation-aware cost forecasting with explicit
    independence assumptions documented in the report.
    """
    
    INDEPENDENCE_DISCLAIMER = (
        "Giả định các task duration độc lập. "
        "Trong thực tế, có thể có correlation do network, provider. "
        "Hỗ trợ covariance sẽ có trong Phase 5C."
    )
    
    def __init__(self, disclaimer_in_report: bool = True):
        self._disclaimer = disclaimer_in_report
    
    async def forecast(
        self,
        plan: PlanGraph,
        historical_data: Optional[dict] = None,
    ) -> CostForecastReport:
        """Generate cost forecast for a plan.
        
        Args:
            plan: The plan to forecast
            historical_data: Optional historical performance data
            
        Returns:
            CostForecastReport with estimates and disclaimer
        """
        task_costs = self._calculate_task_costs(plan)
        
        critical_path = self._find_critical_path(plan)
        
        total_cost = sum(task_costs.values())
        
        estimated_duration = self._estimate_duration(plan, critical_path)
        
        covariance_available = historical_data is not None
        covariance_matrix = None
        
        if historical_data and "covariance_matrix" in historical_data:
            covariance_matrix = historical_data["covariance_matrix"]
        
        return CostForecastReport(
            total_cost=total_cost,
            task_costs=task_costs,
            critical_path=critical_path,
            estimated_duration=estimated_duration,
            independence_disclaimer=self.INDEPENDENCE_DISCLAIMER if self._disclaimer else "",
            covariance_available=covariance_available,
            covariance_matrix=covariance_matrix,
        )
    
    def _calculate_task_costs(self, plan: PlanGraph) -> dict[str, float]:
        """Calculate estimated cost for each task."""
        costs = {}
        
        for node in plan.nodes:
            if node.estimated_cost > 0:
                costs[node.node_id] = node.estimated_cost
            else:
                costs[node.node_id] = self._estimate_node_cost(node)
        
        return costs
    
    def _estimate_node_cost(self, node: PlanNode) -> float:
        """Estimate cost for a node based on its properties."""
        base_cost = 1.0
        
        if node.task_type == "activity":
            base_cost = 2.0
        elif node.task_type == "workflow":
            base_cost = 5.0
        elif node.task_type == "subprocess":
            base_cost = 3.0
        
        complexity_factor = 1.0 + (len(node.depends_on) * 0.1)
        
        if node.branch_options:
            complexity_factor *= 1.0 + (len(node.branch_options) * 0.2)
        
        if node.retry_config:
            retry_count = node.retry_config.get("max_attempts", 1)
            complexity_factor *= 1.0 + (retry_count * 0.1)
        
        return base_cost * complexity_factor
    
    def _find_critical_path(self, plan: PlanGraph) -> list[str]:
        """Find the critical path through the plan.
        
        Returns list of node IDs on the critical path.
        """
        if not plan.nodes or not plan.root_node_id:
            return []
        
        nodes_map = {n.node_id: n for n in plan.nodes}
        
        durations = {}
        predecessors = {}
        
        def calculate_earliest(node_id: str) -> float:
            if node_id in durations:
                return durations[node_id]
            
            node = nodes_map.get(node_id)
            if not node:
                durations[node_id] = 0.0
                return 0.0
            
            if not node.depends_on:
                duration = node.estimated_duration or 1.0
                durations[node_id] = duration
                return duration
            
            max_pred_duration = 0.0
            for dep_id in node.depends_on:
                dep_duration = calculate_earliest(dep_id)
                if dep_duration > max_pred_duration:
                    max_pred_duration = dep_duration
                    predecessors[node_id] = dep_id
            
            duration = max_pred_duration + (node.estimated_duration or 1.0)
            durations[node_id] = duration
            
            return duration
        
        for node in plan.nodes:
            calculate_earliest(node.node_id)
        
        max_duration = 0.0
        end_node = None
        
        for node_id, duration in durations.items():
            if duration > max_duration:
                max_duration = duration
                end_node = node_id
        
        critical_path = []
        current = end_node
        
        while current:
            critical_path.insert(0, current)
            current = predecessors.get(current)
        
        return critical_path
    
    def _estimate_duration(
        self,
        plan: PlanGraph,
        critical_path: list[str],
    ) -> float:
        """Estimate total plan duration based on critical path."""
        if not critical_path:
            return sum(n.estimated_duration or 1.0 for n in plan.nodes)
        
        nodes_map = {n.node_id: n for n in plan.nodes}
        
        total = 0.0
        for node_id in critical_path:
            node = nodes_map.get(node_id)
            if node:
                total += node.estimated_duration or 1.0
        
        return total
    
    async def forecast_with_parallelism(
        self,
        plan: PlanGraph,
        parallel_limit: int = 10,
    ) -> CostForecastReport:
        """Generate forecast accounting for parallel execution.
        
        Args:
            plan: The plan to forecast
            parallel_limit: Maximum parallel tasks
            
        Returns:
            CostForecastReport with parallelization factored in
        """
        base_report = await self.forecast(plan)
        
        parallel_groups = self._find_parallel_groups(plan, parallel_limit)
        
        if not parallel_groups:
            return base_report
        
        sequential_duration = base_report.estimated_duration
        
        parallel_duration = 0.0
        for group in parallel_groups:
            max_in_group = max(
                base_report.task_costs.get(nid, 1.0)
                for nid in group
            )
            parallel_duration += max_in_group
        
        speedup = sequential_duration / max(parallel_duration, 0.001)
        
        adjusted_report = CostForecastReport(
            total_cost=base_report.total_cost,
            task_costs=base_report.task_costs,
            critical_path=base_report.critical_path,
            estimated_duration=parallel_duration,
            independence_disclaimer=base_report.independence_disclaimer,
            covariance_available=base_report.covariance_available,
            covariance_matrix=base_report.covariance_matrix,
        )
        
        return adjusted_report
    
    def _find_parallel_groups(
        self,
        plan: PlanGraph,
        limit: int,
    ) -> list[list[str]]:
        """Find groups of tasks that can run in parallel."""
        if not plan.root_node_id:
            return []
        
        nodes_map = {n.node_id: n for n in plan.nodes}
        
        levels = {}
        
        def assign_level(node_id: str, depth: int) -> None:
            if node_id in levels:
                if depth > levels[node_id]:
                    levels[node_id] = depth
            else:
                levels[node_id] = depth
            
            node = nodes_map.get(node_id)
            if node:
                for dep_id in node.depends_on:
                    assign_level(dep_id, depth + 1)
        
        assign_level(plan.root_node_id, 0)
        
        level_groups = {}
        for node_id, depth in levels.items():
            if depth not in level_groups:
                level_groups[depth] = []
            level_groups[depth].append(node_id)
        
        return list(level_groups.values())


class HistoricalCostAnalyzer:
    """Analyzes historical cost data for better forecasting."""
    
    def __init__(self):
        self._historical: list[dict] = []
    
    def add_observation(
        self,
        plan_id: str,
        actual_cost: float,
        actual_duration: float,
        task_costs: dict[str, float],
    ) -> None:
        """Add a historical observation.
        
        Args:
            plan_id: Plan identifier
            actual_cost: Actual total cost
            actual_duration: Actual duration
            task_costs: Per-task actual costs
        """
        self._historical.append({
            "plan_id": plan_id,
            "actual_cost": actual_cost,
            "actual_duration": actual_duration,
            "task_costs": task_costs,
        })
    
    def calculate_adjustments(self) -> dict[str, float]:
        """Calculate cost adjustment factors based on history.
        
        Returns:
            Dictionary of node_id to adjustment factor
        """
        if len(self._historical) < 3:
            return {}
        
        adjustments = {}
        
        total_cost_ratio = 0.0
        count = 0
        
        for obs in self._historical:
            for node_id, actual_cost in obs["task_costs"].items():
                estimated = obs["task_costs"].get(node_id, 0)
                if estimated > 0:
                    ratio = actual_cost / estimated
                    total_cost_ratio += ratio
                    count += 1
        
        if count > 0:
            avg_ratio = total_cost_ratio / count
            adjustments["_global"] = avg_ratio
        
        return adjustments
    
    def estimate_covariance(self) -> dict:
        """Estimate covariance matrix from historical data.
        
        Returns:
            Covariance matrix (placeholder for Phase 5C)
        """
        return {
            "note": "Covariance estimation available in Phase 5C",
            "sample_size": len(self._historical),
        }
