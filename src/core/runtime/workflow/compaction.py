"""Event Compaction and Retention - Phase 5A (v5).

Implements event compaction for terminal workflows and retention policies.
"""

from __future__ import annotations

import asyncio
import logging
import time
import json
from typing import Optional, Any
from dataclasses import dataclass, field

from .types import WorkflowSnapshot, WorkflowInstance, WorkflowStatus

logger = logging.getLogger(__name__)


@dataclass
class CompactionConfig:
    """Configuration for event compaction."""
    enabled: bool = True
    workflow_terminal_retention_days: int = 1
    archive_path: Optional[str] = None  # e.g., "s3://bucket/events/"
    compact_interval_hours: int = 24


@dataclass
class RetentionConfig:
    """Configuration for retention policies."""
    workflow_completed_retention_days: int = 7
    workflow_failed_retention_days: int = 7
    workflow_cancelled_retention_days: int = 7
    event_retention_days: int = 30
    idempotency_key_retention_days: int = 1
    snapshot_retention_days: int = 14
    cleanup_interval_hours: int = 1


class EventCompactor:
    """Compacts events for terminal workflows.
    
    After workflow completes/fails, raw events are archived
    and only the final snapshot is kept for fast replay.
    """

    def __init__(
        self,
        event_store: "EventStore",
        snapshot_store: "SnapshotStore",
        config: Optional[CompactionConfig] = None,
    ):
        self._event_store = event_store
        self._snapshot_store = snapshot_store
        self._config = config or CompactionConfig()
        
        self._compaction_task: Optional[asyncio.Task] = None
        self._running = False

    async def compact_workflow(self, workflow_id: str) -> bool:
        """Compact events for a terminal workflow.
        
        1. Get final snapshot
        2. Archive raw events
        3. Mark snapshot as terminal
        4. Remove raw events (or keep reference)
        
        Args:
            workflow_id: Workflow to compact.
            
        Returns:
            True if compacted successfully.
        """
        if not self._config.enabled:
            return False
        
        try:
            # Get final snapshot
            snapshot = await self._snapshot_store.get_latest(workflow_id)
            if not snapshot:
                logger.warning(f"No snapshot for {workflow_id}, skipping compaction")
                return False
            
            # Mark as terminal
            snapshot.is_terminal_snapshot = True
            await self._snapshot_store.save(snapshot)
            
            # Archive events
            events = await self._event_store.get_events(workflow_id)
            if events and self._config.archive_path:
                await self._archive_events(workflow_id, events)
            
            # Mark events as archived
            await self._event_store.mark_archived(workflow_id)
            
            logger.info(f"Compacted workflow {workflow_id[:8]}... ({len(events)} events)")
            return True
            
        except Exception as e:
            logger.error(f"Compaction failed for {workflow_id}: {e}")
            return False

    async def _archive_events(self, workflow_id: str, events: list) -> None:
        """Archive events to storage.
        
        In production, this would write to S3, GCS, or similar.
        For now, writes to local file.
        """
        if not self._config.archive_path:
            return
        
        archive_data = {
            "workflow_id": workflow_id,
            "archived_at": time.time(),
            "event_count": len(events),
            "events": [
                {
                    "event_id": e.event_id,
                    "event_type": e.event_type.value if hasattr(e.event_type, 'value') else e.event_type,
                    "sequence": e.sequence,
                    "created_at": e.created_at,
                    "event_data": e.event_data,
                }
                for e in events
            ],
        }
        
        if self._config.archive_path.startswith("s3://"):
            # TODO: Implement S3 archiving
            logger.debug(f"Would archive {len(events)} events to {self._config.archive_path}")
        else:
            # Local file archiving
            import os
            archive_dir = self._config.archive_path
            os.makedirs(archive_dir, exist_ok=True)
            
            filename = f"{archive_dir}/{workflow_id}_events.json"
            with open(filename, "w") as f:
                json.dump(archive_data, f)

    async def start_periodic_compaction(self) -> None:
        """Start periodic compaction job."""
        if self._running:
            return
        
        self._running = True
        self._compaction_task = asyncio.create_task(self._compaction_loop())
        logger.info("Started periodic compaction")

    async def stop_periodic_compaction(self) -> None:
        """Stop periodic compaction job."""
        self._running = False
        if self._compaction_task:
            self._compaction_task.cancel()
            try:
                await self._compaction_task
            except asyncio.CancelledError:
                pass

    async def _compaction_loop(self) -> None:
        """Periodic compaction loop."""
        while self._running:
            try:
                await asyncio.sleep(self._config.compact_interval_hours * 3600)
                
                if self._running:
                    await self._run_compaction_cycle()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Compaction loop error: {e}")

    async def _run_compaction_cycle(self) -> None:
        """Run one compaction cycle."""
        cutoff_time = time.time() - (self._config.workflow_terminal_retention_days * 86400)
        
        # Get terminal workflows older than retention
        workflows = await self._get_terminal_workflows_older_than(cutoff_time)
        
        compacted = 0
        for workflow_id in workflows:
            if await self.compact_workflow(workflow_id):
                compacted += 1
        
        logger.info(f"Compaction cycle complete: {compacted}/{len(workflows)} workflows compacted")

    async def _get_terminal_workflows_older_than(
        self,
        cutoff_time: float,
    ) -> list[str]:
        """Get terminal workflows older than cutoff."""
        return await self._event_store.get_terminal_workflows_before(cutoff_time)


class RetentionManager:
    """Manages retention policies and cleanup.
    
    Cleans up old workflows, events, and snapshots based on retention policies.
    """

    def __init__(
        self,
        event_store: "EventStore",
        snapshot_store: "SnapshotStore",
        idempotency_store: "IdempotencyStore",
        config: Optional[RetentionConfig] = None,
    ):
        self._event_store = event_store
        self._snapshot_store = snapshot_store
        self._idempotency_store = idempotency_store
        self._config = config or RetentionConfig()
        
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    async def start_periodic_cleanup(self) -> None:
        """Start periodic cleanup job."""
        if self._running:
            return
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Started periodic retention cleanup")

    async def stop_periodic_cleanup(self) -> None:
        """Stop periodic cleanup job."""
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
                await asyncio.sleep(self._config.cleanup_interval_hours * 3600)
                
                if self._running:
                    await self._run_cleanup_cycle()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")

    async def _run_cleanup_cycle(self) -> None:
        """Run one cleanup cycle."""
        cleaned = {
            "workflows": 0,
            "events": 0,
            "snapshots": 0,
            "idempotency_keys": 0,
        }
        
        # Clean old completed workflows
        cutoff = time.time() - (self._config.workflow_completed_retention_days * 86400)
        cleaned["workflows"] += await self._cleanup_workflows(WorkflowStatus.COMPLETED, cutoff)
        
        # Clean old failed workflows
        cutoff = time.time() - (self._config.workflow_failed_retention_days * 86400)
        cleaned["workflows"] += await self._cleanup_workflows(WorkflowStatus.FAILED, cutoff)
        
        # Clean old events
        cutoff = time.time() - (self._config.event_retention_days * 86400)
        cleaned["events"] += await self._cleanup_events(cutoff)
        
        # Clean old idempotency keys
        cutoff = time.time() - (self._config.idempotency_key_retention_days * 86400)
        cleaned["idempotency_keys"] += await self._cleanup_idempotency_keys(cutoff)
        
        logger.info(f"Cleanup cycle complete: {cleaned}")

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

    async def _cleanup_events(self, cutoff_time: float) -> int:
        """Clean up old events."""
        return await self._event_store.delete_events_before(cutoff_time)

    async def _cleanup_idempotency_keys(self, cutoff_time: float) -> int:
        """Clean up old idempotency keys."""
        return await self._idempotency_store.delete_before(cutoff_time)

    async def cleanup_workflow(self, workflow_id: str) -> bool:
        """Clean up a specific workflow.
        
        Args:
            workflow_id: Workflow to clean up.
            
        Returns:
            True if cleaned up successfully.
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
    async def get_events(self, workflow_id: str) -> list: ...
    async def mark_archived(self, workflow_id: str) -> None: ...
    async def get_terminal_workflows_before(self, cutoff: float) -> list[str]: ...
    async def get_workflows_by_status_before(self, status, cutoff: float) -> list[str]: ...
    async def delete_workflow(self, workflow_id: str) -> None: ...
    async def delete_events_before(self, cutoff: float) -> int: ...

class SnapshotStore:
    async def get_latest(self, workflow_id: str) -> Optional[WorkflowSnapshot]: ...
    async def save(self, snapshot: WorkflowSnapshot) -> None: ...
    async def delete_workflow(self, workflow_id: str) -> None: ...

class IdempotencyStore:
    async def delete_before(self, cutoff: float) -> int: ...
