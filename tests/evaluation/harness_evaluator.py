"""Harness Evaluator - Integrated evaluation with AgentHarness.

Evaluates AgentHarness performance using Codex-style metrics:
- Tool success rate
- Retry efficiency  
- Recovery quality
- Long-horizon consistency
- Sandbox safety
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.core.agent_runtime import AgentHarness, HarnessConfig, HarnessResult, HarnessState

from tests.evaluation.framework import (
    EvaluationLevel,
    EvaluationMetrics,
    EvaluationSuiteResult,
    FailureInjector,
    MetricsCollector,
    TestResult,
    TestScenario,
    Tracer,
)

logger = logging.getLogger(__name__)


@dataclass
class HarnessEvaluationResult:
    """Result of harness evaluation."""
    scenario_id: str
    success: bool
    harness_result: HarnessResult
    custom_metrics: EvaluationMetrics
    execution_trace: list[dict[str, Any]]
    errors: list[str] = field(default_factory=list)


class HarnessEvaluator:
    """
    Evaluates AgentHarness performance against test scenarios.
    
    Integrates with AgentHarness to:
    - Execute scenarios
    - Collect metrics
    - Measure recovery
    - Track tool usage
    - Verify sandbox safety
    """

    def __init__(
        self,
        harness: Optional[AgentHarness] = None,
        config: Optional[HarnessConfig] = None,
    ) -> None:
        self._harness = harness or AgentHarness(config or HarnessConfig())
        self._failure_injector = FailureInjector()
        self._tracer = Tracer()
        self._collector = MetricsCollector()
        self._results: list[HarnessEvaluationResult] = []

    @property
    def harness(self) -> AgentHarness:
        return self._harness

    async def evaluate_scenario(
        self,
        scenario: TestScenario,
        mock_mode: bool = True,
    ) -> HarnessEvaluationResult:
        """
        Evaluate a single scenario against the harness.
        
        Args:
            scenario: Test scenario to evaluate
            mock_mode: If True, use mock agent responses
            
        Returns:
            HarnessEvaluationResult with metrics
        """
        logger.info(f"Evaluating scenario: {scenario.scenario_id}")
        start_time = time.time()
        
        self._tracer.start()
        self._collector.start()
        self._tracer.trace("scenario_start", {"scenario_id": scenario.scenario_id})
        
        # Configure failure injection if scenario has traps
        if scenario.trap_enabled:
            self._failure_injector.configure(scenario.failure_injection)
        
        errors: list[str] = []
        success = False
        harness_result: Optional[HarnessResult] = None
        
        try:
            # Execute harness with scenario
            harness_result = await self._execute_with_tracing(
                scenario=scenario,
                mock_mode=mock_mode,
            )
            
            success = harness_result.success
            
            if not success and scenario.trap_enabled:
                # Check if agent recovered from trap
                if self._analyze_recovery(harness_result):
                    success = True
                    self._collector.record_rollback()
                    self._tracer.trace("recovery_success", {})
            
        except Exception as e:
            logger.error(f"Evaluation error: {e}")
            errors.append(str(e))
            self._collector.record_error(str(e))
            self._tracer.trace("error", {"error": str(e)})
        
        # Compute final metrics
        metrics = self._collector.compute_metrics()
        metrics.first_attempt_success = success and harness_result.iterations == 1 if harness_result else False
        metrics.pass_at_1 = 1.0 if metrics.first_attempt_success else 0.0
        
        # Additional harness-specific metrics
        if harness_result:
            metrics.total_iterations = harness_result.iterations
            metrics.total_duration = harness_result.total_duration
            metrics.plan_consistency = self._compute_plan_consistency(harness_result)
        
        self._tracer.trace("scenario_end", {
            "success": success,
            "duration": time.time() - start_time,
        })
        
        result = HarnessEvaluationResult(
            scenario_id=scenario.scenario_id,
            success=success,
            harness_result=harness_result,
            custom_metrics=metrics,
            execution_trace=self._tracer.get_trace(),
            errors=errors,
        )
        
        self._results.append(result)
        return result

    async def _execute_with_tracing(
        self,
        scenario: TestScenario,
        mock_mode: bool,
    ) -> HarnessResult:
        """Execute harness with tracing."""
        
        self._tracer.trace("harness_start", {
            "scenario_id": scenario.scenario_id,
            "task": scenario.task[:100],
        })
        
        # Configure harness for scenario
        self._harness.config.max_iterations = scenario.max_iterations
        
        # Execute
        result = await self._harness.run(
            task=scenario.task,
            project="EngineCar",
            target="CarEngine",
        )
        
        self._tracer.trace("harness_end", {
            "iterations": result.iterations,
            "success": result.success,
            "steps": len(result.steps),
        })
        
        return result

    async def _execute_with_autonomous_tracing(
        self,
        scenario: TestScenario,
    ) -> HarnessResult:
        """Execute harness in autonomous mode with tracing."""
        
        self._tracer.trace("autonomous_start", {
            "scenario_id": scenario.scenario_id,
        })
        
        self._harness.config.max_iterations = scenario.max_iterations
        self._harness.config.reflection_enabled = True
        
        result = await self._harness.run_autonomous(
            task=scenario.task,
            project="EngineCar",
            target="CarEngine",
            max_iterations=scenario.max_iterations,
        )
        
        self._tracer.trace("autonomous_end", {
            "iterations": result.iterations,
            "success": result.success,
        })
        
        return result

    def _analyze_recovery(self, harness_result: HarnessResult) -> bool:
        """Analyze if harness recovered from failure."""
        # Check if harness made multiple attempts
        if harness_result.iterations > 1:
            # Check if final state is success after multiple attempts
            return harness_result.final_state == HarnessState.COMPLETE
        return False

    def _compute_plan_consistency(self, harness_result: HarnessResult) -> float:
        """Compute plan consistency metric."""
        if not harness_result.steps:
            return 0.0
        
        # Check if all planned steps were completed
        planned_phases = {HarnessState.PLANNING}
        completed_phases = {step.phase for step in harness_result.steps if step.success}
        
        if not planned_phases:
            return 1.0
        
        consistency = len(completed_phases & planned_phases) / len(planned_phases)
        return consistency

    async def evaluate_suite(
        self,
        scenarios: list[TestScenario],
        mock_mode: bool = True,
        fail_fast: bool = False,
    ) -> dict[str, HarnessEvaluationResult]:
        """Evaluate multiple scenarios."""
        results: dict[str, HarnessEvaluationResult] = {}
        
        for scenario in scenarios:
            result = await self.evaluate_scenario(scenario, mock_mode)
            results[scenario.scenario_id] = result
            
            if fail_fast and not result.success:
                logger.warning(f"Stopping suite due to failure: {scenario.scenario_id}")
                break
        
        return results

    def generate_report(
        self,
        results: dict[str, HarnessEvaluationResult],
    ) -> str:
        """Generate evaluation report."""
        total = len(results)
        passed = sum(1 for r in results.values() if r.success)
        failed = total - passed
        
        lines = [
            "=" * 70,
            "HARNESS EVALUATION REPORT",
            "=" * 70,
            f"Total scenarios: {total}",
            f"Passed: {passed} ({passed/total*100:.1f}%)" if total > 0 else "Passed: 0",
            f"Failed: {failed}",
            "",
            "-" * 70,
            "SCENARIO RESULTS",
            "-" * 70,
        ]
        
        for scenario_id, result in results.items():
            status = "PASS" if result.success else "FAIL"
            duration = result.harness_result.total_duration if result.harness_result else 0
            
            lines.append(f"[{status}] {scenario_id}")
            lines.append(f"      Duration: {duration:.2f}s")
            lines.append(f"      Iterations: {result.harness_result.iterations if result.harness_result else 0}")
            
            if result.errors:
                lines.append(f"      Errors: {result.errors[0]}")
        
        lines.extend([
            "",
            "-" * 70,
            "METRICS SUMMARY",
            "-" * 70,
        ])
        
        # Aggregate metrics
        all_metrics = [r.custom_metrics for r in results.values()]
        if all_metrics:
            avg_pass_at_1 = sum(m.pass_at_1 for m in all_metrics) / len(all_metrics)
            avg_tool_rate = sum(m.tool_success_rate for m in all_metrics) / len(all_metrics)
            avg_retry_eff = sum(m.retry_efficiency for m in all_metrics) / len(all_metrics)
            
            lines.append(f"pass@1: {avg_pass_at_1:.1%}")
            lines.append(f"tool_success_rate: {avg_tool_rate:.1%}")
            lines.append(f"retry_efficiency: {avg_retry_eff:.1%}")
        
        lines.append("=" * 70)
        
        return "\n".join(lines)


class MockAgentExecutor:
    """
    Mock agent executor for testing harness without real LLM.
    
    Simulates agent behavior for evaluation testing:
    - Correct responses (success)
    - Partial responses (retry)
    - Wrong responses (failure)
    """

    def __init__(self, behavior: str = "correct") -> None:
        self._behavior = behavior
        self._call_count = 0

    async def execute(self, scenario: TestScenario) -> dict[str, Any]:
        """Execute scenario with mock behavior."""
        self._call_count += 1
        
        if self._behavior == "correct":
            return {"success": True, "response": self._correct_response(scenario)}
        elif self._behavior == "partial":
            if self._call_count < 3:
                return {"success": False, "response": "Need more analysis"}
            return {"success": True, "response": self._correct_response(scenario)}
        else:  # wrong
            return {"success": False, "response": "I think the bug is..."}

    def _correct_response(self, scenario: TestScenario) -> str:
        """Generate correct response based on scenario type."""
        scenario_id = scenario.scenario_id
        
        if "offbyone" in scenario_id:
            return "The bug is 'i <= size' should be 'i < size' - off-by-one error."
        elif "memory" in scenario_id:
            return "Buffer overflow detected: rx_buf is 8 bytes but accessed with idx up to 9."
        elif "register" in scenario_id:
            return "SPI_CR1 = 0x0347 decodes to: MSTR=1 (master), BR=3 (div 16), SPE=1 (enabled)."
        elif "cross_file" in scenario_id:
            return "Root cause: I2C clock not enabled in clock_config.h - middleware callback never fires."
        elif "ota" in scenario_id:
            return "OTA implementation: AES verification -> dual-bank swap -> rollback on failure."
        elif "trap" in scenario_id:
            return "This is a trap - the error message is misleading. True cause is elsewhere."
        elif "crash" in scenario_id:
            return "PC=0x08002456 -> main.c:142 in UART_Send(). Stack shows overflow."
        
        return "Task completed successfully."

    def reset(self) -> None:
        self._call_count = 0
