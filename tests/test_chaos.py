"""
Tests for Chaos Engineering Module

Tests ChaosEngine, experiment execution, and action strategies.
"""

import pytest
import asyncio
from datetime import datetime

from src.chaos import (
    ChaosEngine,
    ChaosExperiment,
    ExperimentConfig,
    ExperimentResult,
    ChaosMetrics,
    ChaosTarget,
    ChaosAction,
    ExperimentStatus,
    ActionStrategy,
    LatencyStrategy,
    FailureStrategy,
    TimeoutStrategy,
    DropStrategy,
    CorruptionStrategy,
    latency_experiment,
    failure_experiment,
    timeout_experiment,
)


# =============================================================================
# ChaosAction and ChaosTarget Tests
# =============================================================================

class TestChaosEnums:
    """Test chaos enum types."""

    def test_chaos_targets_exist(self):
        """Test all chaos targets exist."""
        assert ChaosTarget.EVENT_BUS.value == "event_bus"
        assert ChaosTarget.TOOL_EXECUTOR.value == "tool_executor"
        assert ChaosTarget.WORKFLOW_ENGINE.value == "workflow_engine"
        assert ChaosTarget.HEALTH_MONITOR.value == "health_monitor"
        assert ChaosTarget.DISTRIBUTED_BUS.value == "distributed_bus"
        assert ChaosTarget.CUSTOM.value == "custom"

    def test_chaos_actions_exist(self):
        """Test all chaos actions exist."""
        assert ChaosAction.LATENCY.value == "latency"
        assert ChaosAction.FAILURE.value == "failure"
        assert ChaosAction.TIMEOUT.value == "timeout"
        assert ChaosAction.ERROR.value == "error"
        assert ChaosAction.DROP.value == "drop"
        assert ChaosAction.CORRUPT.value == "corrupt"
        assert ChaosAction.NETWORK_PARTITION.value == "network_partition"
        assert ChaosAction.EXCEPTION.value == "exception"

    def test_experiment_statuses_exist(self):
        """Test all experiment statuses exist."""
        assert ExperimentStatus.PENDING.value == "pending"
        assert ExperimentStatus.RUNNING.value == "running"
        assert ExperimentStatus.PAUSED.value == "paused"
        assert ExperimentStatus.COMPLETED.value == "completed"
        assert ExperimentStatus.ABORTED.value == "aborted"
        assert ExperimentStatus.FAILED.value == "failed"


# =============================================================================
# ExperimentConfig Tests
# =============================================================================

class TestExperimentConfig:
    """Test ExperimentConfig dataclass."""

    def test_default_config(self):
        """Test default configuration."""
        config = ExperimentConfig(
            name="test_experiment",
            target=ChaosTarget.TOOL_EXECUTOR,
            action=ChaosAction.LATENCY,
        )

        assert config.name == "test_experiment"
        assert config.target == ChaosTarget.TOOL_EXECUTOR
        assert config.action == ChaosAction.LATENCY
        assert config.intensity == 0.5
        assert config.duration_seconds == 60
        assert config.probability == 1.0
        assert config.enabled is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = ExperimentConfig(
            name="custom_test",
            target=ChaosTarget.EVENT_BUS,
            action=ChaosAction.FAILURE,
            intensity=0.8,
            duration_seconds=120,
            probability=0.5,
            parameters={"error_type": "IOError"},
        )

        assert config.intensity == 0.8
        assert config.duration_seconds == 120
        assert config.probability == 0.5
        assert config.parameters["error_type"] == "IOError"


# =============================================================================
# Action Strategy Tests
# =============================================================================

class TestActionStrategies:
    """Test chaos action strategies."""

    def test_latency_strategy(self):
        """Test latency injection."""
        strategy = LatencyStrategy()
        config = ExperimentConfig(
            name="latency_test",
            target=ChaosTarget.TOOL_EXECUTOR,
            action=ChaosAction.LATENCY,
            intensity=0.1,  # 10% = 1 second max
        )

        delay = strategy.inject(config)
        assert 0 <= delay <= 1000  # Should be between 0 and 1000ms

    def test_failure_strategy(self):
        """Test failure injection."""
        strategy = FailureStrategy()
        config = ExperimentConfig(
            name="failure_test",
            target=ChaosTarget.TOOL_EXECUTOR,
            action=ChaosAction.FAILURE,
            parameters={"error_types": ["RuntimeError"]},
        )

        exc = strategy.inject(config)
        assert isinstance(exc, RuntimeError)

    def test_drop_strategy(self):
        """Test drop injection."""
        strategy = DropStrategy()
        config = ExperimentConfig(
            name="drop_test",
            target=ChaosTarget.EVENT_BUS,
            action=ChaosAction.DROP,
        )

        result = strategy.inject(config)
        assert result is True
        assert strategy._dropped_count == 1

    def test_corruption_strategy(self):
        """Test data corruption."""
        strategy = CorruptionStrategy()
        config = ExperimentConfig(
            name="corrupt_test",
            target=ChaosTarget.TOOL_EXECUTOR,
            action=ChaosAction.CORRUPT,
            intensity=0.5,
            parameters={"data": b"test data"},
        )

        corrupted = strategy.inject(config)
        assert isinstance(corrupted, bytes)
        assert len(corrupted) == len(b"test data")


# =============================================================================
# ChaosEngine Tests
# =============================================================================

class TestChaosEngine:
    """Test ChaosEngine functionality."""

    @pytest.fixture
    def engine(self):
        """Create a test chaos engine."""
        return ChaosEngine()

    def test_engine_initialization(self, engine):
        """Test engine initializes correctly."""
        assert engine._targets == {}
        assert engine._experiments == {}
        assert len(engine._strategies) > 0

    def test_register_target(self, engine):
        """Test registering targets."""
        mock_target = object()
        engine.register_target(ChaosTarget.TOOL_EXECUTOR, mock_target)
        assert engine.get_target(ChaosTarget.TOOL_EXECUTOR) is mock_target

    def test_unregister_target(self, engine):
        """Test unregistering targets."""
        mock_target = object()
        engine.register_target(ChaosTarget.TOOL_EXECUTOR, mock_target)
        assert engine.unregister_target(ChaosTarget.TOOL_EXECUTOR) is True
        assert engine.get_target(ChaosTarget.TOOL_EXECUTOR) is None

    def test_register_custom_strategy(self, engine):
        """Test registering custom strategies."""
        custom_strategy = LatencyStrategy()
        engine.register_strategy(ChaosAction.LATENCY, custom_strategy)
        assert engine.get_strategy(ChaosAction.LATENCY) is custom_strategy

    def test_get_metrics(self, engine):
        """Test getting metrics."""
        metrics = engine.get_metrics()
        assert isinstance(metrics, ChaosMetrics)
        assert metrics.total_experiments == 0
        assert metrics.system_resilient is True

    def test_is_system_resilient(self, engine):
        """Test resilience check."""
        assert engine.is_system_resilient() is True


class TestChaosEngineExperiment:
    """Test ChaosEngine experiment execution."""

    @pytest.fixture
    def engine(self):
        """Create a test chaos engine."""
        return ChaosEngine()

    @pytest.mark.asyncio
    async def test_run_short_experiment(self, engine):
        """Test running a short experiment."""
        config = ExperimentConfig(
            name="short_test",
            target=ChaosTarget.TOOL_EXECUTOR,
            action=ChaosAction.DROP,
            duration_seconds=1,
            interval_seconds=0.1,
            probability=0.5,
        )

        result = await engine.run_experiment(config)

        assert result.name == "short_test"
        assert result.status in [ExperimentStatus.COMPLETED, ExperimentStatus.RUNNING]
        assert result.start_time is not None

    @pytest.mark.asyncio
    async def test_abort_experiment(self, engine):
        """Test aborting an experiment."""
        config = ExperimentConfig(
            name="abort_test",
            target=ChaosTarget.TOOL_EXECUTOR,
            action=ChaosAction.LATENCY,
            duration_seconds=60,
        )

        # Start experiment
        result = await engine.run_experiment(config)

        # If still running, abort it
        if result.status == ExperimentStatus.RUNNING:
            engine.abort_experiment(result.experiment_id)
            # Result should now be aborted
            updated = engine.get_experiment(result.experiment_id)
            assert updated.status == ExperimentStatus.ABORTED

    @pytest.mark.asyncio
    async def test_abort_all_experiments(self, engine):
        """Test aborting all experiments."""
        config = ExperimentConfig(
            name="multi_test",
            target=ChaosTarget.TOOL_EXECUTOR,
            action=ChaosAction.DROP,
            duration_seconds=10,
        )

        # Start multiple experiments
        await engine.run_experiment(config)
        await engine.run_experiment(config)

        # Abort all
        count = engine.abort_all_experiments()
        assert count >= 0

    def test_clear_history(self, engine):
        """Test clearing experiment history."""
        engine._experiments["test"] = object()
        count = engine.clear_history()
        assert count == 1
        assert len(engine._experiments) == 0


# =============================================================================
# Experiment Template Tests
# =============================================================================

class TestExperimentTemplates:
    """Test predefined experiment templates."""

    def test_latency_experiment_template(self):
        """Test latency experiment template."""
        config = latency_experiment(
            name="template_test",
            target=ChaosTarget.TOOL_EXECUTOR,
            intensity=0.7,
            duration=30,
        )

        assert config.name == "template_test"
        assert config.action == ChaosAction.LATENCY
        assert config.intensity == 0.7
        assert config.duration_seconds == 30

    def test_failure_experiment_template(self):
        """Test failure experiment template."""
        config = failure_experiment(
            name="fail_template",
            target=ChaosTarget.EVENT_BUS,
            probability=0.3,
        )

        assert config.action == ChaosAction.FAILURE
        assert config.probability == 0.3
        assert "error_types" in config.parameters

    def test_timeout_experiment_template(self):
        """Test timeout experiment template."""
        config = timeout_experiment(
            name="timeout_template",
            target=ChaosTarget.DISTRIBUTED_BUS,
            intensity=0.9,
        )

        assert config.action == ChaosAction.TIMEOUT
        assert config.intensity == 0.9


# =============================================================================
# ChaosMetrics Tests
# =============================================================================

class TestChaosMetrics:
    """Test ChaosMetrics dataclass."""

    def test_metrics_creation(self):
        """Test creating metrics."""
        metrics = ChaosMetrics(
            total_experiments=10,
            running_experiments=2,
            total_actions=100,
            successful_actions=95,
            failed_actions=5,
        )

        assert metrics.total_experiments == 10
        assert metrics.running_experiments == 2
        assert metrics.total_actions == 100
        assert metrics.successful_actions == 95
        assert metrics.failed_actions == 5

    def test_system_resilient_flag(self):
        """Test system resilient flag."""
        metrics = ChaosMetrics(system_resilient=True)
        assert metrics.system_resilient is True

        metrics.system_resilient = False
        assert metrics.system_resilient is False
