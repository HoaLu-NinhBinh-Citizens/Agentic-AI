"""Retention Manager - Phase 5A (v5).

Retention policies and cleanup for workflows, events, and snapshots.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, Any

from .types import WorkflowSnapshot, WorkflowStatus

logger = logging.getLogger(__name__)


class RetentionManager:
    """Manages retention policies and cleanup.
    
    Cleans up old workflows, events, and snapshots based on retention policies.
    """

    def __init__(
        self,
        event_store: "EventStore",
        snapshot_store: "SnapshotStore",
        idempotency_store: "IdempotencyStore",
        workflow_completed_retention_days: int = 7,
        workflow_failed_retention_days: int = 7,
        event_retention_days: int = 30,
        idempotency_key_retention_days: int = 1,
        cleanup_interval_hours: int = 1,
    ):
        self._event_store = event_store
        self._snapshot_store = snapshot_store
        self._idempotency_store = idempotency_store
        
        # Retention config
        self._workflow_completed_retention_days = workflow_completed_retention_days
        self._workflow_failed_retention_days = workflow_failed_retention_days
        self._event_retention_days = event_retention_days
        self._idempotency_key_retention_days = idempotency_key_retention_days
        
        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        self._cleanup_interval_hours = cleanup_interval_hours

    async def start(self) -> None:
        """Start periodic cleanup."""
        if self._running:
            return
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Retention cleanup started")

    async def stop(self) -> None:
        """Stop periodic cleanup."""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup loop."""
        while self._running:
            try:
                await asyncio.sleep(self._cleanup_interval_hours * 3600)
                
                if self._running:
                    await self.run_cleanup()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Retention cleanup error: {e}")

    async def run_cleanup(self) -> dict[str, int]:
        """Run one cleanup cycle.
        
        Returns:
            Cleanup statistics.
        """
        cleaned = {
            "workflows_completed": 0,
            "workflows_failed": 0,
            "events": 0,
            "idempotency_keys": 0,
            "snapshots": 0,
        }
        
        # Clean completed workflows
        cutoff = time.time() - (self._workflow_completed_retention_days * 86400)
        cleaned["workflows_completed"] = await self._cleanup_workflows(
            WorkflowStatus.COMPLETED, cutoff
        )
        
        # Clean failed workflows
        cutoff = time.time() - (self._workflow_failed_retention_days * 86400)
        cleaned["workflows_failed"] = await self._cleanup_workflows(
            WorkflowStatus.FAILED, cutoff
        )
        
        # Clean old events
        cutoff = time.time() - (self._event_retention_days * 86400)
        cleaned["events"] = await self._event_store.delete_events_before(cutoff)
        
        # Clean idempotency keys
        cutoff = time.time() - (self._idempotency_key_retention_days * 86400)
        cleaned["idempotency_keys"] = await self._idempotency_store.delete_before(cutoff)
        
        logger.info(f"Retention cleanup complete: {cleaned}")
        return cleaned

    async def _cleanup_workflows(
        self,
        status: WorkflowStatus,
        cutoff_time: float,
    ) -> int:
        """Clean up workflows by status and age."""
        workflow_ids = await self._event_store.get_workflows_by_status_before(
            status, cutoff_time
        )
        
        deleted = 0
        for workflow_id in workflow_ids:
            try:
                await self._event_store.delete_workflow(workflow_id)
                await self._snapshot_store.delete_workflow(workflow_id)
                deleted += 1
            except Exception as e:
                logger.error(f"Failed to cleanup workflow {workflow_id}: {e}")
        
        return deleted

    async def cleanup_workflow(self, workflow_id: str) -> bool:
        """Clean up a specific workflow.
        
        Args:
            workflow_id: Workflow to clean up.
            
        Returns:
            True if successful.
        """
        try:
            await self._event_store.delete_workflow(workflow_id)
            await self._snapshot_store.delete_workflow(workflow_id)
            logger.info(f"Cleaned up workflow {workflow_id[:8]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to cleanup workflow {workflow_id}: {e}")
            return False


# Placeholder store interfaces
class EventStore:
    async def get_workflows_by_status_before(self, status, cutoff: float) -> list[str]: ...
    async def delete_workflow(self, workflow_id: str) -> None: ...
    async def delete_events_before(self, cutoff: float) -> int: ...

class SnapshotStore:
    async def delete_workflow(self, workflow_id: str) -> None: ...

class IdempotencyStore:
    async def delete_before(self, cutoff: float) -> int: ...
