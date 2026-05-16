"""Session events domain module."""

from dataclasses import dataclass


@dataclass
class SessionEvent:
    """Session event."""
    session_id: str
    type: str
