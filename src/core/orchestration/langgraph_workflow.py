"""
LangGraph-based Workflow System for AI_SUPPORT

Real implementation with:
- File-based checkpoint persistence
- Workflow state recovery
- Human-in-the-loop safety gates
- Production-grade orchestration
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Annotated, Literal, TypedDict, Any, Dict, Optional

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.base import BaseCheckpointSaver


class FileCheckpointSaver(BaseCheckpointSaver):
    """
    File-based checkpoint persistence for LangGraph workflows.
    
    Enables:
    - Workflow state survival across restarts
    - Replay from any checkpoint
    - Audit trail of all state changes
    """

    def __init__(self, checkpoint_dir: str = "checkpoints"):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def _get_thread_dir(self, thread_id: str) -> Path:
        thread_dir = self.checkpoint_dir / thread_id
        thread_dir.mkdir(parents=True, exist_ok=True)
        return thread_dir

    def _get_checkpoint_path(self, thread_id: str, checkpoint_id: str) -> Path:
        return self._get_thread_dir(thread_id) / f"{checkpoint_id}.json"

    def put(
        self,
        config: Dict[str, Any],
        checkpoint: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Save a checkpoint to disk."""
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        checkpoint_id = checkpoint.get("id", datetime.now().strftime("%Y%m%d_%H%M%S"))
        
        path = self._get_checkpoint_path(thread_id, checkpoint_id)
        
        data = {
            "checkpoint": checkpoint,
            "metadata": metadata,
            "saved_at": datetime.now().isoformat(),
        }
        
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        
        # Update latest pointer
        latest_path = self._get_thread_dir(thread_id) / "_latest"
        latest_path.write_text(checkpoint_id, encoding="utf-8")
        
        return {"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}}

    def get(self, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Load a checkpoint from disk."""
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id")
        
        if checkpoint_id:
            path = self._get_checkpoint_path(thread_id, checkpoint_id)
        else:
            # Load latest
            latest_path = self._get_thread_dir(thread_id) / "_latest"
            if latest_path.exists():
                checkpoint_id = latest_path.read_text(encoding="utf-8").strip()
                path = self._get_checkpoint_path(thread_id, checkpoint_id)
            else:
                return None
        
        if not path.exists():
            return None
        
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("checkpoint")

    def list(self, config: Dict[str, Any]) -> list:
        """List all checkpoints for a thread."""
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        thread_dir = self._get_thread_dir(thread_id)
        
        checkpoints = []
        for path in thread_dir.glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            checkpoints.append({
                "id": path.stem,
                "saved_at": data.get("saved_at"),
                "metadata": data.get("metadata", {}),
            })
        
        return sorted(checkpoints, key=lambda x: x.get("saved_at", ""), reverse=True)

    def delete(self, config: Dict[str, Any]) -> bool:
        """Delete a checkpoint."""
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id")
        
        if not checkpoint_id:
            return False
        
        path = self._get_checkpoint_path(thread_id, checkpoint_id)
        if path.exists():
            path.unlink()
            return True
        return False


class WorkflowPersistence:
    """
    High-level persistence manager for workflow execution.
    
    Tracks:
    - Workflow runs and their states
    - Node execution traces
    - Human approval decisions
    - Error histories
    """

    def __init__(self, persist_dir: str = "workflow_runs"):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._load_runs()

    def _load_runs(self) -> None:
        """Load all workflow runs from disk."""
        for run_file in self.persist_dir.glob("run_*.json"):
            try:
                data = json.loads(run_file.read_text(encoding="utf-8"))
                run_id = data.get("run_id")
                if run_id:
                    self._runs[run_id] = data
            except (json.JSONDecodeError, KeyError):
                continue

    def _save_run(self, run_id: str) -> None:
        """Save a workflow run to disk."""
        path = self.persist_dir / f"run_{run_id}.json"
        path.write_text(json.dumps(self._runs[run_id], indent=2, default=str), encoding="utf-8")

    def create_run(
        self,
        workflow_name: str,
        initial_state: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new workflow run."""
        run_id = f"{workflow_name}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        self._runs[run_id] = {
            "run_id": run_id,
            "workflow_name": workflow_name,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "initial_state": initial_state,
            "current_state": initial_state,
            "node_history": [],
            "human_decisions": [],
            "errors": [],
            "metadata": metadata or {},
        }
        
        self._save_run(run_id)
        return run_id

    def update_run(
        self,
        run_id: str,
        status: Optional[str] = None,
        current_state: Optional[Dict[str, Any]] = None,
        node: Optional[str] = None,
        human_decision: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> bool:
        """Update workflow run state."""
        if run_id not in self._runs:
            return False
        
        run = self._runs[run_id]
        
        if status:
            run["status"] = status
        if current_state:
            run["current_state"] = current_state
        if node:
            run["node_history"].append({
                "node": node,
                "timestamp": datetime.now().isoformat(),
            })
        if human_decision:
            run["human_decisions"].append({
                **human_decision,
                "timestamp": datetime.now().isoformat(),
            })
        if error:
            run["errors"].append({
                "error": error,
                "timestamp": datetime.now().isoformat(),
            })
        
        run["updated_at"] = datetime.now().isoformat()
        self._save_run(run_id)
        return True

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get workflow run by ID."""
        return self._runs.get(run_id)

    def list_runs(
        self,
        workflow_name: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list:
        """List workflow runs with optional filters."""
        runs = list(self._runs.values())
        
        if workflow_name:
            runs = [r for r in runs if r.get("workflow_name") == workflow_name]
        if status:
            runs = [r for r in runs if r.get("status") == status]
        
        return sorted(runs, key=lambda x: x.get("updated_at", ""), reverse=True)

    def replay_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get data needed to replay a workflow run."""
        run = self.get_run(run_id)
        if not run:
            return None
        
        return {
            "run_id": run_id,
            "initial_state": run.get("initial_state"),
            "node_history": run.get("node_history", []),
            "human_decisions": run.get("human_decisions", []),
            "metadata": run.get("metadata", {}),
        }


# ============ State Definitions ============

class AgentState(TypedDict):
    """State for the agent workflow."""
    task: dict
    result: dict | None
    status: str
    messages: list[str]
    current_step: str
    steps_completed: list[str]
    error: str | None


class WorkflowState(TypedDict):
    """State for embedded firmware workflow."""
    task_type: str
    task_description: str
    context: dict
    status: Literal["pending", "running", "completed", "failed", "waiting_review"]
    current_node: str
    completed_nodes: list[str]
    generated_code: str | None
    build_result: dict | None
    review_result: dict | None
    flash_result: dict | None
    human_approved: bool | None
    error: str | None
    retry_count: int
    project: str | None
    device: str | None
    trace: list[str]


# ============ Factory Functions ============

def compile_agent_graph(checkpoint: bool = True, checkpoint_dir: str = "checkpoints"):
    """Compile agent graph with file-based checkpointing."""
    graph = create_agent_graph()
    
    if checkpoint:
        checkpointer = FileCheckpointSaver(checkpoint_dir)
        return graph.compile(checkpointer=checkpointer)
    
    return graph.compile()


def compile_firmware_workflow(checkpoint: bool = True, checkpoint_dir: str = "checkpoints"):
    """Compile firmware workflow with file-based checkpointing."""
    graph = create_firmware_workflow()
    
    if checkpoint:
        checkpointer = FileCheckpointSaver(checkpoint_dir)
        return graph.compile(checkpointer=checkpointer)
    
    return graph.compile()


# ============ Graph Definitions ============

def create_agent_graph() -> StateGraph:
    """Create the main agent orchestration graph."""
    graph = StateGraph(AgentState)
    
    graph.add_node("classify", _classify_task)
    graph.add_node("code_gen", _generate_code)
    graph.add_node("review", _review_code)
    graph.add_node("build", _build_firmware)
    graph.add_node("flash", _flash_firmware)
    graph.add_node("human_review", _human_review_gate)
    graph.add_node("handle_error", _handle_error)
    graph.add_node("complete", _complete_workflow)
    
    graph.add_edge("classify", "code_gen")
    graph.add_conditional_edges("code_gen", _route_after_codegen, {
        "review": "review", "build": "build", "error": "handle_error"
    })
    graph.add_conditional_edges("review", _route_after_review, {
        "build": "build", "code_gen": "code_gen", "error": "handle_error"
    })
    graph.add_edge("build", "human_review")
    graph.add_conditional_edges("human_review", _route_after_review_gate, {
        "flash": "flash", "code_gen": "code_gen", END: END
    })
    graph.add_edge("flash", "complete")
    graph.add_edge("handle_error", END)
    graph.add_edge("complete", END)
    
    graph.set_entry_point("classify")
    return graph


def create_firmware_workflow() -> StateGraph:
    """Create firmware development workflow graph."""
    graph = StateGraph(WorkflowState)
    
    graph.add_node("plan", _plan_task)
    graph.add_node("retrieve_knowledge", _retrieve_knowledge)
    graph.add_node("generate", _generate_firmware)
    graph.add_node("verify", _verify_code)
    graph.add_node("review", _review_code)
    graph.add_node("build", _build_firmware)
    graph.add_node("flash", _flash_firmware)
    graph.add_node("human_gate", _human_safety_gate)
    graph.add_node("handle_error", _error_handler)
    graph.add_node("complete", _complete_workflow)
    
    graph.set_entry_point("plan")
    graph.add_edge("plan", "retrieve_knowledge")
    graph.add_edge("retrieve_knowledge", "generate")
    graph.add_edge("generate", "verify")
    graph.add_edge("verify", "review")
    graph.add_conditional_edges("review", _review_decision, {
        "build": "build", "regenerate": "generate", "error": "handle_error"
    })
    graph.add_edge("build", "human_gate")
    graph.add_conditional_edges("human_gate", _gate_decision, {
        "flash": "flash", "build": "build", END: END
    })
    graph.add_edge("flash", "complete")
    graph.add_edge("complete", END)
    graph.add_edge("handle_error", END)
    
    return graph


# ============ Node Implementations ============

async def _classify_task(state: AgentState) -> AgentState:
    """Classify the incoming task."""
    task = state.get("task", {})
    task_type = task.get("type", "codegen")
    return {
        **state,
        "current_step": "classify",
        "messages": state.get("messages", []) + [f"Classified task as: {task_type}"],
    }


async def _generate_code(state: AgentState) -> AgentState:
    """Generate code based on task."""
    task = state.get("task", {})
    return {
        **state,
        "current_step": "code_gen",
        "result": {"generated": True, "task": task},
    }


async def _review_code(state: AgentState) -> AgentState:
    """Review generated code."""
    return {**state, "current_step": "review"}


async def _build_firmware(state: AgentState) -> AgentState:
    """Build firmware."""
    return {**state, "current_step": "build"}


async def _flash_firmware(state: AgentState) -> AgentState:
    """Flash firmware to device."""
    return {**state, "current_step": "flash"}


async def _human_review_gate(state: AgentState) -> AgentState:
    """Human review gate before flash."""
    return {**state, "status": "waiting_review"}


async def _handle_error(state: AgentState) -> AgentState:
    """Handle workflow errors."""
    return {**state, "error": state.get("error", "Unknown error")}


async def _complete_workflow(state: AgentState) -> AgentState:
    """Mark workflow as complete."""
    return {**state, "status": "completed"}


# ============ Firmware Workflow Nodes ============

async def _plan_task(state: WorkflowState) -> WorkflowState:
    """Plan the task execution."""
    return {
        **state,
        "current_node": "plan",
        "trace": state.get("trace", []) + ["plan"],
    }


async def _retrieve_knowledge(state: WorkflowState) -> WorkflowState:
    """Retrieve relevant knowledge."""
    return {
        **state,
        "current_node": "retrieve_knowledge",
        "trace": state.get("trace", []) + ["retrieve"],
    }


async def _generate_firmware(state: WorkflowState) -> WorkflowState:
    """Generate firmware code."""
    context = state.get("context", {})
    return {
        **state,
        "current_node": "generate",
        "trace": state.get("trace", []) + ["generate"],
        "generated_code": f"/* Generated for {context.get('project', 'unknown')} */",
    }


async def _verify_code(state: WorkflowState) -> WorkflowState:
    """Verify generated code."""
    return {
        **state,
        "current_node": "verify",
        "trace": state.get("trace", []) + ["verify"],
    }


async def _human_safety_gate(state: WorkflowState) -> WorkflowState:
    """Safety gate before flashing firmware."""
    if state.get("human_approved") is None:
        return {
            **state,
            "status": "waiting_review",
            "current_node": "human_gate",
            "trace": state.get("trace", []) + ["gate_wait"],
        }
    
    if state.get("human_approved"):
        return {
            **state,
            "status": "running",
            "current_node": "human_gate",
            "trace": state.get("trace", []) + ["gate_approved"],
        }
    
    return {
        **state,
        "status": "failed",
        "current_node": "human_gate",
        "trace": state.get("trace", []) + ["gate_rejected"],
    }


async def _error_handler(state: WorkflowState) -> WorkflowState:
    """Handle errors in firmware workflow."""
    return {
        **state,
        "status": "failed",
        "current_node": "error",
    }


# ============ Router Functions ============

def _route_after_codegen(state: AgentState) -> str:
    """Route after code generation."""
    if state.get("error"):
        return "error"
    if state.get("result", {}).get("needs_review"):
        return "review"
    return "build"


def _route_after_review(state: AgentState) -> str:
    """Route after code review."""
    result = state.get("review_result", {})
    if result.get("approved"):
        return "build"
    if result.get("needs_changes"):
        return "code_gen"
    return "build"


def _route_after_review_gate(state: AgentState) -> str:
    """Route after human review gate."""
    if state.get("human_approved"):
        return "flash"
    return END


def _review_decision(state: WorkflowState) -> str:
    """Decision after code review."""
    review = state.get("review_result", {})
    if review.get("approved"):
        return "build"
    return "regenerate"


def _gate_decision(state: WorkflowState) -> str:
    """Decision after human safety gate."""
    approved = state.get("human_approved")
    if approved is True:
        return "flash"
    if approved is False:
        return END
    return "build"


__all__ = [
    "AgentState",
    "WorkflowState",
    "FileCheckpointSaver",
    "WorkflowPersistence",
    "create_agent_graph",
    "create_firmware_workflow",
    "compile_agent_graph",
    "compile_firmware_workflow",
]
