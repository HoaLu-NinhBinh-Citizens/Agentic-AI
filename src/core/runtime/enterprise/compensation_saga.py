"""Compensation/Saga with retry and dead letter - Phase 5B v10.

Implements Saga pattern for distributed transactions:
- CompensationTask: Individual compensation operations
- SagaCoordinator: Orchestrates compensation
- DeadLetterQueue: Handles failed compensations
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class CompensationStatus(Enum):
    """Status of a compensation task."""
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class CompensationRetryPolicy(Enum):
    """Retry strategy for failed compensations."""
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIXED = "fixed"
    NONE = "none"


@dataclass
class CompensationConfig:
    """Configuration for compensation retry."""
    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 60.0
    retry_policy: CompensationRetryPolicy = CompensationRetryPolicy.EXPONENTIAL


@dataclass
class CompensationTask:
    """A single compensation task."""
    task_id: str
    original_task_id: str
    original_input: dict
    original_output: dict
    compensation_fn: Optional[Callable] = None
    compensation_type: str = ""
    status: CompensationStatus = CompensationStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    last_error: Optional[str] = None
    completed_at: Optional[int] = None
    created_at: int = field(default_factory=lambda: int(time.time()))
    result: Optional[Any] = None


@dataclass
class SagaState:
    """State of a saga execution."""
    saga_id: str
    workflow_id: str
    completed_tasks: list[str] = field(default_factory=list)
    failed_task_id: Optional[str] = None
    compensation_tasks: list[CompensationTask] = field(default_factory=list)
    compensation_in_progress: bool = False
    compensation_complete: bool = False


class DeadLetterReason(Enum):
    """Reason for moving to dead letter queue."""
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"
    COMPENSATION_UNAVAILABLE = "compensation_unavailable"
    INVALID_COMPENSATION_INPUT = "invalid_compensation_input"
    SAGA_ABORTED = "saga_aborted"
    MANUAL_INTERVENTION = "manual_intervention"


@dataclass
class DeadLetterEntry:
    """Entry in the dead letter queue."""
    entry_id: str
    saga_id: str
    task: CompensationTask
    reason: DeadLetterReason
    created_at: int = field(default_factory=lambda: int(time.time()))
    retry_count: int = 0
    resolved: bool = False
    resolved_at: Optional[int] = None
    resolution: Optional[str] = None


class DeadLetterQueue:
    """Queue for failed compensation tasks.
    
    Provides:
    - Storage for failed compensations
    - Retry capability
    - Manual resolution tracking
    """
    
    def __init__(self):
        self._entries: dict[str, DeadLetterEntry] = {}
        self._by_saga: dict[str, list[str]] = {}
    
    async def add(
        self,
        saga_id: str,
        task: CompensationTask,
        reason: DeadLetterReason,
    ) -> DeadLetterEntry:
        """Add a failed compensation to the dead letter queue.
        
        Args:
            saga_id: Saga identifier
            task: Failed compensation task
            reason: Reason for failure
            
        Returns:
            Created dead letter entry
        """
        import uuid
        
        entry = DeadLetterEntry(
            entry_id=str(uuid.uuid4()),
            saga_id=saga_id,
            task=task,
            reason=reason,
        )
        
        self._entries[entry.entry_id] = entry
        
        if saga_id not in self._by_saga:
            self._by_saga[saga_id] = []
        self._by_saga[saga_id].append(entry.entry_id)
        
        return entry
    
    async def get(self, entry_id: str) -> Optional[DeadLetterEntry]:
        """Get a dead letter entry by ID."""
        return self._entries.get(entry_id)
    
    async def get_by_saga(self, saga_id: str) -> list[DeadLetterEntry]:
        """Get all dead letter entries for a saga."""
        entry_ids = self._by_saga.get(saga_id, [])
        return [
            self._entries[eid]
            for eid in entry_ids
            if eid in self._entries
        ]
    
    async def get_unresolved(self) -> list[DeadLetterEntry]:
        """Get all unresolved dead letter entries."""
        return [e for e in self._entries.values() if not e.resolved]
    
    async def resolve(
        self,
        entry_id: str,
        resolution: str,
    ) -> bool:
        """Mark a dead letter entry as resolved.
        
        Args:
            entry_id: Entry identifier
            resolution: How it was resolved
            
        Returns:
            True if resolved successfully
        """
        entry = self._entries.get(entry_id)
        if not entry:
            return False
        
        entry.resolved = True
        entry.resolved_at = int(time.time())
        entry.resolution = resolution
        return True
    
    async def retry(self, entry_id: str) -> bool:
        """Retry a dead letter entry.
        
        Args:
            entry_id: Entry identifier
            
        Returns:
            True if retry scheduled
        """
        entry = self._entries.get(entry_id)
        if not entry:
            return False
        
        entry.retry_count += 1
        return True
    
    async def discard(self, entry_id: str) -> bool:
        """Discard a dead letter entry.
        
        Args:
            entry_id: Entry identifier
            
        Returns:
            True if discarded
        """
        entry = self._entries.get(entry_id)
        if not entry:
            return False
        
        await self.resolve(entry_id, "discarded")
        return True


class SagaCoordinator:
    """Coordinates saga execution and compensation.
    
    When a saga fails, the coordinator runs compensation
    tasks in reverse order of completion.
    """
    
    def __init__(
        self,
        dead_letter_queue: DeadLetterQueue,
        config: Optional[CompensationConfig] = None,
    ):
        self._dlq = dead_letter_queue
        self._config = config or CompensationConfig()
        self._sagas: dict[str, SagaState] = {}
    
    async def start_saga(
        self,
        saga_id: str,
        workflow_id: str,
    ) -> SagaState:
        """Start a new saga.
        
        Args:
            saga_id: Saga identifier
            workflow_id: Associated workflow
            
        Returns:
            Initial saga state
        """
        state = SagaState(
            saga_id=saga_id,
            workflow_id=workflow_id,
        )
        self._sagas[saga_id] = state
        return state
    
    async def record_task_completion(
        self,
        saga_id: str,
        task_id: str,
    ) -> None:
        """Record that a task completed successfully.
        
        Args:
            saga_id: Saga identifier
            task_id: Completed task ID
        """
        state = self._sagas.get(saga_id)
        if state and task_id not in state.completed_tasks:
            state.completed_tasks.append(task_id)
    
    async def fail_saga(
        self,
        saga_id: str,
        failed_task_id: str,
    ) -> list[CompensationTask]:
        """Mark saga as failed and create compensation tasks.
        
        Args:
            saga_id: Saga identifier
            failed_task_id: ID of the task that failed
            
        Returns:
            List of compensation tasks to run
        """
        state = self._sagas.get(saga_id)
        if not state:
            return []
        
        state.failed_task_id = failed_task_id
        
        compensation_tasks = []
        for task_id in reversed(state.completed_tasks):
            task = CompensationTask(
                task_id=f"comp_{task_id}",
                original_task_id=task_id,
                original_input={},
                original_output={},
                status=CompensationStatus.PENDING,
                max_retries=self._config.max_attempts,
            )
            compensation_tasks.append(task)
            state.compensation_tasks.append(task)
        
        return compensation_tasks
    
    async def execute_compensation(
        self,
        saga_id: str,
        task: CompensationTask,
        compensation_fn: Callable,
    ) -> bool:
        """Execute a single compensation task.
        
        Args:
            saga_id: Saga identifier
            task: Compensation task
            compensation_fn: Function to execute
            
        Returns:
            True if compensation succeeded
        """
        task.status = CompensationStatus.RUNNING
        
        try:
            result = await compensation_fn(
                task.original_input,
                task.original_output,
            )
            task.result = result
            task.status = CompensationStatus.COMPLETED
            task.completed_at = int(time.time())
            return True
            
        except Exception as e:
            task.retry_count += 1
            task.last_error = str(e)
            
            if task.retry_count >= task.max_retries:
                task.status = CompensationStatus.FAILED
                
                await self._dlq.add(
                    saga_id,
                    task,
                    DeadLetterReason.MAX_RETRIES_EXCEEDED,
                )
                
                return False
            
            task.status = CompensationStatus.PENDING
            delay = self._calculate_delay(task.retry_count)
            await asyncio.sleep(delay)
            
            return await self.execute_compensation(
                saga_id, task, compensation_fn
            )
    
    def _calculate_delay(self, retry_count: int) -> float:
        """Calculate delay for next retry.
        
        Args:
            retry_count: Current retry count
            
        Returns:
            Delay in seconds
        """
        if self._config.retry_policy == CompensationRetryPolicy.EXPONENTIAL:
            delay = self._config.initial_delay_seconds * (
                self._config.backoff_multiplier ** (retry_count - 1)
            )
        elif self._config.retry_policy == CompensationRetryPolicy.LINEAR:
            delay = self._config.initial_delay_seconds * retry_count
        elif self._config.retry_policy == CompensationRetryPolicy.FIXED:
            delay = self._config.initial_delay_seconds
        else:
            delay = 0
        
        return min(delay, self._config.max_delay_seconds)
    
    async def compensate_saga(
        self,
        saga_id: str,
        compensation_registry: dict[str, Callable],
    ) -> tuple[bool, list[str]]:
        """Execute all compensation tasks for a saga.
        
        Args:
            saga_id: Saga identifier
            compensation_registry: Map of task_id to compensation function
            
        Returns:
            Tuple of (all_succeeded, failed_task_ids)
        """
        state = self._sagas.get(saga_id)
        if not state:
            return False, []
        
        state.compensation_in_progress = True
        
        failed_tasks = []
        
        for task in state.compensation_tasks:
            comp_fn = compensation_registry.get(task.original_task_id)
            
            if comp_fn is None:
                task.status = CompensationStatus.SKIPPED
                continue
            
            success = await self.execute_compensation(saga_id, task, comp_fn)
            
            if not success:
                failed_tasks.append(task.original_task_id)
        
        state.compensation_in_progress = False
        state.compensation_complete = len(failed_tasks) == 0
        
        return state.compensation_complete, failed_tasks
    
    async def get_saga_state(self, saga_id: str) -> Optional[SagaState]:
        """Get current state of a saga."""
        return self._sagas.get(saga_id)
    
    async def abort_saga(self, saga_id: str) -> None:
        """Abort a saga without running compensations.
        
        Args:
            saga_id: Saga identifier
        """
        state = self._sagas.get(saga_id)
        if state:
            state.compensation_complete = True


class CompensationManager:
    """High-level manager for saga and compensation."""
    
    def __init__(
        self,
        coordinator: SagaCoordinator,
        dead_letter_queue: DeadLetterQueue,
    ):
        self._coordinator = coordinator
        self._dlq = dead_letter_queue
    
    async def handle_activity_failure(
        self,
        workflow_id: str,
        task_id: str,
        error: str,
    ) -> None:
        """Handle an activity failure by starting compensation.
        
        Args:
            workflow_id: Workflow identifier
            task_id: Failed task ID
            error: Error message
        """
        saga_id = f"saga_{workflow_id}"
        await self._coordinator.fail_saga(saga_id, task_id)
    
    async def run_compensation(
        self,
        workflow_id: str,
        registry: dict[str, Callable],
    ) -> tuple[bool, list[str]]:
        """Run compensation for a workflow.
        
        Args:
            workflow_id: Workflow identifier
            registry: Compensation function registry
            
        Returns:
            Tuple of (success, failed_tasks)
        """
        saga_id = f"saga_{workflow_id}"
        return await self._coordinator.compensate_saga(saga_id, registry)
