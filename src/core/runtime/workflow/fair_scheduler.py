"""Fair Scheduling with Deficit Round Robin - Phase 5A (v5).

Implements fair CPU time sharing between workflows.
"""

from __future__ import annotations

import asyncio
import logging
import time
import heapq
from typing import Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class WorkflowTask:
    """A runnable workflow task."""
    workflow_id: str
    priority: int = 5
    
    # Scheduling state
    deficit: float = 0.0  # Deficit Round Robin
    last_run_at: float = field(default_factory=time.time)
    
    # State
    is_runnable: bool = True
    is_blocked: bool = False
    
    # For heap ordering
    def __lt__(self, other: "WorkflowTask") -> bool:
        # Priority queue ordering: higher priority first
        if self.priority != other.priority:
            return self.priority > other.priority
        # Then by deficit (more deficit = higher priority)
        return self.deficit > other.deficit


class FairScheduler:
    """Fair scheduler using Deficit Round Robin (DRR).
    
    Features:
    - Deficit Round Robin for fair CPU sharing
    - Priority support
    - Non-work-conserving (can idle if no tasks)
    - Quantized time slices
    """

    def __init__(
        self,
        quantum_ms: float = 100.0,
        max_pending_workflows: int = 10000,
    ):
        self._quantum_ms = quantum_ms
        self._max_pending = max_pending_workflows
        
        # Ready queue (heap)
        self._ready: list[WorkflowTask] = []
        
        # Tracking
        self._workflows: dict[str, WorkflowTask] = {}
        self._running_workflow: Optional[str] = None
        
        # Statistics
        self._total_scheduled = 0
        self._cycle_count = 0
        
        # Lock
        self._lock = asyncio.Lock()

    @property
    def pending_count(self) -> int:
        """Number of pending (runnable) workflows.
        
        Only counts workflows that are runnable and not blocked.
        """
        return sum(1 for task in self._workflows.values() if task.is_runnable and not task.is_blocked)

    async def add_workflow(
        self,
        workflow_id: str,
        priority: int = 5,
    ) -> bool:
        """Add a workflow to the scheduler.
        
        Args:
            workflow_id: Workflow ID.
            priority: Priority (higher = more important).
            
        Returns:
            True if added successfully.
        """
        async with self._lock:
            if len(self._workflows) >= self._max_pending:
                logger.warning(f"Scheduler at capacity: {self._max_pending}")
                return False
            
            if workflow_id in self._workflows:
                return True  # Already added
            
            task = WorkflowTask(
                workflow_id=workflow_id,
                priority=priority,
            )
            
            self._workflows[workflow_id] = task
            heapq.heappush(self._ready, task)
            self._total_scheduled += 1
            
            logger.debug(f"Workflow {workflow_id[:8]}... added to scheduler")
            return True

    async def remove_workflow(self, workflow_id: str) -> None:
        """Remove a workflow from the scheduler."""
        async with self._lock:
            task = self._workflows.pop(workflow_id, None)
            if task:
                task.is_runnable = False

    async def block_workflow(self, workflow_id: str) -> None:
        """Mark workflow as blocked (waiting for activity/signal)."""
        async with self._lock:
            task = self._workflows.get(workflow_id)
            if task:
                task.is_blocked = True
                task.is_runnable = False

    async def unblock_workflow(self, workflow_id: str) -> None:
        """Mark workflow as runnable again."""
        async with self._lock:
            task = self._workflows.get(workflow_id)
            if task and task.is_blocked:
                task.is_blocked = False
                task.is_runnable = True
                if task not in self._ready:
                    heapq.heappush(self._ready, task)

    async def get_next_workflow(self) -> Optional[str]:
        """Get next workflow to run.
        
        Implements Deficit Round Robin:
        1. Add quantum to deficit
        2. If deficit >= quantum, run
        3. Otherwise, skip
        
        Returns:
            Workflow ID to run, or None if no runnable workflows.
        """
        async with self._lock:
            # Drain blocked tasks from ready queue
            while self._ready:
                task = heapq.heappop(self._ready)
                if not task.is_runnable:
                    self._workflows.pop(task.workflow_id, None)
                    continue
                heapq.heappush(self._ready, task)
                break
            
            if not self._ready:
                return None
            
            # Peek at highest priority task
            task = self._ready[0]
            
            # DRR: Add quantum to deficit
            quantum = self._quantum_ms / 1000.0  # Convert to seconds
            task.deficit += quantum
            
            # Check if can run (deficit >= quantum)
            if task.deficit >= quantum:
                self._running_workflow = task.workflow_id
                task.last_run_at = time.time()
                self._cycle_count += 1
                return task.workflow_id
            
            return None

    async def record_execution(
        self,
        workflow_id: str,
        execution_time_ms: float,
    ) -> None:
        """Record workflow execution time and adjust deficit.
        
        Args:
            workflow_id: Workflow that executed.
            execution_time_ms: Time spent executing.
        """
        async with self._lock:
            task = self._workflows.get(workflow_id)
            if not task:
                return
            
            execution_time_s = execution_time_ms / 1000.0
            
            # Subtract from deficit
            task.deficit = max(0, task.deficit - execution_time_s)
            
            if self._running_workflow == workflow_id:
                self._running_workflow = None
            
            # Re-add to queue if still runnable
            if task.is_runnable and not task.is_blocked:
                heapq.heappush(self._ready, task)

    async def yield_workflow(self, workflow_id: str) -> None:
        """Yield a workflow voluntarily (before quantum exhausted)."""
        async with self._lock:
            task = self._workflows.get(workflow_id)
            if task and self._running_workflow == workflow_id:
                self._running_workflow = None
                heapq.heappush(self._ready, task)

    def get_deficit(self, workflow_id: str) -> float:
        """Get deficit for a workflow."""
        task = self._workflows.get(workflow_id)
        return task.deficit if task else 0.0

    def get_stats(self) -> dict:
        """Get scheduler statistics."""
        return {
            "pending_count": len(self._ready),
            "total_workflows": len(self._workflows),
            "total_scheduled": self._total_scheduled,
            "cycle_count": self._cycle_count,
            "quantum_ms": self._quantum_ms,
            "max_pending": self._max_pending,
        }


class DeficitRoundRobin:
    """Alternative name for FairScheduler."""
    
    def __init__(self, quantum_ms: float = 100.0, max_pending: int = 10000):
        self._scheduler = FairScheduler(quantum_ms, max_pending)
    
    async def schedule(self, workflow_id: str, priority: int = 5) -> bool:
        return await self._scheduler.add_workflow(workflow_id, priority)
    
    async def deschedule(self, workflow_id: str) -> None:
        return await self._scheduler.remove_workflow(workflow_id)
    
    async def next(self) -> Optional[str]:
        return await self._scheduler.get_next_workflow()
    
    async def record(self, workflow_id: str, time_ms: float) -> None:
        return await self._scheduler.record_execution(workflow_id, time_ms)
    
    @property
    def pending(self) -> int:
        return self._scheduler.pending_count
