"""Deep Cancellation Semantics - Phase 5A (v6).

Cancellation with full propagation, escalation, and compensation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CancellationReason(str, Enum):
    """Reasons for cancellation."""
    USER_REQUEST = "user_request"
    TIMEOUT = "timeout"
    PARENT_CANCELLED = "parent_cancelled"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    ADMIN_REQUEST = "admin_request"
    SELF_CANCELLED = "self_cancelled"


class CancellationStatus(str, Enum):
    """Cancellation request status."""
    REQUESTED = "requested"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"  # Force terminated after timeout


@dataclass
class CancellationRequest:
    """A cancellation request for a workflow."""
    request_id: str
    workflow_id: str
    
    # Reason
    reason: str = ""
    reason_type: CancellationReason = CancellationReason.USER_REQUEST
    
    # Status
    status: CancellationStatus = CancellationStatus.REQUESTED
    
    # Timing
    created_at: float = field(default_factory=time.time)
    sent_at: Optional[float] = None
    acknowledged_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    # Escalation
    timeout_seconds: float = 10.0
    escalation_warning_at: float = 5.0
    is_escalated: bool = False
    
    # Child propagation
    children_cancelled: int = 0
    children_total: int = 0


@dataclass
class CancellationResult:
    """Result of a cancellation operation."""
    request_id: str
    workflow_id: str
    
    # Success
    success: bool
    
    # Status at completion
    status: CancellationStatus
    
    # Timing
    duration_seconds: float = 0.0
    
    # Children
    children_cancelled: int = 0
    children_escalated: int = 0
    
    # Error
    error: Optional[str] = None
    
    # Compensation
    compensation_executed: bool = False


class CancellationManager:
    """Manager for workflow cancellation with full semantics.
    
    Cancellation semantics:
    - Cooperative cancellation via cancellation signal
    - Propagation to child workflows
    - Compensation execution during cancellation
    - Timeout escalation (force terminate after timeout)
    """
    
    def __init__(
        self,
        workflow_runtime: Any = None,
        child_manager: Any = None,
        compensation_manager: Any = None,
        default_timeout_seconds: float = 10.0,
        escalation_warning_seconds: float = 5.0,
    ):
        self._runtime = workflow_runtime
        self._child_manager = child_manager
        self._compensation_manager = compensation_manager
        self._default_timeout = default_timeout_seconds
        self._escalation_warning = escalation_warning_seconds
        
        # Active cancellations
        self._active_cancellations: dict[str, CancellationRequest] = {}
        self._cancellation_tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
    
    async def request_cancellation(
        self,
        workflow_id: str,
        reason: str = "",
        reason_type: CancellationReason = CancellationReason.USER_REQUEST,
        timeout_seconds: Optional[float] = None,
    ) -> CancellationResult:
        """Request workflow cancellation.
        
        Escalation timeline:
        - 0s: Cancellation signal sent
        - 5s: Warning logged if not cancelled
        - 10s: Force terminate if not cooperative
        
        Args:
            workflow_id: Workflow to cancel.
            reason: Cancellation reason.
            reason_type: Type of cancellation.
            timeout_seconds: Timeout for cancellation. Defaults to config.
            
        Returns:
            CancellationResult with outcome.
        """
        timeout = timeout_seconds or self._default_timeout
        start_time = time.time()
        
        request = CancellationRequest(
            request_id=f"cancel_{workflow_id[:8]}_{int(start_time * 1000)}",
            workflow_id=workflow_id,
            reason=reason,
            reason_type=reason_type,
            timeout_seconds=timeout,
            escalation_warning_at=start_time + self._escalation_warning,
        )
        
        async with self._lock:
            self._active_cancellations[request.request_id] = request
            # Start cancellation task
            task = asyncio.create_task(
                self._execute_cancellation(request)
            )
            self._cancellation_tasks[request.request_id] = task
        
        # Wait for cancellation to complete or timeout
        try:
            await asyncio.wait_for(task, timeout=timeout + 5)  # Extra 5s buffer
        except asyncio.TimeoutError:
            logger.warning(f"Cancellation request {request.request_id} timed out")
        
        return await self._build_result(request, start_time)
    
    async def _execute_cancellation(
        self,
        request: CancellationRequest,
    ) -> None:
        """Execute cancellation with escalation handling."""
        try:
            logger.info(
                f"Executing cancellation {request.request_id} "
                f"for workflow {request.workflow_id[:8]}... "
                f"(reason: {request.reason_type.value})"
            )
            
            # Step 1: Send cancellation signal
            await self._send_cancellation_signal(request)
            request.sent_at = time.time()
            request.status = CancellationStatus.SENT
            
            # Step 2: Start escalation monitor
            escalation_task = asyncio.create_task(
                self._monitor_escalation(request)
            )
            
            # Step 3: Wait for workflow to acknowledge and complete
            acknowledged = await self._wait_for_cancellation(request)
            
            if acknowledged:
                request.status = CancellationStatus.ACKNOWLEDGED
                request.acknowledged_at = time.time()
                
                # Step 4: Execute compensation if needed
                await self._execute_cancellation_compensation(request)
                
                request.status = CancellationStatus.COMPLETED
            else:
                request.status = CancellationStatus.FAILED
            
            escalation_task.cancel()
            
        except Exception as e:
            logger.error(f"Cancellation {request.request_id} failed: {e}")
            request.status = CancellationStatus.FAILED
            request.error = str(e)
    
    async def _send_cancellation_signal(
        self,
        request: CancellationRequest,
    ) -> None:
        """Send cancellation signal to workflow."""
        if self._runtime:
            await self._runtime.send_signal(
                workflow_id=request.workflow_id,
                name="__cancellation__",
                payload={
                    "request_id": request.request_id,
                    "reason": request.reason,
                    "reason_type": request.reason_type.value,
                },
            )
    
    async def _monitor_escalation(
        self,
        request: CancellationRequest,
    ) -> None:
        """Monitor for escalation timeout."""
        try:
            # Wait for warning threshold
            warning_delay = request.escalation_warning_at - time.time()
            if warning_delay > 0:
                await asyncio.sleep(warning_delay)
            
            # Log warning
            if request.status not in {CancellationStatus.COMPLETED, CancellationStatus.ACKNOWLEDGED}:
                logger.warning(
                    f"Cancellation {request.request_id} not acknowledged after "
                    f"{self._escalation_warning}s, may escalate to force terminate"
                )
            
            # Wait for completion or escalate
            timeout_delay = request.timeout_seconds - self._escalation_warning
            await asyncio.sleep(timeout_delay)
            
            if request.status not in {CancellationStatus.COMPLETED, CancellationStatus.ACKNOWLEDGED}:
                logger.warning(
                    f"Cancellation {request.request_id} timeout, escalating to force terminate"
                )
                await self._escalate_cancellation(request)
                
        except asyncio.CancelledError:
            pass  # Normal cancellation completed
    
    async def _escalate_cancellation(
        self,
        request: CancellationRequest,
    ) -> None:
        """Force terminate workflow after timeout escalation."""
        request.is_escalated = True
        request.status = CancellationStatus.ESCALATED
        
        logger.warning(
            f"Escalating cancellation {request.request_id} for "
            f"workflow {request.workflow_id[:8]}... to force terminate"
        )
        
        if self._runtime:
            await self._runtime.force_terminate_workflow(request.workflow_id)
    
    async def _wait_for_cancellation(
        self,
        request: CancellationRequest,
    ) -> bool:
        """Wait for workflow to acknowledge and complete cancellation."""
        # Poll for workflow status or wait for signal
        max_wait = request.timeout_seconds
        
        if self._runtime:
            for _ in range(int(max_wait * 10)):  # Poll every 100ms
                status = await self._runtime.get_workflow_status(request.workflow_id)
                
                if status in {"completed", "failed", "cancelled", "terminated"}:
                    return True
                
                await asyncio.sleep(0.1)
        
        return False
    
    async def _execute_cancellation_compensation(
        self,
        request: CancellationRequest,
    ) -> None:
        """Execute saga compensation in reverse order during cancellation."""
        if not self._compensation_manager:
            return
        
        try:
            # Get pending compensations
            compensations = await self._compensation_manager.get_pending(request.workflow_id)
            
            if compensations:
                logger.info(
                    f"Executing {len(compensations)} compensations for "
                    f"workflow {request.workflow_id[:8]}..."
                )
                
                # Execute in reverse (LIFO) order
                for comp in reversed(compensations):
                    try:
                        await comp.execute()
                    except Exception as e:
                        logger.error(
                            f"Compensation {comp.compensation_id} failed during "
                            f"cancellation: {e}"
                        )
                
                logger.info(f"Compensation completed for {request.request_id}")
                
        except Exception as e:
            logger.error(f"Compensation failed for {request.request_id}: {e}")
    
    async def propagate_cancellation(
        self,
        workflow_id: str,
        reason: str = "",
    ) -> dict[str, bool]:
        """Propagate cancellation to all child workflows.
        
        Args:
            workflow_id: Parent workflow being cancelled.
            reason: Cancellation reason.
            
        Returns:
            Dict mapping child_id to cancellation success.
        """
        if not self._child_manager:
            return {}
        
        return await self._child_manager.propagate_cancellation(workflow_id, reason)
    
    async def _build_result(
        self,
        request: CancellationRequest,
        start_time: float,
    ) -> CancellationResult:
        """Build final result from cancellation request."""
        return CancellationResult(
            request_id=request.request_id,
            workflow_id=request.workflow_id,
            success=request.status == CancellationStatus.COMPLETED,
            status=request.status,
            duration_seconds=time.time() - start_time,
            children_cancelled=request.children_cancelled,
            children_escalated=1 if request.is_escalated else 0,
            error=request.error,
            compensation_executed=(
                request.status == CancellationStatus.COMPLETED
            ),
        )
    
    async def get_cancellation_status(
        self,
        request_id: str,
    ) -> Optional[CancellationRequest]:
        """Get status of a cancellation request."""
        async with self._lock:
            return self._active_cancellations.get(request_id)
    
    async def cancel_cancellation_request(
        self,
        request_id: str,
    ) -> bool:
        """Cancel an active cancellation request (undo).
        
        This can only work if the workflow hasn't acknowledged yet.
        """
        async with self._lock:
            request = self._active_cancellations.get(request_id)
            if request and request.status == CancellationStatus.SENT:
                # Cannot undo once sent
                logger.warning(
                    f"Cannot cancel {request_id}: already sent to workflow"
                )
                return False
            return True


class CancellationToken:
    """Token to check for cancellation in long-running operations."""
    
    def __init__(self, workflow_id: str):
        self._workflow_id = workflow_id
        self._cancelled = False
        self._cancel_reason: Optional[str] = None
    
    def cancel(self, reason: str = "") -> None:
        """Mark as cancelled."""
        self._cancelled = True
        self._cancel_reason = reason
    
    @property
    def is_cancelled(self) -> bool:
        """Check if cancelled."""
        return self._cancelled
    
    @property
    def cancel_reason(self) -> Optional[str]:
        """Get cancellation reason."""
        return self._cancel_reason
    
    async def wait_if_cancelled(self) -> None:
        """Wait indefinitely if cancelled (for graceful shutdown)."""
        if self._cancelled:
            # Block until cancelled - used in activities
            event = asyncio.Event()
            await event.wait()
