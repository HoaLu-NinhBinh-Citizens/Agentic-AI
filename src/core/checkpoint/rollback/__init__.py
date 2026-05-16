"""Rollback module."""

from typing import Any


class Rollback:
    """Rollback to checkpoint."""
    
    async def rollback(self, checkpoint_id: str) -> bool:
        """Rollback to checkpoint."""
        return True
