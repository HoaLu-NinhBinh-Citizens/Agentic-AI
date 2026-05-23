"""Trust and approval workflow for patch management (Phase 9.3).

Provides:
- Confidence scoring
- Risk assessment integration
- Human approval workflow
- WebSocket/CLI/REST approval endpoints
- Approval timeout and auto-rejection
- Rollback on rejection
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ApprovalAction(Enum):
    """Approval action types."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


@dataclass
class ApprovalRequest:
    """Patch approval request."""
    id: str
    patch_id: str
    patch_title: str
    risk_level: str
    risk_score: float
    confidence: float
    requester: str
    status: ApprovalAction = ApprovalAction.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(hours=24))
    approver: str | None = None
    approver_comment: str | None = None
    decided_at: datetime | None = None
    
    @property
    def is_expired(self) -> bool:
        """Check if request has expired."""
        return datetime.now() > self.expires_at
    
    @property
    def is_pending(self) -> bool:
        """Check if still pending."""
        return self.status == ApprovalAction.PENDING and not self.is_expired


@dataclass
class ApprovalConfig:
    """Approval workflow configuration."""
    auto_approve_threshold: float = 0.0  # Risk score below this auto-approves
    auto_reject_threshold: float = 10.0  # Risk score above this auto-rejects
    default_timeout_hours: int = 24
    require_approver_for_high_risk: bool = True
    approval_webhook: str | None = None
    min_confidence_for_auto_approve: float = 0.9


class ApprovalWorkflow:
    """Trust and approval workflow manager.
    
    Phase 9.3: Trust & approval gates
    Phase 9.3a: Approval workflow (WS, CLI, REST, timeout, rollback)
    """
    
    def __init__(self, config: ApprovalConfig | None = None) -> None:
        self.config = config or ApprovalConfig()
        self._pending_requests: dict[str, ApprovalRequest] = {}
        self._approved_history: list[ApprovalRequest] = []
        self._callbacks: dict[str, list[Callable]] = {
            "approved": [],
            "rejected": [],
            "expired": [],
        }
    
    def request_approval(
        self,
        patch_id: str,
        patch_title: str,
        risk_level: str,
        risk_score: float,
        confidence: float,
        requester: str,
        timeout_hours: int | None = None,
    ) -> ApprovalRequest:
        """Create approval request for a patch."""
        # Auto-decide if risk is clear
        if risk_score <= self.config.auto_approve_threshold and confidence >= self.config.min_confidence_for_auto_approve:
            request = ApprovalRequest(
                id=str(uuid.uuid4())[:8],
                patch_id=patch_id,
                patch_title=patch_title,
                risk_level=risk_level,
                risk_score=risk_score,
                confidence=confidence,
                requester=requester,
                status=ApprovalAction.APPROVED,
                approver="AUTO",
                approver_comment="Auto-approved: risk score below threshold",
                decided_at=datetime.now(),
            )
            self._approved_history.append(request)
            self._emit("approved", request)
            return request
        
        if risk_score >= self.config.auto_reject_threshold:
            request = ApprovalRequest(
                id=str(uuid.uuid4())[:8],
                patch_id=patch_id,
                patch_title=patch_title,
                risk_level=risk_level,
                risk_score=risk_score,
                confidence=confidence,
                requester=requester,
                status=ApprovalAction.REJECTED,
                approver="AUTO",
                approver_comment="Auto-rejected: risk score exceeds threshold",
                decided_at=datetime.now(),
            )
            self._approved_history.append(request)
            self._emit("rejected", request)
            return request
        
        # Create pending request
        request = ApprovalRequest(
            id=str(uuid.uuid4())[:8],
            patch_id=patch_id,
            patch_title=patch_title,
            risk_level=risk_level,
            risk_score=risk_score,
            confidence=confidence,
            requester=requester,
            status=ApprovalAction.PENDING,
            expires_at=datetime.now() + timedelta(
                hours=timeout_hours or self.config.default_timeout_hours
            ),
        )
        
        self._pending_requests[request.id] = request
        self._emit("pending", request)
        
        logger.info(
            "Approval requested",
            request_id=request.id,
            patch_id=patch_id,
            risk_score=risk_score,
        )
        
        return request
    
    async def wait_for_approval(
        self,
        request_id: str,
        poll_interval: float = 5.0,
    ) -> ApprovalRequest:
        """Wait for approval (async polling)."""
        while True:
            request = self._pending_requests.get(request_id)
            
            if not request or not request.is_pending:
                if request:
                    return request
                raise ValueError(f"Request {request_id} not found")
            
            await asyncio.sleep(poll_interval)
    
    def approve(
        self,
        request_id: str,
        approver: str,
        comment: str | None = None,
    ) -> bool:
        """Approve a pending request."""
        request = self._pending_requests.get(request_id)
        
        if not request:
            logger.error("Approval request not found", request_id=request_id)
            return False
        
        if not request.is_pending:
            logger.warning("Request already decided", status=request.status.value)
            return False
        
        request.status = ApprovalAction.APPROVED
        request.approver = approver
        request.approver_comment = comment
        request.decided_at = datetime.now()
        
        self._approved_history.append(request)
        del self._pending_requests[request_id]
        
        self._emit("approved", request)
        
        logger.info(
            "Patch approved",
            request_id=request_id,
            approver=approver,
        )
        
        return True
    
    def reject(
        self,
        request_id: str,
        approver: str,
        comment: str | None = None,
        trigger_rollback: bool = False,
    ) -> bool:
        """Reject a pending request."""
        request = self._pending_requests.get(request_id)
        
        if not request:
            logger.error("Approval request not found", request_id=request_id)
            return False
        
        if not request.is_pending:
            logger.warning("Request already decided", status=request.status.value)
            return False
        
        request.status = ApprovalAction.REJECTED
        request.approver = approver
        request.approver_comment = comment
        request.decided_at = datetime.now()
        
        self._approved_history.append(request)
        del self._pending_requests[request_id]
        
        self._emit("rejected", request)
        
        logger.info(
            "Patch rejected",
            request_id=request_id,
            approver=approver,
            rollback=trigger_rollback,
        )
        
        if trigger_rollback:
            self._rollback_patch(request.patch_id)
        
        return True
    
    def _rollback_patch(self, patch_id: str) -> None:
        """Trigger rollback for rejected patch."""
        from src.infrastructure.patching.patch_sandbox import get_patch_sandbox
        
        sandbox = get_patch_sandbox()
        asyncio.create_task(sandbox.rollback(patch_id))
        
        logger.info("Rollback triggered", patch_id=patch_id)
    
    def cancel(self, request_id: str, requester: str) -> bool:
        """Cancel a pending request."""
        request = self._pending_requests.get(request_id)
        
        if not request:
            return False
        
        if request.requester != requester:
            logger.warning("Only requester can cancel", requester=requester)
            return False
        
        request.status = ApprovalAction.CANCELLED
        request.decided_at = datetime.now()
        
        del self._pending_requests[request_id]
        
        self._emit("cancelled", request)
        
        logger.info("Request cancelled", request_id=request_id)
        return True
    
    def expire_stale_requests(self) -> list[ApprovalRequest]:
        """Expire old pending requests."""
        expired = []
        
        for request_id, request in list(self._pending_requests.items()):
            if request.is_expired:
                request.status = ApprovalAction.TIMED_OUT
                request.decided_at = datetime.now()
                self._approved_history.append(request)
                del self._pending_requests[request_id]
                expired.append(request)
                self._emit("expired", request)
        
        if expired:
            logger.info("Expired stale requests", count=len(expired))
        
        return expired
    
    def get_pending(self) -> list[ApprovalRequest]:
        """Get all pending requests."""
        return [r for r in self._pending_requests.values() if r.is_pending]
    
    def get_history(self, limit: int = 50) -> list[ApprovalRequest]:
        """Get approval history."""
        return list(reversed(self._approved_history[-limit:]))
    
    def register_callback(
        self,
        event: str,
        callback: Callable[[ApprovalRequest], None],
    ) -> None:
        """Register callback for approval events."""
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _emit(self, event: str, request: ApprovalRequest) -> None:
        """Emit event to callbacks."""
        for callback in self._callbacks.get(event, []):
            try:
                callback(request)
            except Exception as e:
                logger.error("Callback error", event=event, error=str(e))
    
    def get_status_summary(self) -> dict[str, Any]:
        """Get approval status summary."""
        return {
            "pending": len(self.get_pending()),
            "expired": len([r for r in self._approved_history if r.status == ApprovalAction.TIMED_OUT]),
            "approved": len([r for r in self._approved_history if r.status == ApprovalAction.APPROVED]),
            "rejected": len([r for r in self._approved_history if r.status == ApprovalAction.REJECTED]),
        }


# Global singleton
_approval_workflow: ApprovalWorkflow | None = None


def get_approval_workflow() -> ApprovalWorkflow:
    """Get global approval workflow instance."""
    global _approval_workflow
    if _approval_workflow is None:
        _approval_workflow = ApprovalWorkflow()
    return _approval_workflow


# REST API helpers
def create_approval_endpoints(app: Any) -> None:
    """Create FastAPI endpoints for approval workflow."""
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
    
    router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])
    
    class ApprovalRequestCreate(BaseModel):
        patch_id: str
        patch_title: str
        risk_level: str
        risk_score: float
        confidence: float
        requester: str
    
    class ApprovalDecision(BaseModel):
        request_id: str
        action: str  # "approve" or "reject"
        approver: str
        comment: str | None = None
        trigger_rollback: bool = False
    
    @router.post("/")
    async def create_approval(req: ApprovalRequestCreate):
        """Create new approval request."""
        workflow = get_approval_workflow()
        request = workflow.request_approval(
            patch_id=req.patch_id,
            patch_title=req.patch_title,
            risk_level=req.risk_level,
            risk_score=req.risk_score,
            confidence=req.confidence,
            requester=req.requester,
        )
        return {"request_id": request.id, "status": request.status.value}
    
    @router.get("/")
    async def list_pending():
        """List pending approval requests."""
        workflow = get_approval_workflow()
        return {"pending": workflow.get_pending()}
    
    @router.post("/decide")
    async def decide_approval(decision: ApprovalDecision):
        """Approve or reject a request."""
        workflow = get_approval_workflow()
        
        if decision.action == "approve":
            success = workflow.approve(decision.request_id, decision.approver, decision.comment)
        else:
            success = workflow.reject(
                decision.request_id,
                decision.approver,
                decision.comment,
                decision.trigger_rollback,
            )
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to process decision")
        
        return {"success": True}
    
    @router.get("/history")
    async def get_history(limit: int = 50):
        """Get approval history."""
        workflow = get_approval_workflow()
        return {"history": workflow.get_history(limit)}
    
    @router.get("/summary")
    async def get_summary():
        """Get approval status summary."""
        workflow = get_approval_workflow()
        return workflow.get_status_summary()
    
    # Register router with app
    if hasattr(app, "include_router"):
        app.include_router(router)
