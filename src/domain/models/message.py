"""Message model domain module."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Message:
    """Represents a message."""
    
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
