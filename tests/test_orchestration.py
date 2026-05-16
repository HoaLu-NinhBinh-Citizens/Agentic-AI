"""
Unit Tests for AI_support Orchestration Module - LangGraph Version
"""

import asyncio

import pytest


# ============ TaskQueue Tests ============

class TestTaskQueue:
    """Tests for priority task queue."""

    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self):
        """Test basic enqueue/dequeue."""
        from src.orchestration import TaskQueue, Priority

        queue = TaskQueue()

        await queue.enqueue("task1", {"data": 1}, priority=Priority.NORMAL)
        await queue.enqueue("task2", {"data": 2}, priority=Priority.HIGH)

        # High priority should come first
        task = await queue.dequeue()
        assert task.name == "task2"

        task = await queue.dequeue()
        assert task.name == "task1"

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """Test priority ordering."""
        from src.orchestration import TaskQueue, Priority

        queue = TaskQueue()

        await queue.enqueue("low", {"p": "low"}, priority=Priority.LOW)
        await queue.enqueue("critical", {"p": "critical"}, priority=Priority.CRITICAL)
        await queue.enqueue("normal", {"p": "normal"}, priority=Priority.NORMAL)
        await queue.enqueue("high", {"p": "high"}, priority=Priority.HIGH)

        names = []
        while not queue.is_empty():
            task = await queue.dequeue()
            names.append(task.name)

        assert names == ["critical", "high", "normal", "low"]

    @pytest.mark.asyncio
    async def test_batch_dequeue(self):
        """Test batch dequeue."""
        from src.orchestration import TaskQueue, Priority

        queue = TaskQueue()

        for i in range(5):
            await queue.enqueue(f"task{i}", {"i": i})

        tasks = await queue.dequeue_batch(3)
        assert len(tasks) == 3

        remaining = await queue.dequeue_batch(10)
        assert len(remaining) == 2

    @pytest.mark.asyncio
    async def test_requeue(self):
        """Test task requeue."""
        from src.orchestration import TaskQueue, Priority

        queue = TaskQueue()

        task = await queue.enqueue("task1", {"data": 1}, retries=3)
        dequeued = await queue.dequeue()

        await queue.requeue(dequeued)

        # Should be able to dequeue again
        requeued = await queue.dequeue()
        assert requeued.id == task.id
        assert requeued.retries == 2  # Decremented

    def test_queue_stats(self):
        """Test queue statistics."""
        from src.orchestration import TaskQueue, Priority

        queue = TaskQueue()

        # Sync enqueue for stats
        asyncio.run(queue.enqueue("t1", {}, priority=Priority.HIGH))
        asyncio.run(queue.enqueue("t2", {}, priority=Priority.LOW))

        stats = queue.get_stats()
        assert stats["size"] == 2
        assert stats["priority_counts"]["high"] == 1
        assert stats["priority_counts"]["low"] == 1


# ============ LangGraph Workflow Tests ============

class TestLangGraphWorkflow:
    """Tests for LangGraph workflow system."""

    def test_agent_state_definition(self):
        """Test AgentState is properly defined."""
        from src.orchestration import AgentState

        state: AgentState = {
            "task": {"type": "codegen", "description": "test"},
            "result": None,
            "status": "pending",
            "messages": [],
            "current_step": "",
            "steps_completed": [],
            "error": None,
        }

        assert state["task"]["type"] == "codegen"
        assert state["status"] == "pending"

    def test_workflow_state_definition(self):
        """Test WorkflowState is properly defined."""
        from src.orchestration import WorkflowState

        state: WorkflowState = {
            "task_type": "firmware",
            "task_description": "Generate UART driver",
            "context": {},
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
            "project": "EngineCar",
            "device": None,
            "trace": [],
        }

        assert state["task_type"] == "firmware"
        assert state["project"] == "EngineCar"

    def test_create_agent_graph(self):
        """Test agent graph creation."""
        from src.orchestration import create_agent_graph

        graph = create_agent_graph()
        assert graph is not None

    def test_create_firmware_workflow(self):
        """Test firmware workflow creation."""
        from src.orchestration import create_firmware_workflow

        graph = create_firmware_workflow()
        assert graph is not None

    def test_compile_agent_graph(self):
        """Test compiling agent graph."""
        from src.orchestration import compile_agent_graph

        compiled = compile_agent_graph(checkpoint=True)
        assert compiled is not None

    def test_compile_firmware_workflow(self):
        """Test compiling firmware workflow."""
        from src.orchestration import compile_firmware_workflow

        compiled = compile_firmware_workflow(checkpoint=True)
        assert compiled is not None


class TestLangGraphAgent:
    """Tests for LangGraph agent integration."""

    def test_langgraph_agent_creation(self):
        """Test LangGraphAgent can be created."""
        from src.orchestration import LangGraphAgent

        agent = LangGraphAgent(enable_checkpoint=True)
        assert agent is not None
        assert agent.graph is not None

    def test_langgraph_orchestrator_creation(self):
        """Test LangGraphOrchestrator can be created."""
        from src.orchestration import create_langgraph_orchestrator

        orchestrator = create_langgraph_orchestrator()
        assert orchestrator is not None

    @pytest.mark.asyncio
    async def test_workflow_initialization(self):
        """Test workflow initializes correctly."""
        from src.orchestration import LangGraphAgent
        from src.multi_agent import Task

        agent = LangGraphAgent()

        task = Task(
            type="codegen",
            description="Generate test code",
            context={"project": "EngineCar"},
        )

        # Workflow should initialize (not crash)
        result = await agent.execute(task)
        # Result should have expected keys
        assert "success" in result
        assert "status" in result or "error" in result


# ============ Rollback Tests ============

class TestRollback:
    """Tests for rollback/compensation system."""

    def test_rollback_policy_enum(self):
        """Test rollback policy enum values."""
        from src.orchestration import RollbackPolicy

        assert RollbackPolicy.ABORT.value == "abort"
        assert RollbackPolicy.COMPENSATE.value == "compensate"
        assert RollbackPolicy.IGNORE.value == "ignore"

    def test_rollback_engine_creation(self):
        """Test rollback engine can be created."""
        from src.orchestration import RollbackEngine, RollbackPolicy

        engine = RollbackEngine(default_policy=RollbackPolicy.COMPENSATE)
        assert engine is not None
        assert engine.default_policy == RollbackPolicy.COMPENSATE

    def test_checkpoint_creation(self):
        """Test checkpoint can be created."""
        from src.orchestration import Checkpoint
        from datetime import datetime
        from uuid import uuid4

        checkpoint = Checkpoint(
            id=str(uuid4())[:16],
            workflow_id="wf-1",
            step_id="step-1",
            timestamp=datetime.now(),
            step_output={"result": "test"},
            workflow_variables={"var": "value"},
        )

        assert checkpoint.workflow_id == "wf-1"
        assert checkpoint.step_id == "step-1"
        assert checkpoint.step_output["result"] == "test"

    def test_rollback_context_creation(self):
        """Test rollback context can be created."""
        from src.orchestration import RollbackContext

        context = RollbackContext(workflow_id="wf-1")
        assert context.workflow_id == "wf-1"
        assert len(context.completed_steps) == 0

        context.mark_completed("step-1")
        assert "step-1" in context.completed_steps
        assert context.get_reverse_order() == ["step-1"]

    def test_compensation_status_enum(self):
        """Test compensation status enum values."""
        from src.orchestration import CompensationStatus

        assert CompensationStatus.PENDING.value == "pending"
        assert CompensationStatus.COMPLETED.value == "completed"
        assert CompensationStatus.FAILED.value == "failed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
