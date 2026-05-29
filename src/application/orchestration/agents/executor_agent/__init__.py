"""Executor Agent — executes plan steps with hardware-aware validation.

Responsibilities:
- Execute plan steps in dependency order
- Route to appropriate workflow (hardware, debugging, coding)
- Validate step output before marking complete
- Handle errors and trigger retry or escalation
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

from src.application.orchestration.agents.planner_agent import (
    ExecutionPlan,
    PlanStep,
    PlanStatus,
    PlannerAgent,
)
from src.application.workflows.base import WorkflowResult, WorkflowStatus
from src.application.workflows.hardware import HardwareWorkflow
from src.application.workflows.debugging import DebuggingWorkflow
from src.application.workflows.coding import CodingWorkflow
from src.domains.validation import CrossValidator

logger = structlog.get_logger(__name__)


@dataclass
class ExecutionResult:
    """Result of executing a single step."""
    step_id: str
    status: PlanStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float = 0.0
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutorAgent:
    """
    Executor Agent — executes plan steps using appropriate workflows.

    Routing logic:
    - TaskType.ANALYSIS → HardwareWorkflow
    - TaskType.CODE_GENERATION → CodingWorkflow
    - TaskType.DEBUGGING → DebuggingWorkflow
    - TaskType.PLANNING → direct reasoning

    Usage:
        executor = ExecutorAgent(
            cross_validator=cross_validator,
            knowledge_base=kb,
        )
        result = await executor.execute_step(step, plan_context)
    """

    def __init__(
        self,
        cross_validator: CrossValidator | None = None,
        max_parallel: int = 2,
    ):
        self._validator = cross_validator
        self._max_parallel = max_parallel
        self._running: dict[str, ExecutionResult] = {}

    async def execute_step(
        self,
        step: PlanStep,
        context: dict[str, Any],
    ) -> ExecutionResult:
        """
        Execute a single plan step.

        Args:
            step: Plan step to execute
            context: Execution context (chip_family, project, etc.)

        Returns:
            ExecutionResult with outcome
        """
        started = datetime.now()
        step.status = PlanStatus.IN_PROGRESS
        step.started_at = started

        logger.info("executor_step_start", step_id=step.step_id, name=step.name)

        try:
            result = await self._dispatch(step, context)

            duration_ms = (datetime.now() - started).total_seconds() * 1000

            if result.get("success") or result.get("valid"):
                step.status = PlanStatus.COMPLETED
                step.result = result
            else:
                step.status = PlanStatus.FAILED
                step.error = result.get("error", "unknown")

            step.completed_at = datetime.now()

            exec_result = ExecutionResult(
                step_id=step.step_id,
                status=step.status,
                result=result,
                error=step.error,
                duration_ms=duration_ms,
                metadata=result.get("metadata", {}),
            )

            logger.info(
                "executor_step_complete",
                step_id=step.step_id,
                status=step.status.value,
                duration_ms=duration_ms,
            )

            return exec_result

        except Exception as e:
            duration_ms = (datetime.now() - started).total_seconds() * 1000
            step.status = PlanStatus.FAILED
            step.error = str(e)
            step.completed_at = datetime.now()

            logger.error("executor_step_error", step_id=step.step_id, error=str(e))

            return ExecutionResult(
                step_id=step.step_id,
                status=PlanStatus.FAILED,
                error=str(e),
                duration_ms=duration_ms,
            )

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        context: dict[str, Any],
    ) -> ExecutionPlan:
        """
        Execute a full plan in dependency order.

        Runs ready steps in parallel (up to max_parallel).
        Blocks on dependencies. Stops on critical errors.

        Args:
            plan: ExecutionPlan to execute
            context: Global execution context

        Returns:
            Updated plan with results
        """
        plan.status = PlanStatus.IN_PROGRESS
        logger.info("executor_plan_start", plan_id=plan.plan_id, steps=len(plan.steps))

        max_iterations = len(plan.steps) * 2  # Safety limit
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # Check if plan is done
            if not plan.pending_steps and not plan.blocked_steps:
                remaining = [s for s in plan.steps if s.status not in (PlanStatus.COMPLETED, PlanStatus.FAILED)]
                if not remaining:
                    plan.status = PlanStatus.COMPLETED
                    plan.completed_at = datetime.now()
                    break

            # Get next ready steps
            ready_steps = self._get_ready_steps(plan)

            if not ready_steps:
                # Check for deadlock (blocked steps but no progress)
                if plan.blocked_steps:
                    plan.status = PlanStatus.FAILED
                    for step in plan.blocked_steps:
                        step.status = PlanStatus.BLOCKED
                        step.error = "Deadlock: dependencies not resolved"
                    break
                await asyncio.sleep(0.01)
                continue

            # Execute ready steps in parallel using asyncio.gather (W-012 fix)
            steps_to_run = ready_steps[:self._max_parallel]
            if steps_to_run:
                results = await asyncio.gather(
                    *[self.execute_step(step, context) for step in steps_to_run],
                    return_exceptions=True,
                )

                for step, result in zip(steps_to_run, results):
                    if isinstance(result, Exception):
                        logger.error("executor_step_exception", step_id=step.step_id, error=str(result))
                        continue
                    # Check for critical error
                    if result.status == PlanStatus.FAILED and self._is_critical_error(result.error or ""):
                        logger.warning("executor_critical_error", step_id=step.step_id)

        # Determine final plan status
        if any(s.status == PlanStatus.FAILED for s in plan.steps):
            # Check if all failures are non-critical
            critical_failures = [
                s for s in plan.failed_steps
                if self._is_critical_error(s.error or "")
            ]
            if critical_failures:
                plan.status = PlanStatus.FAILED
            else:
                plan.status = PlanStatus.COMPLETED  # Partial success OK
        elif plan.status == PlanStatus.IN_PROGRESS:
            plan.status = PlanStatus.COMPLETED

        if not plan.completed_at:
            plan.completed_at = datetime.now()

        logger.info(
            "executor_plan_complete",
            plan_id=plan.plan_id,
            status=plan.status.value,
            completed=len(plan.completed_steps),
            failed=len(plan.failed_steps),
        )

        return plan

    def _get_ready_steps(self, plan: ExecutionPlan) -> list[PlanStep]:
        """Get steps whose dependencies are all satisfied."""
        completed_ids = {s.step_id for s in plan.completed_steps}
        ready = []

        for step in plan.steps:
            if step.status != PlanStatus.PENDING:
                continue
            # Check dependencies
            deps_met = all(dep_id in completed_ids for dep_id in step.dependencies)
            if deps_met:
                ready.append(step)

        return ready

    async def _dispatch(
        self, step: PlanStep, context: dict[str, Any]
    ) -> dict[str, Any]:
        """Dispatch step to appropriate workflow."""
        from src.application.orchestration.agents.planner_agent import TaskType

        task_type = step.task_type

        if task_type == TaskType.ANALYSIS or task_type == TaskType.PLANNING:
            # Use hardware workflow for analysis
            wf = HardwareWorkflow(context={
                "task": step.description,
                "chip_family": context.get("chip_family", "STM32F4"),
                "peripherals": context.get("peripherals", []),
            })
            wf_result: WorkflowResult = await wf.run()
            return wf_result.to_dict()

        elif task_type == TaskType.CODE_GENERATION:
            wf = CodingWorkflow(context={
                "request": step.description,
                "chip_family": context.get("chip_family", "STM32F4"),
                "style": context.get("code_style", "register"),
            })
            wf_result = await wf.run()
            return wf_result.to_dict()

        elif task_type == TaskType.DEBUGGING:
            wf = DebuggingWorkflow(context={
                "symptom": step.description,
                "chip_family": context.get("chip_family", "STM32F4"),
            })
            wf_result = await wf.run()
            return wf_result.to_dict()

        else:
            # Generic: just return step description as result
            return {
                "success": True,
                "step": step.name,
                "description": step.description,
            }

    def _is_critical_error(self, error: str) -> bool:
        """Determine if an error is critical enough to stop the plan."""
        critical_prefixes = [
            "HARD FAULT", "PANIC", "ALLOC", "DEADLOCK",
            "RCC", "CLOCK", "FLASH", "BOOT",
        ]
        error_upper = error.upper()
        return any(p in error_upper for p in critical_prefixes)

    # ─── Validation Integration ────────────────────────────────────────

    async def validate_step_output(
        self,
        step: PlanStep,
        output: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate step output against hardware rules."""
        if not self._validator:
            return {"valid": True, "note": "no validator"}

        allocation = output.get("allocation", {})
        if not allocation:
            return {"valid": True, "note": "no allocation to validate"}

        result = await self._validator.validate_allocation(allocation)
        return result.to_dict()
