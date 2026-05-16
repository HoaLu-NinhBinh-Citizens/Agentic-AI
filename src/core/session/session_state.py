"""Session state stub."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionState:
    """State for a single session."""
    
    session_id: str
    data: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def add_event(self, event: dict[str, Any]) -> None:
        """Add event to session history."""
        self.history.append(event)
