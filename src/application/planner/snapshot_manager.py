"""Plan snapshot manager - Phase 5B."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .types import PlanGraph, PlanNode, PlanSnapshot


class PlanSnapshotStore:
    """Store interface for plan snapshots."""
    
    async def save(self, snapshot: PlanSnapshot) -> None:
        """Save a plan snapshot."""
        raise NotImplementedError
    
    async def get(self, plan_id: str) -> Optional[PlanSnapshot]:
        """Get snapshot by plan ID."""
        raise NotImplementedError
    
    async def get_versions(self, plan_id: str) -> list[str]:
        """Get all definition versions for a plan."""
        raise NotImplementedError
    
    async def delete(self, plan_id: str) -> bool:
        """Delete a snapshot."""
        raise NotImplementedError


class InMemoryPlanSnapshotStore(PlanSnapshotStore):
    """In-memory implementation of plan snapshot store."""
    
    def __init__(self):
        self._snapshots: dict[str, PlanSnapshot] = {}
    
    async def save(self, snapshot: PlanSnapshot) -> None:
        """Save a plan snapshot."""
        self._snapshots[snapshot.plan_id] = snapshot
    
    async def get(self, plan_id: str) -> Optional[PlanSnapshot]:
        """Get snapshot by plan ID."""
        return self._snapshots.get(plan_id)
    
    async def get_versions(self, plan_id: str) -> list[str]:
        """Get all definition versions for a plan."""
        snapshot = self._snapshots.get(plan_id)
        if not snapshot:
            return []
        return [snapshot.definition_version]
    
    async def delete(self, plan_id: str) -> bool:
        """Delete a snapshot."""
        if plan_id in self._snapshots:
            del self._snapshots[plan_id]
            return True
        return False


class PlanSnapshotManager:
    """Manages immutable plan snapshots.
    
    Creates and retrieves snapshots that are independent of
    code versions for replay compatibility.
    """
    
    def __init__(self, store: PlanSnapshotStore):
        self._store = store
    
    async def create_snapshot(
        self,
        plan_id: str,
        definition_version: str,
        plan_graph: PlanGraph,
        planner_state: Optional[dict] = None,
    ) -> PlanSnapshot:
        """Create an immutable snapshot of a plan.
        
        Args:
            plan_id: Plan identifier
            definition_version: Plan definition version
            plan_graph: The plan graph to snapshot
            planner_state: Optional planner state
            
        Returns:
            The created snapshot
        """
        snapshot = PlanSnapshot(
            plan_id=plan_id,
            definition_version=definition_version,
            serialized_graph=self._serialize_graph(plan_graph),
            snapshot_events=planner_state or [],
            created_at=int(datetime.now(timezone.utc).timestamp()),
        )
        
        await self._store.save(snapshot)
        
        return snapshot
    
    async def get_snapshot(
        self,
        plan_id: str,
    ) -> Optional[PlanSnapshot]:
        """Get an immutable snapshot by plan ID.
        
        Args:
            plan_id: Plan identifier
            
        Returns:
            The snapshot if exists, None otherwise
        """
        return await self._store.get(plan_id)
    
    async def get_plan_graph(
        self,
        plan_id: str,
    ) -> Optional[PlanGraph]:
        """Get the plan graph from a snapshot.
        
        Args:
            plan_id: Plan identifier
            
        Returns:
            The plan graph if snapshot exists
        """
        snapshot = await self.get_snapshot(plan_id)
        if not snapshot:
            return None
        
        return self._deserialize_graph(snapshot.serialized_graph)
    
    async def update_snapshot(
        self,
        plan_id: str,
        plan_graph: PlanGraph,
    ) -> Optional[PlanSnapshot]:
        """Update an existing snapshot with new graph.
        
        Note: Snapshots are immutable, so this creates a new
        version with incremented version number.
        
        Args:
            plan_id: Plan identifier
            plan_graph: New plan graph
            
        Returns:
            Updated snapshot
        """
        existing = await self.get_snapshot(plan_id)
        
        if not existing:
            return None
        
        parts = existing.definition_version.split(".")
        patch = int(parts[-1]) + 1
        new_version = ".".join(parts[:-1] + [str(patch)])
        
        return await self.create_snapshot(
            plan_id=plan_id,
            definition_version=new_version,
            plan_graph=plan_graph,
            planner_state=existing.snapshot_events,
        )
    
    async def validate_compatibility(
        self,
        plan_id: str,
        current_code_version: str,
    ) -> tuple[bool, Optional[str]]:
        """Check if a snapshot is compatible with current code.
        
        Args:
            plan_id: Plan identifier
            current_code_version: Current code version
            
        Returns:
            Tuple of (compatible, error_message)
        """
        snapshot = await self.get_snapshot(plan_id)
        
        if not snapshot:
            return False, "No snapshot found"
        
        if snapshot.definition_version != current_code_version:
            return True, (
                f"Version mismatch: snapshot is {snapshot.definition_version}, "
                f"code is {current_code_version}. "
                "Replay should still work due to version patching."
            )
        
        return True, None
    
    async def list_snapshots(
        self,
        limit: int = 100,
    ) -> list[PlanSnapshot]:
        """List all snapshots.
        
        Args:
            limit: Maximum number to return
            
        Returns:
            List of snapshots
        """
        if not isinstance(self._store, InMemoryPlanSnapshotStore):
            return []
        
        snapshots = list(self._store._snapshots.values())
        snapshots.sort(key=lambda s: s.created_at, reverse=True)
        
        return snapshots[:limit]
    
    async def delete_snapshot(self, plan_id: str) -> bool:
        """Delete a snapshot.
        
        Args:
            plan_id: Plan identifier
            
        Returns:
            True if deleted
        """
        return await self._store.delete(plan_id)
    
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
                    "input_schema_version": n.input_schema_version,
                    "output_schema_version": n.output_schema_version,
                    "depends_on": n.depends_on,
                    "condition_expr": n.condition_expr,
                    "branch_options": n.branch_options,
                    "join_policy": n.join_policy.value if n.join_policy else None,
                    "retry_config": n.retry_config,
                    "timeout_seconds": n.timeout_seconds,
                    "estimated_cost": n.estimated_cost,
                    "estimated_duration": n.estimated_duration,
                    "metadata": n.metadata,
                }
                for n in graph.nodes
            ],
            "root_node_id": graph.root_node_id,
            "definition_version": graph.definition_version,
            "created_at": graph.created_at,
            "metadata": graph.metadata,
        }
    
    def _deserialize_graph(self, data: dict) -> PlanGraph:
        """Deserialize plan graph from dict."""
        from .types import JoinPolicy
        
        nodes = []
        for node_data in data.get("nodes", []):
            join_policy = None
            if node_data.get("join_policy"):
                try:
                    join_policy = JoinPolicy(node_data["join_policy"])
                except ValueError:
                    pass
            
            nodes.append(PlanNode(
                node_id=node_data["node_id"],
                task_type=node_data.get("task_type", ""),
                description=node_data.get("description", ""),
                input_schema_version=node_data.get("input_schema_version", "1.0"),
                output_schema_version=node_data.get("output_schema_version", "1.0"),
                depends_on=node_data.get("depends_on", []),
                condition_expr=node_data.get("condition_expr"),
                branch_options=node_data.get("branch_options", []),
                join_policy=join_policy,
                retry_config=node_data.get("retry_config"),
                timeout_seconds=node_data.get("timeout_seconds"),
                estimated_cost=node_data.get("estimated_cost", 0.0),
                estimated_duration=node_data.get("estimated_duration", 0.0),
                metadata=node_data.get("metadata", {}),
            ))
        
        return PlanGraph(
            plan_id=data["plan_id"],
            goal=data["goal"],
            nodes=nodes,
            root_node_id=data.get("root_node_id"),
            definition_version=data.get("definition_version", "1.0"),
            created_at=data.get("created_at", 0),
            metadata=data.get("metadata", {}),
        )


class SnapshotValidator:
    """Validates plan snapshots for integrity."""
    
    def validate(self, snapshot: PlanSnapshot) -> tuple[bool, list[str]]:
        """Validate snapshot integrity.
        
        Args:
            snapshot: Snapshot to validate
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        if not snapshot.plan_id:
            errors.append("Missing plan_id")
        
        if not snapshot.definition_version:
            errors.append("Missing definition_version")
        
        if not snapshot.serialized_graph:
            errors.append("Missing serialized_graph")
        else:
            if "plan_id" not in snapshot.serialized_graph:
                errors.append("Missing plan_id in serialized_graph")
            if "nodes" not in snapshot.serialized_graph:
                errors.append("Missing nodes in serialized_graph")
        
        if snapshot.created_at <= 0:
            errors.append("Invalid created_at timestamp")
        
        return len(errors) == 0, errors
