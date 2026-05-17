"""Activity Executor with Heartbeat and Lease - Phase 5A (v5).

Executes activities with heartbeat, lease management, and cancellation.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Optional, Callable
from dataclasses import dataclass

from .types import (
    ActivityTask,
    ActivityStatus,
    ActivityResult,
    StepTimeout,
    HeartbeatRecord,
)
from .workflow_context import ActivityContext

logger = logging.getLogger(__name__)


class ActivityExecutor:
    """Executes activities with heartbeat and lease management.
    
    Features:
    - At-least-once delivery
    - Heartbeat for long-running activities
    - Lease renewal
    - Cancellation support
    - Retry on failure
    """

    def __init__(
        self,
        task_queue: "TaskQueue",
        heartbeat_interval_seconds: float = 10.0,
        lease_duration_seconds: float = 30.0,
        worker_id: str = "",
    ):
        self._task_queue = task_queue
        self._heartbeat_interval = heartbeat_interval_seconds
        self._lease_duration = lease_duration_seconds
        self._worker_id = worker_id or str(uuid.uuid4())[:8]
        
        # Activity handlers registry
        self._handlers: dict[str, Callable] = {}
        
        # Running activities
        self._running_tasks: dict[str, ActivityTask] = {}
        self._running_contexts: dict[str, ActivityContext] = {}
        
        # Cancellation callbacks
        self._cancel_callbacks: dict[str, Callable] = {}
        
        self._lock = asyncio.Lock()

    def register_activity(
        self,
        activity_name: str,
        handler: Callable[[dict, ActivityContext], Any],
    ) -> None:
        """Register an activity handler.
        
        Args:
            activity_name: Name of the activity.
            handler: Function to execute. Takes (input, context).
        """
        self._handlers[activity_name] = handler

    async def execute(
        self,
        task: ActivityTask,
        timeout_seconds: Optional[float] = None,
    ) -> ActivityResult:
        """Execute an activity.
        
        Args:
            task: Activity task to execute.
            timeout_seconds: Optional timeout override.
            
        Returns:
            Activity result.
        """
        start_time = time.time()
        
        result = ActivityResult(
            task_id=task.task_id,
            started_at=start_time,
        )
        
        # Create activity context
        context = ActivityContext(
            task_id=task.task_id,
            workflow_id=task.workflow_id,
            activity_type=task.activity_type,
        )
        context._heartbeat_interval = self._heartbeat_interval
        
        # Track running task
        async with self._lock:
            self._running_tasks[task.task_id] = task
            self._running_contexts[task.task_id] = context
        
        try:
            # Get handler
            handler = self._handlers.get(task.activity_type)
            if not handler:
                raise ValueError(f"No handler for activity: {task.activity_type}")
            
            # Setup context callbacks
            context.set_heartbeat_callback(self._on_heartbeat)
            
            # Execute with timeout
            timeout = timeout_seconds or task.activity_type.start_to_close_timeout
            
            try:
                output = await asyncio.wait_for(
                    handler(task.input, context),
                    timeout=timeout,
                )
                
                result.status = ActivityStatus.COMPLETED
                result.output = output
                
            except asyncio.TimeoutError:
                result.status = ActivityStatus.TIMED_OUT
                result.error = f"Activity timed out after {timeout}s"
                
        except Exception as e:
            result.status = ActivityStatus.FAILED
            result.error = str(e)
            logger.error(f"Activity {task.activity_type} failed: {e}")
            
        finally:
            result.completed_at = time.time()
            result.heartbeat_count = context.heartbeat_count
            
            # Remove from running
            async with self._lock:
                self._running_tasks.pop(task.task_id, None)
                self._running_contexts.pop(task.task_id, None)
        
        return result

    async def _on_heartbeat(
        self,
        task_id: str,
        workflow_id: str,
        details: Any,
        heartbeat_count: int,
    ) -> None:
        """Handle heartbeat from activity."""
        # Update heartbeat record
        record = HeartbeatRecord(
            activity_id=workflow_id,
            task_id=task_id,
            workflow_id=workflow_id,
            last_heartbeat_at=time.time(),
            lease_expiry=time.time() + self._lease_duration,
            details=details,
            worker_id=self._worker_id,
        )
        
        # Extend lease in task queue
        await self._task_queue.extend_lease(task_id, self._lease_duration)
        
        logger.debug(
            f"Activity heartbeat {heartbeat_count} for {task_id[:8]}... "
            f"(worker={self._worker_id})"
        )

    async def cancel_activity(self, task_id: str, reason: str) -> bool:
        """Cancel a running activity.
        
        Args:
            task_id: Task to cancel.
            reason: Cancellation reason.
            
        Returns:
            True if cancelled successfully.
        """
        context = self._running_contexts.get(task_id)
        if context:
            context.report_cancelled(reason)
            logger.info(f"Activity {task_id[:8]}... cancelled: {reason}")
            return True
        
        return False

    async def check_cancellation(self, task_id: str) -> bool:
        """Check if activity should cancel.
        
        Args:
            task_id: Task to check.
            
        Returns:
            True if cancelled.
        """
        context = self._running_contexts.get(task_id)
        return context.is_cancelled() if context else False

    def get_running_count(self) -> int:
        """Get number of running activities."""
        return len(self._running_tasks)

    def get_worker_id(self) -> str:
        """Get worker ID."""
        return self._worker_id


class TaskQueue:
    """Task queue interface for activity execution.
    
    Implementations should provide:
    - Task polling
    - Claim management
    - Lease extension
    """

    async def poll(self, worker_id: str) -> Optional[ActivityTask]:
        """Poll for available task."""
        raise NotImplementedError()

    async def claim(self, task_id: str, worker_id: str) -> bool:
        """Claim a task for execution."""
        raise NotImplementedError()

    async def extend_lease(self, task_id: str, additional_seconds: float) -> bool:
        """Extend task lease."""
        raise NotImplementedError()

    async def complete(self, task_id: str, result: ActivityResult) -> None:
        """Mark task as complete."""
        raise NotImplementedError()

    async def fail(self, task_id: str, error: str) -> None:
        """Mark task as failed."""
        raise NotImplementedError()


class InMemoryTaskQueue(TaskQueue):
    """In-memory task queue implementation."""

    def __init__(self):
        self._tasks: dict[str, ActivityTask] = {}
        self._lock = asyncio.Lock()

    async def add_task(self, task: ActivityTask) -> None:
        async with self._lock:
            self._tasks[task.task_id] = task

    async def poll(self, worker_id: str) -> Optional[ActivityTask]:
        async with self._lock:
            for task_id, task in self._tasks.items():
                if task.status == ActivityStatus.PENDING:
                    task.status = ActivityStatus.RUNNING
                    task.claimed_by = worker_id
                    task.claim_expires_at = time.time() + 30
                    return task
        return None

    async def claim(self, task_id: str, worker_id: str) -> bool:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status == ActivityStatus.PENDING:
                task.status = ActivityStatus.RUNNING
                task.claimed_by = worker_id
                task.claim_expires_at = time.time() + 30
                return True
        return False

    async def extend_lease(self, task_id: str, additional_seconds: float) -> bool:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.claim_expires_at = time.time() + additional_seconds
                return True
        return False

    async def complete(self, task_id: str, result: ActivityResult) -> None:
        async with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = result.status

    async def fail(self, task_id: str, error: str) -> None:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = ActivityStatus.FAILED
                task.error = error
