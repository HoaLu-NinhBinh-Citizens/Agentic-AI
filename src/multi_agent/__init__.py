"""Legacy alias for src.multi_agent module."""

from src.core.multi_agent.core import (
    AgentType,
    AgentStatus,
    BaseAgent,
    MessageBus,
    Task,
    AgentMessage,
)
from src.core.multi_agent.agent import (
    FirmwareAgent,
    OrchestratorAgent,
    CodeGenAgent,
    ReviewAgent,
)

__all__ = [
    "AgentType",
    "AgentStatus",
    "BaseAgent",
    "MessageBus",
    "Task",
    "AgentMessage",
    "FirmwareAgent",
    "OrchestratorAgent",
    "CodeGenAgent",
    "ReviewAgent",
]
