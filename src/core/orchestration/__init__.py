"""
AI_support Orchestration Module

Async workflow orchestration layer with LangGraph integration.

New LangGraph-based workflow provides:
- State management with typed StateGraph
- Workflow visualization
- Checkpointing and persistence
- Human-in-the-loop interrupts
- Parallel fan-out
"""

from src.core.orchestration.langgraph_workflow import (
    AgentState,
    WorkflowState,
    create_agent_graph,
    create_firmware_workflow,
    compile_agent_graph,
    compile_firmware_workflow,
)

from src.core.orchestration.langgraph_agent import (
    LangGraphAgent,
    LangGraphOrchestrator,
    create_langgraph_orchestrator,
)

from src.core.orchestration.queue import TaskQueue, Priority

from src.core.orchestration.rollback import (
    RollbackEngine,
    RollbackContext,
    RollbackPolicy,
    RollbackState,
    CompensationAction,
    CompensationResult,
    CompensationStatus,
    Checkpoint,
)

__all__ = [
    # LangGraph workflow (recommended)
    "AgentState",
    "WorkflowState",
    "create_agent_graph",
    "create_firmware_workflow",
    "compile_agent_graph",
    "compile_firmware_workflow",
    "LangGraphAgent",
    "LangGraphOrchestrator",
    "create_langgraph_orchestrator",
    # Queue
    "TaskQueue",
    "Priority",
    # Rollback
    "RollbackEngine",
    "RollbackContext",
    "RollbackPolicy",
    "RollbackState",
    "CompensationAction",
    "CompensationResult",
    "CompensationStatus",
    "Checkpoint",
]
