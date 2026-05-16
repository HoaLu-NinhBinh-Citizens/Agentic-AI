"""Plan model domain module."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Plan:
    """Execution plan."""
    id: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    status: str = "pending"
