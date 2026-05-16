"""Session manager stub."""

import uuid
from datetime import datetime
from typing import Any


class SessionManager:
    """Manages agent sessions."""
    
    def __init__(self):
        self._sessions: dict[str, dict[str, Any]] = {}
    
    def create_session(self) -> str:
        """Create a new session."""
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = {
            "id": session_id,
            "created_at": datetime.now(),
            "status": "active",
        }
        return session_id
    
    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session by ID."""
        return self._sessions.get(session_id)
    
    def end_session(self, session_id: str) -> None:
        """End a session."""
        if session_id in self._sessions:
            self._sessions[session_id]["status"] = "ended"
