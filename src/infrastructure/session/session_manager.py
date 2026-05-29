"""Session management for Agentic-AI CLI.

Inspired by oh-my-pi's session management pattern:
- Persistent session files
- Session history
- Project-scoped sessions
- Hindsight memory integration

W-012 Fix: messages, tool_calls, and hindsight_facts are now bounded lists
to prevent unbounded growth and OOM after long sessions.
"""

from __future__ import annotations

import json
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


# ─── Bounded list ──────────────────────────────────────────────────────────────

class BoundedList(list):
    """A list that evicts the oldest items when max_size is exceeded.

    Usage:
        bl = BoundedList(max_size=100)
        bl.append(item)  # oldest item dropped when full
    """

    def __init__(self, max_size: int = 1000, iterable=()):
        super().__init__(iterable)
        self._max_size = max_size

    def append(self, item: Any) -> None:
        super().append(item)
        while len(self) > self._max_size:
            self.pop(0)

    def extend(self, items: Any) -> None:
        for item in items:
            self.append(item)


# ─── Data models ───────────────────────────────────────────────────────────────


class SessionStatus(Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


@dataclass
class Message:
    """A message in the session."""
    
    role: str  # "user" | "assistant" | "system" | "tool_result"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    tool_name: str | None = None
    tool_call_id: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            tool_name=data.get("tool_name"),
            tool_call_id=data.get("tool_call_id"),
        )


@dataclass
class ToolCall:
    """A tool call record."""
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    result: str | None = None
    error: str | None = None
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    duration_ms: float | None = None
    blocked: bool = False
    
    def complete(self, result: str | None = None, error: str | None = None) -> None:
        self.result = result
        self.error = error
        self.completed_at = datetime.now()
        if self.started_at:
            self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "blocked": self.blocked,
        }


@dataclass
class SessionContext:
    """Project-scoped session context."""
    
    project_path: Path | None = None
    project_id: str | None = None
    rules: list[str] = field(default_factory=list)  # AGENTS.md, .cursor/rules, etc.
    model: str | None = None
    provider: str | None = None
    working_directory: Path | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "project_path": str(self.project_path) if self.project_path else None,
            "project_id": self.project_id,
            "rules": self.rules,
            "model": self.model,
            "provider": self.provider,
            "working_directory": str(self.working_directory) if self.working_directory else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionContext:
        return cls(
            project_path=Path(data["project_path"]) if data.get("project_path") else None,
            project_id=data.get("project_id"),
            rules=data.get("rules", []),
            model=data.get("model"),
            provider=data.get("provider"),
            working_directory=Path(data["working_directory"]) if data.get("working_directory") else None,
        )


@dataclass
class Session:
    """A persistent session with history."""
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    status: SessionStatus = SessionStatus.ACTIVE

    # W-012 Fix: bounded to prevent OOM after long sessions
    messages: list[Message] = field(default_factory=lambda: BoundedList(max_size=2000))
    tool_calls: list[ToolCall] = field(default_factory=lambda: BoundedList(max_size=2000))
    context: SessionContext = field(default_factory=SessionContext)

    # W-012 Fix: bounded to prevent unbounded growth
    hindsight_facts: list[str] = field(default_factory=lambda: BoundedList(max_size=500))
    
    # Session metadata
    title: str | None = None
    turn_count: int = 0
    token_usage: int = 0
    cost_usd: float = 0.0
    
    def add_message(self, role: str, content: str, **kwargs) -> Message:
        msg = Message(role=role, content=content, **kwargs)
        self.messages.append(msg)
        self.updated_at = datetime.now()
        return msg
    
    def add_tool_call(self, name: str, arguments: dict[str, Any]) -> ToolCall:
        tc = ToolCall(name=name, arguments=arguments)
        self.tool_calls.append(tc)
        self.updated_at = datetime.now()
        return tc
    
    def add_hindsight_fact(self, fact_id: str) -> None:
        if fact_id not in self.hindsight_facts:
            self.hindsight_facts.append(fact_id)
    
    def increment_turn(self) -> None:
        self.turn_count += 1
        self.updated_at = datetime.now()
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "status": self.status.value,
            "messages": [m.to_dict() for m in self.messages],
            "tool_calls": [t.to_dict() for t in self.tool_calls],
            "context": self.context.to_dict(),
            "hindsight_facts": self.hindsight_facts,
            "title": self.title,
            "turn_count": self.turn_count,
            "token_usage": self.token_usage,
            "cost_usd": self.cost_usd,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        session = cls(
            id=data["id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            status=SessionStatus(data["status"]),
            context=SessionContext.from_dict(data.get("context", {})),
            hindsight_facts=data.get("hindsight_facts", []),
            title=data.get("title"),
            turn_count=data.get("turn_count", 0),
            token_usage=data.get("token_usage", 0),
            cost_usd=data.get("cost_usd", 0.0),
        )
        session.messages = [Message.from_dict(m) for m in data.get("messages", [])]
        session.tool_calls = [ToolCall(**t) for t in data.get("tool_calls", [])]
        return session


class SessionStore:
    """Manages persistent session storage."""
    
    def __init__(self, base_path: Path | None = None):
        self.base_path = base_path or self._default_session_path()
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    @staticmethod
    def _default_session_path() -> Path:
        import os
        from pathlib import Path
        
        config_home = os.environ.get("XDG_CONFIG_HOME")
        if config_home:
            base = Path(config_home)
        else:
            base = Path.home() / ".config"
        
        return base / "ai-support" / "sessions"
    
    def _session_path(self, session_id: str) -> Path:
        return self.base_path / f"{session_id}.json"
    
    def save(self, session: Session) -> None:
        """Save session to disk."""
        path = self._session_path(session.id)
        path.write_text(json.dumps(session.to_dict(), indent=2))
    
    def load(self, session_id: str) -> Session | None:
        """Load session from disk."""
        path = self._session_path(session_id)
        if not path.exists():
            return None
        
        data = json.loads(path.read_text())
        return Session.from_dict(data)
    
    def list_sessions(self, project_id: str | None = None) -> list[Session]:
        """List all sessions, optionally filtered by project."""
        sessions = []
        for path in self.base_path.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                if project_id is None or data.get("context", {}).get("project_id") == project_id:
                    sessions.append(Session.from_dict(data))
            except Exception:
                continue
        
        return sorted(sessions, key=lambda s: s.updated_at, reverse=True)
    
    def delete(self, session_id: str) -> bool:
        """Delete a session."""
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()
            return True
        return False
    
    def create_session(self, context: SessionContext | None = None) -> Session:
        """Create a new session."""
        session = Session(context=context or SessionContext())
        self.save(session)
        return session


# Global session store instance
_session_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store


def create_session(project_path: Path | None = None) -> Session:
    """Create a new session for a project."""
    store = get_session_store()
    
    context = SessionContext()
    if project_path:
        context.project_path = project_path
        context.project_id = str(project_path.absolute())
        context.working_directory = project_path
        
        # Discover rules
        rules = discover_project_rules(project_path)
        context.rules = rules
    
    return store.create_session(context)


def discover_project_rules(project_path: Path) -> list[str]:
    """Discover agent rules in project."""
    rules = []
    
    rule_files = [
        "AGENTS.md",
        ".cursor/rules/AGENTS.md",
        ".cursor/rules/.mdc",
        ".claude/rules.md",
        ".codex/rules.md",
    ]
    
    for rule_file in rule_files:
        path = project_path / rule_file
        if path.exists():
            rules.append(str(path))
    
    return rules
