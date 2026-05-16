"""PT Y session module."""

from typing import Any


class PTYSession:
    """PTY session wrapper."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
    
    async def write(self, data: str) -> None:
        """Write to PTY."""
        pass
    
    async def read(self) -> str:
        """Read from PTY."""
        return ""
