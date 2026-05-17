"""Unit tests for multi-tenant isolation and RBAC.

Tests cover:
- test_multi_tenant_isolation: Tenant A hogs resources, Tenant B still has slot
- test_rbac_denial: User without role can't resume
"""

from __future__ import annotations

import pytest
import asyncio

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from core.runtime.enterprise.multi_tenant import (
    MultiTenantQuotaManager,
    WeightedFairScheduler,
    TenantQuota,
    TenantUsage,
    InMemoryQuotaStore,
    InMemoryUsageStore,
    PriorityClass,
    QuotaCheckResult,
)
from core.runtime.enterprise.rbac_approval import (
    RBACEngine,
    RBACApprovalEngine,
    User,
    Role,
    Permission,
    ApprovalRequest,
    AuthorizationResult,
)


# ============================================================================
# Multi-Tenant Quota Manager Tests
# ============================================================================

class TestMultiTenantQuotaManager:
    """Test multi-tenant quota management."""

    @pytest.fixture
    def manager(self):
        """Create quota manager."""
        return MultiTenantQuotaManager(
            quota_store=InMemoryQuotaStore(),
            usage_store=InMemoryUsageStore(),
            default_quota=TenantQuota(
                tenant_id="default",
                max_concurrent_workflows=10,
                max_daily_cost_usd=100.0,
            ),
        )

    @pytest.mark.asyncio
    async def test_check_workflow_allowed(self, manager):
        """Test checking if workflow is allowed."""
        result = await manager.check_workflow_allowed("tenant1")
        
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_record_workflow_start(self, manager):
        """Test recording workflow start."""
        success = await manager.record_workflow_start("tenant1")
        
        assert success is True
        
        usage = await manager.get_usage("tenant1")
        assert usage.active_workflows == 1

    @pytest.mark.asyncio
    async def test_record_workflow_end(self, manager):
        """Test recording workflow end."""
        await manager.record_workflow_start("tenant1")
        await manager.record_workflow_start("tenant1")
        await manager.record_workflow_end("tenant1")
        
        usage = await manager.get_usage("tenant1")
        assert usage.active_workflows == 1

    @pytest.mark.asyncio
    async def test_quota_exceeded(self, manager):
        """Test quota exceeded blocks new workflows."""
        await manager.set_quota(TenantQuota(
            tenant_id="limited",
            max_concurrent_workflows=2,
        ))
        
        await manager.record_workflow_start("limited")
        await manager.record_workflow_start("limited")
        
        # Third should be blocked
        result = await manager.check_workflow_allowed("limited")
        
        assert result.allowed is False
        assert "reached" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, manager):
        """Test that tenants are isolated - one hogging doesn't affect another."""
        # Set low quota for tenant A
        await manager.set_quota(TenantQuota(
            tenant_id="tenant_a",
            max_concurrent_workflows=5,
        ))
        
        # Fill tenant A's quota
        for _ in range(5):
            await manager.record_workflow_start("tenant_a")
        
        # Tenant B should still be allowed (uses default quota)
        result = await manager.check_workflow_allowed("tenant_b")
        
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_different_tenants_independent(self, manager):
        """Test that tenant quotas are independent."""
        await manager.set_quota(TenantQuota(
            tenant_id="rich",
            max_concurrent_workflows=100,
        ))
        await manager.set_quota(TenantQuota(
            tenant_id="poor",
            max_concurrent_workflows=1,
        ))
        
        # Fill poor tenant
        await manager.record_workflow_start("poor")
        
        # Rich tenant should still have quota
        rich_allowed = await manager.check_workflow_allowed("rich")
        poor_allowed = await manager.check_workflow_allowed("poor")
        
        assert rich_allowed.allowed is True
        assert poor_allowed.allowed is False

    @pytest.mark.asyncio
    async def test_check_cost_allowed(self, manager):
        """Test cost checking."""
        result = await manager.check_cost_allowed("tenant1", 50.0)
        
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_record_cost(self, manager):
        """Test recording cost."""
        await manager.record_cost("tenant1", 25.0)
        await manager.record_cost("tenant1", 30.0)
        
        usage = await manager.get_usage("tenant1")
        
        assert usage.daily_cost == 55.0

    @pytest.mark.asyncio
    async def test_cost_limit_exceeded(self, manager):
        """Test cost limit enforcement."""
        await manager.set_quota(TenantQuota(
            tenant_id="budget",
            max_daily_cost_usd=50.0,
        ))
        
        result = await manager.check_cost_allowed("budget", 60.0)
        
        assert result.allowed is False


# ============================================================================
# Weighted Fair Scheduler Tests
# ============================================================================

class TestWeightedFairScheduler:
    """Test weighted fair scheduling."""

    @pytest.fixture
    def scheduler(self):
        """Create fair scheduler."""
        quota_store = InMemoryQuotaStore()
        usage_store = InMemoryUsageStore()
        quota_manager = MultiTenantQuotaManager(
            quota_store=quota_store,
            usage_store=usage_store,
        )
        return WeightedFairScheduler(quota_manager)

    @pytest.mark.asyncio
    async def test_get_next_tenant_priority(self, scheduler):
        """Test that higher priority tenants get scheduled first."""
        await scheduler._quota_manager.set_quota(TenantQuota(
            tenant_id="high",
            priority_class=PriorityClass.HIGH,
            max_concurrent_workflows=100,
        ))
        await scheduler._quota_manager.set_quota(TenantQuota(
            tenant_id="low",
            priority_class=PriorityClass.LOW,
            max_concurrent_workflows=100,
        ))
        
        next_tenant = await scheduler.get_next_tenant(["high", "low"])
        
        assert next_tenant == "high"

    @pytest.mark.asyncio
    async def test_get_next_tenant_fairness(self, scheduler):
        """Test fairness when priorities are equal."""
        await scheduler._quota_manager.set_quota(TenantQuota(
            tenant_id="tenant1",
            priority_class=PriorityClass.NORMAL,
            max_concurrent_workflows=10,
        ))
        await scheduler._quota_manager.set_quota(TenantQuota(
            tenant_id="tenant2",
            priority_class=PriorityClass.NORMAL,
            max_concurrent_workflows=10,
        ))
        
        # Start workflows for tenant1
        for _ in range(5):
            await scheduler._quota_manager.record_workflow_start("tenant1")
        
        next_tenant = await scheduler.get_next_tenant(["tenant1", "tenant2"])
        
        # tenant2 should be next (less usage)
        assert next_tenant == "tenant2"

    @pytest.mark.asyncio
    async def test_get_schedule_order(self, scheduler):
        """Test getting schedule order."""
        for tid in ["a", "b", "c"]:
            await scheduler._quota_manager.set_quota(TenantQuota(
                tenant_id=tid,
                max_concurrent_workflows=10,
            ))
        
        order = await scheduler.get_schedule_order(["a", "b", "c"], limit=3)
        
        assert len(order) == 3
        assert set(order) == {"a", "b", "c"}

    @pytest.mark.asyncio
    async def test_skips_tenant_at_quota(self, scheduler):
        """Test that tenant at quota is skipped."""
        await scheduler._quota_manager.set_quota(TenantQuota(
            tenant_id="full",
            max_concurrent_workflows=1,
        ))
        await scheduler._quota_manager.set_quota(TenantQuota(
            tenant_id="available",
            max_concurrent_workflows=10,
        ))
        
        await scheduler._quota_manager.record_workflow_start("full")
        
        next_tenant = await scheduler.get_next_tenant(["full", "available"])
        
        assert next_tenant == "available"


# ============================================================================
# RBAC Engine Tests
# ============================================================================

class TestRBACEngine:
    """Test RBAC engine."""

    @pytest.fixture
    def rbac(self):
        """Create RBAC engine."""
        return RBACEngine()

    def test_user_permissions_admin(self, rbac):
        """Test admin has all permissions."""
        admin = User(user_id="admin1", username="admin", roles=[Role.ADMIN])
        
        permissions = rbac.get_permissions(admin)
        
        assert Permission.PLAN_DELETE in permissions
        assert Permission.ADMIN_MANAGE in permissions

    def test_user_permissions_normal(self, rbac):
        """Test normal user has limited permissions."""
        user = User(user_id="user1", username="user", roles=[Role.USER])
        
        permissions = rbac.get_permissions(user)
        
        assert Permission.PLAN_READ in permissions
        assert Permission.PLAN_DELETE not in permissions

    def test_has_permission(self, rbac):
        """Test permission checking."""
        user = User(user_id="user1", username="user", roles=[Role.OPERATOR])
        
        assert rbac.has_permission(user, Permission.PLAN_CREATE) is True
        assert rbac.has_permission(user, Permission.PLAN_DELETE) is False

    def test_authorize_success(self, rbac):
        """Test successful authorization."""
        user = User(user_id="user1", username="user", roles=[Role.OPERATOR])
        
        result = rbac.authorize(user, Permission.PLAN_CREATE)
        
        assert result.authorized is True

    def test_authorize_denied(self, rbac):
        """Test authorization denial."""
        user = User(user_id="user1", username="user", roles=[Role.USER])
        
        result = rbac.authorize(user, Permission.PLAN_DELETE)
        
        assert result.authorized is False
        assert result.denied_reason is not None

    def test_get_roles_for_permission(self, rbac):
        """Test getting roles for a permission."""
        roles = rbac.get_roles_for_permission(Permission.PLAN_RESUME)
        
        assert Role.ADMIN in roles
        assert Role.SUPERVISOR in roles
        assert Role.OPERATOR in roles
        assert Role.USER in roles

    def test_rbac_denial(self, rbac):
        """Test that user without role can't perform action."""
        viewer = User(user_id="viewer1", username="viewer", roles=[Role.VIEWER])
        
        # Viewer can read plans
        result = rbac.authorize(viewer, Permission.PLAN_READ)
        assert result.authorized is True
        
        # Viewer cannot create plans
        result = rbac.authorize(viewer, Permission.PLAN_CREATE)
        assert result.authorized is False

    def test_multiple_roles(self, rbac):
        """Test user with multiple roles."""
        user = User(user_id="user1", username="user", roles=[Role.USER, Role.VIEWER])
        
        permissions = rbac.get_permissions(user)
        
        # Should have permissions from both roles
        assert Permission.PLAN_READ in permissions
        assert Permission.PLAN_RESUME in permissions


# ============================================================================
# RBAC Approval Engine Tests
# ============================================================================

class TestRBACApprovalEngine:
    """Test RBAC approval workflow."""

    @pytest.fixture
    def approval_engine(self):
        """Create approval engine."""
        rbac = RBACEngine()
        return RBACApprovalEngine(rbac)

    @pytest.mark.asyncio
    async def test_create_approval_request(self, approval_engine):
        """Test creating approval request."""
        request = await approval_engine.create_approval_request(
            plan_id="plan1",
            action=Permission.PLAN_APPROVE,
            requested_by="user1",
        )
        
        assert request.plan_id == "plan1"
        assert request.action == Permission.PLAN_APPROVE
        assert request.status == "pending"

    @pytest.mark.asyncio
    async def test_approve_request(self, approval_engine):
        """Test approving request."""
        supervisor = User(user_id="super1", username="supervisor", roles=[Role.SUPERVISOR])
        
        request = await approval_engine.create_approval_request(
            plan_id="plan1",
            action=Permission.PLAN_APPROVE,
            requested_by="user1",
            required_roles=[Role.SUPERVISOR],
        )
        
        approved = await approval_engine.approve(request.request_id, supervisor)
        
        assert approved is True

    @pytest.mark.asyncio
    async def test_approve_without_permission(self, approval_engine):
        """Test approval without permission fails."""
        regular_user = User(user_id="user1", username="user", roles=[Role.USER])
        
        request = await approval_engine.create_approval_request(
            plan_id="plan1",
            action=Permission.PLAN_APPROVE,
            requested_by="user1",
            required_roles=[Role.SUPERVISOR],
        )
        
        approved = await approval_engine.approve(request.request_id, regular_user)
        
        assert approved is False

    @pytest.mark.asyncio
    async def test_reject_request(self, approval_engine):
        """Test rejecting request."""
        supervisor = User(user_id="super1", username="supervisor", roles=[Role.SUPERVISOR])
        
        request = await approval_engine.create_approval_request(
            plan_id="plan1",
            action=Permission.PLAN_APPROVE,
            requested_by="user1",
        )
        
        rejected = await approval_engine.reject(
            request.request_id,
            supervisor,
            "Insufficient justification",
        )
        
        assert rejected is True
        
        updated = await approval_engine.get_request(request.request_id)
        assert updated.status == "rejected"

    @pytest.mark.asyncio
    async def test_get_pending_requests(self, approval_engine):
        """Test getting pending requests for user."""
        supervisor = User(user_id="super1", username="supervisor", roles=[Role.SUPERVISOR])
        
        await approval_engine.create_approval_request(
            plan_id="plan1",
            action=Permission.PLAN_APPROVE,
            requested_by="user1",
            required_roles=[Role.SUPERVISOR],
        )
        
        pending = await approval_engine.get_pending_requests(supervisor)
        
        assert len(pending) == 1

    @pytest.mark.asyncio
    async def test_escalate_request(self, approval_engine):
        """Test escalating request."""
        request = await approval_engine.create_approval_request(
            plan_id="plan1",
            action=Permission.PLAN_APPROVE,
            requested_by="user1",
            required_roles=[Role.OPERATOR],
        )
        
        escalated = await approval_engine.escalate(request.request_id)
        
        assert escalated is True

    @pytest.mark.asyncio
    async def test_authorize_action_no_approval(self, approval_engine):
        """Test authorizing action without approval."""
        user = User(user_id="user1", username="user", roles=[Role.USER])
        
        result = await approval_engine.authorize_action(
            user,
            Permission.PLAN_READ,
            "plan1",
            require_approval=False,
        )
        
        assert result.authorized is True

    @pytest.mark.asyncio
    async def test_authorize_action_requires_approval(self, approval_engine):
        """Test action requiring approval."""
        user = User(user_id="user1", username="user", roles=[Role.USER])
        
        result = await approval_engine.authorize_action(
            user,
            Permission.PLAN_APPROVE,
            "plan1",
            require_approval=True,
        )
        
        assert result.authorized is False
