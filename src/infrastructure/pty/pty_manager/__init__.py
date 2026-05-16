"""PTY manager stub."""

import asyncio
from typing import Any


class PTYManager:
    """Manages PTY sessions."""
    
    def __init__(self):
        self._sessions: dict[str, Any] = {}
    
    async def create_session(self) -> str:
        """Create a new PTY session."""
        session_id = f"pty_{len(self._sessions)}"
        self._sessions[session_id] = {"id": session_id}
        return session_id
    
    async def write(self, session_id: str, data: str) -> None:
        """Write to PTY session."""
        pass
    
    async def read(self, session_id: str) -> str:
        """Read from PTY session."""
        return ""
    
    async def close(self, session_id: str) -> None:
        """Close PTY session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
