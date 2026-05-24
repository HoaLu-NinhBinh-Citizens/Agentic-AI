"""Base workflow engine for AI_SUPPORT.

Provides common infrastructure for all workflows:
- Step sequencing
- Error recovery
- Result aggregation
- Integration with ReasoningLoop and KnowledgeBase
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class WorkflowStatus(Enum):
    """Workflow execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowStep:
    """A single step in a workflow."""
    step_id: str
    name: str
    description: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    result: Any = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return None


@dataclass
class WorkflowResult:
    """Result of a workflow execution."""
    workflow_name: str
    status: WorkflowStatus
    steps: list[WorkflowStep]
    final_result: dict[str, Any]
    errors: list[str]
    warnings: list[str]
    started_at: datetime
    completed_at: datetime
    total_duration_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == WorkflowStatus.COMPLETED

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow_name,
            "status": self.status.value,
            "success": self.success,
            "steps": [
                {
                    "id": s.step_id,
                    "name": s.name,
                    "status": s.status.value,
                    "duration_ms": s.duration_ms,
                    "error": s.error,
                }
                for s in self.steps
            ],
            "errors": self.errors,
            "warnings": self.warnings,
            "duration_ms": self.total_duration_ms,
            "result": self.final_result,
        }


class BaseWorkflow(ABC):
    """
    Base class for all AI_SUPPORT workflows.

    Provides:
    - Step management
    - Reasoning loop integration
    - Error handling
    - Progress tracking

    Usage:
        class MyWorkflow(BaseWorkflow):
            async def _execute(self) -> dict[str, Any]:
                # Implement workflow logic
                pass

        workflow = MyWorkflow(context={"task": "..."})
        result = await workflow.run()
    """

    def __init__(
        self,
        context: dict[str, Any],
        max_retries: int = 2,
        timeout_seconds: float = 60.0,
    ):
        self.context = context
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds

        self._steps: list[WorkflowStep] = []
        self._errors: list[str] = []
        self._warnings: list[str] = []
        self._status = WorkflowStatus.PENDING
        self._cancellation_event: asyncio.Event | None = None

        # Sub-systems (can be injected)
        self._reasoning_loop = None
        self._knowledge_base = None
        self._hardware_validator = None

    # ─── Public API ───────────────────────────────────────────────────

    async def run(self) -> WorkflowResult:
        """Run the workflow."""
        import uuid
        started_at = datetime.now()
        self._status = WorkflowStatus.RUNNING
        self._cancellation_event = asyncio.Event()

        logger.info("workflow_start", workflow=self.name, context_keys=list(self.context.keys()))

        try:
            # Timeout wrapper
            result = await asyncio.wait_for(
                self._execute(),
                timeout=self.timeout_seconds,
            )
            self._status = WorkflowStatus.COMPLETED
            logger.info("workflow_complete", workflow=self.name, duration_ms=(datetime.now() - started_at).total_seconds() * 1000)
        except asyncio.TimeoutError:
            self._status = WorkflowStatus.FAILED
            self._errors.append(f"Workflow timed out after {self.timeout_seconds}s")
            logger.error("workflow_timeout", workflow=self.name, timeout=self.timeout_seconds)
            result = {"error": "timeout", "message": f"Workflow exceeded {self.timeout_seconds}s"}
        except Exception as e:
            self._status = WorkflowStatus.FAILED
            self._errors.append(str(e))
            logger.error("workflow_error", workflow=self.name, error=str(e))
            result = {"error": "failed", "message": str(e)}

        completed_at = datetime.now()

        return WorkflowResult(
            workflow_name=self.name,
            status=self._status,
            steps=self._steps,
            final_result=result,
            errors=self._errors,
            warnings=self._warnings,
            started_at=started_at,
            completed_at=completed_at,
            total_duration_ms=(completed_at - started_at).total_seconds() * 1000,
        )

    def cancel(self) -> None:
        """Cancel the workflow."""
        if self._cancellation_event:
            self._cancellation_event.set()
        self._status = WorkflowStatus.CANCELLED

    # ─── Step Management ──────────────────────────────────────────────

    def add_step(self, step_id: str, name: str, description: str) -> WorkflowStep:
        """Add a workflow step."""
        step = WorkflowStep(
            step_id=step_id,
            name=name,
            description=description,
        )
        self._steps.append(step)
        return step

    async def run_step(
        self,
        step_id: str,
        coro,
        *args,
        **kwargs,
    ) -> Any:
        """
        Run a step with automatic status tracking.

        Args:
            step_id: ID of step to update
            coro: Coroutine to execute
            *args, **kwargs: Arguments for coro

        Returns:
            Result of coro
        """
        step = self._get_step(step_id)
        if not step:
            raise ValueError(f"Step not found: {step_id}")

        # Check cancellation
        if self._cancellation_event and self._cancellation_event.is_set():
            step.status = WorkflowStatus.CANCELLED
            raise asyncio.CancelledError()

        step.status = WorkflowStatus.RUNNING
        step.started_at = datetime.now()

        for attempt in range(self.max_retries):
            try:
                result = await coro(*args, **kwargs)
                step.status = WorkflowStatus.COMPLETED
                step.completed_at = datetime.now()
                step.result = result
                return result
            except asyncio.CancelledError:
                step.status = WorkflowStatus.CANCELLED
                raise
            except Exception as e:
                if attempt == self.max_retries - 1:
                    step.status = WorkflowStatus.FAILED
                    step.error = str(e)
                    self._errors.append(f"[{step.name}] {e}")
                    raise
                logger.warning(
                    "workflow_step_retry",
                    step=step_id,
                    attempt=attempt + 1,
                    error=str(e),
                )
                await asyncio.sleep(0.1 * (attempt + 1))

    def _get_step(self, step_id: str) -> WorkflowStep | None:
        """Get step by ID."""
        for step in self._steps:
            if step.step_id == step_id:
                return step
        return None

    def _mark_step_error(self, step_id: str, error: str) -> None:
        """Mark a step as failed."""
        step = self._get_step(step_id)
        if step:
            step.status = WorkflowStatus.FAILED
            step.error = error
        self._errors.append(error)

    def _mark_step_warning(self, step_id: str, warning: str) -> None:
        """Mark a step with a warning."""
        step = self._get_step(step_id)
        if step:
            step.metadata.setdefault("warnings", []).append(warning)
        self._warnings.append(f"[{step_id}] {warning}")

    # ─── Sub-system Injection ─────────────────────────────────────────

    def inject_reasoning_loop(self, reasoning_loop) -> None:
        """Inject ReasoningLoop instance."""
        self._reasoning_loop = reasoning_loop

    def inject_knowledge_base(self, kb) -> None:
        """Inject KnowledgeBase instance."""
        self._knowledge_base = kb

    def inject_hardware_validator(self, validator) -> None:
        """Inject HardwareValidator instance."""
        self._hardware_validator = validator

    # ─── Abstract Methods ─────────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Workflow name."""
        ...

    @property
    def description(self) -> str:
        """Workflow description."""
        return ""

    @abstractmethod
    async def _execute(self) -> dict[str, Any]:
        """
        Execute the workflow.

        Implement workflow logic here using:
        - self.add_step() to define steps
        - self.run_step() to execute with tracking
        - self._knowledge_base to query hardware knowledge
        - self._reasoning_loop to perform formal reasoning
        - self._hardware_validator to validate hardware

        Returns:
            Final result dict
        """
        ...
