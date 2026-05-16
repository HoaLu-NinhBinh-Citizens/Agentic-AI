"""Task model domain module."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Task:
    """Represents a task."""
    
    id: str
    description: str
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.now)
    result: dict[str, Any] | None = None
