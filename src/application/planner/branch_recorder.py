"""Branch decision recording for deterministic replay - Phase 5B."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .types import BranchDecision


class BranchDecisionStore:
    """Store interface for branch decisions."""
    
    async def save(self, decision: BranchDecision) -> None:
        """Save a branch decision."""
        raise NotImplementedError
    
    async def get(
        self,
        workflow_id: str,
        task_id: str,
    ) -> Optional[BranchDecision]:
        """Get a branch decision by workflow and task."""
        raise NotImplementedError
    
    async def get_all_for_workflow(
        self,
        workflow_id: str,
    ) -> list[BranchDecision]:
        """Get all branch decisions for a workflow."""
        raise NotImplementedError


class InMemoryBranchDecisionStore(BranchDecisionStore):
    """In-memory implementation of branch decision store."""
    
    def __init__(self):
        self._decisions: dict[tuple[str, str], BranchDecision] = {}
    
    async def save(self, decision: BranchDecision) -> None:
        """Save a branch decision."""
        key = (decision.workflow_id, decision.task_id)
        self._decisions[key] = decision
    
    async def get(
        self,
        workflow_id: str,
        task_id: str,
    ) -> Optional[BranchDecision]:
        """Get a branch decision."""
        key = (workflow_id, task_id)
        return self._decisions.get(key)
    
    async def get_all_for_workflow(
        self,
        workflow_id: str,
    ) -> list[BranchDecision]:
        """Get all branch decisions for a workflow."""
        return [
            d for key, d in self._decisions.items()
            if key[0] == workflow_id
        ]


class BranchDecisionRecorder:
    """Records and retrieves branch decisions for deterministic replay.
    
    This component ensures that when a plan is replayed, the same
    branch decisions are made without re-evaluating conditions.
    """
    
    def __init__(self, store: BranchDecisionStore):
        self._store = store
    
    async def record(
        self,
        workflow_id: str,
        task_id: str,
        selected_branch: str,
        condition_expr: str,
    ) -> BranchDecision:
        """Record a branch decision.
        
        Args:
            workflow_id: Workflow identifier
            task_id: Task identifier with the branch
            selected_branch: The branch that was selected
            condition_expr: The original condition expression
            
        Returns:
            The recorded BranchDecision
        """
        decision = BranchDecision(
            workflow_id=workflow_id,
            task_id=task_id,
            selected_branch=selected_branch,
            evaluated_at=int(datetime.utcnow().timestamp()),
            condition_expr=condition_expr,
        )
        
        await self._store.save(decision)
        
        return decision
    
    async def get_decision(
        self,
        workflow_id: str,
        task_id: str,
    ) -> Optional[BranchDecision]:
        """Get a recorded branch decision for replay.
        
        Args:
            workflow_id: Workflow identifier
            task_id: Task identifier
            
        Returns:
            The recorded decision if exists, None otherwise
        """
        return await self._store.get(workflow_id, task_id)
    
    async def has_decision(
        self,
        workflow_id: str,
        task_id: str,
    ) -> bool:
        """Check if a branch decision exists.
        
        Args:
            workflow_id: Workflow identifier
            task_id: Task identifier
            
        Returns:
            True if decision exists
        """
        decision = await self._store.get(workflow_id, task_id)
        return decision is not None
    
    async def get_all_for_workflow(
        self,
        workflow_id: str,
    ) -> list[BranchDecision]:
        """Get all recorded decisions for a workflow.
        
        Useful for audit and debugging.
        """
        return await self._store.get_all_for_workflow(workflow_id)
    
    async def replay_decision(
        self,
        workflow_id: str,
        task_id: str,
    ) -> Optional[str]:
        """Get branch for replay - returns None if not recorded.
        
        This is used during replay to retrieve the recorded branch
        without re-evaluating the condition.
        
        Args:
            workflow_id: Workflow identifier
            task_id: Task identifier
            
        Returns:
            The selected branch name if recorded, None otherwise
        """
        decision = await self._store.get(workflow_id, task_id)
        if decision:
            return decision.selected_branch
        return None


class ReplayDecisionResolver:
    """Resolves branch decisions during plan replay.
    
    This component is used during replay to decide whether to
    use a recorded decision or evaluate the condition fresh.
    """
    
    def __init__(
        self,
        recorder: BranchDecisionRecorder,
        condition_evaluator,  # ConditionEvaluator
    ):
        self._recorder = recorder
        self._evaluator = condition_evaluator
    
    async def resolve_branch(
        self,
        workflow_id: str,
        task_id: str,
        condition_expr: str,
        branch_options: list[str],
        context: dict,
        is_replay: bool = False,
    ) -> tuple[Optional[str], bool]:
        """Resolve which branch to take.
        
        Args:
            workflow_id: Workflow identifier
            task_id: Task identifier
            condition_expr: The condition expression
            branch_options: Available branch options
            context: Evaluation context
            is_replay: Whether this is a replay
            
        Returns:
            Tuple of (selected_branch, was_recorded).
            If was_recorded is True, the branch came from the decision log.
            If was_recorded is False, it was freshly evaluated.
        """
        if is_replay:
            recorded = await self._recorder.replay_decision(
                workflow_id, task_id
            )
            if recorded:
                return recorded, True
        
        result, error = self._evaluator.evaluate(condition_expr, context)
        
        if error:
            raise ValueError(f"Condition evaluation failed: {error}")
        
        selected = self._select_branch(result, branch_options)
        
        await self._recorder.record(
            workflow_id=workflow_id,
            task_id=task_id,
            selected_branch=selected,
            condition_expr=condition_expr,
        )
        
        return selected, False
    
    def _select_branch(
        self,
        condition_result: bool,
        branch_options: list[str],
    ) -> str:
        """Select branch based on condition result.
        
        Assumes first branch is for True, second is for False.
        """
        if condition_result:
            return branch_options[0] if branch_options else "true_branch"
        else:
            return branch_options[1] if len(branch_options) > 1 else "false_branch"
