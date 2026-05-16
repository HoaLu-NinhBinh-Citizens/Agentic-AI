"""Session store for chat history persistence and forking."""

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class ChatTurn:
    """A single turn in a chat session."""
    role: str
    content: str
    timestamp: str


@dataclass
class ChatSession:
    """A saved chat session with history."""
    session_id: str
    turns: list[ChatTurn]
    created_at: str
    last_updated: str
    project_root: str = ""
    active_provider: str = "ollama"

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "turns": [asdict(t) if isinstance(t, ChatTurn) else t for t in self.turns],
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "project_root": self.project_root,
            "active_provider": self.active_provider,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChatSession":
        turns = [ChatTurn(**t) if isinstance(t, dict) else t for t in data.get("turns", [])]
        return cls(
            session_id=data.get("session_id", ""),
            turns=turns,
            created_at=data.get("created_at", ""),
            last_updated=data.get("last_updated", ""),
            project_root=data.get("project_root", ""),
            active_provider=data.get("active_provider", "ollama"),
        )


class SessionStore:
    """Persistent storage for chat sessions."""

    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = Path.home() / ".carv" / "sessions"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        """Get the file path for a session."""
        return self.storage_dir / f"{session_id}.json"

    def save(self, session: ChatSession) -> str:
        """Save a session and return its ID."""
        session.last_updated = datetime.now().isoformat()
        path = self._session_path(session.session_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
        return session.session_id

    def load(self, session_id: str) -> Optional[ChatSession]:
        """Load a session by ID."""
        path = self._session_path(session_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ChatSession.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None

    def list_sessions(self) -> list[ChatSession]:
        """List all saved sessions, sorted by last_updated descending."""
        sessions = []
        for path in self.storage_dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sessions.append(ChatSession.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue
        sessions.sort(key=lambda s: s.last_updated, reverse=True)
        return sessions

    def delete(self, session_id: str) -> bool:
        """Delete a session by ID. Returns True if deleted."""
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def fork_session(self, original: ChatSession, label: str = "") -> ChatSession:
        """Create a fork of an existing session with a new ID."""
        new_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{label or 'fork'}"
        forked = ChatSession(
            session_id=new_id,
            turns=original.turns.copy(),
            created_at=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
            project_root=original.project_root,
            active_provider=original.active_provider,
        )
        self.save(forked)
        return forked
