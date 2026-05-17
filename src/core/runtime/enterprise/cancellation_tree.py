"""Cancellation tree with policies - Phase 5B v10.

Implements cancellation with different policies:
- CASCADE: Cancel all sub-workflows and activities
- DETACH: Only cancel current workflow
- GRACEFUL: Wait for current activities to complete
- FORCE: Immediate termination
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable


class CancellationPolicy(Enum):
    """Policy for workflow cancellation."""
    CASCADE = "cascade"
    DETACH = "detach"
    GRACEFUL = "graceful"
    FORCE = "force"


class CancellationStatus(Enum):
    """Status of a cancellation request."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class CancellationRequest:
    """Request for workflow cancellation."""
    request_id: str
    workflow_id: str
    policy: CancellationPolicy
    reason: str
    initiated_by: str
    initiated_at: int = field(default_factory=lambda: int(time.time()))
    completed_at: Optional[int] = None
    status: CancellationStatus = CancellationStatus.PENDING


@dataclass
class CancellationResult:
    """Result of a cancellation operation."""
    success: bool
    cancelled_workflows: list[str] = field(default_factory=list)
    cancelled_activities: list[str] = field(default_factory=list)
    pending_cancellations: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class CancellationNode:
    """Node in the cancellation tree."""
    
    def __init__(
        self,
        workflow_id: str,
        child_ids: list[str] = None,
    ):
        self.workflow_id = workflow_id
        self.child_ids: list[str] = child_ids or []
        self.activity_ids: list[str] = []
        self.cancelled: bool = False
    
    def add_child(self, workflow_id: str) -> None:
        """Add a child workflow to this node."""
        if workflow_id not in self.child_ids:
            self.child_ids.append(workflow_id)
    
    def add_activity(self, activity_id: str) -> None:
        """Add an activity to this node."""
        if activity_id not in self.activity_ids:
            self.activity_ids.append(activity_id)


class CancellationTree:
    """Tree structure for tracking cancellation hierarchy."""
    
    def __init__(self, root_workflow_id: str):
        self._nodes: dict[str, CancellationNode] = {}
        self._root = root_workflow_id
        self._nodes[root_workflow_id] = CancellationNode(root_workflow_id)
    
    def add_workflow(
        self,
        parent_id: str,
        workflow_id: str,
    ) -> None:
        """Add a child workflow to the tree."""
        if parent_id not in self._nodes:
            self._nodes[parent_id] = CancellationNode(parent_id)
        
        if workflow_id not in self._nodes:
            self._nodes[workflow_id] = CancellationNode(workflow_id)
        
        self._nodes[parent_id].add_child(workflow_id)
    
    def add_activity(
        self,
        workflow_id: str,
        activity_id: str,
    ) -> None:
        """Add an activity to a workflow node."""
        if workflow_id not in self._nodes:
            self._nodes[workflow_id] = CancellationNode(workflow_id)
        
        self._nodes[workflow_id].add_activity(activity_id)
    
    def get_all_workflows(self) -> list[str]:
        """Get all workflow IDs in the tree."""
        return list(self._nodes.keys())
    
    def get_leaf_workflows(self) -> list[str]:
        """Get all leaf workflow IDs (no children)."""
        return [
            wf_id for wf_id, node in self._nodes.items()
            if not node.child_ids
        ]
    
    def get_root(self) -> str:
        """Get the root workflow ID."""
        return self._root
    
    def mark_cancelled(self, workflow_id: str) -> None:
        """Mark a workflow as cancelled."""
        if workflow_id in self._nodes:
            self._nodes[workflow_id].cancelled = True
    
    def is_cancelled(self, workflow_id: str) -> bool:
        """Check if a workflow is cancelled."""
        return self._nodes.get(workflow_id, CancellationNode("")).cancelled
    
    def get_cancellation_order(self, policy: CancellationPolicy) -> list[str]:
        """Get the order in which to cancel workflows.
        
        For CASCADE: deepest first (bottom-up)
        For DETACH: only root
        """
        if policy == CancellationPolicy.DETACH:
            return [self._root]
        
        if policy == CancellationPolicy.CASCADE:
            return self._get_bottom_up_order()
        
        if policy == CancellationPolicy.GRACEFUL:
            return self._get_graceful_order()
        
        if policy == CancellationPolicy.FORCE:
            return list(self._nodes.keys())
        
        return [self._root]
    
    def _get_bottom_up_order(self) -> list[str]:
        """Get cancellation order bottom-up."""
        result = []
        
        def traverse(wf_id: str, visited: set) -> None:
            if wf_id in visited:
                return
            visited.add(wf_id)
            
            node = self._nodes.get(wf_id)
            if node:
                for child_id in node.child_ids:
                    traverse(child_id, visited)
            
            result.append(wf_id)
        
        visited = set()
        traverse(self._root, visited)
        
        return result
    
    def _get_graceful_order(self) -> list[str]:
        """Get cancellation order for graceful shutdown."""
        leaves = self.get_leaf_workflows()
        return leaves + [self._root]


class CancellationExecutor:
    """Executes cancellation with different policies.
    
    Coordinates the cancellation of workflows, sub-workflows,
    and activities according to the specified policy.
    """
    
    def __init__(
        self,
        send_signal_fn: Optional[Callable] = None,
        cancel_activity_fn: Optional[Callable] = None,
        graceful_timeout_seconds: float = 60.0,
    ):
        self._send_signal = send_signal_fn
        self._cancel_activity = cancel_activity_fn
        self._graceful_timeout = graceful_timeout_seconds
    
    async def execute(
        self,
        request: CancellationRequest,
        tree: CancellationTree,
    ) -> CancellationResult:
        """Execute cancellation according to policy.
        
        Args:
            request: Cancellation request
            tree: Cancellation tree
            
        Returns:
            Result of cancellation
        """
        if request.policy == CancellationPolicy.CASCADE:
            return await self._execute_cascade(request, tree)
        elif request.policy == CancellationPolicy.DETACH:
            return await self._execute_detach(request, tree)
        elif request.policy == CancellationPolicy.GRACEFUL:
            return await self._execute_graceful(request, tree)
        elif request.policy == CancellationPolicy.FORCE:
            return await self._execute_force(request, tree)
        else:
            return CancellationResult(success=False, errors=["Unknown policy"])
    
    async def _execute_cascade(
        self,
        request: CancellationRequest,
        tree: CancellationTree,
    ) -> CancellationResult:
        """Execute cascade cancellation (cancel everything)."""
        result = CancellationResult(success=True)
        order = tree.get_cancellation_order(CancellationPolicy.CASCADE)
        
        for workflow_id in order:
            node = tree._nodes.get(workflow_id)
            if not node:
                continue
            
            if self._send_signal:
                try:
                    await self._send_signal(workflow_id, "cancel", {"reason": request.reason})
                    result.cancelled_workflows.append(workflow_id)
                except Exception as e:
                    result.errors.append(f"{workflow_id}: {str(e)}")
            
            for activity_id in node.activity_ids:
                if self._cancel_activity:
                    try:
                        await self._cancel_activity(activity_id)
                        result.cancelled_activities.append(activity_id)
                    except Exception as e:
                        result.errors.append(f"Activity {activity_id}: {str(e)}")
        
        return result
    
    async def _execute_detach(
        self,
        request: CancellationRequest,
        tree: CancellationTree,
    ) -> CancellationResult:
        """Execute detach cancellation (only current workflow)."""
        result = CancellationResult(success=True)
        
        if self._send_signal:
            try:
                await self._send_signal(request.workflow_id, "cancel", {"reason": request.reason})
                result.cancelled_workflows.append(request.workflow_id)
            except Exception as e:
                result.success = False
                result.errors.append(str(e))
        
        return result
    
    async def _execute_graceful(
        self,
        request: CancellationRequest,
        tree: CancellationTree,
    ) -> CancellationResult:
        """Execute graceful cancellation (wait for activities)."""
        result = CancellationResult(success=True)
        
        if self._send_signal:
            try:
                await self._send_signal(
                    request.workflow_id,
                    "graceful_cancel",
                    {"reason": request.reason, "timeout": self._graceful_timeout}
                )
                result.cancelled_workflows.append(request.workflow_id)
            except Exception as e:
                result.errors.append(str(e))
        
        result.pending_cancellations = tree.get_leaf_workflows()
        
        return result
    
    async def _execute_force(
        self,
        request: CancellationRequest,
        tree: CancellationTree,
    ) -> CancellationResult:
        """Execute force cancellation (immediate termination)."""
        result = CancellationResult(success=True)
        
        for workflow_id in tree.get_all_workflows():
            node = tree._nodes.get(workflow_id)
            if not node:
                continue
            
            if self._send_signal:
                try:
                    await self._send_signal(workflow_id, "force_cancel", {"reason": request.reason})
                    result.cancelled_workflows.append(workflow_id)
                except Exception as e:
                    result.errors.append(f"{workflow_id}: {str(e)}")
            
            for activity_id in node.activity_ids:
                if self._cancel_activity:
                    try:
                        await self._cancel_activity(activity_id, force=True)
                        result.cancelled_activities.append(activity_id)
                    except Exception as e:
                        result.errors.append(f"Activity {activity_id}: {str(e)}")
        
        return result


class CancellationManager:
    """Manages workflow cancellation lifecycle."""
    
    def __init__(
        self,
        executor: CancellationExecutor,
        default_policy: CancellationPolicy = CancellationPolicy.CASCADE,
    ):
        self._executor = executor
        self._default_policy = default_policy
        self._pending: dict[str, CancellationRequest] = {}
        self._results: dict[str, CancellationResult] = {}
    
    async def request_cancellation(
        self,
        workflow_id: str,
        reason: str,
        initiated_by: str,
        policy: Optional[CancellationPolicy] = None,
    ) -> CancellationRequest:
        """Request cancellation of a workflow.
        
        Args:
            workflow_id: Workflow to cancel
            reason: Reason for cancellation
            initiated_by: Who initiated the cancellation
            policy: Cancellation policy
            
        Returns:
            Cancellation request
        """
        import uuid
        
        request = CancellationRequest(
            request_id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            policy=policy or self._default_policy,
            reason=reason,
            initiated_by=initiated_by,
        )
        
        self._pending[workflow_id] = request
        return request
    
    async def execute_request(
        self,
        request: CancellationRequest,
        tree: CancellationTree,
    ) -> CancellationResult:
        """Execute a cancellation request.
        
        Args:
            request: Cancellation request
            tree: Cancellation tree
            
        Returns:
            Cancellation result
        """
        request.status = CancellationStatus.IN_PROGRESS
        
        result = await self._executor.execute(request, tree)
        
        if result.success:
            request.status = CancellationStatus.COMPLETED
        else:
            request.status = CancellationStatus.FAILED
        
        request.completed_at = int(time.time())
        self._results[request.request_id] = result
        
        return result
    
    def get_pending_cancellations(self) -> list[CancellationRequest]:
        """Get all pending cancellation requests."""
        return list(self._pending.values())
    
    def get_result(self, request_id: str) -> Optional[CancellationResult]:
        """Get result of a cancellation."""
        return self._results.get(request_id)
