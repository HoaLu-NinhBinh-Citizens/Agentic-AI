"""Unit tests for Agent Runtime Kernel - Phase 5.6."""

import asyncio
import pytest

from core.agent_runtime import (
    AgentLifecycle,
    AgentState,
    LifecycleEvent,
    AgentSandbox,
    SandboxConfig,
    SandboxPermission,
    ResourceQuota,
    DeterministicFSM,
    FSMState,
    FSMAction,
    AgentScheduler,
    SchedulingPolicy,
    PriorityLevel,
    FailureIsolation,
    ErrorSeverity,
    ErrorCategory,
)


class TestAgentLifecycle:
    """Tests for AgentLifecycle."""

    @pytest.mark.asyncio
    async def test_initial_state(self):
        """Test lifecycle starts in CREATED state."""
        lifecycle = AgentLifecycle("agent1")
        assert lifecycle.state == AgentState.CREATED
        assert lifecycle.agent_id == "agent1"

    @pytest.mark.asyncio
    async def test_spawn_transition(self):
        """Test spawn transitions to INITIALIZING."""
        lifecycle = AgentLifecycle("agent1")
        result = await lifecycle.spawn()
        assert result is True
        assert lifecycle.state == AgentState.INITIALIZING

    @pytest.mark.asyncio
    async def test_start_transition(self):
        """Test start transitions to RUNNING."""
        lifecycle = AgentLifecycle("agent1")
        await lifecycle.spawn()
        result = await lifecycle.start()
        assert result is True
        assert lifecycle.state == AgentState.RUNNING

    @pytest.mark.asyncio
    async def test_suspend_transition(self):
        """Test suspend transitions to SUSPENDED."""
        lifecycle = AgentLifecycle("agent1")
        await lifecycle.spawn()
        await lifecycle.start()
        result = await lifecycle.suspend()
        assert result is True
        assert lifecycle.state == AgentState.SUSPENDED

    @pytest.mark.asyncio
    async def test_resume_transition(self):
        """Test resume transitions back to RUNNING."""
        lifecycle = AgentLifecycle("agent1")
        await lifecycle.spawn()
        await lifecycle.start()
        await lifecycle.suspend()
        result = await lifecycle.resume()
        assert result is True
        assert lifecycle.state == AgentState.RUNNING

    @pytest.mark.asyncio
    async def test_invalid_transition(self):
        """Test invalid transition is rejected."""
        lifecycle = AgentLifecycle("agent1")
        result = await lifecycle.suspend()
        assert result is False

    @pytest.mark.asyncio
    async def test_checkpoint(self):
        """Test checkpoint creation."""
        lifecycle = AgentLifecycle("agent1")
        await lifecycle.spawn()
        await lifecycle.start()
        lifecycle.increment_step()

        checkpoint = await lifecycle.checkpoint()
        assert checkpoint.agent_id == "agent1"
        assert checkpoint.step == 1

    @pytest.mark.asyncio
    async def test_context_update(self):
        """Test context updates."""
        lifecycle = AgentLifecycle("agent1")
        lifecycle.update_context("key1", "value1")
        assert lifecycle.context["key1"] == "value1"


class TestAgentSandbox:
    """Tests for AgentSandbox."""

    @pytest.mark.asyncio
    async def test_tool_permission_allowed(self):
        """Test allowed tool is permitted."""
        sandbox = AgentSandbox()
        result = await sandbox.check_tool_permission("read_file")
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_tool_permission_denied(self):
        """Test denied tool is rejected."""
        config = SandboxConfig(denied_tools=["delete_all"])
        sandbox = AgentSandbox(config)
        result = await sandbox.check_tool_permission("delete_all")
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_tool_permission_allowed_list(self):
        """Test allowed tools list."""
        config = SandboxConfig(allowed_tools=["read", "write"])
        sandbox = AgentSandbox(config)
        assert (await sandbox.check_tool_permission("read")).allowed is True
        assert (await sandbox.check_tool_permission("delete")).allowed is False

    @pytest.mark.asyncio
    async def test_record_tool_call(self):
        """Test recording tool calls."""
        sandbox = AgentSandbox()
        result = await sandbox.record_tool_call("test_tool", 100)
        assert result is True
        stats = sandbox.get_stats()
        assert stats["tool_calls"] == 1
        assert stats["tokens_used"] == 100

    @pytest.mark.asyncio
    async def test_quota_exceeded(self):
        """Test quota enforcement."""
        config = SandboxConfig(quota=ResourceQuota(max_tool_calls=2))
        sandbox = AgentSandbox(config)
        await sandbox.record_tool_call("tool1")
        await sandbox.record_tool_call("tool2")
        result = await sandbox.check_tool_permission("tool3")
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_stats(self):
        """Test sandbox statistics."""
        sandbox = AgentSandbox()
        sandbox.start()
        await sandbox.record_tool_call("tool1", 50)

        stats = sandbox.get_stats()
        assert stats["tool_calls"] == 1
        assert stats["tokens_used"] == 50


class TestDeterministicFSM:
    """Tests for DeterministicFSM."""

    @pytest.mark.asyncio
    async def test_initial_state(self):
        """Test FSM starts in IDLE state."""
        fsm = DeterministicFSM()
        assert fsm.state == FSMState.IDLE

    @pytest.mark.asyncio
    async def test_start_action(self):
        """Test START action transitions to RUNNING."""
        fsm = DeterministicFSM()
        success, _ = await fsm.execute_action(FSMAction.START)
        assert success is True
        assert fsm.state == FSMState.RUNNING

    @pytest.mark.asyncio
    async def test_pause_action(self):
        """Test PAUSE action from RUNNING."""
        fsm = DeterministicFSM()
        await fsm.execute_action(FSMAction.START)
        success, _ = await fsm.execute_action(FSMAction.PAUSE)
        assert success is True
        assert fsm.state == FSMState.PAUSED

    @pytest.mark.asyncio
    async def test_invalid_action(self):
        """Test invalid action is rejected."""
        fsm = DeterministicFSM()
        success, msg = await fsm.execute_action(FSMAction.PAUSE)
        assert success is False
        assert "Invalid action" in msg

    @pytest.mark.asyncio
    async def test_action_logging(self):
        """Test action logging."""
        fsm = DeterministicFSM()
        entry = await fsm.log_action("test_action", {"arg": "value"}, "result")
        assert entry.action_type == "test_action"
        assert len(fsm.action_log) == 1

    @pytest.mark.asyncio
    async def test_replay(self):
        """Test action replay."""
        fsm = DeterministicFSM()
        await fsm.log_action("action1", {}, "result1")
        await fsm.log_action("action2", {}, "result2")

        success, msg, entries = await fsm.replay(from_index=0)
        assert success is True
        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_idempotency_verification(self):
        """Test idempotency check."""
        fsm = DeterministicFSM()
        await fsm.log_action("action1", {"id": "1"}, "result1")
        await fsm.log_action("action1", {"id": "2"}, "result2")

        is_idempotent, issues = fsm.verify_idempotency()
        assert is_idempotent is True


class TestAgentScheduler:
    """Tests for AgentScheduler."""

    @pytest.mark.asyncio
    async def test_submit_task(self):
        """Test submitting a task."""
        scheduler = AgentScheduler()
        result = await scheduler.submit("task1", {"data": "value"}, PriorityLevel.NORMAL)
        assert result.success is True
        assert result.position == 1

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """Test priority ordering."""
        scheduler = AgentScheduler(policy=SchedulingPolicy.PRIORITY)
        await scheduler.submit("task_low", "low", PriorityLevel.LOW)
        await scheduler.submit("task_high", "high", PriorityLevel.HIGH)
        await scheduler.submit("task_normal", "normal", PriorityLevel.NORMAL)

        task = await scheduler.next()
        assert task.priority == PriorityLevel.HIGH

    @pytest.mark.asyncio
    async def test_fifo_ordering(self):
        """Test FIFO ordering."""
        scheduler = AgentScheduler(policy=SchedulingPolicy.FIFO)
        await scheduler.submit("task1", "first")
        await scheduler.submit("task2", "second")

        task = await scheduler.next()
        assert task.task_id == "task1"

    @pytest.mark.asyncio
    async def test_backpressure_threshold(self):
        """Test backpressure activation when queue exceeds threshold."""
        scheduler = AgentScheduler(max_queue_size=4, backpressure_threshold=0.5)

        for i in range(3):
            await scheduler.submit(f"task{i}", "data", PriorityLevel.NORMAL)

        scheduler._update_backpressure()
        assert scheduler.backpressure_active is True

    @pytest.mark.asyncio
    async def test_cancel_task(self):
        """Test task cancellation."""
        scheduler = AgentScheduler()
        await scheduler.submit("task1", "data")
        result = await scheduler.cancel("task1")
        assert result is True

    @pytest.mark.asyncio
    async def test_stats(self):
        """Test scheduler statistics."""
        scheduler = AgentScheduler()
        await scheduler.submit("task1", "data")
        await scheduler.submit("task2", "data")

        stats = await scheduler.get_stats()
        assert stats["total_scheduled"] == 2
        assert stats["pending"] == 2


class TestFailureIsolation:
    """Tests for FailureIsolation."""

    @pytest.mark.asyncio
    async def test_error_classification(self):
        """Test error classification."""
        isolation = FailureIsolation()

        timeout_error = TimeoutError("Connection timed out")
        info = isolation.classify_error(timeout_error)
        assert info.category == ErrorCategory.TIMEOUT
        assert info.severity == ErrorSeverity.MEDIUM

    @pytest.mark.asyncio
    async def test_create_boundary(self):
        """Test creating isolation boundary."""
        isolation = FailureIsolation()
        boundary = await isolation.create_boundary("agent1")
        assert boundary.agent_id == "agent1"
        assert len(boundary.errors) == 0

    @pytest.mark.asyncio
    async def test_record_error(self):
        """Test recording errors."""
        isolation = FailureIsolation()
        await isolation.create_boundary("agent1")

        error = ValueError("Test error")
        info = await isolation.record_error("agent1", error)
        assert info.severity == ErrorSeverity.MEDIUM

    @pytest.mark.asyncio
    async def test_isolation_threshold(self):
        """Test isolation after threshold."""
        isolation = FailureIsolation(max_retries=3, isolation_threshold=3)

        await isolation.create_boundary("agent1")

        for _ in range(3):
            error = RuntimeError("Test error")
            await isolation.record_error("agent1", error)

        should_isolate = await isolation.should_isolate("agent1")
        assert should_isolate is True

    @pytest.mark.asyncio
    async def test_retry_boundary(self):
        """Test retry boundary management."""
        isolation = FailureIsolation(max_retries=3)
        await isolation.create_boundary("agent1")

        can_retry1, _ = await isolation.can_retry("agent1")
        assert can_retry1 is True

        for _ in range(3):
            recorded = await isolation.record_retry("agent1")
            assert recorded is True

        can_retry2, _ = await isolation.can_retry("agent1")
        assert can_retry2 is False

    @pytest.mark.asyncio
    async def test_reset(self):
        """Test resetting isolation."""
        isolation = FailureIsolation()
        await isolation.create_boundary("agent1")

        error = RuntimeError("Test error")
        await isolation.record_error("agent1", error)
        await isolation.record_retry("agent1")

        await isolation.reset("agent1")
        boundary = await isolation.get_boundary("agent1")
        assert len(boundary.errors) == 0

    @pytest.mark.asyncio
    async def test_stats(self):
        """Test failure isolation statistics."""
        isolation = FailureIsolation()
        await isolation.create_boundary("agent1")

        error = ValueError("Test error")
        await isolation.record_error("agent1", error)

        stats = await isolation.get_stats()
        assert stats["total_errors"] == 1
        assert stats["total_boundaries"] == 1
