"""
Workflow Rollback Engine

Deterministic rollback/compensation for workflow failures:
- Checkpoint-based state snapshots
- Compensation actions in reverse dependency order
- Rollback policies: ABORT, COMPENSATE, IGNORE
- Idempotent compensation support
- Rollback state machine integration
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class RollbackPolicy(Enum):
    """Rollback behavior when workflow fails."""
    ABORT = "abort"       # Stop immediately, no rollback
    COMPENSATE = "compensate"  # Execute compensation actions
    IGNORE = "ignore"     # Mark as failed, continue


class RollbackState(Enum):
    """Rollback execution states."""
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # Some compensations failed


class CompensationStatus(Enum):
    """Status of a compensation action."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_NEEDED = "not_needed"


@dataclass
class Checkpoint:
    """
    Snapshot of workflow state at a point in time.

    Captures step outputs and workflow variables for rollback.
    """
    id: str
    workflow_id: str
    step_id: str
    timestamp: datetime
    step_output: Any = None
    workflow_variables: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "step_id": self.step_id,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class CompensationAction:
    """
    Defines how to compensate/rollback a step.

    Attributes:
        step_id: The step to compensate
        compensate_fn: Async function(step, checkpoint, context) -> result
        timeout: Max time for compensation
        retry_policy: How to retry failed compensation
        idempotent: If True, safe to call multiple times
        required: If True, failure blocks workflow completion
    """
    step_id: str
    step_name: str
    compensate_fn: Callable
    timeout: int = 30
    retry_policy: Optional[Any] = None  # RetryPolicy
    idempotent: bool = True
    required: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompensationResult:
    """Result of executing a compensation action."""
    step_id: str
    status: CompensationStatus
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    attempts: int = 1
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "attempts": self.attempts,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class RollbackContext:
    """Context for rollback execution."""
    workflow_id: str
    workflow_variables: Dict[str, Any] = field(default_factory=dict)
    checkpoints: Dict[str, Checkpoint] = field(default_factory=dict)
    completed_steps: Set[str] = field(default_factory=set)
    _completion_order: List[str] = field(default_factory=list)  # Track completion order
    rollback_results: Dict[str, CompensationResult] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def add_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Add a checkpoint."""
        self.checkpoints[checkpoint.step_id] = checkpoint

    def get_checkpoint(self, step_id: str) -> Optional[Checkpoint]:
        """Get checkpoint for a step."""
        return self.checkpoints.get(step_id)

    def mark_completed(self, step_id: str) -> None:
        """Mark a step as completed in order."""
        if step_id not in self.completed_steps:
            self.completed_steps.add(step_id)
            self._completion_order.append(step_id)

    def get_reverse_order(self) -> List[str]:
        """Get completed steps in reverse order of completion."""
        return list(reversed(self._completion_order))


class RollbackEngine:
    """
    Deterministic rollback engine for workflow failures.

    Features:
    - Checkpoint-based state snapshots
    - Compensation in reverse dependency order
    - Idempotent compensation support
    - Partial rollback handling
    - Rollback state machine

    Usage:
        engine = RollbackEngine()

        # Register compensation actions
        engine.register_compensation(
            step_id="step_1",
            compensate_fn=my_compensation,
            idempotent=True,
        )

        # Capture checkpoint after step
        engine.capture_checkpoint(
            workflow_id="wf-1",
            step_id="step_1",
            step_output=result.output,
            workflow_variables={"counter": 5},
        )

        # Execute rollback on failure
        result = await engine.rollback(
            workflow_id="wf-1",
            rollback_context=ctx,
        )
    """

    def __init__(
        self,
        default_policy: RollbackPolicy = RollbackPolicy.COMPENSATE,
        default_timeout: int = 30,
        max_rollback_attempts: int = 3,
    ):
        self.default_policy = default_policy
        self.default_timeout = default_timeout
        self.max_rollback_attempts = max_rollback_attempts

        self._compensation_actions: Dict[str, CompensationAction] = {}
        self._rollback_handlers: Dict[str, Callable] = {}

        # Rollback statistics
        self._stats = {
            "total_rollbacks": 0,
            "successful_rollbacks": 0,
            "failed_rollbacks": 0,
            "partial_rollbacks": 0,
        }

    def register_compensation(
        self,
        step_id: str,
        compensate_fn: Callable,
        step_name: str = "",
        timeout: int = 30,
        idempotent: bool = True,
        required: bool = True,
        retry_policy: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register a compensation action for a step.

        Args:
            step_id: Step identifier
            compensate_fn: Async function(step, checkpoint, context) -> result
            step_name: Human-readable name
            timeout: Max execution time
            idempotent: Safe to retry
            required: Must succeed to mark rollback complete
            retry_policy: Retry configuration
            metadata: Additional data
        """
        action = CompensationAction(
            step_id=step_id,
            step_name=step_name or step_id,
            compensate_fn=compensate_fn,
            timeout=timeout,
            retry_policy=retry_policy,
            idempotent=idempotent,
            required=required,
            metadata=metadata or {},
        )
        self._compensation_actions[step_id] = action
        logger.debug(f"Registered compensation for step: {step_id}")

    def unregister_compensation(self, step_id: str) -> bool:
        """Remove compensation action."""
        if step_id in self._compensation_actions:
            del self._compensation_actions[step_id]
            return True
        return False

    def get_compensation(self, step_id: str) -> Optional[CompensationAction]:
        """Get compensation action."""
        return self._compensation_actions.get(step_id)

    def on_rollback(self, handler: Callable) -> Callable:
        """
        Decorator to register rollback handler.

        Usage:
            @engine.on_rollback()
            async def rollback_handler(workflow_id, rollback_context):
                # Custom rollback logic
                pass
        """
        self._rollback_handlers["global"] = handler
        return handler

    def capture_checkpoint(
        self,
        workflow_id: str,
        step_id: str,
        step_output: Any = None,
        workflow_variables: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Checkpoint:
        """
        Capture a checkpoint before step execution.

        Args:
            workflow_id: Workflow identifier
            step_id: Step identifier
            step_output: Output from step (before changes)
            workflow_variables: Current workflow variables
            metadata: Additional checkpoint data

        Returns:
            Checkpoint object
        """
        from uuid import uuid4

        checkpoint = Checkpoint(
            id=str(uuid4())[:16],
            workflow_id=workflow_id,
            step_id=step_id,
            timestamp=datetime.now(),
            step_output=step_output,
            workflow_variables=workflow_variables or {},
            metadata=metadata or {},
        )

        logger.debug(
            f"Captured checkpoint for workflow {workflow_id}, step {step_id}"
        )
        return checkpoint

    async def execute_rollback(
        self,
        workflow_id: str,
        rollback_context: RollbackContext,
        failed_step_id: str,
        failed_step_output: Any = None,
        policy: Optional[RollbackPolicy] = None,
    ) -> Dict[str, CompensationResult]:
        """
        Execute rollback for a failed workflow.

        Args:
            workflow_id: Workflow identifier
            rollback_context: Rollback context with checkpoints
            failed_step_id: Step that failed
            failed_step_output: Output from failed step
            policy: Override default policy

        Returns:
            Dict mapping step_id to CompensationResult
        """
        policy = policy or self.default_policy

        if policy == RollbackPolicy.ABORT:
            logger.info(f"Rollback ABORT for workflow {workflow_id}")
            return {}

        if policy == RollbackPolicy.IGNORE:
            logger.info(f"Rollback IGNORE for workflow {workflow_id}")
            return {
                failed_step_id: CompensationResult(
                    step_id=failed_step_id,
                    status=CompensationStatus.NOT_NEEDED,
                )
            }

        # COMPENSATE policy
        logger.info(
            f"Executing COMPENSATE rollback for workflow {workflow_id}, "
            f"failed at step {failed_step_id}"
        )

        rollback_context.started_at = datetime.now()
        results: Dict[str, CompensationResult] = {}

        # Get steps to compensate (reverse order of completion)
        steps_to_compensate = rollback_context.get_reverse_order()

        # Skip the failed step itself
        if failed_step_id in steps_to_compensate:
            steps_to_compensate.remove(failed_step_id)

        for step_id in steps_to_compensate:
            checkpoint = rollback_context.get_checkpoint(step_id)
            compensation = self.get_compensation(step_id)

            if not compensation:
                logger.debug(f"No compensation registered for step: {step_id}")
                results[step_id] = CompensationResult(
                    step_id=step_id,
                    status=CompensationStatus.SKIPPED,
                )
                continue

            # Execute compensation
            result = await self._execute_compensation(
                step_id=step_id,
                compensation=compensation,
                checkpoint=checkpoint,
                rollback_context=rollback_context,
            )
            results[step_id] = result

            # Check if required compensation failed
            if result.status == CompensationStatus.FAILED and compensation.required:
                logger.error(f"Required compensation failed for step: {step_id}")
                rollback_context.rollback_results.update(results)
                rollback_context.completed_at = datetime.now()
                self._stats["partial_rollbacks"] += 1
                return results

        rollback_context.rollback_results.update(results)
        rollback_context.completed_at = datetime.now()
        self._stats["total_rollbacks"] += 1

        # Determine overall result
        failed_count = sum(
            1 for r in results.values()
            if r.status == CompensationStatus.FAILED
        )
        if failed_count == 0:
            self._stats["successful_rollbacks"] += 1
        else:
            self._stats["partial_rollbacks"] += 1

        logger.info(
            f"Rollback complete for workflow {workflow_id}: "
            f"{len(results)} compensations executed"
        )

        return results

    async def _execute_compensation(
        self,
        step_id: str,
        compensation: CompensationAction,
        checkpoint: Optional[Checkpoint],
        rollback_context: RollbackContext,
    ) -> CompensationResult:
        """Execute a single compensation action."""
        start_time = datetime.now()
        attempts = 0

        max_attempts = self.max_rollback_attempts
        if compensation.retry_policy:
            max_attempts = compensation.retry_policy.max_attempts

        while attempts < max_attempts:
            attempts += 1

            try:
                # Execute compensation with timeout
                result = await asyncio.wait_for(
                    compensation.compensate_fn(
                        step_id=step_id,
                        checkpoint=checkpoint,
                        context=rollback_context,
                    ),
                    timeout=compensation.timeout,
                )

                duration_ms = (
                    datetime.now() - start_time
                ).total_seconds() * 1000

                return CompensationResult(
                    step_id=step_id,
                    status=CompensationStatus.COMPLETED,
                    output=result,
                    duration_ms=duration_ms,
                    attempts=attempts,
                )

            except asyncio.TimeoutError:
                logger.warning(
                    f"Compensation timeout for step {step_id}, "
                    f"attempt {attempts}/{max_attempts}"
                )
                if attempts >= max_attempts:
                    return CompensationResult(
                        step_id=step_id,
                        status=CompensationStatus.FAILED,
                        error=f"Timeout after {attempts} attempts",
                        duration_ms=(
                            datetime.now() - start_time
                        ).total_seconds() * 1000,
                        attempts=attempts,
                    )

            except Exception as e:
                logger.warning(
                    f"Compensation failed for step {step_id}: {e}, "
                    f"attempt {attempts}/{max_attempts}"
                )
                if attempts >= max_attempts:
                    return CompensationResult(
                        step_id=step_id,
                        status=CompensationStatus.FAILED,
                        error=str(e),
                        duration_ms=(
                            datetime.now() - start_time
                        ).total_seconds() * 1000,
                        attempts=attempts,
                    )

            # Wait before retry (exponential backoff)
            if attempts < max_attempts:
                await asyncio.sleep(min(2 ** attempts, 10))

        return CompensationResult(
            step_id=step_id,
            status=CompensationStatus.FAILED,
            error="Max attempts exceeded",
            duration_ms=(
                datetime.now() - start_time
            ).total_seconds() * 1000,
            attempts=attempts,
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get rollback statistics."""
        return {
            **self._stats,
            "registered_compensations": len(self._compensation_actions),
        }

    def reset_stats(self) -> None:
        """Reset statistics."""
        self._stats = {
            "total_rollbacks": 0,
            "successful_rollbacks": 0,
            "failed_rollbacks": 0,
            "partial_rollbacks": 0,
        }


# Global rollback engine instance
_rollback_engine: Optional[RollbackEngine] = None


def get_rollback_engine() -> RollbackEngine:
    """Get the global rollback engine."""
    global _rollback_engine
    if _rollback_engine is None:
        _rollback_engine = RollbackEngine()
    return _rollback_engine
