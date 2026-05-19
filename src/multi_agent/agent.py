"""Legacy alias for src.multi_agent.agent module."""

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
    SecurityAgent,
    DevOpsAgent,
    MonitoringAgent,
    UnifiedAgent,
)

# Import TestAgent if it exists
try:
    from src.core.multi_agent.agent import TestAgent
except ImportError:
    TestAgent = None

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
    "SecurityAgent",
    "TestAgent",
    "DevOpsAgent",
    "MonitoringAgent",
    "UnifiedAgent",
]
