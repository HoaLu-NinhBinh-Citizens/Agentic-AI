"""Test infrastructure for Phase 5B Enterprise tests.

Provides shared fixtures for:
- Async event loops
- Planner components
- Workflow enterprise components
- Mock factories
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Generator
import pytest
import pytest_asyncio

# Add src to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default asyncio event loop policy."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def anyio_backend():
    """Configure anyio backend for async tests."""
    return "asyncio"


# ============================================================================
# Planner Fixtures
# ============================================================================

@pytest.fixture
def sample_goal() -> str:
    """Sample planning goal."""
    return "Build a REST API with authentication"


@pytest.fixture
def sample_context() -> dict[str, Any]:
    """Sample planning context."""
    return {
        "project_type": "web_api",
        "language": "python",
        "framework": "fastapi",
        "requirements": ["auth", "database", "validation"],
    }


@pytest.fixture
def sample_plan_graph_data() -> dict[str, Any]:
    """Sample plan graph data."""
    return {
        "plan_id": "plan-001",
        "goal": "Build REST API",
        "nodes": [
            {
                "node_id": "root",
                "task_type": "task",
                "description": "Root task",
                "depends_on": [],
                "branch_options": [],
                "condition_expr": None,
                "join_policy": None,
                "estimated_cost": 1.0,
                "estimated_duration_seconds": 10.0,
            },
            {
                "node_id": "task1",
                "task_type": "task",
                "description": "Task 1",
                "depends_on": ["root"],
                "branch_options": [],
                "condition_expr": None,
                "join_policy": None,
                "estimated_cost": 2.0,
                "estimated_duration_seconds": 20.0,
            },
            {
                "node_id": "task2",
                "task_type": "task",
                "description": "Task 2",
                "depends_on": ["root"],
                "branch_options": [],
                "condition_expr": None,
                "join_policy": None,
                "estimated_cost": 2.0,
                "estimated_duration_seconds": 20.0,
            },
            {
                "node_id": "join1",
                "task_type": "join",
                "description": "Join after parallel tasks",
                "depends_on": ["task1", "task2"],
                "branch_options": [],
                "condition_expr": None,
                "join_policy": "ALL_COMPLETE",
                "estimated_cost": 0.0,
                "estimated_duration_seconds": 0.0,
            },
        ],
        "root_node_id": "root",
    }


@pytest.fixture
def cyclic_plan_graph_data() -> dict[str, Any]:
    """Plan graph with cycle for deadlock testing."""
    return {
        "plan_id": "plan-cycle",
        "goal": "Cyclic Plan",
        "nodes": [
            {
                "node_id": "a",
                "task_type": "task",
                "description": "Task A",
                "depends_on": ["c"],
                "branch_options": [],
                "condition_expr": None,
                "join_policy": None,
                "estimated_cost": 1.0,
                "estimated_duration_seconds": 10.0,
            },
            {
                "node_id": "b",
                "task_type": "task",
                "description": "Task B",
                "depends_on": ["a"],
                "branch_options": [],
                "condition_expr": None,
                "join_policy": None,
                "estimated_cost": 1.0,
                "estimated_duration_seconds": 10.0,
            },
            {
                "node_id": "c",
                "task_type": "task",
                "description": "Task C",
                "depends_on": ["b"],
                "branch_options": [],
                "condition_expr": None,
                "join_policy": None,
                "estimated_cost": 1.0,
                "estimated_duration_seconds": 10.0,
            },
        ],
        "root_node_id": "a",
    }


@pytest.fixture
def orphan_plan_graph_data() -> dict[str, Any]:
    """Plan graph with orphan tasks."""
    return {
        "plan_id": "plan-orphan",
        "goal": "Plan with Orphans",
        "nodes": [
            {
                "node_id": "root",
                "task_type": "task",
                "description": "Root",
                "depends_on": [],
                "branch_options": [],
                "condition_expr": None,
                "join_policy": None,
                "estimated_cost": 1.0,
                "estimated_duration_seconds": 10.0,
            },
            {
                "node_id": "orphan",
                "task_type": "task",
                "description": "Orphan Task",
                "depends_on": [],
                "branch_options": [],
                "condition_expr": None,
                "join_policy": None,
                "estimated_cost": 1.0,
                "estimated_duration_seconds": 10.0,
            },
        ],
        "root_node_id": "root",
    }


# ============================================================================
# Workflow Enterprise Fixtures
# ============================================================================

@pytest.fixture
def sample_workflow_id() -> str:
    """Sample workflow ID."""
    return "wf-test-001"


@pytest.fixture
def sample_activity_id() -> str:
    """Sample activity ID."""
    return "act-test-001"


@pytest.fixture
def sample_worker_id() -> str:
    """Sample worker ID."""
    return "worker-001"


@pytest.fixture
def sample_tenant_id() -> str:
    """Sample tenant ID."""
    return "tenant-test-001"


@pytest.fixture
def sample_event_data() -> list[dict[str, Any]]:
    """Sample workflow events for hash chain testing."""
    return [
        {"event_id": "e1", "sequence": 0, "event_type": "workflow_started", "data": {"initiated_by": "user1"}},
        {"event_id": "e2", "sequence": 1, "event_type": "task_scheduled", "data": {"task_id": "task1"}},
        {"event_id": "e3", "sequence": 2, "event_type": "task_completed", "data": {"task_id": "task1", "result": "success"}},
        {"event_id": "e4", "sequence": 3, "event_type": "workflow_completed", "data": {"outcome": "success"}},
    ]


@pytest.fixture
def sample_tool_output() -> dict[str, Any]:
    """Sample tool output."""
    return {
        "status": "success",
        "data": {"result": "file_created", "path": "/tmp/test.txt"},
        "metadata": {"execution_time_ms": 100},
    }


# ============================================================================
# Schema Fixtures
# ============================================================================

@pytest.fixture
def schema_v1() -> dict[str, Any]:
    """Schema version 1."""
    return {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "action": {"type": "string"},
        },
        "required": ["user_id", "action"],
    }


@pytest.fixture
def schema_v2() -> dict[str, Any]:
    """Schema version 2 with new fields."""
    return {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "action": {"type": "string"},
            "tenant": {"type": "string"},
            "metadata": {"type": "object"},
        },
        "required": ["user_id", "action", "tenant"],
    }


@pytest.fixture
def invalid_schema() -> dict[str, Any]:
    """Invalid schema for negative testing."""
    return {
        "type": "object",
        "properties": {
            "count": {"type": "integer"},
            "enabled": {"type": "boolean"},
        },
        "required": ["count", "enabled", "missing_field"],
    }


# ============================================================================
# Mock Factories
# ============================================================================

class MockIdempotencyRecord:
    """Mock idempotency record for testing."""
    
    def __init__(self, key: str, result: Any = None):
        self.key = key
        self.result = result or {"status": "completed", "data": "test"}
        self.call_count = 0
    
    def get_result(self) -> Any:
        self.call_count += 1
        return self.result


class MockCompensationFn:
    """Mock compensation function for testing."""
    
    def __init__(self, should_fail: bool = False, delay: float = 0.0):
        self.should_fail = should_fail
        self.delay = delay
        self.call_count = 0
        self.calls: list[tuple[Any, Any]] = []
    
    async def __call__(self, original_input: Any, original_output: Any) -> Any:
        import asyncio
        self.call_count += 1
        self.calls.append((original_input, original_output))
        
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        
        if self.should_fail:
            raise RuntimeError("Compensation failed")
        
        return {"compensated": True, "original_input": original_input}


# ============================================================================
# Async Test Utilities
# ============================================================================

async def run_with_timeout(coro, timeout_seconds: float = 5.0) -> Any:
    """Run coroutine with timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        pytest.fail(f"Test timed out after {timeout_seconds} seconds")


async def simulate_time_passing(seconds: float) -> None:
    """Simulate time passing in tests."""
    await asyncio.sleep(seconds)
