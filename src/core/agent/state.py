"""Agent state stub."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    """Current state of the agent."""
    
    task: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    memory: list[dict[str, Any]] = field(default_factory=list)
    status: str = "idle"
