"""Artifact model domain module."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Artifact:
    """Code artifact."""
    id: str
    name: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
