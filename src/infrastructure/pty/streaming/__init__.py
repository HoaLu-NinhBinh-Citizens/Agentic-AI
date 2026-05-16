"""PTY streaming module."""

from typing import Any


class PTYStreaming:
    """Streaming for PTY sessions."""
    
    async def start_stream(self, session_id: str) -> None:
        """Start streaming."""
        pass
    
    async def stop_stream(self, session_id: str) -> None:
        """Stop streaming."""
        pass
