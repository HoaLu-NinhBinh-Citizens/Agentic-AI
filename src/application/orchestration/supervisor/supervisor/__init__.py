"""Supervisor — monitors multi-agent execution and handles escalation."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import structlog

from src.application.orchestration.agents.planner_agent import ExecutionPlan, PlanStatus

logger = structlog.get_logger(__name__)


class EscalationReason(Enum):
    """Reasons for escalation."""
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    DEADLOCK_DETECTED = "deadlock_detected"
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"
    VALIDATION_FAILED = "validation_failed"
    UNKNOWN_ERROR = "unknown_error"
    USER_CONFIRMATION_REQUIRED = "user_confirmation_required"
    SAFETY_CRITICAL = "safety_critical"


@dataclass
class EscalationEvent:
    """An escalation event requiring attention."""
    reason: EscalationReason
    plan_id: str
    step_id: str | None
    message: str
    severity: str  # "info", "warning", "critical"
    timestamp: datetime = field(default_factory=datetime.now)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class SupervisionResult:
    """Result of supervision check."""
    plan_id: str
    status: PlanStatus
    should_continue: bool
    escalations: list[EscalationEvent]
    suggestions: list[str]


class Supervisor:
    """
    Supervisor — monitors execution and handles escalation.

    Responsibilities:
    - Monitor plan execution health
    - Detect deadlocks and circuit breaker conditions
    - Decide when to escalate (to user or human review)
    - Provide execution suggestions

    Usage:
        supervisor = Supervisor()
        result = await supervisor.supervise(plan, context)
        if result.escalations:
            for esc in result.escalations:
                print(f"[{esc.severity}] {esc.message}")
    """

    def __init__(
        self,
        max_plan_duration_seconds: float = 300.0,
        deadlock_threshold_seconds: float = 30.0,
    ):
        self.max_plan_duration = max_plan_duration_seconds
        self.deadlock_threshold = deadlock_threshold_seconds
        self._escalations: list[EscalationEvent] = []
        self._circuit_breakers: dict[str, int] = {}  # plan_id → failure count

    async def supervise(
        self,
        plan: ExecutionPlan,
        context: dict[str, Any] | None = None,
    ) -> SupervisionResult:
        """
        Supervise plan execution and detect issues.

        Args:
            plan: ExecutionPlan to supervise
            context: Execution context

        Returns:
            SupervisionResult with escalations and suggestions
        """
        context = context or {}
        escalations: list[EscalationEvent] = []
        suggestions: list[str] = []

        # Check: Plan duration
        if plan.created_at:
            duration = (datetime.now() - plan.created_at).total_seconds()
            if duration > self.max_plan_duration:
                escalations.append(EscalationEvent(
                    reason=EscalationReason.UNKNOWN_ERROR,
                    plan_id=plan.plan_id,
                    message=f"Plan exceeded max duration ({duration:.0f}s > {self.max_plan_duration}s)",
                    severity="critical",
                ))

        # Check: Deadlock (no progress for extended period)
        if plan.pending_steps and plan.blocked_steps and not plan.completed_steps:
            last_completed = max(
                (s.completed_at for s in plan.completed_steps if s.completed_at),
                default=None,
            )
            if last_completed:
                stalled = (datetime.now() - last_completed).total_seconds()
                if stalled > self.deadlock_threshold:
                    escalations.append(EscalationEvent(
                        reason=EscalationReason.DEADLOCK_DETECTED,
                        plan_id=plan.plan_id,
                        message=f"Deadlock detected: no progress for {stalled:.0f}s",
                        severity="critical",
                    ))
                    suggestions.append("Cancel plan and restart with more specific task")

        # Check: Failed steps
        for step in plan.failed_steps:
            if step.retry_count >= step.max_retries:
                escalations.append(EscalationEvent(
                    reason=EscalationReason.MAX_RETRIES_EXCEEDED,
                    plan_id=plan.plan_id,
                    step_id=step.step_id,
                    message=f"Step '{step.name}' failed after {step.retry_count} retries: {step.error}",
                    severity="warning",
                ))
                suggestions.append(f"Review failed step: {step.name}")

                # Check for validation failures
                if "validation" in (step.error or "").lower():
                    escalations.append(EscalationEvent(
                        reason=EscalationReason.VALIDATION_FAILED,
                        plan_id=plan.plan_id,
                        step_id=step.step_id,
                        message=f"Validation failed in step '{step.name}': {step.error}",
                        severity="critical",
                        context={"step": step.to_dict() if hasattr(step, "to_dict") else {}},
                    ))
                    suggestions.append("Fix hardware constraints before regenerating code")

        # Check: Safety-critical operations
        task_lower = plan.original_task.lower()
        if any(k in task_lower for k in ["flash", "erase", "bootloader", "ota"]):
            escalations.append(EscalationEvent(
                reason=EscalationReason.SAFETY_CRITICAL,
                plan_id=plan.plan_id,
                message="Safety-critical operation detected — manual verification recommended",
                severity="warning",
            ))
            suggestions.append("Verify flash/bootloader changes manually before deployment")

        # Record escalations
        self._escalations.extend(escalations)

        # Circuit breaker: count failures per plan
        failure_count = self._circuit_breakers.get(plan.plan_id, 0)
        if plan.status == PlanStatus.FAILED:
            self._circuit_breakers[plan.plan_id] = failure_count + 1
            if failure_count >= 3:
                escalations.append(EscalationEvent(
                    reason=EscalationReason.CIRCUIT_BREAKER_OPEN,
                    plan_id=plan.plan_id,
                    message=f"Circuit breaker open: plan failed {failure_count + 1} times",
                    severity="critical",
                ))

        should_continue = plan.status not in (PlanStatus.FAILED, PlanStatus.CANCELLED)
        if escalations:
            for esc in escalations:
                if esc.severity == "critical":
                    should_continue = False
                    break

        return SupervisionResult(
            plan_id=plan.plan_id,
            status=plan.status,
            should_continue=should_continue,
            escalations=escalations,
            suggestions=suggestions,
        )

    def get_escalation_summary(self) -> dict[str, Any]:
        """Get summary of all escalations."""
        return {
            "total": len(self._escalations),
            "by_severity": {
                "critical": sum(1 for e in self._escalations if e.severity == "critical"),
                "warning": sum(1 for e in self._escalations if e.severity == "warning"),
                "info": sum(1 for e in self._escalations if e.severity == "info"),
            },
            "by_reason": {
                r.value: sum(1 for e in self._escalations if e.reason == r)
                for r in EscalationReason
            },
        }

    def clear_escalations(self, plan_id: str | None = None) -> None:
        """Clear escalation history."""
        if plan_id:
            self._escalations = [e for e in self._escalations if e.plan_id != plan_id]
        else:
            self._escalations.clear()
        if plan_id and plan_id in self._circuit_breakers:
            del self._circuit_breakers[plan_id]
