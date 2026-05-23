"""Admission Controller - Phase 5A (v5).

Implements admission control with backpressure and resource limits.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ResourceLimits:
    """Resource limits for admission control."""
    max_pending_workflows: int = 10000
    max_pending_tasks: int = 50000
    max_concurrent_activities: int = 1000
    
    # Reject policy
    reject_policy: str = "fail"  # "fail" or "queue"


@dataclass
class ResourceUsage:
    """Current resource usage."""
    pending_workflows: int = 0
    pending_tasks: int = 0
    running_activities: int = 0
    
    # Peak usage tracking
    peak_pending_workflows: int = 0
    peak_pending_tasks: int = 0
    
    last_updated: float = field(default_factory=time.time)


class AdmissionController:
    """Admission controller for workflow runtime.
    
    Features:
    - Limit pending workflows
    - Limit pending tasks
    - Backpressure signaling
    - Reject or queue policy
    - Metrics and monitoring
    """

    def __init__(
        self,
        limits: Optional[ResourceLimits] = None,
    ):
        self._limits = limits or ResourceLimits()
        self._usage = ResourceUsage()
        
        self._lock = asyncio.Lock()
        
        # Backpressure callbacks
        self._backpressure_callbacks: list[callable] = []
        
        # Statistics
        self._total_rejected = 0
        self._total_accepted = 0
        self._backpressure_events = 0

    async def can_start_workflow(self) -> tuple[bool, str]:
        """Check if workflow can be started.
        
        Returns:
            (can_start, reason)
        """
        async with self._lock:
            if self._usage.pending_workflows >= self._limits.max_pending_workflows:
                self._total_rejected += 1
                reason = f"Too many pending workflows: {self._usage.pending_workflows}/{self._limits.max_pending_workflows}"
                
                if self._limits.reject_policy == "fail":
                    logger.warning(f"Admission rejected: {reason}")
                    await self._trigger_backpressure()
                return False, reason
            
            self._total_accepted += 1
            self._usage.pending_workflows += 1
            self._update_peaks()
            return True, "OK"

    async def can_submit_task(self) -> tuple[bool, str]:
        """Check if task can be submitted.
        
        Returns:
            (can_submit, reason)
        """
        async with self._lock:
            if self._usage.pending_tasks >= self._limits.max_pending_tasks:
                self._total_rejected += 1
                reason = f"Too many pending tasks: {self._usage.pending_tasks}/{self._limits.max_pending_tasks}"
                logger.warning(f"Task admission rejected: {reason}")
                return False, reason
            
            self._total_accepted += 1
            self._usage.pending_tasks += 1
            self._update_peaks()
            return True, "OK"

    async def can_run_activity(self) -> tuple[bool, str]:
        """Check if activity can run.
        
        Returns:
            (can_run, reason)
        """
        async with self._lock:
            if self._usage.running_activities >= self._limits.max_concurrent_activities:
                reason = f"Too many running activities: {self._usage.running_activities}/{self._limits.max_concurrent_activities}"
                logger.warning(f"Activity admission rejected: {reason}")
                return False, reason
            
            return True, "OK"

    async def on_workflow_complete(self, workflow_id: str) -> None:
        """Called when workflow completes."""
        async with self._lock:
            self._usage.pending_workflows = max(0, self._usage.pending_workflows - 1)

    async def on_task_complete(self, task_id: str) -> None:
        """Called when task completes."""
        async with self._lock:
            self._usage.pending_tasks = max(0, self._usage.pending_tasks - 1)

    async def on_activity_start(self) -> None:
        """Called when activity starts."""
        async with self._lock:
            self._usage.running_activities += 1

    async def on_activity_complete(self) -> None:
        """Called when activity completes."""
        async with self._lock:
            self._usage.running_activities = max(0, self._usage.running_activities - 1)

    async def on_workflow_fail(self, workflow_id: str) -> None:
        """Called when workflow fails."""
        await self.on_workflow_complete(workflow_id)

    async def on_task_fail(self, task_id: str) -> None:
        """Called when task fails."""
        await self.on_task_complete(task_id)

    async def get_backpressure_level(self) -> float:
        """Get current backpressure level (0.0 to 1.0).
        
        Returns:
            Backpressure percentage.
        """
        async with self._lock:
            workflow_ratio = self._usage.pending_workflows / self._limits.max_pending_workflows
            task_ratio = self._usage.pending_tasks / self._limits.max_pending_tasks
            
            return max(workflow_ratio, task_ratio)

    def register_backpressure_callback(self, callback: callable) -> None:
        """Register callback for backpressure events."""
        self._backpressure_callbacks.append(callback)

    async def _trigger_backpressure(self) -> None:
        """Trigger backpressure event."""
        self._backpressure_events += 1
        
        for callback in self._backpressure_callbacks:
            try:
                level = await self.get_backpressure_level()
                callback(level)
            except Exception as e:
                logger.error(f"Backpressure callback error: {e}")

    def _update_peaks(self) -> None:
        """Update peak usage tracking."""
        self._usage.peak_pending_workflows = max(
            self._usage.peak_pending_workflows,
            self._usage.pending_workflows,
        )
        self._usage.peak_pending_tasks = max(
            self._usage.peak_pending_tasks,
            self._usage.pending_tasks,
        )
        self._usage.last_updated = time.time()

    async def get_stats(self) -> dict:
        """Get admission control statistics."""
        async with self._lock:
            return {
                "limits": {
                    "max_pending_workflows": self._limits.max_pending_workflows,
                    "max_pending_tasks": self._limits.max_pending_tasks,
                    "max_concurrent_activities": self._limits.max_concurrent_activities,
                    "reject_policy": self._limits.reject_policy,
                },
                "usage": {
                    "pending_workflows": self._usage.pending_workflows,
                    "pending_tasks": self._usage.pending_tasks,
                    "running_activities": self._usage.running_activities,
                },
                "peaks": {
                    "peak_pending_workflows": self._usage.peak_pending_workflows,
                    "peak_pending_tasks": self._usage.peak_pending_tasks,
                },
                "stats": {
                    "total_accepted": self._total_accepted,
                    "total_rejected": self._total_rejected,
                    "backpressure_events": self._backpressure_events,
                    "rejection_rate": self._total_rejected / max(1, self._total_accepted + self._total_rejected),
                },
            }

    async def update_limits(self, limits: ResourceLimits) -> None:
        """Update resource limits."""
        async with self._lock:
            self._limits = limits
            logger.info(f"Updated admission limits: workflows={limits.max_pending_workflows}, tasks={limits.max_pending_tasks}")

    async def reset_stats(self) -> None:
        """Reset statistics."""
        async with self._lock:
            self._total_rejected = 0
            self._total_accepted = 0
            self._backpressure_events = 0
            # Also reset usage to ensure clean state
            self._usage.pending_workflows = 0
            self._usage.pending_tasks = 0
            self._usage.running_activities = 0
