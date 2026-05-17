"""Feedback processor with exactly-once guarantee."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

from src.infrastructure.router.types import Feedback, FeedbackResult

if TYPE_CHECKING:
    from src.infrastructure.router.consistency.read_after_write import ReadAfterWriteGuard
    from src.infrastructure.router.observation.exactly_once import ExactlyOnceProcessor
    from src.infrastructure.router.snapshot import SnapshotManager

logger = logging.getLogger(__name__)


class FeedbackProcessor:
    """
    Processes feedback with exactly-once guarantee.
    
    Combines ExactlyOnceProcessor with ReadAfterWriteGuard for
    consistent feedback processing.
    """

    def __init__(
        self,
        exactly_once: ExactlyOnceProcessor,
        consistency_guard: ReadAfterWriteGuard,
        snapshot_manager: SnapshotManager,
    ):
        self._exactly_once = exactly_once
        self._consistency_guard = consistency_guard
        self._snapshot_manager = snapshot_manager

    async def report_feedback(self, feedback: Feedback) -> FeedbackResult:
        """
        Report feedback with exactly-once guarantee.
        
        Args:
            feedback: Feedback to process
            
        Returns:
            FeedbackResult with processing status
        """
        is_new = await self._exactly_once.process_feedback(feedback)

        if not is_new:
            return FeedbackResult(
                success=True,
                was_idempotent=True,
            )

        await self._consistency_guard.on_feedback_written()

        new_snapshot = await self._consistency_guard.after_feedback(
            self._snapshot_manager
        )

        return FeedbackResult(
            success=True,
            was_idempotent=False,
            new_snapshot_id=new_snapshot.snapshot_id if new_snapshot else None,
        )

    def get_consistency_status(self) -> dict:
        """Get consistency guard status."""
        return self._consistency_guard.get_guard_status()
