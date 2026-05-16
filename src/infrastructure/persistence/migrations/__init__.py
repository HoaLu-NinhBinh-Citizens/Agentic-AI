"""Persistence migrations module."""

from typing import Any


class Migration:
    """Database migration."""
    
    version: str = ""
    
    async def up(self) -> None:
        """Apply migration."""
        pass
    
    async def down(self) -> None:
        """Revert migration."""
        pass
