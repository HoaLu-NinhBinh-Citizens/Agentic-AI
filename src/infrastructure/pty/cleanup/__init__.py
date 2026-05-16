"""PTY cleanup module."""

from typing import Any


class PTYCleanup:
    """Cleans up PTY sessions."""
    
    async def cleanup(self) -> int:
        """Clean up dead sessions."""
        return 0
