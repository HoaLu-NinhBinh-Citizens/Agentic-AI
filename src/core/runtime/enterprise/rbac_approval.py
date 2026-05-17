"""RBAC approval for human-in-the-loop - Phase 5B v10.

Implements role-based access control:
- Role: Role definitions
- RBACEngine: Core RBAC logic
- RBACApprovalEngine: Approval workflow
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Role(Enum):
    """User roles."""
    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    OPERATOR = "operator"
    USER = "user"
    VIEWER = "viewer"


class Permission(Enum):
    """Permissions."""
    PLAN_CREATE = "plan:create"
    PLAN_READ = "plan:read"
    PLAN_UPDATE = "plan:update"
    PLAN_DELETE = "plan:delete"
    PLAN_APPROVE = "plan:approve"
    PLAN_REJECT = "plan:reject"
    PLAN_RESUME = "plan:resume"
    PLAN_CANCEL = "plan:cancel"
    WORKFLOW_START = "workflow:start"
    WORKFLOW_CANCEL = "workflow:cancel"
    INTERRUPT_RESOLVE = "interrupt:resolve"
    INTERRUPT_ESCALATE = "interrupt:escalate"
    AUDIT_READ = "audit:read"
    ADMIN_MANAGE = "admin:manage"


ROLE_PERMISSIONS = {
    Role.ADMIN: set(Permission),
    Role.SUPERVISOR: {
        Permission.PLAN_CREATE,
        Permission.PLAN_READ,
        Permission.PLAN_APPROVE,
        Permission.PLAN_REJECT,
        Permission.PLAN_RESUME,
        Permission.PLAN_CANCEL,
        Permission.WORKFLOW_START,
        Permission.WORKFLOW_CANCEL,
        Permission.INTERRUPT_RESOLVE,
        Permission.INTERRUPT_ESCALATE,
        Permission.AUDIT_READ,
    },
    Role.OPERATOR: {
        Permission.PLAN_CREATE,
        Permission.PLAN_READ,
        Permission.PLAN_RESUME,
        Permission.WORKFLOW_START,
    },
    Role.USER: {
        Permission.PLAN_READ,
        Permission.PLAN_RESUME,
    },
    Role.VIEWER: {
        Permission.PLAN_READ,
    },
}


@dataclass
class User:
    """User with roles."""
    user_id: str
    username: str
    roles: list[Role]
    email: Optional[str] = None
    mfa_enabled: bool = False


@dataclass
class ApprovalRequest:
    """Request for approval."""
    request_id: str
    plan_id: str
    interrupt_id: Optional[str]
    action: Permission
    requested_by: str
    required_roles: list[Role]
    requested_at: int = field(default_factory=lambda: int(time.time()))
    approval_threshold: int = 1
    status: str = "pending"


@dataclass
class ApprovalDecision:
    """Decision on an approval request."""
    decision_id: str
    request_id: str
    approver_id: str
    decision: str  # "approved" or "rejected"
    reason: Optional[str] = None
    decided_at: int = field(default_factory=lambda: int(time.time()))


@dataclass
class AuthorizationResult:
    """Result of authorization check."""
    authorized: bool
    denied_reason: Optional[str] = None


class RBACEngine:
    """Core RBAC engine."""
    
    def __init__(self, default_roles_required: list[Role] = None):
        self._default_roles = default_roles_required or [Role.USER]
        self._custom_permissions: dict[str, set[Permission]] = {}
    
    def get_permissions(self, user: User) -> set[Permission]:
        """Get all permissions for a user."""
        permissions = set()
        
        for role in user.roles:
            role_perms = ROLE_PERMISSIONS.get(role, set())
            permissions.update(role_perms)
        
        user_perms = self._custom_permissions.get(user.user_id, set())
        permissions.update(user_perms)
        
        return permissions
    
    def has_permission(self, user: User, permission: Permission) -> bool:
        """Check if user has a permission."""
        return permission in self.get_permissions(user)
    
    def authorize(
        self,
        user: User,
        permission: Permission,
    ) -> AuthorizationResult:
        """Authorize user for a permission."""
        if self.has_permission(user, permission):
            return AuthorizationResult(authorized=True)
        
        return AuthorizationResult(
            authorized=False,
            denied_reason=f"User {user.username} lacks permission: {permission.value}",
        )
    
    def get_roles_for_permission(
        self,
        permission: Permission,
    ) -> list[Role]:
        """Get roles that have a permission."""
        return [
            role for role, perms in ROLE_PERMISSIONS.items()
            if permission in perms
        ]


class RBACApprovalEngine:
    """Approval workflow for RBAC."""
    
    def __init__(
        self,
        rbac: RBACEngine,
        escalation_role: Role = Role.ADMIN,
    ):
        self._rbac = rbac
        self._escalation_role = escalation_role
        self._pending_requests: dict[str, ApprovalRequest] = {}
        self._decisions: dict[str, list[ApprovalDecision]] = {}
    
    async def create_approval_request(
        self,
        plan_id: str,
        action: Permission,
        requested_by: str,
        interrupt_id: Optional[str] = None,
        required_roles: Optional[list[Role]] = None,
        approval_threshold: int = 1,
    ) -> ApprovalRequest:
        """Create an approval request.
        
        Args:
            plan_id: Plan identifier
            action: Required permission
            requested_by: User requesting
            interrupt_id: Optional interrupt ID
            required_roles: Required roles for approval
            approval_threshold: Number of approvals needed
            
        Returns:
            Created approval request
        """
        import uuid
        
        request = ApprovalRequest(
            request_id=str(uuid.uuid4()),
            plan_id=plan_id,
            interrupt_id=interrupt_id,
            action=action,
            requested_by=requested_by,
            required_roles=required_roles or [Role.USER],
            approval_threshold=approval_threshold,
        )
        
        self._pending_requests[request.request_id] = request
        self._decisions[request.request_id] = []
        
        return request
    
    async def approve(
        self,
        request_id: str,
        approver: User,
        reason: Optional[str] = None,
    ) -> bool:
        """Approve an approval request.
        
        Args:
            request_id: Request ID
            approver: Approving user
            reason: Optional reason
            
        Returns:
            True if approval was recorded
        """
        request = self._pending_requests.get(request_id)
        if not request:
            return False
        
        if request.status != "pending":
            return False
        
        authorized = self._rbac.authorize(approver, request.action)
        if not authorized.authorized:
            return False
        
        approver_has_role = any(role in approver.roles for role in request.required_roles)
        if not approver_has_role:
            return False
        
        if approver.mfa_enabled:
            pass
        
        decision = ApprovalDecision(
            decision_id=f"{request_id}_approval",
            request_id=request_id,
            approver_id=approver.user_id,
            decision="approved",
            reason=reason,
        )
        
        self._decisions[request_id].append(decision)
        
        await self._check_threshold(request)
        
        return True
    
    async def reject(
        self,
        request_id: str,
        rejector: User,
        reason: str,
    ) -> bool:
        """Reject an approval request.
        
        Args:
            request_id: Request ID
            rejector: Rejecting user
            reason: Rejection reason
            
        Returns:
            True if rejection was recorded
        """
        request = self._pending_requests.get(request_id)
        if not request:
            return False
        
        if request.status != "pending":
            return False
        
        decision = ApprovalDecision(
            decision_id=f"{request_id}_rejection",
            request_id=request_id,
            approver_id=rejector.user_id,
            decision="rejected",
            reason=reason,
        )
        
        self._decisions[request_id].append(decision)
        
        request.status = "rejected"
        
        return True
    
    async def _check_threshold(self, request: ApprovalRequest) -> None:
        """Check if approval threshold is met."""
        decisions = self._decisions.get(request.request_id, [])
        
        approvals = sum(1 for d in decisions if d.decision == "approved")
        
        if approvals >= request.approval_threshold:
            request.status = "approved"
    
    async def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get an approval request."""
        return self._pending_requests.get(request_id)
    
    async def get_pending_requests(self, user: User) -> list[ApprovalRequest]:
        """Get pending requests that a user can approve."""
        pending = []
        
        for request in self._pending_requests.values():
            if request.status != "pending":
                continue
            
            has_role = any(role in user.roles for role in request.required_roles)
            if has_role:
                pending.append(request)
        
        return pending
    
    async def escalate(self, request_id: str) -> bool:
        """Escalate a request to higher authority.
        
        Args:
            request_id: Request to escalate
            
        Returns:
            True if escalated
        """
        request = self._pending_requests.get(request_id)
        if not request:
            return False
        
        if self._escalation_role.value not in [
            r.value for r in request.required_roles
        ]:
            request.required_roles.append(self._escalation_role)
            return True
        
        return False
    
    async def authorize_action(
        self,
        user: User,
        action: Permission,
        plan_id: str,
        require_approval: bool = False,
    ) -> AuthorizationResult:
        """Authorize an action, optionally requiring approval.
        
        Args:
            user: User performing action
            action: Action permission
            plan_id: Plan identifier
            require_approval: Whether approval is required
            
        Returns:
            Authorization result
        """
        if not require_approval:
            return self._rbac.authorize(user, action)
        
        if not self._rbac.has_permission(user, action):
            return AuthorizationResult(
                authorized=False,
                denied_reason=f"Action {action.value} requires approval",
            )
        
        return AuthorizationResult(authorized=True)


class ApprovalChain:
    """Chain of approvals for high-value actions."""
    
    def __init__(
        self,
        approval_engine: RBACApprovalEngine,
    ):
        self._engine = approval_engine
    
    async def create_chain(
        self,
        plan_id: str,
        actions: list[tuple[Permission, list[Role]]],
        requested_by: str,
    ) -> list[ApprovalRequest]:
        """Create an approval chain.
        
        Args:
            plan_id: Plan identifier
            actions: List of (action, required_roles) tuples
            requested_by: User requesting
            
        Returns:
            List of approval requests
        """
        requests = []
        
        for action, required_roles in actions:
            request = await self._engine.create_approval_request(
                plan_id=plan_id,
                action=action,
                requested_by=requested_by,
                required_roles=required_roles,
            )
            requests.append(request)
        
        return requests
