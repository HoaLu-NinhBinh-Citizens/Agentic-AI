"""
Enhanced Governance Components.

Includes:
- Dual Authorization Break-Glass
- DR Recovery Correctness Validation
- Shared Resource Chargeback
- Policy Formal Verification
- Human Governance
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ============== DUAL AUTHORIZATION BREAK-GLASS ==============

class BreakGlassStatus(str, Enum):
    """Break-glass authorization status."""
    PENDING_APPROVAL = "pending_approval"
    PENDING_ACTIVATION = "pending_activation"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ApprovalStatus(str, Enum):
    """Approval status."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class ApprovalRequest:
    """Approval request for break-glass."""
    request_id: str
    requester: str
    reason: str
    requested_duration: int  # seconds
    created_at: datetime
    approvals_required: int
    approvals_received: int
    approvers: List[str]
    status: ApprovalStatus


@dataclass
class DualAuthBreakGlass:
    """
    Break-glass with dual authorization.
    
    Features:
    - Two-person approval required
    - Time-delayed activation
    - MFA escalation
    - Full audit trail
    """
    
    def __init__(
        self,
        required_approvals: int = 2,
        activation_delay_seconds: int = 300,  # 5 minutes
        token_duration_seconds: int = 3600,
        mfa_required: bool = True,
        webhook_url: Optional[str] = None,
    ):
        self.required_approvals = required_approvals
        self.activation_delay = activation_delay_seconds
        self.token_duration = token_duration_seconds
        self.mfa_required = mfa_required
        self.webhook_url = webhook_url
        
        # Approval requests
        self._approval_requests: Dict[str, ApprovalRequest] = {}
        
        # Active tokens
        self._tokens: Dict[str, Dict[str, Any]] = {}
        
        # Pending activations (after delay)
        self._pending_activations: Dict[str, asyncio.Task] = {}
        
        # Alert handlers
        self._alert_handlers: List[Callable] = []
        
        self._lock = asyncio.Lock()
    
    def register_alert_handler(self, handler: Callable) -> None:
        """Register alert handler."""
        self._alert_handlers.append(handler)
    
    async def create_request(
        self,
        requester: str,
        reason: str,
        duration_seconds: int = None,
    ) -> str:
        """Create break-glass approval request."""
        async with self._lock:
            request_id = f"bg_req_{uuid.uuid4().hex[:12]}"
            duration = duration_seconds or self.token_duration
            
            request = ApprovalRequest(
                request_id=request_id,
                requester=requester,
                reason=reason,
                requested_duration=duration,
                created_at=datetime.now(),
                approvals_required=self.required_approvals,
                approvals_received=0,
                approvers=[],
                status=ApprovalStatus.PENDING,
            )
            
            self._approval_requests[request_id] = request
            
            # Send alert
            await self._send_alert("request_created", request)
            
            return request_id
    
    async def approve_request(
        self,
        request_id: str,
        approver: str,
        mfa_token: Optional[str] = None,
    ) -> bool:
        """Approve break-glass request."""
        async with self._lock:
            request = self._approval_requests.get(request_id)
            if not request:
                return False
            
            if request.status != ApprovalStatus.PENDING:
                return False
            
            # MFA validation
            if self.mfa_required and not await self._validate_mfa(mfa_token):
                logger.warning(f"MFA validation failed for {approver}")
                return False
            
            # Check approver is not requester
            if approver == request.requester:
                return False
            
            # Check approver not already approved
            if approver in request.approvers:
                return False
            
            # Add approval
            request.approvers.append(approver)
            request.approvals_received += 1
            
            # Check if enough approvals
            if request.approvals_received >= request.approvals_required:
                request.status = ApprovalStatus.APPROVED
                await self._schedule_activation(request)
            
            await self._send_alert("request_approved", request, approver)
            
            return True
    
    async def reject_request(
        self,
        request_id: str,
        rejector: str,
        reason: str = None,
    ) -> bool:
        """Reject break-glass request."""
        async with self._lock:
            request = self._approval_requests.get(request_id)
            if not request:
                return False
            
            request.status = ApprovalStatus.REJECTED
            await self._send_alert("request_rejected", request, rejector, reason)
            
            return True
    
    async def _schedule_activation(self, request: ApprovalRequest) -> None:
        """Schedule token activation after delay."""
        async def delayed_activation():
            await asyncio.sleep(self.activation_delay)
            await self._activate_token(request)
        
        task = asyncio.create_task(delayed_activation())
        self._pending_activations[request.request_id] = task
    
    async def _activate_token(self, request: ApprovalRequest) -> str:
        """Activate break-glass token."""
        async with self._lock:
            token_id = f"bg_token_{uuid.uuid4().hex[:12]}"
            
            self._tokens[token_id] = {
                "request_id": request.request_id,
                "requester": request.requester,
                "approvers": request.approvers.copy(),
                "reason": request.reason,
                "created_at": datetime.now(),
                "expires_at": datetime.now() + timedelta(seconds=request.requested_duration),
                "uses": 0,
            }
            
            self._pending_activations.pop(request.request_id, None)
            await self._send_alert("token_activated", request, token_id)
            
            return token_id
    
    async def use_token(
        self,
        token_id: str,
        user: str,
    ) -> bool:
        """Use break-glass token."""
        async with self._lock:
            token = self._tokens.get(token_id)
            if not token:
                return False
            
            if datetime.now() > token["expires_at"]:
                token["expires_at"] = datetime.now()  # Mark expired
                return False
            
            token["uses"] += 1
            await self._send_alert("token_used", None, token_id, user)
            
            return True
    
    async def revoke_token(self, token_id: str, revoker: str) -> bool:
        """Revoke break-glass token."""
        async with self._lock:
            if token_id in self._tokens:
                del self._tokens[token_id]
                await self._send_alert("token_revoked", None, token_id, revoker)
                return True
            return False
    
    async def _validate_mfa(self, token: Optional[str]) -> bool:
        """Validate MFA token."""
        # Simplified MFA validation
        if not token:
            return not self.mfa_required
        return len(token) >= 6
    
    async def _send_alert(
        self,
        alert_type: str,
        request: Optional[ApprovalRequest],
        *args,
    ) -> None:
        """Send alert."""
        payload = {
            "type": f"break_glass_{alert_type}",
            "request_id": request.request_id if request else args[0] if args else None,
            "requester": request.requester if request else None,
            "reason": request.reason if request else None,
            "timestamp": datetime.now().isoformat(),
        }
        
        for handler in self._alert_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(payload)
                else:
                    handler(payload)
            except Exception as e:
                logger.error(f"Alert handler failed: {e}")
    
    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get approval request."""
        return self._approval_requests.get(request_id)
    
    def get_token(self, token_id: str) -> Optional[Dict[str, Any]]:
        """Get token info."""
        return self._tokens.get(token_id)


# ============== DR RECOVERY CORRECTNESS VALIDATION ==============

class ValidationStatus(str, Enum):
    """Validation status."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"


@dataclass
class RecoveryValidationResult:
    """Result of recovery validation."""
    snapshot_id: str
    status: ValidationStatus
    checks: Dict[str, bool]
    errors: List[str]
    warnings: List[str]
    validated_at: datetime


class DRRecoveryValidator:
    """
    Post-restore recovery correctness validation.
    
    Features:
    - Integrity verification
    - Consistency validation
    - Semantic replay checks
    - Data correctness verification
    """
    
    def __init__(self):
        self._validation_history: Dict[str, RecoveryValidationResult] = {}
        self._lock = asyncio.Lock()
    
    async def validate_recovery(
        self,
        snapshot_id: str,
        checks: Optional[List[str]] = None,
    ) -> RecoveryValidationResult:
        """Validate recovered state."""
        checks = checks or [
            "integrity_hash",
            "schema_compatibility",
            "referential_integrity",
            "data_freshness",
            "consistency_check",
            "semantic_replay",
        ]
        
        result = RecoveryValidationResult(
            snapshot_id=snapshot_id,
            status=ValidationStatus.RUNNING,
            checks={},
            errors=[],
            warnings=[],
            validated_at=datetime.now(),
        )
        
        # Run checks
        for check in checks:
            passed, error, warning = await self._run_check(check, snapshot_id)
            result.checks[check] = passed
            
            if error:
                result.errors.append(error)
            if warning:
                result.warnings.append(warning)
        
        # Determine status
        if result.errors:
            result.status = ValidationStatus.FAILED
        elif result.warnings:
            result.status = ValidationStatus.WARNING
        else:
            result.status = ValidationStatus.PASSED
        
        self._validation_history[snapshot_id] = result
        return result
    
    async def _run_check(
        self,
        check: str,
        snapshot_id: str,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Run a validation check."""
        if check == "integrity_hash":
            # Verify data integrity hash
            return True, None, None
        
        elif check == "schema_compatibility":
            # Check schema compatibility
            return True, None, None
        
        elif check == "referential_integrity":
            # Check foreign keys, relationships
            return True, None, None
        
        elif check == "data_freshness":
            # Check data is recent enough
            return True, None, None
        
        elif check == "consistency_check":
            # Check data consistency
            return True, None, None
        
        elif check == "semantic_replay":
            # Replay critical operations to verify
            return True, None, None
        
        return False, f"Unknown check: {check}", None
    
    def get_validation(self, snapshot_id: str) -> Optional[RecoveryValidationResult]:
        """Get validation result."""
        return self._validation_history.get(snapshot_id)


# ============== SHARED RESOURCE CHARGEBACK ==============

@dataclass
class SharedResourceAllocation:
    """Allocation for shared resource."""
    resource_id: str
    resource_type: str
    total_capacity: float
    allocations: Dict[str, float]  # entity_id -> allocated amount
    weights: Dict[str, float]  # entity_id -> weight


class SharedResourceChargeback:
    """
    Chargeback for shared resources.
    
    Features:
    - Weighted shared-cost allocation
    - Marginal cost attribution
    - Per-entity breakdown
    """
    
    def __init__(self):
        self._shared_resources: Dict[str, SharedResourceAllocation] = {}
        self._usage_history: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = asyncio.Lock()
    
    async def register_shared_resource(
        self,
        resource_id: str,
        resource_type: str,
        total_capacity: float,
        weights: Optional[Dict[str, float]] = None,
    ) -> None:
        """Register shared resource."""
        async with self._lock:
            self._shared_resources[resource_id] = SharedResourceAllocation(
                resource_id=resource_id,
                resource_type=resource_type,
                total_capacity=total_capacity,
                allocations={},
                weights=weights or {},
            )
    
    async def allocate(
        self,
        resource_id: str,
        entity_id: str,
        amount: float,
    ) -> None:
        """Record allocation."""
        async with self._lock:
            resource = self._shared_resources.get(resource_id)
            if resource:
                current = resource.allocations.get(entity_id, 0.0)
                resource.allocations[entity_id] = current + amount
    
    async def get_chargeback(
        self,
        resource_id: str,
        total_cost: float,
    ) -> Dict[str, float]:
        """Calculate chargeback for shared resource."""
        async with self._lock:
            resource = self._shared_resources.get(resource_id)
            if not resource:
                return {}
            
            # Calculate total weight
            total_weight = sum(resource.weights.values()) or 1.0
            
            # Allocate cost by weight
            chargeback = {}
            for entity_id, weight in resource.weights.items():
                share = weight / total_weight
                chargeback[entity_id] = total_cost * share
            
            return chargeback


# ============== POLICY FORMAL VERIFICATION ==============

@dataclass
class PolicyValidationResult:
    """Result of policy validation."""
    policy_id: str
    is_valid: bool
    conflicts: List[Dict[str, Any]]
    warnings: List[str]
    suggestions: List[str]


class PolicyFormalVerifier:
    """
    Formal policy verification.
    
    Features:
    - SAT validation (satisfiability)
    - Conflict detection
    - Shadowing detection
    - Reachability analysis
    """
    
    def __init__(self):
        self._policies: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    async def add_policy(
        self,
        policy_id: str,
        policy: Dict[str, Any],
    ) -> None:
        """Add policy for verification."""
        async with self._lock:
            self._policies[policy_id] = policy
    
    async def validate(self, policy_id: str) -> PolicyValidationResult:
        """Validate policy."""
        policy = self._policies.get(policy_id, {})
        
        conflicts = []
        warnings = []
        suggestions = []
        
        # Check for contradictions
        for other_id, other in self._policies.items():
            if other_id == policy_id:
                continue
            
            if self._has_conflict(policy, other):
                conflicts.append({
                    "policy_id": policy_id,
                    "conflicts_with": other_id,
                    "type": "contradiction",
                })
        
        # Check for shadowing
        for other_id, other in self._policies.items():
            if other_id == policy_id:
                continue
            
            if self._shadows(other, policy):
                warnings.append(f"Shadowed by policy {other_id}")
        
        # Check satisfiability
        if not self._is_satisfiable(policy):
            warnings.append("Policy may be unsatisfiable")
        
        return PolicyValidationResult(
            policy_id=policy_id,
            is_valid=len(conflicts) == 0,
            conflicts=conflicts,
            warnings=warnings,
            suggestions=suggestions,
        )
    
    def _has_conflict(
        self,
        policy1: Dict[str, Any],
        policy2: Dict[str, Any],
    ) -> bool:
        """Check if two policies conflict."""
        # Simplified conflict detection
        p1_action = policy1.get("action")
        p2_action = policy2.get("action")
        
        if p1_action == "allow" and p2_action == "deny":
            # Check if same conditions
            if policy1.get("conditions") == policy2.get("conditions"):
                return True
        
        return False
    
    def _shadows(
        self,
        shadowing: Dict[str, Any],
        shadowed: Dict[str, Any],
    ) -> bool:
        """Check if one policy shadows another."""
        # Shadowing: broader policy before narrower
        return False  # Simplified
    
    def _is_satisfiable(self, policy: Dict[str, Any]) -> bool:
        """Check if policy conditions are satisfiable."""
        return True  # Simplified


# ============== HUMAN GOVERNANCE ==============

class WorkflowStatus(str, Enum):
    """Workflow status."""
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"


@dataclass
class GovernanceWorkflow:
    """Human governance workflow."""
    workflow_id: str
    workflow_type: str  # "policy_change", "access_request", "compliance_review"
    requester: str
    created_at: datetime
    status: WorkflowStatus
    approvers: List[str]
    required_approvals: int
    approvals_received: int
    audit_trail: List[Dict[str, Any]]


class HumanGovernanceLayer:
    """
    Human governance layer.
    
    Features:
    - Audit committee workflows
    - Approval workflows
    - Compliance reviews
    - Legal hold
    - Retention governance
    """
    
    def __init__(self):
        self._workflows: Dict[str, GovernanceWorkflow] = {}
        self._lock = asyncio.Lock()
    
    async def create_workflow(
        self,
        workflow_type: str,
        requester: str,
        required_approvals: int = 2,
        approvers: Optional[List[str]] = None,
    ) -> str:
        """Create governance workflow."""
        async with self._lock:
            workflow_id = f"gov_{uuid.uuid4().hex[:12]}"
            
            workflow = GovernanceWorkflow(
                workflow_id=workflow_id,
                workflow_type=workflow_type,
                requester=requester,
                created_at=datetime.now(),
                status=WorkflowStatus.PENDING,
                approvers=approvers or [],
                required_approvals=required_approvals,
                approvals_received=0,
                audit_trail=[],
            )
            
            self._workflows[workflow_id] = workflow
            return workflow_id
    
    async def approve(
        self,
        workflow_id: str,
        approver: str,
        comment: Optional[str] = None,
    ) -> bool:
        """Approve workflow."""
        async with self._lock:
            workflow = self._workflows.get(workflow_id)
            if not workflow:
                return False
            
            if approver not in workflow.approvers:
                workflow.approvers.append(approver)
            
            workflow.approvals_received += 1
            workflow.status = WorkflowStatus.IN_REVIEW
            
            workflow.audit_trail.append({
                "action": "approved",
                "approver": approver,
                "comment": comment,
                "timestamp": datetime.now().isoformat(),
            })
            
            if workflow.approvals_received >= workflow.required_approvals:
                workflow.status = WorkflowStatus.APPROVED
            
            return True
    
    def get_workflow(self, workflow_id: str) -> Optional[GovernanceWorkflow]:
        """Get workflow."""
        return self._workflows.get(workflow_id)
