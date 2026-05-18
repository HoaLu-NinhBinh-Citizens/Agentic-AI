"""
Hierarchical Fair Share Quota with Brownout Error Budget.

Features:
- Multi-level DRF (tenant -> team -> project -> user)
- Brownout strategy for error budget
- Progressive degradation
- Adaptive QoS
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
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
    EMBEDDING = "embedding"
    RERANK = "rerank"


class HierarchyLevel(str, Enum):
    """Hierarchy levels."""
    GLOBAL = "global"
    TENANT = "tenant"
    TEAM = "team"
    PROJECT = "project"
    USER = "user"


class BrownoutAction(str, Enum):
    """Brownout actions for gradual degradation."""
    NONE = "none"
    REDUCE_QUALITY = "reduce_quality"       # Lower embedding quality
    REDUCE_DEPTH = "reduce_depth"           # Reduce rerank depth
    REDUCE_CONTEXT = "reduce_context"       # Reduce context size
    INCREASE_LATENCY_TOLERANCE = "increase_latency"  # Allow higher latency
    REJECT_NON_CRITICAL = "reject_non_critical"  # Reject low priority
    RATE_LIMIT = "rate_limit"              # Apply rate limits


@dataclass
class HierarchyNode:
    """Node in hierarchy."""
    level: HierarchyLevel
    id: str
    parent_id: Optional[str]
    weight: float = 1.0
    min_guarantee: Dict[ResourceType, float] = field(default_factory=dict)
    max_limit: Dict[ResourceType, float] = field(default_factory=dict)
    current_usage: Dict[ResourceType, float] = field(default_factory=dict)


@dataclass
class BrownoutConfig:
    """Configuration for brownout degradation."""
    action: BrownoutAction
    trigger_threshold: float  # Budget ratio to trigger this action
    priority: int  # Lower = apply first
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AllocationResult:
    """Result of allocation request."""
    allocated: bool
    entity_id: str
    entity_level: HierarchyLevel
    resource_type: ResourceType
    requested: float
    granted: float
    dominant_share: float
    reason: str
    applied_brownouts: List[BrownoutAction] = field(default_factory=list)


class HierarchicalDRFQuota:
    """
    Hierarchical Dominant Resource Fairness quota.
    
    Hierarchy:
    Global -> Tenant -> Team -> Project -> User
    
    Features:
    - Multi-level fairness
    - Min guarantees at each level
    - Max limits enforcement
    - DRF allocation within constraints
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
        
        # Hierarchy tree
        self._nodes: Dict[str, HierarchyNode] = {}
        self._children: Dict[str, Set[str]] = {}  # parent_id -> set of child_ids
        
        # Initialize global node
        self._init_global()
        
        self._lock = asyncio.Lock()
    
    def _init_global(self) -> None:
        """Initialize global node."""
        global_node = HierarchyNode(
            level=HierarchyLevel.GLOBAL,
            id="global",
            parent_id=None,
            weight=1.0,
            min_guarantee={},
            max_limit={},
            current_usage={r: 0.0 for r in self.resources},
        )
        self._nodes["global"] = global_node
        self._children["global"] = set()
    
    async def add_entity(
        self,
        entity_id: str,
        level: HierarchyLevel,
        parent_id: str,
        weight: float = 1.0,
        min_guarantee: Optional[Dict[ResourceType, float]] = None,
        max_limit: Optional[Dict[ResourceType, float]] = None,
    ) -> HierarchyNode:
        """Add entity to hierarchy."""
        async with self._lock:
            node = HierarchyNode(
                level=level,
                id=entity_id,
                parent_id=parent_id,
                weight=weight,
                min_guarantee=min_guarantee or {},
                max_limit=max_limit or {},
                current_usage={r: 0.0 for r in self.resources},
            )
            
            self._nodes[entity_id] = node
            
            # Add as child
            if parent_id not in self._children:
                self._children[parent_id] = set()
            self._children[parent_id].add(entity_id)
            
            return node
    
    async def request_allocation(
        self,
        entity_id: str,
        resource_type: ResourceType,
        amount: float,
    ) -> AllocationResult:
        """Request resource allocation with hierarchical fairness."""
        async with self._lock:
            node = self._nodes.get(entity_id)
            if not node:
                return AllocationResult(
                    allocated=False,
                    entity_id=entity_id,
                    entity_level=HierarchyLevel.USER,
                    resource_type=resource_type,
                    requested=amount,
                    granted=0.0,
                    dominant_share=0.0,
                    reason=f"entity_not_found",
                )
            
            # Check max limit
            max_limit = node.max_limit.get(resource_type, float("inf"))
            if amount > max_limit:
                return AllocationResult(
                    allocated=False,
                    entity_id=entity_id,
                    entity_level=node.level,
                    resource_type=resource_type,
                    requested=amount,
                    granted=0.0,
                    dominant_share=0.0,
                    reason="exceeds_max_limit",
                )
            
            # Check within guarantee
            min_guarantee = node.min_guarantee.get(resource_type, 0.0)
            current = node.current_usage.get(resource_type, 0.0)
            
            if current + amount <= min_guarantee:
                # Within guarantee, allocate directly
                node.current_usage[resource_type] = current + amount
                await self._update_ancestors(entity_id, resource_type, amount)
                
                return AllocationResult(
                    allocated=True,
                    entity_id=entity_id,
                    entity_level=node.level,
                    resource_type=resource_type,
                    requested=amount,
                    granted=amount,
                    dominant_share=await self._calculate_dominant_share(entity_id),
                    reason="within_min_guarantee",
                )
            
            # Check capacity
            total_used = sum(
                n.current_usage.get(resource_type, 0.0)
                for n in self._nodes.values()
            )
            capacity = self.total_capacity.get(resource_type, 0.0)
            available = capacity - total_used
            
            if amount <= available:
                # Allocate
                node.current_usage[resource_type] = current + amount
                await self._update_ancestors(entity_id, resource_type, amount)
                
                return AllocationResult(
                    allocated=True,
                    entity_id=entity_id,
                    entity_level=node.level,
                    resource_type=resource_type,
                    requested=amount,
                    granted=amount,
                    dominant_share=await self._calculate_dominant_share(entity_id),
                    reason="capacity_available",
                )
            
            # Not enough capacity - use DRF
            dominant_share = await self._calculate_dominant_share(entity_id)
            max_share = await self._get_max_share_in_subtree(entity_id)
            
            if dominant_share > max_share:
                return AllocationResult(
                    allocated=False,
                    entity_id=entity_id,
                    entity_level=node.level,
                    resource_type=resource_type,
                    requested=amount,
                    granted=0.0,
                    dominant_share=dominant_share,
                    reason="max_share_exceeded",
                )
            
            # Partial allocation
            granted = available
            if granted > 0:
                node.current_usage[resource_type] = current + granted
                await self._update_ancestors(entity_id, resource_type, granted)
            
            return AllocationResult(
                allocated=granted > 0,
                entity_id=entity_id,
                entity_level=node.level,
                resource_type=resource_type,
                requested=amount,
                granted=granted,
                dominant_share=await self._calculate_dominant_share(entity_id),
                reason="partial_allocation",
            )
    
    async def _update_ancestors(
        self,
        entity_id: str,
        resource_type: ResourceType,
        amount: float,
    ) -> None:
        """Update ancestor nodes with usage."""
        node = self._nodes.get(entity_id)
        while node and node.parent_id:
            parent = self._nodes.get(node.parent_id)
            if parent:
                parent.current_usage[resource_type] = (
                    parent.current_usage.get(resource_type, 0.0) + amount
                )
            node = parent
    
    async def _calculate_dominant_share(self, entity_id: str) -> float:
        """Calculate dominant share for entity."""
        node = self._nodes.get(entity_id)
        if not node:
            return 0.0
        
        weight = node.weight
        max_share = 0.0
        
        for resource in self.resources:
            usage = node.current_usage.get(resource, 0.0)
            capacity = self.total_capacity.get(resource, 1.0)
            
            if capacity > 0:
                share = (usage / capacity) / weight
                max_share = max(max_share, share)
        
        return max_share
    
    async def _get_max_share_in_subtree(self, entity_id: str) -> float:
        """Get max dominant share in subtree."""
        max_share = 0.0
        
        for child_id in self._get_all_descendants(entity_id):
            share = await self._calculate_dominant_share(child_id)
            max_share = max(max_share, share)
        
        return max_share
    
    def _get_all_descendants(self, entity_id: str) -> Set[str]:
        """Get all descendants of entity."""
        descendants = set()
        to_visit = list(self._children.get(entity_id, set()))
        
        while to_visit:
            child_id = to_visit.pop()
            descendants.add(child_id)
            to_visit.extend(self._children.get(child_id, set()))
        
        return descendants
    
    async def release_allocation(
        self,
        entity_id: str,
        resource_type: ResourceType,
        amount: float,
    ) -> None:
        """Release allocation."""
        async with self._lock:
            node = self._nodes.get(entity_id)
            if node:
                current = node.current_usage.get(resource_type, 0.0)
                node.current_usage[resource_type] = max(0.0, current - amount)
                await self._update_ancestors(entity_id, resource_type, -amount)


class BrownoutErrorBudgetPolicy:
    """
    Error budget policy with brownout strategy.
    
    Instead of hard reject, applies gradual degradation:
    - Reduce embedding quality
    - Reduce rerank depth
    - Reduce context size
    - Increase latency tolerance
    - Reject non-critical
    - Apply rate limits
    """
    
    def __init__(
        self,
        window_hours: float = 24.0,
        critical_priority_threshold: int = 5,
    ):
        self.window_hours = window_hours
        self.critical_priority_threshold = critical_priority_threshold
        
        # Budget tracking
        self._budgets: Dict[str, Dict[str, Any]] = {}  # tenant_id -> budget state
        
        # Brownout configurations
        self._brownout_configs: List[BrownoutConfig] = self._get_default_configs()
        
        # Active brownouts per tenant
        self._active_brownouts: Dict[str, Set[BrownoutAction]] = {}
        
        self._lock = asyncio.Lock()
    
    def _get_default_configs(self) -> List[BrownoutConfig]:
        """Get default brownout configurations."""
        return [
            BrownoutConfig(
                action=BrownoutAction.REDUCE_QUALITY,
                trigger_threshold=0.8,
                priority=1,
                parameters={"embedding_quality": "medium"},
            ),
            BrownoutConfig(
                action=BrownoutAction.REDUCE_DEPTH,
                trigger_threshold=0.6,
                priority=2,
                parameters={"rerank_depth": 50},
            ),
            BrownoutConfig(
                action=BrownoutAction.REDUCE_CONTEXT,
                trigger_threshold=0.5,
                priority=3,
                parameters={"max_context_tokens": 4096},
            ),
            BrownoutConfig(
                action=BrownoutAction.INCREASE_LATENCY_TOLERANCE,
                trigger_threshold=0.4,
                priority=4,
                parameters={"max_latency_ms": 5000},
            ),
            BrownoutConfig(
                action=BrownoutAction.REJECT_NON_CRITICAL,
                trigger_threshold=0.2,
                priority=5,
                parameters={"min_priority": 7},
            ),
            BrownoutConfig(
                action=BrownoutAction.RATE_LIMIT,
                trigger_threshold=0.1,
                priority=6,
                parameters={"rate_multiplier": 0.5},
            ),
        ]
    
    async def initialize_budget(
        self,
        tenant_id: str,
        total_budget: float,
    ) -> None:
        """Initialize budget for tenant."""
        async with self._lock:
            self._budgets[tenant_id] = {
                "total_budget": total_budget,
                "consumed": 0.0,
                "remaining": total_budget,
                "budget_ratio": 1.0,
                "last_updated": datetime.now(),
            }
            self._active_brownouts[tenant_id] = set()
    
    async def record_error(
        self,
        tenant_id: str,
        error_weight: float = 1.0,
    ) -> Dict[str, Any]:
        """Record error and update budget."""
        async with self._lock:
            if tenant_id not in self._budgets:
                await self.initialize_budget(tenant_id, 100.0)
            
            budget = self._budgets[tenant_id]
            budget["consumed"] += error_weight
            budget["remaining"] = max(0.0, budget["total_budget"] - budget["consumed"])
            budget["budget_ratio"] = budget["remaining"] / budget["total_budget"]
            budget["last_updated"] = datetime.now()
            
            # Determine active brownouts
            await self._update_brownouts(tenant_id)
            
            return self._get_status(tenant_id)
    
    async def _update_brownouts(self, tenant_id: str) -> None:
        """Update active brownouts based on budget."""
        budget = self._budgets[tenant_id]
        budget_ratio = budget["budget_ratio"]
        
        active = set()
        
        for config in sorted(self._brownout_configs, key=lambda c: c.priority):
            if budget_ratio <= config.trigger_threshold:
                active.add(config.action)
        
        self._active_brownouts[tenant_id] = active
    
    async def check_request(
        self,
        tenant_id: str,
        priority: int,
        request_type: str = "normal",
    ) -> Dict[str, Any]:
        """
        Check if request is allowed under brownout policy.
        
        Returns:
        - allowed: bool
        - brownouts: list of active brownouts
        - adjustments: requested parameter adjustments
        - reason: str
        """
        if tenant_id not in self._budgets:
            return {
                "allowed": True,
                "brownouts": [],
                "adjustments": {},
                "reason": "no_budget_tracking",
            }
        
        budget = self._budgets[tenant_id]
        active = self._active_brownouts.get(tenant_id, set())
        
        # Check rejection
        if BrownoutAction.REJECT_NON_CRITICAL in active:
            if priority < self.critical_priority_threshold:
                return {
                    "allowed": False,
                    "brownouts": [a.value for a in active],
                    "adjustments": {},
                    "reason": "rejected_non_critical_budget_exhausted",
                }
        
        # Build adjustments
        adjustments = {}
        for config in self._brownout_configs:
            if config.action in active:
                adjustments.update(config.parameters)
        
        # Calculate rate limit
        rate_multiplier = 1.0
        if BrownoutAction.RATE_LIMIT in active:
            rate_config = next(
                (c for c in self._brownout_configs if c.action == BrownoutAction.RATE_LIMIT),
                None
            )
            if rate_config:
                rate_multiplier = rate_config.parameters.get("rate_multiplier", 1.0)
        
        return {
            "allowed": True,
            "brownouts": [a.value for a in active],
            "adjustments": adjustments,
            "rate_multiplier": rate_multiplier,
            "budget_ratio": budget["budget_ratio"],
            "reason": "allowed_with_brownouts" if active else "allowed",
        }
    
    async def get_brownout_summary(self, tenant_id: str) -> Dict[str, Any]:
        """Get brownout summary for tenant."""
        if tenant_id not in self._budgets:
            return {}
        
        budget = self._budgets[tenant_id]
        active = self._active_brownouts.get(tenant_id, set())
        
        return {
            "tenant_id": tenant_id,
            "budget_ratio": budget["budget_ratio"],
            "active_brownouts": [a.value for a in active],
            "budget_remaining": budget["remaining"],
            "triggered_actions": len(active),
        }
    
    async def _get_status(self, tenant_id: str) -> Dict[str, Any]:
        """Get budget status."""
        if tenant_id not in self._budgets:
            return {}
        
        budget = self._budgets[tenant_id]
        active = self._active_brownouts.get(tenant_id, set())
        
        return {
            "tenant_id": tenant_id,
            "total_budget": budget["total_budget"],
            "consumed": budget["consumed"],
            "remaining": budget["remaining"],
            "budget_ratio": budget["budget_ratio"],
            "is_exhausted": budget["remaining"] <= 0,
            "active_brownouts": [a.value for a in active],
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get error budget metrics."""
        total_tenants = len(self._budgets)
        exhausted = sum(
            1 for b in self._budgets.values() if b["remaining"] <= 0
        )
        
        # Count brownout actions
        brownout_counts: Dict[str, int] = {}
        for active_set in self._active_brownouts.values():
            for action in active_set:
                brownout_counts[action.value] = brownout_counts.get(action.value, 0) + 1
        
        return {
            "tracked_tenants": total_tenants,
            "exhausted_tenants": exhausted,
            "brownout_actions": brownout_counts,
            "critical_threshold": self.critical_priority_threshold,
        }


# =============================================================================
# Phase 5D v2: HierarchicalQuotaManager (Original)
# =============================================================================

class QuotaScope(str, Enum):
    """Quota scope levels."""
    GLOBAL = "global"
    REGION = "region"
    ORG = "org"
    TENANT = "tenant"
    AGENT = "agent"


class QuotaPolicy(str, Enum):
    """Quota enforcement policies."""
    HARD = "hard"      # Strictly enforce
    SOFT = "soft"      # Warn but allow
    RELAXED = "relaxed"  # No enforcement


class QuotaExceededError(Exception):
    """Raised when quota is exceeded."""
    pass


@dataclass
class QuotaNode:
    """Node in quota hierarchy."""
    scope: QuotaScope
    id: str
    quota: float
    used: float = 0.0
    policy: QuotaPolicy = QuotaPolicy.HARD
    parent_key: str = ""


class HierarchicalQuotaManager:
    """
    Hierarchical quota manager for multi-tenant resources.
    
    Features:
    - Quota at Global, Region, Org, Tenant, Agent levels
    - Inheritance with override capability
    - Soft and hard quota enforcement
    """
    
    def __init__(
        self,
        default_quota: float = 1000.0,
        default_policy: QuotaPolicy = QuotaPolicy.HARD,
    ):
        self.default_quota = default_quota
        self.default_policy = default_policy
        
        # Hierarchy nodes: key -> QuotaNode
        self._nodes: Dict[str, QuotaNode] = {}
        
        # Initialize global node
        self._initialize_hierarchy()
        
        self._lock = asyncio.Lock()
    
    def _initialize_hierarchy(self) -> None:
        """Initialize quota hierarchy."""
        global_node = QuotaNode(
            scope=QuotaScope.GLOBAL,
            id="global",
            quota=10000.0,
            used=0.0,
            policy=QuotaPolicy.HARD,
            parent_key="",
        )
        self._nodes["global:global"] = global_node
    
    def _get_node_key(self, scope: QuotaScope, id: str) -> str:
        """Get node key."""
        return f"{scope.value}:{id}"
    
    async def set_quota(
        self,
        scope: QuotaScope,
        id: str,
        quota: float,
        policy: QuotaPolicy = None,
        parent_id: str = None,
    ) -> None:
        """Set quota for scope."""
        async with self._lock:
            key = self._get_node_key(scope, id)
            parent_key = ""
            
            if parent_id:
                parent_scope = self._get_parent_scope(scope)
                parent_key = self._get_node_key(parent_scope, parent_id)
            
            node = QuotaNode(
                scope=scope,
                id=id,
                quota=quota,
                used=0.0,
                policy=policy or self.default_policy,
                parent_key=parent_key,
            )
            
            self._nodes[key] = node
    
    def _get_parent_scope(self, scope: QuotaScope) -> QuotaScope:
        """Get parent scope."""
        parent_map = {
            QuotaScope.REGION: QuotaScope.GLOBAL,
            QuotaScope.ORG: QuotaScope.REGION,
            QuotaScope.TENANT: QuotaScope.ORG,
            QuotaScope.AGENT: QuotaScope.TENANT,
        }
        return parent_map.get(scope, QuotaScope.GLOBAL)
    
    async def allocate(
        self,
        scope: QuotaScope,
        id: str,
        amount: float,
    ) -> bool:
        """Allocate quota."""
        async with self._lock:
            key = self._get_node_key(scope, id)
            node = self._nodes.get(key)
            
            if not node:
                return False
            
            if node.used + amount > node.quota:
                if node.policy == QuotaPolicy.HARD:
                    return False
            
            node.used += amount
            
            # Propagate to parent
            if node.parent_key:
                parent = self._nodes.get(node.parent_key)
                if parent:
                    parent.used += amount
            
            return True
    
    async def release(
        self,
        scope: QuotaScope,
        id: str,
        amount: float,
    ) -> None:
        """Release quota."""
        async with self._lock:
            key = self._get_node_key(scope, id)
            node = self._nodes.get(key)
            
            if node:
                node.used = max(0.0, node.used - amount)
    
    async def get_available(
        self,
        scope: QuotaScope,
        id: str,
    ) -> float:
        """Get available quota."""
        async with self._lock:
            key = self._get_node_key(scope, id)
            node = self._nodes.get(key)
            
            if not node:
                return self.default_quota
            
            return max(0.0, node.quota - node.used)
