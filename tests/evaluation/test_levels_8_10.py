"""Test runner for Level 8-10 evaluation scenarios.

This module provides pytest-compatible test functions for running
Sandbox Safety, Context Management, and Concurrency evaluation scenarios.

Usage:
    # Run all Level 8-10 scenarios
    python -m pytest tests/evaluation/test_levels_8_10.py -v

    # Run specific level
    python -m pytest tests/evaluation/test_levels_8_10.py -v -k "level_8"

    # Run specific scenario
    python -m pytest tests/evaluation/test_levels_8_10.py -v -k "dangerous_shell"
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any, Generator

import pytest

from tests.evaluation.framework import (
    EvaluationFramework,
    EvaluationLevel,
    TestScenario,
)
from tests.evaluation.scenarios_levels_8_10 import (
    LEVEL_10_SCENARIOS,
    LEVEL_8_SCENARIOS,
    LEVEL_9_SCENARIOS,
    get_all_level_10_scenarios,
    get_all_level_8_scenarios,
    get_all_level_9_scenarios,
    get_all_new_scenarios,
)

logger = logging.getLogger(__name__)


class MockAgentExecutor:
    """Mock agent executor for testing scenarios without real agent."""

    def __init__(self, mock_result: bool = True) -> None:
        self.mock_result = mock_result
        self.call_count = 0

    async def __call__(self, scenario: TestScenario) -> dict[str, Any]:
        """Mock agent execution."""
        self.call_count += 1
        logger.info(f"MockAgent executing: {scenario.name}")

        await asyncio.sleep(0.01)

        return {
            "success": self.mock_result,
            "iterations": 1,
            "result": f"Mock execution for {scenario.scenario_id}",
        }


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "level_8: Level 8 Sandbox Safety tests")
    config.addinivalue_line("markers", "level_9: Level 9 Context Management tests")
    config.addinivalue_line("markers", "level_10: Level 10 Concurrency tests")
    config.addinivalue_line("markers", "sandbox_safety: Sandbox Safety scenarios")
    config.addinivalue_line("markers", "context_management: Context Management scenarios")
    config.addinivalue_line("markers", "concurrency: Concurrency scenarios")


@pytest.fixture
def framework() -> Generator[EvaluationFramework, None, None]:
    """Create evaluation framework with registered scenarios."""
    fw = EvaluationFramework()
    fw.register_scenarios(get_all_new_scenarios())
    yield fw


@pytest.fixture
def mock_executor() -> MockAgentExecutor:
    """Create mock agent executor."""
    return MockAgentExecutor(mock_result=True)


@pytest.fixture
def failing_mock_executor() -> MockAgentExecutor:
    """Create mock agent executor that fails."""
    return MockAgentExecutor(mock_result=False)


# =============================================================================
# LEVEL 8: SANDBOX SAFETY TESTS
# =============================================================================

class TestLevel8SandboxSafety:
    """Test suite for Level 8 Sandbox Safety scenarios."""

    @pytest.mark.level_8
    @pytest.mark.sandbox_safety
    @pytest.mark.asyncio
    async def test_dangerous_shell_blocking(
        self,
        framework: EvaluationFramework,
        mock_executor: MockAgentExecutor,
    ) -> None:
        """TC-009: Test dangerous shell command blocking."""
        scenarios = framework.get_scenarios_by_level(EvaluationLevel.LEVEL_8_SANDBOX_SAFETY)
        dangerous_scenario = next(
            s for s in scenarios if s.scenario_id == "l8_dangerous_shell_block"
        )

        result = await framework.evaluate_scenario(dangerous_scenario, mock_executor)

        assert result.scenario_id == "l8_dangerous_shell_block"
        assert result.level == EvaluationLevel.LEVEL_8_SANDBOX_SAFETY
        assert mock_executor.call_count >= 1

    @pytest.mark.level_8
    @pytest.mark.sandbox_safety
    @pytest.mark.asyncio
    async def test_permission_escalation_prevention(
        self,
        framework: EvaluationFramework,
        mock_executor: MockAgentExecutor,
    ) -> None:
        """TC-009: Test permission escalation prevention."""
        scenarios = framework.get_scenarios_by_level(EvaluationLevel.LEVEL_8_SANDBOX_SAFETY)
        scenario = next(
            s for s in scenarios if s.scenario_id == "l8_permission_escalation"
        )

        result = await framework.evaluate_scenario(scenario, mock_executor)

        assert result.scenario_id == "l8_permission_escalation"
        assert result.level == EvaluationLevel.LEVEL_8_SANDBOX_SAFETY

    @pytest.mark.level_8
    @pytest.mark.sandbox_safety
    @pytest.mark.asyncio
    async def test_violation_detection(
        self,
        framework: EvaluationFramework,
        mock_executor: MockAgentExecutor,
    ) -> None:
        """TC-009: Test violation detection and logging."""
        scenarios = framework.get_scenarios_by_level(EvaluationLevel.LEVEL_8_SANDBOX_SAFETY)
        scenario = next(
            s for s in scenarios if s.scenario_id == "l8_violation_detection"
        )

        result = await framework.evaluate_scenario(scenario, mock_executor)

        assert result.scenario_id == "l8_violation_detection"
        assert result.level == EvaluationLevel.LEVEL_8_SANDBOX_SAFETY

    @pytest.mark.level_8
    @pytest.mark.sandbox_safety
    @pytest.mark.asyncio
    async def test_approval_flow(
        self,
        framework: EvaluationFramework,
        mock_executor: MockAgentExecutor,
    ) -> None:
        """TC-009: Test approval workflow for sensitive operations."""
        scenarios = framework.get_scenarios_by_level(EvaluationLevel.LEVEL_8_SANDBOX_SAFETY)
        scenario = next(s for s in scenarios if s.scenario_id == "l8_approval_flow")

        result = await framework.evaluate_scenario(scenario, mock_executor)

        assert result.scenario_id == "l8_approval_flow"
        assert result.level == EvaluationLevel.LEVEL_8_SANDBOX_SAFETY

    @pytest.mark.level_8
    @pytest.mark.asyncio
    async def test_all_level_8_scenarios_registered(
        self,
        framework: EvaluationFramework,
    ) -> None:
        """Verify all Level 8 scenarios are registered."""
        scenarios = framework.get_scenarios_by_level(EvaluationLevel.LEVEL_8_SANDBOX_SAFETY)
        scenario_ids = {s.scenario_id for s in scenarios}

        expected_ids = {
            "l8_dangerous_shell_block",
            "l8_permission_escalation",
            "l8_violation_detection",
            "l8_approval_flow",
        }

        assert expected_ids.issubset(scenario_ids), f"Missing scenarios: {expected_ids - scenario_ids}"
        assert len(scenarios) == 4, f"Expected 4 Level 8 scenarios, got {len(scenarios)}"


# =============================================================================
# LEVEL 9: CONTEXT MANAGEMENT TESTS
# =============================================================================

class TestLevel9ContextManagement:
    """Test suite for Level 9 Context Management scenarios."""

    @pytest.mark.level_9
    @pytest.mark.context_management
    @pytest.mark.asyncio
    async def test_context_overflow_handling(
        self,
        framework: EvaluationFramework,
        mock_executor: MockAgentExecutor,
    ) -> None:
        """TC-006: Test context overflow handling."""
        scenarios = framework.get_scenarios_by_level(EvaluationLevel.LEVEL_9_CONTEXT_MANAGEMENT)
        scenario = next(s for s in scenarios if s.scenario_id == "l9_context_overflow")

        result = await framework.evaluate_scenario(scenario, mock_executor)

        assert result.scenario_id == "l9_context_overflow"
        assert result.level == EvaluationLevel.LEVEL_9_CONTEXT_MANAGEMENT

    @pytest.mark.level_9
    @pytest.mark.context_management
    @pytest.mark.asyncio
    async def test_context_retention(
        self,
        framework: EvaluationFramework,
        mock_executor: MockAgentExecutor,
    ) -> None:
        """TC-006: Test context retention over long tasks."""
        scenarios = framework.get_scenarios_by_level(EvaluationLevel.LEVEL_9_CONTEXT_MANAGEMENT)
        scenario = next(s for s in scenarios if s.scenario_id == "l9_context_retention")

        result = await framework.evaluate_scenario(scenario, mock_executor)

        assert result.scenario_id == "l9_context_retention"
        assert result.level == EvaluationLevel.LEVEL_9_CONTEXT_MANAGEMENT
        assert scenario.max_iterations == 150

    @pytest.mark.level_9
    @pytest.mark.context_management
    @pytest.mark.asyncio
    async def test_context_chunking(
        self,
        framework: EvaluationFramework,
        mock_executor: MockAgentExecutor,
    ) -> None:
        """TC-006: Test context chunking strategies."""
        scenarios = framework.get_scenarios_by_level(EvaluationLevel.LEVEL_9_CONTEXT_MANAGEMENT)
        scenario = next(s for s in scenarios if s.scenario_id == "l9_context_chunking")

        result = await framework.evaluate_scenario(scenario, mock_executor)

        assert result.scenario_id == "l9_context_chunking"
        assert result.level == EvaluationLevel.LEVEL_9_CONTEXT_MANAGEMENT

    @pytest.mark.level_9
    @pytest.mark.context_management
    @pytest.mark.asyncio
    async def test_memory_limit_boundary(
        self,
        framework: EvaluationFramework,
        mock_executor: MockAgentExecutor,
    ) -> None:
        """TC-006: Test behavior at memory/context limits."""
        scenarios = framework.get_scenarios_by_level(EvaluationLevel.LEVEL_9_CONTEXT_MANAGEMENT)
        scenario = next(s for s in scenarios if s.scenario_id == "l9_memory_limit_boundary")

        result = await framework.evaluate_scenario(scenario, mock_executor)

        assert result.scenario_id == "l9_memory_limit_boundary"
        assert result.level == EvaluationLevel.LEVEL_9_CONTEXT_MANAGEMENT

    @pytest.mark.level_9
    @pytest.mark.asyncio
    async def test_all_level_9_scenarios_registered(
        self,
        framework: EvaluationFramework,
    ) -> None:
        """Verify all Level 9 scenarios are registered."""
        scenarios = framework.get_scenarios_by_level(EvaluationLevel.LEVEL_9_CONTEXT_MANAGEMENT)
        scenario_ids = {s.scenario_id for s in scenarios}

        expected_ids = {
            "l9_context_overflow",
            "l9_context_retention",
            "l9_context_chunking",
            "l9_memory_limit_boundary",
        }

        assert expected_ids.issubset(scenario_ids), f"Missing scenarios: {expected_ids - scenario_ids}"
        assert len(scenarios) == 4, f"Expected 4 Level 9 scenarios, got {len(scenarios)}"


# =============================================================================
# LEVEL 10: CONCURRENCY TESTS
# =============================================================================

class TestLevel10Concurrency:
    """Test suite for Level 10 Concurrency scenarios."""

    @pytest.mark.level_10
    @pytest.mark.concurrency
    @pytest.mark.asyncio
    async def test_race_condition_detection(
        self,
        framework: EvaluationFramework,
        mock_executor: MockAgentExecutor,
    ) -> None:
        """TC-008: Test race condition detection."""
        scenarios = framework.get_scenarios_by_level(EvaluationLevel.LEVEL_10_CONCURRENCY)
        scenario = next(s for s in scenarios if s.scenario_id == "l10_race_condition")

        result = await framework.evaluate_scenario(scenario, mock_executor)

        assert result.scenario_id == "l10_race_condition"
        assert result.level == EvaluationLevel.LEVEL_10_CONCURRENCY

    @pytest.mark.level_10
    @pytest.mark.concurrency
    @pytest.mark.asyncio
    async def test_deadlock_analysis(
        self,
        framework: EvaluationFramework,
        mock_executor: MockAgentExecutor,
    ) -> None:
        """TC-008: Test deadlock detection and prevention."""
        scenarios = framework.get_scenarios_by_level(EvaluationLevel.LEVEL_10_CONCURRENCY)
        scenario = next(s for s in scenarios if s.scenario_id == "l10_deadlock_analysis")

        result = await framework.evaluate_scenario(scenario, mock_executor)

        assert result.scenario_id == "l10_deadlock_analysis"
        assert result.level == EvaluationLevel.LEVEL_10_CONCURRENCY

    @pytest.mark.level_10
    @pytest.mark.concurrency
    @pytest.mark.asyncio
    async def test_thread_safety_verification(
        self,
        framework: EvaluationFramework,
        mock_executor: MockAgentExecutor,
    ) -> None:
        """TC-008: Test thread safety verification."""
        scenarios = framework.get_scenarios_by_level(EvaluationLevel.LEVEL_10_CONCURRENCY)
        scenario = next(s for s in scenarios if s.scenario_id == "l10_thread_safety")

        result = await framework.evaluate_scenario(scenario, mock_executor)

        assert result.scenario_id == "l10_thread_safety"
        assert result.level == EvaluationLevel.LEVEL_10_CONCURRENCY

    @pytest.mark.level_10
    @pytest.mark.concurrency
    @pytest.mark.asyncio
    async def test_lock_ordering_validation(
        self,
        framework: EvaluationFramework,
        mock_executor: MockAgentExecutor,
    ) -> None:
        """TC-008: Test lock ordering validation."""
        scenarios = framework.get_scenarios_by_level(EvaluationLevel.LEVEL_10_CONCURRENCY)
        scenario = next(s for s in scenarios if s.scenario_id == "l10_lock_ordering")

        result = await framework.evaluate_scenario(scenario, mock_executor)

        assert result.scenario_id == "l10_lock_ordering"
        assert result.level == EvaluationLevel.LEVEL_10_CONCURRENCY

    @pytest.mark.level_10
    @pytest.mark.concurrency
    @pytest.mark.asyncio
    async def test_isr_safety(
        self,
        framework: EvaluationFramework,
        mock_executor: MockAgentExecutor,
    ) -> None:
        """TC-008: Test ISR interrupt safety."""
        scenarios = framework.get_scenarios_by_level(EvaluationLevel.LEVEL_10_CONCURRENCY)
        scenario = next(s for s in scenarios if s.scenario_id == "l10_isr_safety")

        result = await framework.evaluate_scenario(scenario, mock_executor)

        assert result.scenario_id == "l10_isr_safety"
        assert result.level == EvaluationLevel.LEVEL_10_CONCURRENCY

    @pytest.mark.level_10
    @pytest.mark.asyncio
    async def test_all_level_10_scenarios_registered(
        self,
        framework: EvaluationFramework,
    ) -> None:
        """Verify all Level 10 scenarios are registered."""
        scenarios = framework.get_scenarios_by_level(EvaluationLevel.LEVEL_10_CONCURRENCY)
        scenario_ids = {s.scenario_id for s in scenarios}

        expected_ids = {
            "l10_race_condition",
            "l10_deadlock_analysis",
            "l10_thread_safety",
            "l10_lock_ordering",
            "l10_isr_safety",
        }

        assert expected_ids.issubset(scenario_ids), f"Missing scenarios: {expected_ids - scenario_ids}"
        assert len(scenarios) == 5, f"Expected 5 Level 10 scenarios, got {len(scenarios)}"


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for the complete Level 8-10 suite."""

    @pytest.mark.asyncio
    async def test_full_level_8_suite(
        self,
        framework: EvaluationFramework,
        mock_executor: MockAgentExecutor,
    ) -> None:
        """Run complete Level 8 suite."""
        suite_result = await framework.run_suite(
            "Level_8_Sandbox_Safety",
            scenario_ids=[
                "l8_dangerous_shell_block",
                "l8_permission_escalation",
                "l8_violation_detection",
                "l8_approval_flow",
            ],
            agent_executor=mock_executor,
        )

        assert suite_result.total_scenarios == 4
        assert suite_result.suite_name == "Level_8_Sandbox_Safety"
        assert len(suite_result.results) == 4

    @pytest.mark.asyncio
    async def test_full_level_9_suite(
        self,
        framework: EvaluationFramework,
        mock_executor: MockAgentExecutor,
    ) -> None:
        """Run complete Level 9 suite."""
        suite_result = await framework.run_suite(
            "Level_9_Context_Management",
            scenario_ids=[
                "l9_context_overflow",
                "l9_context_retention",
                "l9_context_chunking",
                "l9_memory_limit_boundary",
            ],
            agent_executor=mock_executor,
        )

        assert suite_result.total_scenarios == 4
        assert suite_result.suite_name == "Level_9_Context_Management"
        assert len(suite_result.results) == 4

    @pytest.mark.asyncio
    async def test_full_level_10_suite(
        self,
        framework: EvaluationFramework,
        mock_executor: MockAgentExecutor,
    ) -> None:
        """Run complete Level 10 suite."""
        suite_result = await framework.run_suite(
            "Level_10_Concurrency",
            scenario_ids=[
                "l10_race_condition",
                "l10_deadlock_analysis",
                "l10_thread_safety",
                "l10_lock_ordering",
                "l10_isr_safety",
            ],
            agent_executor=mock_executor,
        )

        assert suite_result.total_scenarios == 5
        assert suite_result.suite_name == "Level_10_Concurrency"
        assert len(suite_result.results) == 5

    @pytest.mark.asyncio
    async def test_complete_8_10_suite(
        self,
        framework: EvaluationFramework,
        mock_executor: MockAgentExecutor,
    ) -> None:
        """Run complete Level 8-10 suite."""
        suite_result = await framework.run_suite(
            "Level_8_10_Complete",
            agent_executor=mock_executor,
        )

        assert suite_result.total_scenarios == 13
        assert len(suite_result.results) == 13

        level_breakdown = suite_result.level_breakdown
        assert level_breakdown[EvaluationLevel.LEVEL_8_SANDBOX_SAFETY.value]["total"] == 4
        assert level_breakdown[EvaluationLevel.LEVEL_9_CONTEXT_MANAGEMENT.value]["total"] == 4
        assert level_breakdown[EvaluationLevel.LEVEL_10_CONCURRENCY.value]["total"] == 5

    @pytest.mark.asyncio
    async def test_report_generation(
        self,
        framework: EvaluationFramework,
        mock_executor: MockAgentExecutor,
    ) -> None:
        """Test report generation for Level 8-10 suite."""
        suite_result = await framework.run_suite(
            "Level_8_10_Report_Test",
            agent_executor=mock_executor,
        )

        report = framework.generate_report(suite_result)

        assert "Level_8_10_Report_Test" in report
        assert "Total Scenarios: 13" in report
        assert "level_8_sandbox_safety" in report
        assert "level_9_context_management" in report
        assert "level_10_concurrency" in report


# =============================================================================
# SCENARIO VALIDATION TESTS
# =============================================================================

class TestScenarioValidation:
    """Validate scenario definitions and configurations."""

    def test_level_8_scenario_definitions(self) -> None:
        """Validate Level 8 scenario definitions."""
        scenarios = get_all_level_8_scenarios()

        for scenario in scenarios:
            assert scenario.scenario_id.startswith("l8_")
            assert scenario.level == EvaluationLevel.LEVEL_8_SANDBOX_SAFETY
            assert scenario.verify_fn is not None
            assert len(scenario.task) > 100
            assert scenario.max_iterations > 0
            assert scenario.timeout_seconds > 0

    def test_level_9_scenario_definitions(self) -> None:
        """Validate Level 9 scenario definitions."""
        scenarios = get_all_level_9_scenarios()

        for scenario in scenarios:
            assert scenario.scenario_id.startswith("l9_")
            assert scenario.level == EvaluationLevel.LEVEL_9_CONTEXT_MANAGEMENT
            assert scenario.verify_fn is not None
            assert len(scenario.task) > 100
            assert scenario.max_iterations > 0
            assert scenario.timeout_seconds > 0

    def test_level_10_scenario_definitions(self) -> None:
        """Validate Level 10 scenario definitions."""
        scenarios = get_all_level_10_scenarios()

        for scenario in scenarios:
            assert scenario.scenario_id.startswith("l10_")
            assert scenario.level == EvaluationLevel.LEVEL_10_CONCURRENCY
            assert scenario.verify_fn is not None
            assert len(scenario.task) > 100
            assert scenario.max_iterations > 0
            assert scenario.timeout_seconds > 0

    def test_no_duplicate_scenario_ids(self) -> None:
        """Ensure no duplicate scenario IDs across all levels."""
        all_scenarios = get_all_new_scenarios()
        scenario_ids = [s.scenario_id for s in all_scenarios]

        assert len(scenario_ids) == len(set(scenario_ids)), "Duplicate scenario IDs found"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
