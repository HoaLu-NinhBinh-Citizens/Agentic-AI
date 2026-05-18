"""
Fair Share Quota and Error Budget Policy.

Fair Share Quota (DRF):
- Dominant Resource Fairness for resource allocation
- Weighted fair share when resources are insufficient

Error Budget Policy:
- Track error budget consumption
- Automatic degradation when budget exhausted
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ResourceType(str, Enum):
    """Resource types for quota allocation."""
    TASK = "task"
    CPU = "cpu"
    MEMORY = "memory"
    STORAGE = "storage"
    NETWORK = "network"


@dataclass
class TenantUsage:
    """Usage record for a tenant."""
    tenant_id: str
    usage: Dict[ResourceType, float] = field(default_factory=dict)
    demands: Dict[ResourceType, float] = field(default_factory=dict)
    shares: Dict[ResourceType, float] = field(default_factory=dict)


@dataclass
class AllocationResult:
    """Result of allocation request."""
    allocated: bool
    tenant_id: str
    resource_type: ResourceType
    requested: float
    granted: float
    dominant_share: float
    reason: str


class FairShareQuota:
    """
    Fair share quota using Dominant Resource Fairness (DRF).
    
    DRF Algorithm:
    1. Calculate share fraction for each tenant: usage / weight
    2. Find dominant resource (max fraction)
    3. Allocate to tenant with smallest dominant share
    4. Repeat until resources exhausted
    
    Features:
    - Weighted fair share
    - Min guarantee enforcement
    - Dominant share calculation
    - Resource-aware allocation
    """
    
    def __init__(
        self,
        resources: Optional[List[ResourceType]] = None,
        total_capacity: Optional[Dict[ResourceType, float]] = None,
    ):
        self.resources = resources or [
            ResourceType.TASK,
            ResourceType.CPU,
            ResourceType.MEMORY,
        ]
        
        self.total_capacity = total_capacity or {
            ResourceType.TASK: 1000.0,
            ResourceType.CPU: 100.0,
            ResourceType.MEMORY: 128.0,
        }
        
        # Tenant weights (share weight)
        self._weights: Dict[str, float] = {}
        
        # Tenant usage
        self._usage: Dict[str, Dict[ResourceType, float]] = {}
        
        # Min guarantees per tenant
        self._min_guarantees: Dict[str, Dict[ResourceType, float]] = {}
        
        self._lock = asyncio.Lock()
    
    def set_weight(self, tenant_id: str, weight: float) -> None:
        """Set share weight for tenant."""
        self._weights[tenant_id] = weight
    
    def set_min_guarantee(
        self,
        tenant_id: str,
        guarantees: Dict[ResourceType, float],
    ) -> None:
        """Set minimum guarantee for tenant."""
        self._min_guarantees[tenant_id] = guarantees
    
    async def request_allocation(
        self,
        tenant_id: str,
        resource_type: ResourceType,
        amount: float,
    ) -> AllocationResult:
        """Request resource allocation."""
        async with self._lock:
            # Initialize tenant if needed
            if tenant_id not in self._usage:
                self._usage[tenant_id] = {
                    r: 0.0 for r in self.resources
                }
            
            weight = self._weights.get(tenant_id, 1.0)
            capacity = self.total_capacity.get(resource_type, 0.0)
            
            # Check min guarantee
            min_guarantee = self._min_guarantees.get(tenant_id, {}).get(resource_type, 0.0)
            current_usage = self._usage[tenant_id].get(resource_type, 0.0)
            
            # Check if request is within guarantee
            if current_usage + amount <= min_guarantee:
                # Within guarantee, allocate directly
                self._usage[tenant_id][resource_type] = current_usage + amount
                
                return AllocationResult(
                    allocated=True,
                    tenant_id=tenant_id,
                    resource_type=resource_type,
                    requested=amount,
                    granted=amount,
                    dominant_share=await self._calculate_dominant_share(tenant_id),
                    reason="within_min_guarantee",
                )
            
            # Calculate available capacity
            total_used = sum(
                u.get(resource_type, 0.0) for u in self._usage.values()
            )
            available = capacity - total_used
            
            if amount <= available:
                # Enough capacity available
                self._usage[tenant_id][resource_type] = current_usage + amount
                
                return AllocationResult(
                    allocated=True,
                    tenant_id=tenant_id,
                    resource_type=resource_type,
                    requested=amount,
                    granted=amount,
                    dominant_share=await self._calculate_dominant_share(tenant_id),
                    reason="capacity_available",
                )
            
            # Not enough capacity, use DRF to decide
            dominant_share = await self._calculate_dominant_share(tenant_id)
            max_share_tenant = await self._get_max_share_tenant(resource_type)
            
            if dominant_share > max_share_tenant["share"]:
                # This tenant already has highest share, reject
                return AllocationResult(
                    allocated=False,
                    tenant_id=tenant_id,
                    resource_type=resource_type,
                    requested=amount,
                    granted=0.0,
                    dominant_share=dominant_share,
                    reason=f"tenant_{tenant_id}_has_max_share",
                )
            
            # Partial allocation
            granted = available
            self._usage[tenant_id][resource_type] = current_usage + granted
            
            return AllocationResult(
                allocated=granted > 0,
                tenant_id=tenant_id,
                resource_type=resource_type,
                requested=amount,
                granted=granted,
                dominant_share=await self._calculate_dominant_share(tenant_id),
                reason="partial_allocation",
            )
    
    async def release_allocation(
        self,
        tenant_id: str,
        resource_type: ResourceType,
        amount: float,
    ) -> None:
        """Release resource allocation."""
        async with self._lock:
            if tenant_id in self._usage:
                current = self._usage[tenant_id].get(resource_type, 0.0)
                self._usage[tenant_id][resource_type] = max(0.0, current - amount)
    
    async def _calculate_dominant_share(self, tenant_id: str) -> float:
        """Calculate dominant share fraction for tenant."""
        if tenant_id not in self._usage:
            return 0.0
        
        weight = self._weights.get(tenant_id, 1.0)
        max_share = 0.0
        
        for resource in self.resources:
            usage = self._usage[tenant_id].get(resource, 0.0)
            capacity = self.total_capacity.get(resource, 1.0)
            
            if capacity > 0:
                share = (usage / capacity) / weight
                max_share = max(max_share, share)
        
        return max_share
    
    async def _get_max_share_tenant(
        self,
        exclude_resource: Optional[ResourceType] = None,
    ) -> Dict[str, Any]:
        """Get tenant with maximum share."""
        max_share = 0.0
        max_tenant = None
        
        for tenant_id in self._usage:
            share = await self._calculate_dominant_share(tenant_id)
            if share > max_share:
                max_share = share
                max_tenant = tenant_id
        
        return {
            "tenant_id": max_tenant,
            "share": max_share,
        }
    
    async def get_dominant_share(self, tenant_id: str) -> float:
        """Get dominant share for tenant."""
        return await self._calculate_dominant_share(tenant_id)
    
    async def get_utilization(self) -> Dict[str, float]:
        """Get utilization percentage by resource."""
        utilization = {}
        
        for resource in self.resources:
            capacity = self.total_capacity.get(resource, 0.0)
            if capacity > 0:
                total_used = sum(
                    u.get(resource, 0.0) for u in self._usage.values()
                )
                utilization[resource.value] = (total_used / capacity) * 100
        
        return utilization
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get quota metrics."""
        return {
            "tracked_tenants": len(self._usage),
            "resources": [r.value for r in self.resources],
            "total_capacity": {r.value: v for r, v in self.total_capacity.items()},
            "weights": self._weights,
            "utilization": asyncio.get_event_loop().run_until_complete(
                self.get_utilization()
            ),
        }


@dataclass
class ErrorBudgetStatus:
    """Status of error budget."""
    tenant_id: str
    total_budget: float
    consumed: float
    remaining: float
    budget_ratio: float  # remaining / total
    is_exhausted: bool
    degraded: bool
    last_updated: datetime


class ErrorBudgetPolicy:
    """
    Error budget policy with automatic degradation.
    
    When error budget is exhausted:
    - Reject non-critical requests (priority < threshold)
    - Reduce concurrency limits
    - Switch to degraded mode
    - Send alerts
    
    Auto-recovery when budget is restored.
    """
    
    def __init__(
        self,
        window_hours: float = 24.0,
        critical_priority_threshold: int = 5,
        reduce_concurrency_ratio: float = 0.5,
        degrade_non_critical: bool = True,
    ):
        self.window_hours = window_hours
        self.critical_priority_threshold = critical_priority_threshold
        self.reduce_concurrency_ratio = reduce_concurrency_ratio
        self.degrade_non_critical = degrade_non_critical
        
        # Error budget tracking
        self._budgets: Dict[str, ErrorBudgetStatus] = {}
        
        # Degraded tenants
        self._degraded_tenants: Set[str] = set()
        
        # Concurrency limits
        self._original_limits: Dict[str, int] = {}
        self._reduced_limits: Dict[str, int] = {}
        
        # Alert handlers
        self._alert_handlers: List[Callable] = []
        
        self._lock = asyncio.Lock()
    
    def register_alert_handler(self, handler: Callable) -> None:
        """Register alert handler."""
        self._alert_handlers.append(handler)
    
    async def initialize_budget(
        self,
        tenant_id: str,
        total_budget: float,
    ) -> ErrorBudgetStatus:
        """Initialize budget for tenant."""
        async with self._lock:
            status = ErrorBudgetStatus(
                tenant_id=tenant_id,
                total_budget=total_budget,
                consumed=0.0,
                remaining=total_budget,
                budget_ratio=1.0,
                is_exhausted=False,
                degraded=False,
                last_updated=datetime.now(),
            )
            self._budgets[tenant_id] = status
            return status
    
    async def record_error(
        self,
        tenant_id: str,
        error_weight: float = 1.0,
    ) -> ErrorBudgetStatus:
        """Record an error against budget."""
        async with self._lock:
            if tenant_id not in self._budgets:
                await self.initialize_budget(tenant_id, 100.0)  # Default 100%
            
            budget = self._budgets[tenant_id]
            
            # Consume budget
            budget.consumed += error_weight
            budget.remaining = max(0.0, budget.total_budget - budget.consumed)
            budget.budget_ratio = budget.remaining / budget.total_budget
            budget.last_updated = datetime.now()
            
            # Check exhaustion
            was_exhausted = budget.is_exhausted
            budget.is_exhausted = budget.remaining <= 0
            
            if budget.is_exhausted and not was_exhausted:
                # Just became exhausted
                await self._degrade_tenant(tenant_id)
                await self._send_alert(tenant_id, "ERROR_BUDGET_EXHAUSTED")
            
            return budget
    
    async def check_request_allowed(
        self,
        tenant_id: str,
        priority: int,
    ) -> tuple[bool, str]:
        """Check if request is allowed under current budget."""
        if tenant_id not in self._budgets:
            return True, "no_budget_tracking"
        
        budget = self._budgets[tenant_id]
        
        if budget.is_exhausted:
            # Budget exhausted
            if self.degrade_non_critical and priority < self.critical_priority_threshold:
                return False, "non_critical_rejected_budget_exhausted"
            
            # Critical requests allowed but may be rate limited
            return True, "critical_allowed_degraded_mode"
        
        if budget.budget_ratio < 0.2:
            # Low budget warning
            return True, "low_budget_warning"
        
        return True, "allowed"
    
    async def get_concurrency_limit(self, tenant_id: str) -> Optional[int]:
        """Get current concurrency limit for tenant."""
        if tenant_id in self._reduced_limits:
            return self._reduced_limits[tenant_id]
        return self._original_limits.get(tenant_id)
    
    async def set_concurrency_limit(
        self,
        tenant_id: str,
        limit: int,
    ) -> None:
        """Set concurrency limit for tenant."""
        self._original_limits[tenant_id] = limit
        
        if tenant_id in self._degraded_tenants:
            self._reduced_limits[tenant_id] = int(
                limit * self.reduce_concurrency_ratio
            )
    
    async def _degrade_tenant(self, tenant_id: str) -> None:
        """Degrade tenant when budget exhausted."""
        self._degraded_tenants.add(tenant_id)
        
        # Reduce concurrency
        if tenant_id in self._original_limits:
            self._reduced_limits[tenant_id] = int(
                self._original_limits[tenant_id] * self.reduce_concurrency_ratio
            )
        
        logger.warning(f"Tenant {tenant_id} degraded due to error budget exhaustion")
    
    async def _recover_tenant(self, tenant_id: str) -> None:
        """Recover tenant when budget restored."""
        self._degraded_tenants.discard(tenant_id)
        self._reduced_limits.pop(tenant_id, None)
        
        logger.info(f"Tenant {tenant_id} recovered from degraded mode")
    
    async def _send_alert(self, tenant_id: str, alert_type: str) -> None:
        """Send alert for budget event."""
        for handler in self._alert_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(tenant_id, alert_type)
                else:
                    handler(tenant_id, alert_type)
            except Exception as e:
                logger.error(f"Alert handler failed: {e}")
    
    async def get_status(self, tenant_id: str) -> Optional[ErrorBudgetStatus]:
        """Get budget status for tenant."""
        return self._budgets.get(tenant_id)
    
    async def get_all_statuses(self) -> List[ErrorBudgetStatus]:
        """Get all budget statuses."""
        return list(self._budgets.values())
    
    async def auto_recover(self) -> List[str]:
        """Check and auto-recover tenants with restored budget."""
        recovered = []
        
        async with self._lock:
            for tenant_id in list(self._degraded_tenants):
                budget = self._budgets.get(tenant_id)
                if budget and budget.remaining > 0:
                    await self._recover_tenant(tenant_id)
                    await self._send_alert(tenant_id, "ERROR_BUDGET_RECOVERED")
                    recovered.append(tenant_id)
        
        return recovered
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get error budget metrics."""
        total_exhausted = sum(1 for b in self._budgets.values() if b.is_exhausted)
        total_degraded = len(self._degraded_tenants)
        
        return {
            "tracked_tenants": len(self._budgets),
            "exhausted_tenants": total_exhausted,
            "degraded_tenants": total_degraded,
            "critical_threshold": self.critical_priority_threshold,
        }
