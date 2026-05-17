"""Semantic plan retrieval with quality filtering - Phase 5B."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .types import PlanGraph, RetrievedPlan


@dataclass
class StoredPlan:
    """Stored plan metadata for retrieval."""
    plan_id: str
    goal_text: str
    plan_graph_data: dict
    quality_score: float
    human_verified: bool
    failure_rate: float
    created_at: int
    completed_at: Optional[int] = None


class PlanHistoryStore:
    """Store interface for plan history."""
    
    async def save(self, plan: StoredPlan) -> None:
        """Save a plan to history."""
        raise NotImplementedError
    
    async def get(self, plan_id: str) -> Optional[StoredPlan]:
        """Get a plan by ID."""
        raise NotImplementedError
    
    async def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[StoredPlan]:
        """Search plans by goal text."""
        raise NotImplementedError
    
    async def get_quality_filtered(
        self,
        min_quality: float,
        max_failure_rate: float,
        require_verified: bool,
        limit: int = 10,
    ) -> list[StoredPlan]:
        """Get plans filtered by quality metrics."""
        raise NotImplementedError


class InMemoryPlanHistoryStore(PlanHistoryStore):
    """In-memory implementation of plan history store."""
    
    def __init__(self):
        self._plans: dict[str, StoredPlan] = {}
    
    async def save(self, plan: StoredPlan) -> None:
        """Save a plan to history."""
        self._plans[plan.plan_id] = plan
    
    async def get(self, plan_id: str) -> Optional[StoredPlan]:
        """Get a plan by ID."""
        return self._plans.get(plan_id)
    
    async def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[StoredPlan]:
        """Search plans by goal text (simple substring match)."""
        query_lower = query.lower()
        matches = [
            p for p in self._plans.values()
            if query_lower in p.goal_text.lower()
        ]
        return sorted(matches, key=lambda p: p.quality_score, reverse=True)[:limit]
    
    async def get_quality_filtered(
        self,
        min_quality: float,
        max_failure_rate: float,
        require_verified: bool,
        limit: int = 10,
    ) -> list[StoredPlan]:
        """Get plans filtered by quality metrics."""
        filtered = []
        
        for plan in self._plans.values():
            if plan.quality_score < min_quality:
                continue
            if plan.failure_rate > max_failure_rate:
                continue
            if require_verified and not plan.human_verified:
                continue
            filtered.append(plan)
        
        return sorted(filtered, key=lambda p: p.quality_score, reverse=True)[:limit]


class SemanticPlanRetriever:
    """Retrieves plans using semantic search with quality filtering.
    
    Implements anti-corruption safeguards to prevent using
    low-quality or unverified plans as templates.
    """
    
    def __init__(
        self,
        store: PlanHistoryStore,
        min_quality_score: float = 0.8,
        require_human_verified: bool = True,
        max_failure_rate: float = 0.2,
    ):
        self._store = store
        self._min_quality = min_quality_score
        self._require_verified = require_human_verified
        self._max_failure_rate = max_failure_rate
    
    async def retrieve_similar(
        self,
        goal: str,
        limit: int = 5,
    ) -> list[RetrievedPlan]:
        """Retrieve similar plans from history.
        
        Only returns plans meeting quality thresholds.
        
        Args:
            goal: Goal text to search for
            limit: Maximum number of plans to return
            
        Returns:
            List of RetrievedPlan objects sorted by quality
        """
        candidates = await self._store.search(goal, limit * 2)
        
        retrieved = []
        for plan in candidates:
            if plan.quality_score < self._min_quality:
                continue
            if plan.failure_rate > self._max_failure_rate:
                continue
            if self._require_verified and not plan.human_verified:
                continue
            
            reliability_weight = 1.0 - plan.failure_rate
            
            retrieved.append(RetrievedPlan(
                plan_id=plan.plan_id,
                goal_text=plan.goal_text,
                plan_graph=self._deserialize_graph(plan.plan_graph_data),
                quality_score=plan.quality_score,
                reliability_weight=reliability_weight,
                human_verified=plan.human_verified,
                failure_rate=plan.failure_rate,
            ))
            
            if len(retrieved) >= limit:
                break
        
        return retrieved
    
    async def retrieve_for_template(
        self,
        goal: str,
    ) -> Optional[RetrievedPlan]:
        """Retrieve the best plan for use as a template.
        
        Returns the highest quality matching plan.
        """
        plans = await self.retrieve_similar(goal, limit=1)
        return plans[0] if plans else None
    
    async def get_plan(self, plan_id: str) -> Optional[RetrievedPlan]:
        """Get a specific plan by ID.
        
        Does not apply quality filtering (plan is already stored).
        """
        plan = await self._store.get(plan_id)
        if not plan:
            return None
        
        reliability_weight = 1.0 - plan.failure_rate
        
        return RetrievedPlan(
            plan_id=plan.plan_id,
            goal_text=plan.goal_text,
            plan_graph=self._deserialize_graph(plan.plan_graph_data),
            quality_score=plan.quality_score,
            reliability_weight=reliability_weight,
            human_verified=plan.human_verified,
            failure_rate=plan.failure_rate,
        )
    
    async def save_plan(
        self,
        plan_id: str,
        goal_text: str,
        plan_graph: PlanGraph,
        quality_score: float,
        human_verified: bool = False,
        failure_rate: float = 0.0,
    ) -> None:
        """Save a plan to history.
        
        Args:
            plan_id: Unique plan identifier
            goal_text: Goal text
            plan_graph: The plan graph
            quality_score: Quality score (0-1)
            human_verified: Whether human verified
            failure_rate: Historical failure rate (0-1)
        """
        stored = StoredPlan(
            plan_id=plan_id,
            goal_text=goal_text,
            plan_graph_data=self._serialize_graph(plan_graph),
            quality_score=quality_score,
            human_verified=human_verified,
            failure_rate=failure_rate,
            created_at=int(datetime.now(timezone.utc).timestamp()),
        )
        
        await self._store.save(stored)
    
    async def update_metrics(
        self,
        plan_id: str,
        success: bool,
    ) -> None:
        """Update failure rate for a plan based on execution result.
        
        This implements exponential moving average for failure rate.
        
        Args:
            plan_id: Plan identifier
            success: Whether execution succeeded
        """
        plan = await self._store.get(plan_id)
        if not plan:
            return
        
        alpha = 0.2
        new_failure = 0.0 if success else 1.0
        plan.failure_rate = alpha * new_failure + (1 - alpha) * plan.failure_rate
        
        await self._store.save(plan)
    
    def _serialize_graph(self, graph: PlanGraph) -> dict:
        """Serialize plan graph to dict."""
        return {
            "plan_id": graph.plan_id,
            "goal": graph.goal,
            "nodes": [
                {
                    "node_id": n.node_id,
                    "task_type": n.task_type,
                    "description": n.description,
                    "depends_on": n.depends_on,
                    "condition_expr": n.condition_expr,
                    "branch_options": n.branch_options,
                    "estimated_cost": n.estimated_cost,
                    "estimated_duration": n.estimated_duration,
                }
                for n in graph.nodes
            ],
            "root_node_id": graph.root_node_id,
        }
    
    def _deserialize_graph(self, data: dict) -> PlanGraph:
        """Deserialize plan graph from dict."""
        from .types import PlanNode
        
        nodes = []
        for node_data in data.get("nodes", []):
            nodes.append(PlanNode(
                node_id=node_data["node_id"],
                task_type=node_data.get("task_type", ""),
                description=node_data.get("description", ""),
                depends_on=node_data.get("depends_on", []),
                condition_expr=node_data.get("condition_expr"),
                branch_options=node_data.get("branch_options", []),
                estimated_cost=node_data.get("estimated_cost", 0.0),
                estimated_duration=node_data.get("estimated_duration", 0.0),
            ))
        
        return PlanGraph(
            plan_id=data["plan_id"],
            goal=data["goal"],
            nodes=nodes,
            root_node_id=data.get("root_node_id"),
        )


class RetrievalMetrics:
    """Metrics for semantic retrieval monitoring."""
    
    def __init__(self):
        self._retrieval_count = 0
        self._cache_hits = 0
        self._total_quality = 0.0
        self._quality_samples = 0
    
    def record_retrieval(self, retrieved_plan: RetrievedPlan) -> None:
        """Record a retrieval event."""
        self._retrieval_count += 1
        self._total_quality += retrieved_plan.quality_score
        self._quality_samples += 1
    
    def record_cache_hit(self) -> None:
        """Record a cache hit."""
        self._cache_hits += 1
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        if self._retrieval_count == 0:
            return 0.0
        return self._cache_hits / self._retrieval_count
    
    @property
    def average_quality(self) -> float:
        """Calculate average retrieval quality."""
        if self._quality_samples == 0:
            return 0.0
        return self._total_quality / self._quality_samples
    
    def get_stats(self) -> dict:
        """Get retrieval statistics."""
        return {
            "retrieval_count": self._retrieval_count,
            "cache_hits": self._cache_hits,
            "hit_rate": self.hit_rate,
            "average_quality": self.average_quality,
            "quality_samples": self._quality_samples,
        }
