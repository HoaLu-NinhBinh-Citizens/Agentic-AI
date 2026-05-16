"""
Multi-Agent System Package

Exports:
- Core: AgentType, AgentStatus, BaseAgent, MessageBus, OrchestratorAgent, Task
- Agents: CodeGenAgent, ReviewAgent, SecurityAgent, TestGenerationAgent, TestAgent (alias), DevOpsAgent, MonitoringAgent, BuildAgent, FlashAgent, FirmwareAgent
- UnifiedAgent: Production-grade unified agent
- SharedMemory: Cross-agent state management
- LangGraph: LangGraphAgent, LangGraphOrchestrator (LangGraph-powered workflow)
"""

from src.core.multi_agent.core import (
    AgentType,
    AgentStatus,
    BaseAgent,
    MessageBus,
    Task,
    AgentMessage,
    ExecutionTrace,
)

from src.core.multi_agent.agent import (
    OrchestratorAgent,
    CodeGenAgent,
    ReviewAgent,
    SecurityAgent,
    UnityTestAgent,  # Renamed from TestAgent
    TestAgent,  # Alias for backward compatibility
    TestGenerationAgent,  # Alias for backward compatibility
    DevOpsAgent,
    MonitoringAgent,
    BuildAgent,
    FlashAgent,
    FirmwareAgent,
    UnifiedAgent,
    Vulnerability,
    DeploymentResult,
    DeploymentStrategy,
    SharedMemory,
    KBEntry,
    BuildRecord,
    FlashRecord,
    TestRecord,
    PRE_COMMIT_HOOK,
    COMMIT_MSG_HOOK,
    PRE_PUSH_HOOK,
    UNITY_TEST_HEADER,
    UNITY_TEST_FOOTER,
)

# LangGraph integration
from src.core.orchestration.langgraph_agent import (
    LangGraphAgent,
    LangGraphOrchestrator,
    create_langgraph_orchestrator,
)

__all__ = [
    # Core
    "AgentType",
    "AgentStatus",
    "BaseAgent",
    "MessageBus",
    "Task",
    "AgentMessage",
    "ExecutionTrace",
    # Agents
    "OrchestratorAgent",
    "CodeGenAgent",
    "ReviewAgent",
    "SecurityAgent",
    "TestAgent",
    "DevOpsAgent",
    "MonitoringAgent",
    "BuildAgent",
    "FlashAgent",
    "FirmwareAgent",
    "UnifiedAgent",
    # Dataclasses
    "Vulnerability",
    "DeploymentResult",
    "KBEntry",
    "BuildRecord",
    "FlashRecord",
    "TestRecord",
    # Enums
    "DeploymentStrategy",
    # Hooks
    "PRE_COMMIT_HOOK",
    "COMMIT_MSG_HOOK",
    "PRE_PUSH_HOOK",
    # Test
    "UNITY_TEST_HEADER",
    "UNITY_TEST_FOOTER",
    # Memory
    "SharedMemory",
    # LangGraph
    "LangGraphAgent",
    "LangGraphOrchestrator",
    "create_langgraph_orchestrator",
]
