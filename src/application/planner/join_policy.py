"""Join policy engine for parallel branches - Phase 5B."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .types import JoinPolicy, JoinResult


@dataclass
class BranchResult:
    """Result from a parallel branch execution."""
    branch_id: str
    status: str  # "success", "failed", "skipped"
    result: Any = None
    error: Optional[str] = None
    duration: float = 0.0


class JoinPolicyEngine:
    """Evaluates join conditions for parallel branches.
    
    Supports multiple join policies:
    - ALL_SUCCESS: All branches must succeed
    - ANY_SUCCESS: At least one branch succeeds
    - QUORUM: At least n branches succeed
    - ALL_COMPLETED: All branches complete (use partial results)
    """
    
    async def evaluate_join(
        self,
        join_task_id: str,
        policy: JoinPolicy,
        branch_results: dict[str, BranchResult],
        quorum_count: int = 1,
    ) -> JoinResult:
        """Evaluate a join condition based on policy.
        
        Args:
            join_task_id: The join task identifier
            policy: The join policy to apply
            branch_results: Map of branch_id to BranchResult
            quorum_count: Required count for QUORUM policy
            
        Returns:
            JoinResult indicating whether join can proceed
        """
        if policy == JoinPolicy.ALL_SUCCESS:
            return self._evaluate_all_success(join_task_id, branch_results)
        
        if policy == JoinPolicy.ANY_SUCCESS:
            return self._evaluate_any_success(join_task_id, branch_results)
        
        if policy == JoinPolicy.QUORUM:
            return self._evaluate_quorum(
                join_task_id, branch_results, quorum_count
            )
        
        if policy == JoinPolicy.ALL_COMPLETED:
            return self._evaluate_all_completed(join_task_id, branch_results)
        
        raise ValueError(f"Unknown join policy: {policy}")
    
    def _evaluate_all_success(
        self,
        join_task_id: str,
        branch_results: dict[str, BranchResult],
    ) -> JoinResult:
        """Evaluate ALL_SUCCESS policy.
        
        Proceeds only if all branches succeeded.
        """
        successful = []
        failed = []
        
        for branch_id, result in branch_results.items():
            if result.status == "success":
                successful.append(branch_id)
            elif result.status == "failed":
                failed.append(branch_id)
        
        can_proceed = len(failed) == 0 and len(successful) == len(branch_results)
        
        return JoinResult(
            can_proceed=can_proceed,
            policy=JoinPolicy.ALL_SUCCESS,
            satisfied_branches=successful,
            failed_branches=failed,
        )
    
    def _evaluate_any_success(
        self,
        join_task_id: str,
        branch_results: dict[str, BranchResult],
    ) -> JoinResult:
        """Evaluate ANY_SUCCESS policy.
        
        Proceeds if at least one branch succeeded.
        """
        successful = []
        failed = []
        
        for branch_id, result in branch_results.items():
            if result.status == "success":
                successful.append(branch_id)
            elif result.status == "failed":
                failed.append(branch_id)
        
        can_proceed = len(successful) >= 1
        
        return JoinResult(
            can_proceed=can_proceed,
            policy=JoinPolicy.ANY_SUCCESS,
            satisfied_branches=successful,
            failed_branches=failed,
        )
    
    def _evaluate_quorum(
        self,
        join_task_id: str,
        branch_results: dict[str, BranchResult],
        quorum_count: int,
    ) -> JoinResult:
        """Evaluate QUORUM policy.
        
        Proceeds if at least n branches succeeded.
        """
        successful = []
        failed = []
        
        for branch_id, result in branch_results.items():
            if result.status == "success":
                successful.append(branch_id)
            elif result.status == "failed":
                failed.append(branch_id)
        
        can_proceed = len(successful) >= quorum_count
        
        return JoinResult(
            can_proceed=can_proceed,
            policy=JoinPolicy.QUORUM,
            satisfied_branches=successful,
            failed_branches=failed,
        )
    
    def _evaluate_all_completed(
        self,
        join_task_id: str,
        branch_results: dict[str, BranchResult],
    ) -> JoinResult:
        """Evaluate ALL_COMPLETED policy.
        
        Proceeds when all branches complete (regardless of success).
        Uses partial results if some failed.
        """
        successful = []
        failed = []
        completed = []
        
        for branch_id, result in branch_results.items():
            completed.append(branch_id)
            if result.status == "success":
                successful.append(branch_id)
            elif result.status == "failed":
                failed.append(branch_id)
        
        partial_results = {
            branch_id: result.result
            for branch_id, result in branch_results.items()
            if result.result is not None
        }
        
        can_proceed = len(completed) == len(branch_results)
        
        return JoinResult(
            can_proceed=can_proceed,
            policy=JoinPolicy.ALL_COMPLETED,
            satisfied_branches=successful,
            failed_branches=failed,
            partial_results=partial_results,
        )


class JoinTaskTracker:
    """Tracks parallel branch execution for a join task.
    
    Manages branch state and determines when join
    conditions are satisfied.
    """
    
    def __init__(
        self,
        join_task_id: str,
        branch_ids: list[str],
        policy: JoinPolicy,
        quorum_count: int = 1,
    ):
        self._join_task_id = join_task_id
        self._expected_branches = set(branch_ids)
        self._branch_results: dict[str, BranchResult] = {}
        self._policy = policy
        self._quorum_count = quorum_count
    
    async def record_branch_result(
        self,
        branch_id: str,
        result: BranchResult,
    ) -> None:
        """Record a branch result.
        
        Args:
            branch_id: Branch identifier
            result: The branch execution result
        """
        self._branch_results[branch_id] = result
    
    async def check_join_ready(
        self,
        engine: JoinPolicyEngine,
    ) -> tuple[bool, JoinResult]:
        """Check if join is ready to proceed.
        
        Args:
            engine: The join policy engine
            
        Returns:
            Tuple of (is_ready, join_result)
        """
        if len(self._branch_results) < len(self._expected_branches):
            return False, JoinResult(
                can_proceed=False,
                policy=self._policy,
            )
        
        result = await engine.evaluate_join(
            self._join_task_id,
            self._policy,
            self._branch_results,
            self._quorum_count,
        )
        
        return result.can_proceed, result
    
    async def wait_for_completion(
        self,
        engine: JoinPolicyEngine,
        branch_results_iter,  # Async iterator of BranchResult
        timeout_seconds: Optional[float] = None,
    ) -> JoinResult:
        """Wait for all branches to complete.
        
        Args:
            engine: The join policy engine
            branch_results_iter: Async iterator of branch results
            timeout_seconds: Optional timeout
            
        Returns:
            Final JoinResult
        """
        import asyncio
        start_time = asyncio.get_event_loop().time()
        
        async for branch_id, result in branch_results_iter:
            self._branch_results[branch_id] = result
            
            is_ready, join_result = await self.check_join_ready(engine)
            
            if is_ready:
                return join_result
            
            if timeout_seconds:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= timeout_seconds:
                    return JoinResult(
                        can_proceed=False,
                        policy=self._policy,
                        satisfied_branches=list(self._branch_results.keys()),
                        failed_branches=[],
                    )
        
        return await engine.evaluate_join(
            self._join_task_id,
            self._policy,
            self._branch_results,
            self._quorum_count,
        )
    
    def get_pending_branches(self) -> list[str]:
        """Get list of branches that haven't reported yet."""
        return [
            bid for bid in self._expected_branches
            if bid not in self._branch_results
        ]
    
    def get_completed_branches(self) -> list[str]:
        """Get list of branches that have reported."""
        return list(self._branch_results.keys())


class JoinPolicyFactory:
    """Factory for creating join policies."""
    
    @staticmethod
    def create(
        policy_name: str,
        **kwargs,
    ) -> JoinPolicy:
        """Create a join policy from name.
        
        Args:
            policy_name: Policy name (all_success, any_success, quorum, all_completed)
            **kwargs: Additional policy parameters
            
        Returns:
            JoinPolicy enum value
        """
        policy_map = {
            "all_success": JoinPolicy.ALL_SUCCESS,
            "any_success": JoinPolicy.ANY_SUCCESS,
            "quorum": JoinPolicy.QUORUM,
            "all_completed": JoinPolicy.ALL_COMPLETED,
        }
        
        policy = policy_map.get(policy_name.lower())
        if policy is None:
            raise ValueError(f"Unknown policy: {policy_name}")
        
        return policy
    
    @staticmethod
    def get_default() -> JoinPolicy:
        """Get the default join policy."""
        return JoinPolicy.ALL_SUCCESS
