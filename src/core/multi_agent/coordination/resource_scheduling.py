"""
Resource-Aware Scheduling with Timeout and Fallback.

Provides scheduling with:
- Resource requirement tracking
- Timeout handling
- Fallback mechanisms
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ResourceType(str, Enum):
    """Types of resources."""
    CPU = "cpu"
    MEMORY = "memory"
    GPU = "gpu"
    DISK = "disk"
    NETWORK = "network"
    CUSTOM = "custom"


@dataclass
class ResourceRequirement:
    """Resource requirements for a task."""
    cpu_cores: float = 1.0
    memory_mb: float = 512.0
    gpu_count: int = 0
    disk_mb: int = 0
    custom: Dict[str, float] = field(default_factory=dict)


@dataclass
class ResourceAvailability:
    """Available resources on a worker."""
    worker_id: str
    cpu_cores: float
    memory_mb: float
    gpu_count: int
    disk_mb: int
    custom: Dict[str, float] = field(default_factory=dict)


@dataclass
class TaskSchedulingInfo:
    """Scheduling information for a task."""
    task_id: str
    requirements: ResourceRequirement
    timeout_seconds: float
    fallback_enabled: bool
    fallback_task_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failed_reason: Optional[str] = None
    status: str = "pending"


@dataclass
class SchedulingResult:
    """Result of scheduling attempt."""
    success: bool
    worker_id: Optional[str]
    reason: str
    task_id: str


class ResourceTimeoutHandler:
    """
    Handles resource-aware scheduling with timeout and fallback.
    
    Features:
    - Resource requirement tracking
    - Timeout monitoring
    - Fallback task execution
    - Resource availability tracking
    
    Timeout Reasons:
    - RESOURCE_UNAVAILABLE: No worker with required resources
    - TIMEOUT: Task exceeded timeout limit
    - WORKER_FAILED: Worker became unavailable
    """
    
    def __init__(
        self,
        default_timeout_seconds: float = 30.0,
        check_interval_seconds: float = 1.0,
        max_pending_tasks: int = 10000,
    ):
        self.default_timeout = default_timeout_seconds
        self.check_interval = check_interval_seconds
        self.max_pending = max_pending_tasks
        
        # Task tracking
        self._pending_tasks: Dict[str, TaskSchedulingInfo] = {}
        self._running_tasks: Dict[str, TaskSchedulingInfo] = {}
        
        # Resource tracking
        self._worker_resources: Dict[str, ResourceAvailability] = {}
        self._worker_allocations: Dict[str, Dict[str, float]] = defaultdict(dict)
        
        # Fallback handlers
        self._fallback_handlers: Dict[str, Callable] = {}
        
        # Timeout callbacks
        self._timeout_callbacks: List[Callable[[str, str], None]] = []
        
        self._lock = asyncio.Lock()
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    def register_timeout_callback(
        self,
        callback: Callable[[str, str], None],
    ) -> None:
        """Register callback for task timeouts."""
        self._timeout_callbacks.append(callback)
    
    def register_fallback_handler(
        self,
        task_type: str,
        handler: Callable[[str], Any],
    ) -> None:
        """Register fallback handler for task type."""
        self._fallback_handlers[task_type] = handler
    
    async def register_worker(
        self,
        worker_id: str,
        resources: ResourceAvailability,
    ) -> None:
        """Register a worker with its resources."""
        async with self._lock:
            self._worker_resources[worker_id] = resources
            logger.info(f"Registered worker {worker_id} with resources: {resources}")
    
    async def unregister_worker(self, worker_id: str) -> None:
        """Unregister a worker."""
        async with self._lock:
            self._worker_resources.pop(worker_id, None)
            self._worker_allocations.pop(worker_id, None)
            logger.info(f"Unregistered worker {worker_id}")
    
    async def submit_task(
        self,
        task_id: str,
        requirements: ResourceRequirement,
        timeout_seconds: Optional[float] = None,
        fallback_enabled: bool = False,
        fallback_task_id: Optional[str] = None,
    ) -> SchedulingResult:
        """Submit a task for scheduling."""
        async with self._lock:
            # Check pending limit
            if len(self._pending_tasks) >= self.max_pending:
                return SchedulingResult(
                    success=False,
                    worker_id=None,
                    reason="QUEUE_FULL",
                    task_id=task_id,
                )
            
            # Create scheduling info
            info = TaskSchedulingInfo(
                task_id=task_id,
                requirements=requirements,
                timeout_seconds=timeout_seconds or self.default_timeout,
                fallback_enabled=fallback_enabled,
                fallback_task_id=fallback_task_id,
            )
            
            # Try to schedule immediately
            worker = await self._find_available_worker(requirements)
            
            if worker:
                info.scheduled_at = datetime.now()
                info.started_at = datetime.now()
                info.status = "running"
                self._running_tasks[task_id] = info
                
                # Allocate resources
                await self._allocate_resources(worker, requirements)
                
                return SchedulingResult(
                    success=True,
                    worker_id=worker,
                    reason="SCHEDULED",
                    task_id=task_id,
                )
            
            # Add to pending
            self._pending_tasks[task_id] = info
            
            return SchedulingResult(
                success=True,
                worker_id=None,
                reason="PENDING",
                task_id=task_id,
            )
    
    async def complete_task(self, task_id: str) -> None:
        """Mark task as completed."""
        async with self._lock:
            if task_id in self._pending_tasks:
                info = self._pending_tasks.pop(task_id)
                if info.started_at:
                    info.completed_at = datetime.now()
                    info.status = "completed"
            
            if task_id in self._running_tasks:
                info = self._running_tasks.pop(task_id)
                info.completed_at = datetime.now()
                info.status = "completed"
                
                # Release resources
                await self._release_resources(info)
    
    async def fail_task(self, task_id: str, reason: str) -> None:
        """Mark task as failed."""
        async with self._lock:
            if task_id in self._pending_tasks:
                info = self._pending_tasks.pop(task_id)
                info.failed_reason = reason
                info.status = "failed"
            
            if task_id in self._running_tasks:
                info = self._running_tasks.pop(task_id)
                info.failed_reason = reason
                info.status = "failed"
                
                # Release resources
                await self._release_resources(info)
    
    async def _find_available_worker(
        self,
        requirements: ResourceRequirement,
    ) -> Optional[str]:
        """Find a worker with available resources."""
        for worker_id, resources in self._worker_resources.items():
            if self._can_allocate(worker_id, requirements):
                return worker_id
        return None
    
    def _can_allocate(
        self,
        worker_id: str,
        requirements: ResourceRequirement,
    ) -> bool:
        """Check if worker can allocate resources."""
        resources = self._worker_resources.get(worker_id)
        if not resources:
            return False
        
        allocations = self._worker_allocations.get(worker_id, {})
        
        # Check CPU
        used_cpu = allocations.get("cpu", 0)
        if resources.cpu_cores - used_cpu < requirements.cpu_cores:
            return False
        
        # Check Memory
        used_mem = allocations.get("memory", 0)
        if resources.memory_mb - used_mem < requirements.memory_mb:
            return False
        
        # Check GPU
        used_gpu = allocations.get("gpu", 0)
        if resources.gpu_count - used_gpu < requirements.gpu_count:
            return False
        
        return True
    
    async def _allocate_resources(
        self,
        worker_id: str,
        requirements: ResourceRequirement,
    ) -> None:
        """Allocate resources on worker."""
        allocations = self._worker_allocations[worker_id]
        allocations["cpu"] = allocations.get("cpu", 0) + requirements.cpu_cores
        allocations["memory"] = allocations.get("memory", 0) + requirements.memory_mb
        allocations["gpu"] = allocations.get("gpu", 0) + requirements.gpu_count
    
    async def _release_resources(self, info: TaskSchedulingInfo) -> None:
        """Release resources from task."""
        for worker_id, allocations in self._worker_allocations.items():
            allocations["cpu"] = max(0, allocations.get("cpu", 0) - info.requirements.cpu_cores)
            allocations["memory"] = max(0, allocations.get("memory", 0) - info.requirements.memory_mb)
            allocations["gpu"] = max(0, allocations.get("gpu", 0) - info.requirements.gpu_count)
    
    async def start(self) -> None:
        """Start timeout monitoring."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Resource timeout handler started")
    
    async def stop(self) -> None:
        """Stop timeout monitoring."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Resource timeout handler stopped")
    
    async def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self._running:
            try:
                await asyncio.sleep(self.check_interval)
                await self._check_timeouts()
                await self._retry_pending()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
    
    async def _check_timeouts(self) -> None:
        """Check for timed out tasks."""
        now = datetime.now()
        timed_out = []
        
        for task_id, info in list(self._running_tasks.items()):
            if not info.started_at:
                continue
            
            elapsed = (now - info.started_at).total_seconds()
            if elapsed > info.timeout_seconds:
                timed_out.append(task_id)
        
        for task_id in timed_out:
            logger.warning(f"Task {task_id} timed out after {info.timeout_seconds}s")
            
            # Call timeout callbacks
            for callback in self._timeout_callbacks:
                try:
                    callback(task_id, "TIMEOUT")
                except Exception as e:
                    logger.error(f"Timeout callback error: {e}")
            
            # Handle fallback
            if self._pending_tasks.get(task_id, TaskSchedulingInfo(
                task_id=task_id,
                requirements=ResourceRequirement(),
                timeout_seconds=30,
                fallback_enabled=False,
            )).fallback_enabled:
                fallback_id = self._pending_tasks.get(task_id)
                if fallback_id:
                    await self._execute_fallback(fallback_id)
            
            # Mark as failed
            await self.fail_task(task_id, "TIMEOUT")
    
    async def _retry_pending(self) -> None:
        """Retry pending tasks when resources available."""
        pending = list(self._pending_tasks.items())
        
        for task_id, info in pending:
            worker = await self._find_available_worker(info.requirements)
            
            if worker:
                self._pending_tasks.pop(task_id)
                info.scheduled_at = datetime.now()
                info.started_at = datetime.now()
                info.status = "running"
                self._running_tasks[task_id] = info
                
                await self._allocate_resources(worker, info.requirements)
                
                logger.info(f"Scheduled pending task {task_id} on {worker}")
    
    async def _execute_fallback(self, task_id: str) -> None:
        """Execute fallback for a task."""
        # Implementation would call the registered fallback handler
        logger.info(f"Executing fallback for task {task_id}")
    
    async def get_task_status(self, task_id: str) -> Optional[TaskSchedulingInfo]:
        """Get task scheduling status."""
        return self._pending_tasks.get(task_id) or self._running_tasks.get(task_id)
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get scheduling metrics."""
        async with self._lock:
            return {
                "pending_tasks": len(self._pending_tasks),
                "running_tasks": len(self._running_tasks),
                "registered_workers": len(self._worker_resources),
                "timeout_count": sum(
                    1 for t in self._running_tasks.values()
                    if t.failed_reason == "TIMEOUT"
                ),
            }
