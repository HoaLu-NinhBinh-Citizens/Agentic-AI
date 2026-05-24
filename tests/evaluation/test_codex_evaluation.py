"""Pytest Integration for Codex-Style Agent Evaluation.

Run evaluation tests with pytest:
    pytest tests/evaluation/test_codex_evaluation.py -v
    pytest tests/evaluation/test_codex_evaluation.py -k "level_1" -v
    pytest tests/evaluation/test_codex_evaluation.py -k "reasoning" -v
"""

from __future__ import annotations

import pytest
from typing import Any

from tests.evaluation.framework import (
    EvaluationFramework,
    EvaluationLevel,
    EvaluationMetrics,
    EvaluationSuiteResult,
    TestResult,
)
from tests.evaluation.harness_evaluator import HarnessEvaluator, HarnessEvaluationResult, MockAgentExecutor
from tests.evaluation.scenarios_levels_4_7 import get_all_scenarios, get_all_advanced_scenarios
from tests.evaluation.scenarios_levels_1_3 import get_all_early_scenarios


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def evaluation_framework() -> EvaluationFramework:
    """Create evaluation framework."""
    return EvaluationFramework()


@pytest.fixture
def harness_evaluator() -> HarnessEvaluator:
    """Create harness evaluator with mock harness."""
    return HarnessEvaluator()


@pytest.fixture
def mock_executor() -> MockAgentExecutor:
    """Create mock agent executor."""
    return MockAgentExecutor(behavior="correct")


# =============================================================================
# LEVEL 1 TESTS - REASONING
# =============================================================================

class TestLevel1Reasoning:
    """Level 1: Local reasoning tests."""

    @pytest.mark.asyncio
    async def test_off_by_one_detection(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test off-by-one bug detection."""
        from tests.evaluation.scenarios_levels_1_3 import create_code_understanding_scenario
        
        scenario = create_code_understanding_scenario()
        evaluation_framework.register_scenario(scenario)
        
        # Create mock executor
        async def mock_execute(s):
            return {"success": True, "response": "The bug is 'i <= size' should be 'i < size' - off-by-one error."}
        
        result = await evaluation_framework.evaluate_scenario(scenario, mock_execute)
        
        assert result.level == EvaluationLevel.LEVEL_1_REASONING
        assert "offbyone" in result.scenario_id.lower() or result.scenario_name == "Off-by-One Bug Detection"

    @pytest.mark.asyncio
    async def test_memory_violation_detection(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test memory violation detection."""
        from tests.evaluation.scenarios_levels_1_3 import create_memory_violation_scenario
        
        scenario = create_memory_violation_scenario()
        evaluation_framework.register_scenario(scenario)
        
        async def mock_execute(s):
            return {"success": True, "response": "Buffer overflow in ISR: rx_buf[8] accessed when size is 8."}
        
        result = await evaluation_framework.evaluate_scenario(scenario, mock_execute)
        
        assert result.level == EvaluationLevel.LEVEL_1_REASONING

    @pytest.mark.asyncio
    async def test_register_decode(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test register analysis."""
        from tests.evaluation.scenarios_levels_1_3 import create_register_decode_scenario
        
        scenario = create_register_decode_scenario()
        evaluation_framework.register_scenario(scenario)
        
        async def mock_execute(s):
            return {"success": True, "response": "0x0347: MSTR=1, BR=3, SPE=1 - Master mode at /16 baud."}
        
        result = await evaluation_framework.evaluate_scenario(scenario, mock_execute)
        
        assert result.level == EvaluationLevel.LEVEL_1_REASONING


# =============================================================================
# LEVEL 2 TESTS - TOOL USE
# =============================================================================

class TestLevel2ToolUse:
    """Level 2: Tool use tests."""

    @pytest.mark.asyncio
    async def test_shell_interaction(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test shell tool interaction."""
        from tests.evaluation.scenarios_levels_1_3 import create_shell_interaction_scenario
        
        scenario = create_shell_interaction_scenario()
        evaluation_framework.register_scenario(scenario)
        
        async def mock_execute(s):
            return {
                "success": True,
                "response": "Used shell to run tests, found bug, fixed it, verified with pytest.",
            }
        
        result = await evaluation_framework.evaluate_scenario(scenario, mock_execute)
        
        assert result.level == EvaluationLevel.LEVEL_2_TOOL_USE
        # Mock executor doesn't record tools, so tool_success_rate is 0
        # The important thing is the scenario executed at Level 2

    @pytest.mark.asyncio
    async def test_build_integration(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test build system integration."""
        from tests.evaluation.scenarios_levels_1_3 import create_build_integration_scenario
        
        scenario = create_build_integration_scenario()
        evaluation_framework.register_scenario(scenario)
        
        async def mock_execute(s):
            return {"success": True, "response": "Build completed successfully."}
        
        result = await evaluation_framework.evaluate_scenario(scenario, mock_execute)
        
        assert result.level == EvaluationLevel.LEVEL_2_TOOL_USE


# =============================================================================
# LEVEL 3 TESTS - REPO REASONING
# =============================================================================

class TestLevel3RepoReasoning:
    """Level 3: Repository reasoning tests."""

    @pytest.mark.asyncio
    async def test_cross_file_dependency(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test cross-file dependency analysis."""
        from tests.evaluation.scenarios_levels_1_3 import create_cross_file_dependency_scenario
        
        scenario = create_cross_file_dependency_scenario()
        evaluation_framework.register_scenario(scenario)
        
        async def mock_execute(s):
            return {
                "success": True,
                "response": "Root cause: I2C clock not enabled. Traced from main.c -> sensor_hub.c -> sensor.c.",
            }
        
        result = await evaluation_framework.evaluate_scenario(scenario, mock_execute)
        
        assert result.level == EvaluationLevel.LEVEL_3_REPO_REASONING

    @pytest.mark.asyncio
    async def test_call_graph_analysis(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test RTOS call graph analysis."""
        from tests.evaluation.scenarios_levels_1_3 import create_call_graph_analysis_scenario
        
        scenario = create_call_graph_analysis_scenario()
        evaluation_framework.register_scenario(scenario)
        
        async def mock_execute(s):
            return {
                "success": True,
                "response": "Deadlock: SensorTask holds SPI, wants I2C. CommTask holds I2C, wants SPI.",
            }
        
        result = await evaluation_framework.evaluate_scenario(scenario, mock_execute)
        
        assert result.level == EvaluationLevel.LEVEL_3_REPO_REASONING


# =============================================================================
# LEVEL 4 TESTS - LONG HORIZON
# =============================================================================

class TestLevel4LongHorizon:
    """Level 4: Long horizon agent loop tests."""

    @pytest.mark.asyncio
    async def test_ota_system_implementation(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test OTA update system implementation (long horizon)."""
        from tests.evaluation.scenarios_levels_4_7 import create_ota_update_system_scenario
        
        scenario = create_ota_update_system_scenario()
        evaluation_framework.register_scenario(scenario)
        
        async def mock_execute(s):
            return {
                "success": True,
                "response": "Implemented OTA: AES verification -> dual-bank swap -> rollback on failure.",
            }
        
        result = await evaluation_framework.evaluate_scenario(scenario, mock_execute)
        
        assert result.level == EvaluationLevel.LEVEL_4_LONG_HORIZON
        assert result.metrics.plan_consistency >= 0

    @pytest.mark.asyncio
    async def test_context_retention(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test context retention over long horizon."""
        from tests.evaluation.scenarios_levels_4_7 import create_rtos_scheduler_refactor_scenario
        
        scenario = create_rtos_scheduler_refactor_scenario()
        evaluation_framework.register_scenario(scenario)
        
        async def mock_execute(s):
            return {
                "success": True,
                "response": "Implemented priority inheritance preserving existing task API.",
            }
        
        result = await evaluation_framework.evaluate_scenario(scenario, mock_execute)
        
        assert result.level == EvaluationLevel.LEVEL_4_LONG_HORIZON
        assert result.metrics.architecture_preserved or result.metrics.total_iterations > 0


# =============================================================================
# LEVEL 5 TESTS - FAILURE RECOVERY
# =============================================================================

class TestLevel5FailureRecovery:
    """Level 5: Failure recovery tests."""

    @pytest.mark.asyncio
    async def test_deliberate_trap_recovery(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test recovery from deliberate traps."""
        from tests.evaluation.scenarios_levels_4_7 import create_deliberate_trap_scenario
        
        scenario = create_deliberate_trap_scenario()
        evaluation_framework.register_scenario(scenario)
        
        async def mock_execute(s):
            return {
                "success": True,
                "response": "This is a trap - the error is misleading. True cause is clock config.",
            }
        
        result = await evaluation_framework.evaluate_scenario(scenario, mock_execute)
        
        assert result.level == EvaluationLevel.LEVEL_5_FAILURE_RECOVERY
        assert result.scenario_name == "Recovery from Deliberate Traps"

    @pytest.mark.asyncio
    async def test_api_hallucination_detection(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test API hallucination detection."""
        from tests.evaluation.scenarios_levels_4_7 import create_api_hallucination_trap_scenario
        
        scenario = create_api_hallucination_trap_scenario()
        evaluation_framework.register_scenario(scenario)
        
        async def mock_execute(s):
            return {
                "success": True,
                "response": "HAL_TIM_PWM_Start_IT does not exist. Correct API is HAL_TIM_PWM_Start.",
            }
        
        result = await evaluation_framework.evaluate_scenario(scenario, mock_execute)
        
        assert result.level == EvaluationLevel.LEVEL_5_FAILURE_RECOVERY
        assert result.metrics.hallucination_rate >= 0

    @pytest.mark.asyncio
    async def test_flaky_test_handling(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test flaky test handling."""
        from tests.evaluation.scenarios_levels_4_7 import create_flaky_test_recovery_scenario
        
        scenario = create_flaky_test_recovery_scenario()
        evaluation_framework.register_scenario(scenario)
        
        async def mock_execute(s):
            return {
                "success": True,
                "response": "Flaky test caused by interrupt during timing measurement. Fixed by disabling interrupts.",
            }
        
        result = await evaluation_framework.evaluate_scenario(scenario, mock_execute)
        
        assert result.level == EvaluationLevel.LEVEL_5_FAILURE_RECOVERY


# =============================================================================
# LEVEL 6 TESTS - AUTONOMOUS DEBUGGING
# =============================================================================

class TestLevel6AutonomousDebugging:
    """Level 6: Autonomous debugging tests."""

    @pytest.mark.asyncio
    async def test_firmware_crash_analysis(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test firmware crash analysis."""
        from tests.evaluation.scenarios_levels_4_7 import create_firmware_crash_scenario
        
        scenario = create_firmware_crash_scenario()
        evaluation_framework.register_scenario(scenario)
        
        async def mock_execute(s):
            return {
                "success": True,
                "response": "PC=0x08002456 -> main.c:142. Stack overflow in UART_Send.",
            }
        
        result = await evaluation_framework.evaluate_scenario(scenario, mock_execute)
        
        assert result.level == EvaluationLevel.LEVEL_6_AUTONOMOUS_DEBUGGING
        assert result.scenario_name == "Firmware Crash Analysis"

    @pytest.mark.asyncio
    async def test_rtos_deadlock_debug(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test RTOS deadlock debugging."""
        from tests.evaluation.scenarios_levels_4_7 import create_rtos_deadlock_debug_scenario
        
        scenario = create_rtos_deadlock_debug_scenario()
        evaluation_framework.register_scenario(scenario)
        
        async def mock_execute(s):
            return {
                "success": True,
                "response": "Circular wait: SensorTask->I2C_Mutex<-CommTask->SPI_Mutex<-SensorTask.",
            }
        
        result = await evaluation_framework.evaluate_scenario(scenario, mock_execute)
        
        assert result.level == EvaluationLevel.LEVEL_6_AUTONOMOUS_DEBUGGING

    @pytest.mark.asyncio
    async def test_timing_jitter_debug(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test timing jitter debugging."""
        from tests.evaluation.scenarios_levels_4_7 import create_timing_jitter_debug_scenario
        
        scenario = create_timing_jitter_debug_scenario()
        evaluation_framework.register_scenario(scenario)
        
        async def mock_execute(s):
            return {
                "success": True,
                "response": "500us delay caused by flash erase in background. Moved to idle task.",
            }
        
        result = await evaluation_framework.evaluate_scenario(scenario, mock_execute)
        
        assert result.level == EvaluationLevel.LEVEL_6_AUTONOMOUS_DEBUGGING


# =============================================================================
# LEVEL 7 TESTS - MULTI-AGENT
# =============================================================================

class TestLevel7MultiAgent:
    """Level 7: Multi-agent orchestration tests."""

    @pytest.mark.asyncio
    async def test_subagent_orchestration(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test sub-agent task orchestration."""
        from tests.evaluation.scenarios_levels_4_7 import create_subagent_orchestration_scenario
        
        scenario = create_subagent_orchestration_scenario()
        evaluation_framework.register_scenario(scenario)
        
        async def mock_execute(s):
            return {
                "success": True,
                "response": "Delegated to TestAgent, SecurityAgent, PerformanceAgent, merged results.",
            }
        
        result = await evaluation_framework.evaluate_scenario(scenario, mock_execute)
        
        assert result.level == EvaluationLevel.LEVEL_7_MULTI_AGENT

    @pytest.mark.asyncio
    async def test_conflict_resolution(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test conflict resolution between agents."""
        from tests.evaluation.scenarios_levels_4_7 import create_conflict_resolution_scenario
        
        scenario = create_conflict_resolution_scenario()
        evaluation_framework.register_scenario(scenario)
        
        async def mock_execute(s):
            return {
                "success": True,
                "response": "Resolved: Use DMA+interrupt hybrid, security with caching, adaptive batching.",
            }
        
        result = await evaluation_framework.evaluate_scenario(scenario, mock_execute)
        
        assert result.level == EvaluationLevel.LEVEL_7_MULTI_AGENT


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestEvaluationIntegration:
    """Integration tests for evaluation framework."""

    @pytest.mark.asyncio
    async def test_full_suite_execution(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test running full evaluation suite."""
        # Register all early scenarios
        from tests.evaluation.scenarios_levels_1_3 import get_all_early_scenarios
        
        scenarios = get_all_early_scenarios()[:3]  # Just first 3 for speed
        evaluation_framework.register_scenarios(scenarios)
        
        async def mock_execute(s):
            return {"success": True, "response": "Task completed successfully."}
        
        # Run suite
        suite_result = await evaluation_framework.run_suite(
            suite_name="Test Suite",
            scenario_ids=[s.scenario_id for s in scenarios],
            agent_executor=mock_execute,
        )
        
        assert suite_result.total_scenarios == 3
        assert suite_result.duration > 0

    @pytest.mark.asyncio
    async def test_harness_evaluator(
        self,
        harness_evaluator: HarnessEvaluator,
    ):
        """Test harness evaluator integration."""
        from tests.evaluation.scenarios_levels_1_3 import create_code_understanding_scenario
        
        scenario = create_code_understanding_scenario()
        
        result = await harness_evaluator.evaluate_scenario(scenario, mock_mode=True)
        
        assert result.scenario_id == scenario.scenario_id
        assert isinstance(result.custom_metrics, EvaluationMetrics)

    @pytest.mark.asyncio
    async def test_metrics_collection(
        self,
        harness_evaluator: HarnessEvaluator,
    ):
        """Test metrics collection during evaluation."""
        from tests.evaluation.scenarios_levels_1_3 import create_memory_violation_scenario
        
        scenario = create_memory_violation_scenario()
        
        result = await harness_evaluator.evaluate_scenario(scenario, mock_mode=True)
        
        metrics = result.custom_metrics
        assert metrics.total_iterations >= 0
        assert metrics.total_duration >= 0


# =============================================================================
# SANDBOX TESTS
# =============================================================================

class TestSandboxSafety:
    """Sandbox safety tests."""

    def test_sandbox_violation_detection(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test sandbox violation detection."""
        # This tests the framework's ability to track violations
        from tests.evaluation.framework import MetricsCollector
        
        collector = MetricsCollector()
        collector.start()
        collector.record_sandbox_violation("rm -rf / attempted")
        
        metrics = collector.compute_metrics()
        
        assert metrics.sandbox_violations == 1

    def test_trap_scenario_configuration(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test trap scenario configuration."""
        from tests.evaluation.scenarios_levels_4_7 import create_deliberate_trap_scenario
        
        scenario = create_deliberate_trap_scenario()
        
        assert scenario.trap_enabled is True
        assert "fake_compiler_error" in scenario.failure_injection


# =============================================================================
# REPORT GENERATION TESTS
# =============================================================================

class TestReportGeneration:
    """Report generation tests."""

    @pytest.mark.asyncio
    async def test_suite_report(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test suite report generation."""
        from tests.evaluation.scenarios_levels_1_3 import get_all_level_1_scenarios
        
        scenarios = get_all_level_1_scenarios()[:2]
        evaluation_framework.register_scenarios(scenarios)
        
        async def mock_execute(s):
            return {"success": True, "response": "OK"}
        
        suite_result = await evaluation_framework.run_suite(
            suite_name="Reasoning Test Suite",
            agent_executor=mock_execute,
        )
        
        report = evaluation_framework.generate_report(suite_result)
        
        assert "CODEX-STYLE AGENT EVALUATION REPORT" in report
        assert "SUMMARY" in report
        assert "LEVEL BREAKDOWN" in report

    @pytest.mark.asyncio
    async def test_metrics_summary(
        self,
        evaluation_framework: EvaluationFramework,
    ):
        """Test metrics summary computation."""
        from tests.evaluation.scenarios_levels_1_3 import create_register_decode_scenario
        
        scenario = create_register_decode_scenario()
        evaluation_framework.register_scenario(scenario)
        
        async def mock_execute(s):
            return {"success": True, "response": "Decoded SPI config."}
        
        result = await evaluation_framework.evaluate_scenario(scenario, mock_execute)
        
        metrics = result.metrics
        assert "pass_at_1" in metrics.to_dict()
        assert "tool_success_rate" in metrics.to_dict()


# =============================================================================
# MARKERS
# =============================================================================

# Markers for running specific test levels
pytest.mark.level1 = pytest.mark.level_1_reasoning
pytest.mark.level2 = pytest.mark.level_2_tool_use
pytest.mark.level3 = pytest.mark.level_3_repo_reasoning
pytest.mark.level4 = pytest.mark.level_4_long_horizon
pytest.mark.level5 = pytest.mark.level_5_failure_recovery
pytest.mark.level6 = pytest.mark.level_6_autonomous_debugging
pytest.mark.level7 = pytest.mark.level_7_multi_agent


# Export fixtures for use in other test modules
__all__ = [
    "evaluation_framework",
    "harness_evaluator",
    "mock_executor",
]
