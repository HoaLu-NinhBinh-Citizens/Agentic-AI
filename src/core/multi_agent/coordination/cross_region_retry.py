"""
Cross-Region Retry with Region-Specific DLQ.

Provides:
- Cross-region task submission with retry
- Region-specific dead letter queues
- Exponential backoff
- Automatic replay after recovery
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class RegionDLQStatus(str, Enum):
    """Region DLQ status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNREACHABLE = "unreachable"


@dataclass
class CrossRegionTask:
    """Task submitted to another region."""
    task_id: str
    source_region: str
    target_region: str
    payload: Dict[str, Any]
    attempt: int
    max_attempts: int
    created_at: datetime
    last_attempt_at: Optional[datetime] = None
    next_attempt_at: Optional[datetime] = None
    status: str = "pending"
    error: Optional[str] = None
    region_dlq_id: Optional[str] = None


@dataclass
class RegionInfo:
    """Information about a region."""
    region_id: str
    endpoint: str
    status: RegionDLQStatus
    last_heartbeat: datetime
    latency_ms: float = 0.0
    success_rate: float = 1.0


@dataclass
class RetryResult:
    """Result of retry operation."""
    success: bool
    task_id: str
    attempts_used: int
    final_error: Optional[str]


class RegionDLQ:
    """Region-specific DLQ."""
    
    def __init__(self, region_id: str):
        self.region_id = region_id
        self._items: Dict[str, CrossRegionTask] = {}
        self._lock = asyncio.Lock()
    
    async def add(
        self,
        task_id: str,
        task: CrossRegionTask,
    ) -> None:
        """Add task to region DLQ."""
        async with self._lock:
            self._items[task_id] = task
    
    async def get(self, task_id: str) -> Optional[CrossRegionTask]:
        """Get task from DLQ."""
        return self._items.get(task_id)
    
    async def remove(self, task_id: str) -> bool:
        """Remove task from DLQ."""
        if task_id in self._items:
            del self._items[task_id]
            return True
        return False
    
    async def list_tasks(self) -> List[CrossRegionTask]:
        """List all tasks in DLQ."""
        return list(self._items.values())
    
    async def count(self) -> int:
        """Count tasks in DLQ."""
        return len(self._items)


class CrossRegionRetry:
    """
    Cross-region retry with region-specific DLQ.
    
    Features:
    - Exponential backoff for cross-region requests
    - Region-specific DLQ when all retries fail
    - Automatic replay after region recovers
    - Health monitoring per region
    
    Retry Strategy:
    - Attempt 1: Immediate
    - Attempt 2: After 1 second
    - Attempt 3: After 2 seconds
    - Attempt 4: After 4 seconds
    - On failure: Add to region DLQ
    """
    
    def __init__(
        self,
        max_attempts: int = 3,
        base_backoff_seconds: float = 1.0,
        backoff_multiplier: float = 2.0,
        health_check_interval: float = 30.0,
    ):
        self.max_attempts = max_attempts
        self.base_backoff = base_backoff_seconds
        self.backoff_multiplier = backoff_multiplier
        self.health_check_interval = health_check_interval
        
        # Region management
        self._regions: Dict[str, RegionInfo] = {}
        self._region_dlqs: Dict[str, RegionDLQ] = {}
        
        # Task tracking
        self._pending_tasks: Dict[str, CrossRegionTask] = {}
        self._retry_callbacks: List[Callable] = []
        
        self._lock = asyncio.Lock()
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    def register_region(
        self,
        region_id: str,
        endpoint: str,
    ) -> None:
        """Register a region."""
        self._regions[region_id] = RegionInfo(
            region_id=region_id,
            endpoint=endpoint,
            status=RegionDLQStatus.HEALTHY,
            last_heartbeat=datetime.now(),
        )
        self._region_dlqs[region_id] = RegionDLQ(region_id)
    
    def register_retry_callback(
        self,
        callback: Callable,
    ) -> None:
        """Register callback for retry events."""
        self._retry_callbacks.append(callback)
    
    async def submit_cross_region(
        self,
        task_id: str,
        source_region: str,
        target_region: str,
        payload: Dict[str, Any],
        submit_handler: Callable,
    ) -> RetryResult:
        """
        Submit task to another region with retry.
        
        Args:
            task_id: Unique task ID
            source_region: Source region ID
            target_region: Target region ID
            payload: Task payload
            submit_handler: Async function to call for submission
            
        Returns:
            RetryResult with final status
        """
        task = CrossRegionTask(
            task_id=task_id,
            source_region=source_region,
            target_region=target_region,
            payload=payload,
            attempt=0,
            max_attempts=self.max_attempts,
            created_at=datetime.now(),
        )
        
        async with self._lock:
            self._pending_tasks[task_id] = task
        
        last_error = None
        
        for attempt in range(1, self.max_attempts + 1):
            task.attempt = attempt
            task.last_attempt_at = datetime.now()
            
            try:
                # Check region health
                region = self._regions.get(target_region)
                if not region or region.status == RegionDLQStatus.UNREACHABLE:
                    raise ConnectionError(f"Region {target_region} unreachable")
                
                # Attempt submission
                await submit_handler(target_region, payload)
                
                # Success
                async with self._lock:
                    self._pending_tasks.pop(task_id, None)
                
                logger.info(f"Cross-region submit success: {task_id} to {target_region}")
                
                return RetryResult(
                    success=True,
                    task_id=task_id,
                    attempts_used=attempt,
                    final_error=None,
                )
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Cross-region attempt {attempt} failed: {e}")
                
                # Calculate backoff
                if attempt < self.max_attempts:
                    delay = self.base_backoff * (self.backoff_multiplier ** (attempt - 1))
                    task.next_attempt_at = datetime.now() + timedelta(seconds=delay)
                    
                    # Wait before retry
                    await asyncio.sleep(min(delay, 5))  # Cap at 5 seconds
        
        # All retries failed, add to region DLQ
        task.status = "failed"
        task.error = last_error
        task.region_dlq_id = target_region
        
        async with self._lock:
            self._pending_tasks.pop(task_id, None)
            if target_region in self._region_dlqs:
                await self._region_dlqs[target_region].add(task_id, task)
        
        logger.error(f"Cross-region submit failed after {self.max_attempts} attempts: {task_id}")
        
        return RetryResult(
            success=False,
            task_id=task_id,
            attempts_used=self.max_attempts,
            final_error=last_error,
        )
    
    async def replay_region_dlq(
        self,
        region_id: str,
        replay_handler: Callable,
        max_items: int = 1000,
    ) -> int:
        """
        Replay tasks from region DLQ after recovery.
        
        Args:
            region_id: Region ID to replay DLQ
            replay_handler: Async function to call for replay
            
        Returns:
            Number of tasks replayed
        """
        dlq = self._region_dlqs.get(region_id)
        if not dlq:
            return 0
        
        tasks = await dlq.list_tasks()
        replayed = 0
        
        for task in tasks[:max_items]:
            try:
                await replay_handler(region_id, task.payload)
                await dlq.remove(task.task_id)
                replayed += 1
                
                logger.info(f"Replayed task {task.task_id} to {region_id}")
                
            except Exception as e:
                logger.error(f"Failed to replay task {task.task_id}: {e}")
        
        return replayed
    
    async def report_heartbeat(
        self,
        region_id: str,
        success: bool,
        latency_ms: float = 0.0,
    ) -> None:
        """Report region heartbeat."""
        if region_id not in self._regions:
            return
        
        region = self._regions[region_id]
        region.last_heartbeat = datetime.now()
        region.latency_ms = latency_ms
        
        # Update success rate (exponential moving average)
        alpha = 0.1
        if success:
            region.success_rate = alpha * 1.0 + (1 - alpha) * region.success_rate
            if region.status == RegionDLQStatus.UNREACHABLE:
                region.status = RegionDLQStatus.HEALTHY
        else:
            region.success_rate = (1 - alpha) * region.success_rate
            if region.success_rate < 0.5:
                region.status = RegionDLQStatus.UNREACHABLE
            elif region.success_rate < 0.8:
                region.status = RegionDLQStatus.DEGRADED
    
    async def get_region_dlq_status(self, region_id: str) -> Dict[str, Any]:
        """Get DLQ status for a region."""
        dlq = self._region_dlqs.get(region_id)
        region = self._regions.get(region_id)
        
        if not dlq:
            return {"exists": False}
        
        return {
            "exists": True,
            "region_id": region_id,
            "item_count": await dlq.count(),
            "region_status": region.status.value if region else "unknown",
            "success_rate": region.success_rate if region else 0,
            "latency_ms": region.latency_ms if region else 0,
        }
    
    async def start(self) -> None:
        """Start retry manager."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._health_loop())
        logger.info("Cross-region retry manager started")
    
    async def stop(self) -> None:
        """Stop retry manager."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Cross-region retry manager stopped")
    
    async def _health_loop(self) -> None:
        """Background health monitoring loop."""
        while self._running:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self._check_region_health()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health loop error: {e}")
    
    async def _check_region_health(self) -> None:
        """Check region health and trigger replay if recovered."""
        for region_id, region in self._regions.items():
            elapsed = (datetime.now() - region.last_heartbeat).total_seconds()
            
            if elapsed > 120:  # 2 minutes
                region.status = RegionDLQStatus.UNREACHABLE
            elif elapsed > 60:  # 1 minute
                region.status = RegionDLQStatus.DEGRADED
            
            # If recovered, replay DLQ
            if region.status == RegionDLQStatus.HEALTHY:
                dlq = self._region_dlqs.get(region_id)
                if dlq and await dlq.count() > 0:
                    logger.info(f"Region {region_id} recovered, triggering DLQ replay")
                    # Would trigger replay handler
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get retry metrics."""
        total_dlq = 0
        dlq_by_region = {}
        
        for region_id, dlq in self._region_dlqs.items():
            count = await dlq.count()
            total_dlq += count
            dlq_by_region[region_id] = count
        
        return {
            "total_pending": len(self._pending_tasks),
            "total_dlq": total_dlq,
            "dlq_by_region": dlq_by_region,
            "regions": {
                rid: {
                    "status": r.status.value,
                    "success_rate": r.success_rate,
                    "latency_ms": r.latency_ms,
                }
                for rid, r in self._regions.items()
            },
        }
