"""DTO schemas module."""

from dataclasses import dataclass
from typing import Any


@dataclass
class TaskDTO:
    """Task data transfer object."""
    
    id: str
    description: str
    status: str = "pending"


@dataclass
class ResultDTO:
    """Result data transfer object."""
    
    success: bool
    data: Any | None = None
    error: str | None = None
