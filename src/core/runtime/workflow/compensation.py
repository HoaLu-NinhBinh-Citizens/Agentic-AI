"""Compensation State Machine for Saga Pattern - Phase 5A (v5).

Implements idempotent compensation with state machine, retry support.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Optional, Callable
from dataclasses import dataclass, field

from .types import (
    Compensation,
    CompensationStatus,
    WorkflowInstance,
    DeadLetterItem,
)

logger = logging.getLogger(__name__)


class CompensationStateMachine:
    """State machine for Saga compensation.
    
    Compensation states:
    - PENDING: Compensating action queued
    - RUNNING: Compensation executing
    - COMPLETED: Compensation succeeded
    - FAILED: Compensation failed (will retry)
    
    Features:
    - Idempotent compensation (can be retried safely)
    - Retry with exponential backoff
    - Dead letter for repeated failures
    - Audit trail
    """

    def __init__(
        self,
        compensation_store: "CompensationStore",
        dead_letter_handler: Optional["DeadLetterHandler"] = None,
    ):
        self._store = compensation_store
        self._dead_letter = dead_letter_handler
        self._handlers: dict[str, Callable] = {}

    def register_compensation(
        self,
        activity_name: str,
        handler: Callable[[dict, Any], Any],
    ) -> None:
        """Register compensation handler for an activity.
        
        Args:
            activity_name: Name of activity to compensate.
            handler: Function to execute compensation.
                      Takes (original_input, original_output) and returns compensation_result.
        """
        self._handlers[activity_name] = handler

    async def schedule_compensation(
        self,
        step_id: str,
        activity_name: str,
        original_input: dict,
        original_output: Any,
    ) -> str:
        """Schedule compensation for a completed activity.
        
        Args:
            step_id: The activity step that needs compensation.
            activity_name: Name of the activity.
            original_input: Input passed to original activity.
            original_output: Output from original activity.
            
        Returns:
            Compensation ID.
        """
        compensation = Compensation(
            compensation_id=str(uuid.uuid4()),
            step_id=step_id,
            activity_name=activity_name,
            original_input=original_input,
            original_output=original_output,
            status=CompensationStatus.PENDING,
            idempotency_key=f"compensate:{step_id}",
        )

        await self._store.save(compensation)

        logger.info(
            f"Scheduled compensation {compensation.compensation_id} for step {step_id}"
        )

        return compensation.compensation_id

    async def execute_compensation(self, compensation_id: str) -> bool:
        """Execute a compensation.

        Idempotent: Safe to call multiple times.

        Args:
            compensation_id: ID of compensation to execute.

        Returns:
            True if compensation succeeded.
        """
        compensation = await self._store.get(compensation_id)
        if not compensation:
            logger.error(f"Compensation {compensation_id} not found")
            return False

        # Idempotent: Already completed
        if compensation.status == CompensationStatus.COMPLETED:
            logger.info(f"Compensation {compensation_id} already completed")
            return True

        # Idempotent: Skip if explicitly skipped
        if compensation.status == CompensationStatus.SKIPPED:
            logger.info(f"Compensation {compensation_id} skipped")
            return True

        # Check if should retry (manual retry ignores backoff)
        if compensation.status == CompensationStatus.FAILED:
            if compensation.retry_count >= compensation.max_retries:
                return await self._move_to_dead_letter(compensation)
            # Reset to pending for retry (manual retry ignores backoff)
            compensation.status = CompensationStatus.PENDING

        # Execute compensation
        return await self._do_compensate(compensation)

    async def _do_compensate(self, compensation: Compensation) -> bool:
        """Execute compensation logic."""
        handler = self._handlers.get(compensation.activity_name)
        if not handler:
            logger.error(
                f"No compensation handler for {compensation.activity_name}"
            )
            return await self._fail_compensation(
                compensation,
                f"No handler for {compensation.activity_name}"
            )

        # Update to running
        compensation.status = CompensationStatus.RUNNING
        compensation.started_at = time.time()
        await self._store.save(compensation)

        try:
            # Execute compensation (idempotent)
            result = await handler(
                compensation.original_input,
                compensation.original_output,
            )

            # Success
            compensation.status = CompensationStatus.COMPLETED
            compensation.completed_at = time.time()
            compensation.result = result
            await self._store.save(compensation)

            logger.info(f"Compensation {compensation.compensation_id} completed")
            return True

        except Exception as e:
            logger.error(f"Compensation failed: {e}")
            return await self._fail_compensation(compensation, str(e))

    async def _fail_compensation(
        self,
        compensation: Compensation,
        error: str,
    ) -> bool:
        """Handle compensation failure with retry logic."""
        compensation.status = CompensationStatus.FAILED
        compensation.retry_count += 1
        compensation.error = error

        # Calculate next retry time (exponential backoff)
        delay = min(1.0 * (2 ** (compensation.retry_count - 1)), 60.0)
        compensation.next_retry_at = time.time() + delay

        await self._store.save(compensation)

        logger.warning(
            f"Compensation {compensation.compensation_id} failed "
            f"(attempt {compensation.retry_count}/{compensation.max_retries}), "
            f"retry in {delay}s"
        )

        # Check if should move to dead letter
        if compensation.retry_count >= compensation.max_retries:
            return await self._move_to_dead_letter(compensation)

        return False

    async def _move_to_dead_letter(self, compensation: Compensation) -> bool:
        """Move exhausted compensation to dead letter queue."""
        if self._dead_letter:
            item = DeadLetterItem(
                workflow_id=compensation.step_id.split(":")[0],
                task_id=compensation.compensation_id,
                source_type="compensation",
                payload={
                    "activity_name": compensation.activity_name,
                    "original_input": compensation.original_input,
                    "original_output": compensation.original_output,
                },
                error=compensation.error or "Max retries exceeded",
                failure_count=compensation.retry_count,
            )
            await self._dead_letter.add(item)

        logger.error(
            f"Compensation {compensation.compensation_id} moved to dead letter "
            f"after {compensation.retry_count} attempts"
        )
        return False

    async def skip_compensation(self, compensation_id: str) -> bool:
        """Skip a compensation (idempotent)."""
        compensation = await self._store.get(compensation_id)
        if not compensation:
            return False

        compensation.status = CompensationStatus.SKIPPED
        compensation.completed_at = time.time()
        await self._store.save(compensation)

        logger.info(f"Compensation {compensation_id} skipped")
        return True

    async def get_pending_compensations(
        self,
        workflow_id: str,
    ) -> list[Compensation]:
        """Get all pending compensations for a workflow."""
        return await self._store.get_pending_for_workflow(workflow_id)

    async def cancel_pending(self, workflow_id: str) -> int:
        """Cancel all pending compensations for a workflow."""
        count = 0
        pending = await self.get_pending_compensations(workflow_id)
        for comp in pending:
            comp.status = CompensationStatus.SKIPPED
            await self._store.save(comp)
            count += 1
        return count


class CompensationStore:
    """Storage interface for compensations."""

    async def save(self, compensation: Compensation) -> None:
        """Save compensation state."""
        raise NotImplementedError()

    async def get(self, compensation_id: str) -> Optional[Compensation]:
        """Get compensation by ID."""
        raise NotImplementedError()

    async def get_pending_for_workflow(
        self,
        workflow_id: str,
    ) -> list[Compensation]:
        """Get all pending compensations for a workflow."""
        raise NotImplementedError()

    async def delete(self, compensation_id: str) -> None:
        """Delete compensation."""
        raise NotImplementedError()


class InMemoryCompensationStore(CompensationStore):
    """In-memory implementation of compensation store."""

    def __init__(self):
        self._compensations: dict[str, Compensation] = {}
        self._lock = asyncio.Lock()

    async def save(self, compensation: Compensation) -> None:
        async with self._lock:
            self._compensations[compensation.compensation_id] = compensation

    async def get(self, compensation_id: str) -> Optional[Compensation]:
        async with self._lock:
            return self._compensations.get(compensation_id)

    async def get_pending_for_workflow(
        self,
        workflow_id: str,
    ) -> list[Compensation]:
        async with self._lock:
            return [
                c for c in self._compensations.values()
                if c.status == CompensationStatus.PENDING
                and workflow_id in c.step_id
            ]

    async def delete(self, compensation_id: str) -> None:
        async with self._lock:
            self._compensations.pop(compensation_id, None)


class DeadLetterHandler:
    """Handler for dead letter items."""

    async def add(self, item: DeadLetterItem) -> None:
        """Add item to dead letter queue."""
        raise NotImplementedError()

    async def get(self, item_id: str) -> Optional[DeadLetterItem]:
        """Get item from dead letter queue."""
        raise NotImplementedError()

    async def retry(self, item_id: str) -> bool:
        """Retry a dead letter item."""
        raise NotImplementedError()

    async def discard(self, item_id: str) -> None:
        """Discard a dead letter item."""
        raise NotImplementedError()

    async def list_pending(self, limit: int = 100) -> list[DeadLetterItem]:
        """List pending dead letter items."""
        raise NotImplementedError()
