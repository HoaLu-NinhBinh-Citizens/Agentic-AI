"""Request context factory."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from src.infrastructure.router.types import Request, RequestContext, Snapshot

if TYPE_CHECKING:
    from src.infrastructure.router.snapshot import SnapshotManager

logger = logging.getLogger(__name__)


class RequestContextFactory:
    """
    Factory for creating immutable request contexts.
    
    Creates RequestContext with frozen snapshot at the start of routing.
    """

    def __init__(self, snapshot_manager: SnapshotManager):
        self._snapshot_manager = snapshot_manager

    async def create_context(self, request: Request) -> RequestContext:
        """
        Create immutable request context.
        
        Creates snapshot once at start, embeds in context for pipeline.
        """
        snapshot = await self._snapshot_manager.get_current_snapshot()

        context = RequestContext.create(
            snapshot=snapshot,
            request=request,
        )

        logger.debug(
            f"Created context {context.context_id} with snapshot {snapshot.snapshot_id}"
        )
        return context

    async def create_context_with_snapshot(
        self,
        request: Request,
        snapshot: Snapshot,
    ) -> RequestContext:
        """
        Create context with specific snapshot (for testing).
        """
        return RequestContext.create(
            snapshot=snapshot,
            request=request,
        )
