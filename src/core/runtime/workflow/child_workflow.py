"""Child Workflow Manager with ParentClosePolicy - Phase 5A (v6).

Manages child workflows with configurable close policies.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Optional
from dataclasses import dataclass, field

from .types import (
    ChildWorkflow,
    WorkflowInstance,
    WorkflowStatus,
    ParentClosePolicy,
)

logger = logging.getLogger(__name__)


class ClosePolicy:
    """Parent close policy constants."""
    TERMINATE = ParentClosePolicy.TERMINATE
    ABANDON = ParentClosePolicy.ABANDON
    REQUEST_CANCEL = ParentClosePolicy.REQUEST_CANCEL


class ChildWorkflowManager:
    """Manages child workflow lifecycle with parent close policy.
    
    Features:
    - Create child workflows
    - Track parent-child relationships
    - Enforce close policies
    - Handle orphan detection
    - Cancellation propagation
    - Compensation during cancellation
    """
    
    # Cancellation timeout
    DEFAULT_CANCEL_TIMEOUT_SECONDS = 10.0
    ESCALATION_WARNING_SECONDS = 5.0

    def __init__(
        self,
        child_store: "ChildWorkflowStore",
        workflow_runtime: Optional[Any] = None,
        cancellation_timeout_seconds: float = DEFAULT_CANCEL_TIMEOUT_SECONDS,
    ):
        self._store = child_store
        self._runtime = workflow_runtime
        self._awaiters: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()
        self._cancellation_timeout = cancellation_timeout_seconds
        self._pending_cancellations: dict[str, asyncio.Task] = {}

    async def start_child(
        self,
        parent: WorkflowInstance,
        child_workflow_type: str,
        input: dict,
        policy: ParentClosePolicy = ParentClosePolicy.TERMINATE,
        idempotency_key: Optional[str] = None,
    ) -> str:
        """Start a child workflow.
        
        Args:
            parent: Parent workflow instance.
            child_workflow_type: Type name of child workflow.
            input: Input for child workflow.
            policy: Close policy when parent terminates.
            idempotency_key: Optional idempotency key.
            
        Returns:
            Child workflow ID.
        """
        child_id = idempotency_key or str(uuid.uuid4())

        # Check if already exists (idempotent start)
        existing = await self._store.get_by_idempotency(child_id)
        if existing:
            logger.info(f"Child workflow {child_id} already exists (idempotent)")
            return existing.child_id

        child = ChildWorkflow(
            child_id=child_id,
            parent_workflow_id=parent.workflow_id,
            workflow_type=child_workflow_type,
            close_policy=policy,
            input=input,
        )

        await self._store.save(child)

        # Create future for awaiting parent
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        async with self._lock:
            self._awaiters[child_id] = future

        # Submit to runtime
        if self._runtime:
            await self._runtime.start_workflow(
                workflow_type=child_workflow_type,
                input=input,
                workflow_id=child_id,
                parent_workflow_id=parent.workflow_id,
            )

        logger.info(
            f"Started child workflow {child_id} "
            f"(parent={parent.workflow_id[:8]}..., policy={policy.value})"
        )

        return child_id

    async def wait_for_child(self, child_id: str) -> Any:
        """Wait for child workflow to complete.
        
        Args:
            child_id: Child workflow ID.
            
        Returns:
            Child workflow result.
        """
        async with self._lock:
            future = self._awaiters.get(child_id)
        
        if not future:
            child = await self._store.get_by_id(child_id)
            if child and child.status in {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED}:
                if child.status == WorkflowStatus.COMPLETED:
                    return child.result
                else:
                    raise ChildWorkflowError(f"Child {child_id} failed: {child.error}")
            raise ValueError(f"Unknown child workflow: {child_id}")
        
        return await future

    async def on_child_complete(self, child_id: str, result: Any) -> None:
        """Called when child workflow completes.
        
        Args:
            child_id: Child workflow ID.
            result: Child workflow result.
        """
        child = await self._store.get_by_id(child_id)
        if child:
            child.status = WorkflowStatus.COMPLETED
            child.result = result
            child.completed_at = time.time()
            await self._store.save(child)

        # Notify waiting parent
        async with self._lock:
            future = self._awaiters.pop(child_id, None)
        
        if future and not future.done():
            future.set_result(result)

    async def on_child_fail(self, child_id: str, error: str) -> None:
        """Called when child workflow fails.
        
        Args:
            child_id: Child workflow ID.
            error: Error message.
        """
        child = await self._store.get_by_id(child_id)
        if child:
            child.status = WorkflowStatus.FAILED
            child.error = error
            child.completed_at = time.time()
            await self._store.save(child)

        # Notify waiting parent with error
        async with self._lock:
            future = self._awaiters.pop(child_id, None)
        
        if future and not future.done():
            future.set_exception(ChildWorkflowError(f"Child {child_id} failed: {error}"))

    async def on_parent_close(
        self,
        parent: WorkflowInstance,
        close_type: WorkflowStatus,
    ) -> None:
        """Handle parent workflow close according to policies.
        
        Args:
            parent: Parent workflow that closed.
            close_type: How parent closed (completed, failed, cancelled, terminated).
        """
        children = await self._store.get_by_parent(parent.workflow_id)
        
        for child in children:
            if child.status != WorkflowStatus.RUNNING:
                continue

            policy = child.close_policy

            if policy == ParentClosePolicy.TERMINATE:
                await self._terminate_child(child, parent, close_type)
            
            elif policy == ParentClosePolicy.ABANDON:
                await self._abandon_child(child, parent)
            
            elif policy == ParentClosePolicy.REQUEST_CANCEL:
                await self._request_cancel_child(child, parent)

    async def _terminate_child(
        self,
        child: ChildWorkflow,
        parent: WorkflowInstance,
        close_type: WorkflowStatus,
    ) -> None:
        """Terminate child immediately."""
        logger.warning(
            f"Terminating child {child.child_id} "
            f"(parent {parent.workflow_id[:8]}... {close_type.value})"
        )
        
        if self._runtime:
            await self._runtime.terminate_workflow(child.child_id)
        
        child.status = WorkflowStatus.TERMINATED
        child.error = f"Parent {close_type.value}"
        child.completed_at = time.time()
        await self._store.save(child)

    async def _abandon_child(
        self,
        child: ChildWorkflow,
        parent: WorkflowInstance,
    ) -> None:
        """Leave child to run independently."""
        logger.info(
            f"Abandoning child {child.child_id} "
            f"(parent {parent.workflow_id[:8]}... completed)"
        )
        
        # Detach from parent
        child.parent_workflow_id = None
        await self._store.save(child)

    async def _request_cancel_child(
        self,
        child: ChildWorkflow,
        parent: WorkflowInstance,
    ) -> None:
        """Send cancellation signal to child."""
        logger.info(
            f"Requesting cancel for child {child.child_id} "
            f"(parent {parent.workflow_id[:8]}...)"
        )
        
        if self._runtime:
            await self._runtime.cancel_workflow(child.child_id)

    async def get_children(self, parent_id: str) -> list[ChildWorkflow]:
        """Get all children of a workflow."""
        return await self._store.get_by_parent(parent_id)

    async def get_child(self, child_id: str) -> Optional[ChildWorkflow]:
        """Get a child workflow by ID."""
        return await self._store.get_by_id(child_id)

    async def propagate_cancellation(
        self,
        parent_id: str,
        reason: str = "",
    ) -> dict[str, bool]:
        """Propagate cancellation to all child workflows.
        
        Args:
            parent_id: Parent workflow ID being cancelled.
            reason: Cancellation reason.
            
        Returns:
            Dict mapping child_id to cancellation success.
        """
        children = await self._store.get_by_parent(parent_id)
        results = {}
        
        for child in children:
            if child.status == WorkflowStatus.RUNNING:
                success = await self._cancel_child_with_escalation(child, reason)
                results[child.child_id] = success
        
        return results

    async def _cancel_child_with_escalation(
        self,
        child: ChildWorkflow,
        reason: str,
    ) -> bool:
        """Cancel child with timeout escalation.
        
        Cancellation is cooperative. If child doesn't respond within
        timeout, force termination.
        """
        # Start cooperative cancellation
        cancel_task = asyncio.create_task(
            self._request_cancel_child(child, child.parent_workflow_id)
        )
        
        # Track cancellation
        self._pending_cancellations[child.child_id] = cancel_task
        
        try:
            # Wait for cancellation with timeout
            await asyncio.wait_for(
                cancel_task,
                timeout=self._cancellation_timeout,
            )
            return True
            
        except asyncio.TimeoutError:
            # Escalation: force terminate after timeout
            logger.warning(
                f"Child {child.child_id} did not cancel in "
                f"{self._cancellation_timeout}s, forcing termination"
            )
            
            await self._terminate_child(
                child,
                type('Parent', (), {'workflow_id': 'cancellation-escalation'})(),
                WorkflowStatus.CANCELLED,
            )
            return False
            
        finally:
            self._pending_cancellations.pop(child.child_id, None)

    async def execute_cancellation_compensation(
        self,
        workflow_id: str,
        compensations: list,
    ) -> None:
        """Execute saga compensation in reverse order during cancellation.
        
        Args:
            workflow_id: Workflow being cancelled.
            compensations: List of compensation objects in execution order.
        """
        # Execute in reverse (LIFO) order
        for comp in reversed(compensations):
            try:
                await comp.execute()
            except Exception as e:
                logger.error(
                    f"Compensation {comp.compensation_id} failed during "
                    f"cancellation of {workflow_id}: {e}"
                )
                # Continue with other compensations


class ChildWorkflowStore:
    """Storage interface for child workflows."""

    async def save(self, child: ChildWorkflow) -> None:
        raise NotImplementedError()

    async def get_by_id(self, child_id: str) -> Optional[ChildWorkflow]:
        raise NotImplementedError()

    async def get_by_idempotency(self, idempotency_key: str) -> Optional[ChildWorkflow]:
        raise NotImplementedError()

    async def get_by_parent(self, parent_id: str) -> list[ChildWorkflow]:
        raise NotImplementedError()


class InMemoryChildWorkflowStore(ChildWorkflowStore):
    """In-memory implementation of child workflow store."""

    def __init__(self):
        self._children: dict[str, ChildWorkflow] = {}
        self._by_idempotency: dict[str, str] = {}  # idempotency_key -> child_id
        self._by_parent: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()

    async def save(self, child: ChildWorkflow) -> None:
        async with self._lock:
            self._children[child.child_id] = child
            
            if child.parent_workflow_id:
                if child.parent_workflow_id not in self._by_parent:
                    self._by_parent[child.parent_workflow_id] = set()
                self._by_parent[child.parent_workflow_id].add(child.child_id)

    async def get_by_id(self, child_id: str) -> Optional[ChildWorkflow]:
        async with self._lock:
            return self._children.get(child_id)

    async def get_by_idempotency(self, idempotency_key: str) -> Optional[ChildWorkflow]:
        async with self._lock:
            child_id = self._by_idempotency.get(idempotency_key)
            if child_id:
                return self._children.get(child_id)
        return None

    async def get_by_parent(self, parent_id: str) -> list[ChildWorkflow]:
        async with self._lock:
            child_ids = self._by_parent.get(parent_id, set())
            return [self._children[c] for c in child_ids if c in self._children]


class ChildWorkflowError(Exception):
    """Child workflow error."""
    pass
