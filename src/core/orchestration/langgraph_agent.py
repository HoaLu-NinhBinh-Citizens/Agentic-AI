"""
LangGraph Agent Integration

Bridges LangGraph workflow with existing multi_agent system.
Maintains backward compatibility while enabling LangGraph features.
"""

import asyncio
import logging
from typing import Any, Callable, Optional

from langgraph.graph import StateGraph

from src.core.orchestration.langgraph_workflow import (
    AgentState,
    WorkflowState,
    compile_agent_graph,
    compile_firmware_workflow,
)

logger = logging.getLogger(__name__)


class LangGraphAgent:
    """
    LangGraph-powered agent with workflow orchestration.
    
    Combines LangGraph state management with existing agent types.
    """

    def __init__(
        self,
        agents: dict[str, Any] = None,
        enable_checkpoint: bool = True,
        enable_human_gate: bool = True,
    ):
        self.agents = agents or {}
        self.enable_checkpoint = enable_checkpoint
        self.enable_human_gate = enable_human_gate
        
        self.graph = compile_firmware_workflow(checkpoint=enable_checkpoint)
        self._running = False

    def register_agent(self, agent_type: str, agent: Any) -> None:
        """Register an agent for use in workflow nodes."""
        self.agents[agent_type] = agent

    async def execute(self, task: Any) -> dict[str, Any]:
        """
        Execute task through LangGraph workflow.
        
        Args:
            task: Task to execute
            
        Returns:
            Workflow result
        """
        logger.info(f"LangGraphAgent: Executing task")
        
        # Get task attributes safely
        task_type = getattr(task, 'type', 'unknown')
        task_desc = getattr(task, 'description', '')
        task_ctx = getattr(task, 'context', {})
        task_id = getattr(task, 'id', 'unknown')
        
        initial_state: WorkflowState = {
            "task_type": task_type,
            "task_description": task_desc,
            "context": task_ctx,
            "status": "pending",
            "current_node": "",
            "completed_nodes": [],
            "generated_code": None,
            "build_result": None,
            "review_result": None,
            "flash_result": None,
            "human_approved": None,
            "error": None,
            "retry_count": 0,
            "project": task_ctx.get("project"),
            "device": task_ctx.get("device"),
            "trace": [],
        }
        
        config = {"configurable": {"thread_id": task_id}}
        
        try:
            result = await self.graph.ainvoke(initial_state, config)
            return self._format_result(result)
        except Exception as exc:
            logger.error(f"Workflow failed: {exc}")
            return {
                "success": False,
                "error": str(exc),
                "task_id": task_id,
            }

    def _format_result(self, state: WorkflowState) -> dict[str, Any]:
        """Format workflow state as result."""
        return {
            "success": state["status"] == "completed",
            "status": state["status"],
            "generated_code": state.get("generated_code"),
            "build_result": state.get("build_result"),
            "review_result": state.get("review_result"),
            "flash_result": state.get("flash_result"),
            "error": state.get("error"),
            "trace": state.get("trace", []),
        }

    async def resume(self, thread_id: str) -> dict[str, Any]:
        """
        Resume a paused workflow (e.g., after human approval).
        
        Args:
            thread_id: Workflow thread ID
            
        Returns:
            Updated workflow result
        """
        config = {"configurable": {"thread_id": thread_id}}
        
        current_state = self.graph.get_state(config)
        if not current_state:
            return {"error": "No workflow found with this thread_id"}
        
        if current_state["status"] != "waiting_review":
            return {"error": "Workflow is not waiting for review"}
        
        result = await self.graph.ainvoke(None, config)
        return self._format_result(result)

    def approve(self, thread_id: str) -> None:
        """
        Approve workflow to continue (e.g., after human review).
        
        Args:
            thread_id: Workflow thread ID
        """
        self.graph.update_state(
            config={"configurable": {"thread_id": thread_id}},
            values={"human_approved": True, "status": "running"},
        )

    def reject(self, thread_id: str, reason: str = "") -> None:
        """
        Reject workflow (e.g., human rejected flash).
        
        Args:
            thread_id: Workflow thread ID
            reason: Rejection reason
        """
        self.graph.update_state(
            config={"configurable": {"thread_id": thread_id}},
            values={"human_approved": False, "status": "failed", "error": reason},
        )

    def get_workflow_status(self, thread_id: str) -> Optional[dict[str, Any]]:
        """
        Get current workflow status.
        
        Args:
            thread_id: Workflow thread ID
            
        Returns:
            Current state or None
        """
        config = {"configurable": {"thread_id": thread_id}}
        state = self.graph.get_state(config)
        return dict(state) if state else None


class LangGraphOrchestrator:
    """
    LangGraph-based orchestrator replacing custom orchestration.
    
    Uses conditional edges for task routing instead of manual routing.
    """

    def __init__(
        self,
        agents: dict[str, Any] = None,
        model_router: Any = None,
    ):
        self.agents = agents or {}
        self.model_router = model_router
        self.langgraph_agent = LangGraphAgent(agents=agents)
        
        for agent_type, agent in self.agents.items():
            self.langgraph_agent.register_agent(agent_type, agent)

    async def process_task(self, task: Any) -> dict[str, Any]:
        """Process a task using LangGraph workflow."""
        return await self.langgraph_agent.execute(task)

    def route_task(self, task: Any) -> str:
        """
        Route task to appropriate agent type.
        
        Uses LLM for intelligent routing when available.
        """
        task_type = getattr(task, 'type', 'unknown').lower()
        
        if "codegen" in task_type or "generate" in task_type:
            return "code_gen"
        if "review" in task_type or "analyze" in task_type:
            return "review"
        if "security" in task_type or "vuln" in task_type:
            return "security"
        if "test" in task_type:
            return "test"
        if "build" in task_type or "flash" in task_type:
            return "devops"
        if "monitor" in task_type:
            return "monitoring"
        if "firmware" in task_type or "embedded" in task_type:
            return "firmware"
        
        return "orchestrator"


def create_langgraph_orchestrator(
    agents: dict[str, Any] = None,
    model_router: Any = None,
) -> LangGraphOrchestrator:
    """
    Factory function to create a LangGraph orchestrator.
    
    Args:
        agents: Dictionary of agent type -> agent instance
        model_router: LLM model router
        
    Returns:
        Configured LangGraphOrchestrator
    """
    return LangGraphOrchestrator(agents=agents, model_router=model_router)


__all__ = [
    "LangGraphAgent",
    "LangGraphOrchestrator",
    "create_langgraph_orchestrator",
]
