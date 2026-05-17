"""Multi-tenant isolation and quotas - Phase 5B v10.

Implements multi-tenant isolation:
- TenantQuota: Quota configuration
- MultiTenantQuotaManager: Manages tenant quotas
- WeightedFairScheduler: Fair scheduling across tenants
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PriorityClass(Enum):
    """Priority class for tenant scheduling."""
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4
    BATCH = 5


@dataclass
class TenantQuota:
    """Quota configuration for a tenant."""
    tenant_id: str
    max_concurrent_workflows: int = 10
    max_daily_cost_usd: float = 100.0
    max_pending_tasks: int = 100
    priority_class: PriorityClass = PriorityClass.NORMAL
    isolation_group: Optional[str] = None
    rate_limit_per_minute: int = 60
    

@dataclass
class TenantUsage:
    """Current usage for a tenant."""
    tenant_id: str
    active_workflows: int = 0
    active_tasks: int = 0
    daily_cost: float = 0.0
    last_reset: int = field(default_factory=lambda: int(time.time()))


@dataclass
class QuotaCheckResult:
    """Result of a quota check."""
    allowed: bool
    reason: Optional[str] = None
    current_usage: Optional[TenantUsage] = None
    limit: Optional[int] = None


class TenantQuotaStore:
    """Store interface for tenant quotas."""
    
    async def get_quota(self, tenant_id: str) -> Optional[TenantQuota]:
        """Get quota for a tenant."""
        raise NotImplementedError
    
    async def save_quota(self, quota: TenantQuota) -> None:
        """Save quota for a tenant."""
        raise NotImplementedError
    
    async def delete_quota(self, tenant_id: str) -> bool:
        """Delete quota for a tenant."""
        raise NotImplementedError


class InMemoryQuotaStore(TenantQuotaStore):
    """In-memory implementation of quota store."""
    
    def __init__(self):
        self._quotas: dict[str, TenantQuota] = {}
    
    async def get_quota(self, tenant_id: str) -> Optional[TenantQuota]:
        return self._quotas.get(tenant_id)
    
    async def save_quota(self, quota: TenantQuota) -> None:
        self._quotas[quota.tenant_id] = quota
    
    async def delete_quota(self, tenant_id: str) -> bool:
        if tenant_id in self._quotas:
            del self._quotas[tenant_id]
            return True
        return False


class TenantUsageStore:
    """Store interface for tenant usage."""
    
    async def get_usage(self, tenant_id: str) -> TenantUsage:
        """Get current usage for a tenant."""
        raise NotImplementedError
    
    async def increment_workflow(self, tenant_id: str) -> None:
        """Increment active workflow count."""
        raise NotImplementedError
    
    async def decrement_workflow(self, tenant_id: str) -> None:
        """Decrement active workflow count."""
        raise NotImplementedError
    
    async def increment_task(self, tenant_id: str) -> None:
        """Increment active task count."""
        raise NotImplementedError
    
    async def decrement_task(self, tenant_id: str) -> None:
        """Decrement active task count."""
        raise NotImplementedError
    
    async def add_cost(self, tenant_id: str, cost: float) -> None:
        """Add to daily cost."""
        raise NotImplementedError
    
    async def reset_daily(self, tenant_id: str) -> None:
        """Reset daily counters."""
        raise NotImplementedError


class InMemoryUsageStore(TenantUsageStore):
    """In-memory implementation of usage store."""
    
    def __init__(self):
        self._usage: dict[str, TenantUsage] = {}
    
    async def get_usage(self, tenant_id: str) -> TenantUsage:
        if tenant_id not in self._usage:
            self._usage[tenant_id] = TenantUsage(tenant_id=tenant_id)
        
        usage = self._usage[tenant_id]
        
        day_start = int(time.time()) // 86400
        last_day = usage.last_reset // 86400
        
        if day_start > last_day:
            usage.daily_cost = 0.0
            usage.last_reset = int(time.time())
        
        return usage
    
    async def increment_workflow(self, tenant_id: str) -> None:
        usage = await self.get_usage(tenant_id)
        usage.active_workflows += 1
    
    async def decrement_workflow(self, tenant_id: str) -> None:
        usage = await self.get_usage(tenant_id)
        usage.active_workflows = max(0, usage.active_workflows - 1)
    
    async def increment_task(self, tenant_id: str) -> None:
        usage = await self.get_usage(tenant_id)
        usage.active_tasks += 1
    
    async def decrement_task(self, tenant_id: str) -> None:
        usage = await self.get_usage(tenant_id)
        usage.active_tasks = max(0, usage.active_tasks - 1)
    
    async def add_cost(self, tenant_id: str, cost: float) -> None:
        usage = await self.get_usage(tenant_id)
        usage.daily_cost += cost
    
    async def reset_daily(self, tenant_id: str) -> None:
        usage = await self.get_usage(tenant_id)
        usage.daily_cost = 0.0
        usage.last_reset = int(time.time())


class MultiTenantQuotaManager:
    """Manages quotas across tenants.
    
    Enforces resource limits per tenant and provides
    usage tracking.
    """
    
    def __init__(
        self,
        quota_store: TenantQuotaStore,
        usage_store: TenantUsageStore,
        default_quota: Optional[TenantQuota] = None,
    ):
        self._quota_store = quota_store
        self._usage_store = usage_store
        self._default_quota = default_quota or TenantQuota(
            tenant_id="default",
            max_concurrent_workflows=10,
            max_daily_cost_usd=100.0,
        )
    
    async def get_quota(self, tenant_id: str) -> TenantQuota:
        """Get quota for a tenant (or default)."""
        quota = await self._quota_store.get_quota(tenant_id)
        return quota or self._default_quota
    
    async def check_workflow_allowed(self, tenant_id: str) -> QuotaCheckResult:
        """Check if a new workflow is allowed for tenant."""
        quota = await self.get_quota(tenant_id)
        usage = await self._usage_store.get_usage(tenant_id)
        
        if usage.active_workflows >= quota.max_concurrent_workflows:
            return QuotaCheckResult(
                allowed=False,
                reason=f"Max concurrent workflows ({quota.max_concurrent_workflows}) reached",
                current_usage=usage,
                limit=quota.max_concurrent_workflows,
            )
        
        return QuotaCheckResult(
            allowed=True,
            current_usage=usage,
            limit=quota.max_concurrent_workflows,
        )
    
    async def check_cost_allowed(self, tenant_id: str, additional_cost: float) -> QuotaCheckResult:
        """Check if additional cost is allowed."""
        quota = await self.get_quota(tenant_id)
        usage = await self._usage_store.get_usage(tenant_id)
        
        if usage.daily_cost + additional_cost > quota.max_daily_cost_usd:
            return QuotaCheckResult(
                allowed=False,
                reason=f"Daily cost limit ({quota.max_daily_cost_usd}) would be exceeded",
                current_usage=usage,
                limit=quota.max_daily_cost_usd,
            )
        
        return QuotaCheckResult(
            allowed=True,
            current_usage=usage,
            limit=quota.max_daily_cost_usd,
        )
    
    async def record_workflow_start(self, tenant_id: str) -> bool:
        """Record that a workflow started."""
        check = await self.check_workflow_allowed(tenant_id)
        
        if check.allowed:
            await self._usage_store.increment_workflow(tenant_id)
            return True
        
        return False
    
    async def record_workflow_end(self, tenant_id: str) -> None:
        """Record that a workflow ended."""
        await self._usage_store.decrement_workflow(tenant_id)
    
    async def record_task_start(self, tenant_id: str) -> None:
        """Record that a task started."""
        await self._usage_store.increment_task(tenant_id)
    
    async def record_task_end(self, tenant_id: str) -> None:
        """Record that a task ended."""
        await self._usage_store.decrement_task(tenant_id)
    
    async def record_cost(self, tenant_id: str, cost: float) -> None:
        """Record cost for a tenant."""
        await self._usage_store.add_cost(tenant_id, cost)
    
    async def set_quota(self, quota: TenantQuota) -> None:
        """Set quota for a tenant."""
        await self._quota_store.save_quota(quota)
    
    async def get_usage(self, tenant_id: str) -> TenantUsage:
        """Get current usage for a tenant."""
        return await self._usage_store.get_usage(tenant_id)


class WeightedFairScheduler:
    """Weighted fair queue scheduler across tenants.
    
    Schedules tasks based on:
    - Priority class (lower = higher priority)
    - Current usage vs quota ratio
    """
    
    def __init__(
        self,
        quota_manager: MultiTenantQuotaManager,
    ):
        self._quota_manager = quota_manager
    
    def _calculate_weight(self, tenant_id: str, quota: TenantQuota, usage) -> float:
        """Calculate scheduling weight for a tenant.
        
        Lower weight = higher priority.
        """
        priority_weight = quota.priority_class.value * 1000
        
        usage_ratio = 0.0
        if quota.max_concurrent_workflows > 0:
            usage_ratio = usage.active_workflows / quota.max_concurrent_workflows
        
        fairness_weight = usage_ratio * 100
        
        return priority_weight + fairness_weight
    
    async def get_next_tenant(self, tenant_ids: list[str]) -> Optional[str]:
        """Get the next tenant to schedule based on weighted fair queue.
        
        Args:
            tenant_ids: List of tenant IDs
            
        Returns:
            Next tenant ID or None
        """
        best_tenant = None
        best_weight = float('inf')
        
        for tenant_id in tenant_ids:
            quota = await self._quota_manager.get_quota(tenant_id)
            usage = await self._quota_manager.get_usage(tenant_id)
            
            check = await self._quota_manager.check_workflow_allowed(tenant_id)
            
            if not check.allowed:
                continue
            
            weight = self._calculate_weight(tenant_id, quota, usage)
            
            if weight < best_weight:
                best_weight = weight
                best_tenant = tenant_id
        
        return best_tenant
    
    async def get_schedule_order(
        self,
        tenant_ids: list[str],
        limit: int = 10,
    ) -> list[str]:
        """Get ordered list of tenants for scheduling.
        
        Args:
            tenant_ids: List of tenant IDs
            limit: Maximum number to return
            
        Returns:
            Ordered list of tenant IDs
        """
        result = []
        available = set(tenant_ids)
        
        while len(result) < limit and available:
            next_tenant = await self.get_next_tenant(list(available))
            
            if not next_tenant:
                break
            
            result.append(next_tenant)
            available.remove(next_tenant)
        
        return result
