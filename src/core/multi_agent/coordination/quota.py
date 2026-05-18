"""
Quota Enforcer for Multi-Agent Coordination.

Enforces resource quotas per agent:
- Concurrent tasks limit
- Message rate limit
- Workspace size limit
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.core.multi_agent.coordination.types import AgentQuota

logger = logging.getLogger(__name__)


class QuotaExceededError(Exception):
    """Raised when agent quota is exceeded."""
    
    def __init__(
        self,
        message: str,
        quota_type: str,
        limit: int,
        current: int,
        retry_after: float = 0.0,
    ):
        super().__init__(message)
        self.quota_type = quota_type
        self.limit = limit
        self.current = current
        self.retry_after = retry_after


class QuotaStore:
    """Interface for quota storage."""
    
    async def get_quota(self, agent_id: str) -> Optional[AgentQuota]:
        raise NotImplementedError
    
    async def save_quota(self, quota: AgentQuota) -> None:
        raise NotImplementedError
    
    async def delete_quota(self, agent_id: str) -> None:
        raise NotImplementedError
    
    async def list_quotas(self) -> List[AgentQuota]:
        raise NotImplementedError


class InMemoryQuotaStore(QuotaStore):
    """In-memory implementation of QuotaStore."""
    
    def __init__(self):
        self._quotas: Dict[str, AgentQuota] = {}
        self._lock = asyncio.Lock()
    
    async def get_quota(self, agent_id: str) -> Optional[AgentQuota]:
        return self._quotas.get(agent_id)
    
    async def save_quota(self, quota: AgentQuota) -> None:
        async with self._lock:
            self._quotas[quota.agent_id] = quota
    
    async def delete_quota(self, agent_id: str) -> None:
        async with self._lock:
            self._quotas.pop(agent_id, None)
    
    async def list_quotas(self) -> List[AgentQuota]:
        return list(self._quotas.values())


@dataclass
class RateLimitBucket:
    """Token bucket for rate limiting."""
    tokens: float
    last_refill: float
    requests: deque = field(default_factory=lambda: deque())


class QuotaEnforcer:
    """
    Quota enforcer for multi-agent coordination.
    
    Enforces resource quotas per agent:
    - max_concurrent_tasks: Maximum concurrent tasks
    - max_message_rate: Maximum messages per second
    - max_workspace_bytes: Maximum workspace size in bytes
    
    Uses token bucket algorithm for rate limiting.
    """
    
    def __init__(
        self,
        store: Optional[QuotaStore] = None,
        default_max_concurrent: int = 10,
        default_max_message_rate: int = 100,
        default_max_workspace_bytes: int = 10 * 1024 * 1024,
    ):
        self.store = store or InMemoryQuotaStore()
        self.default_max_concurrent = default_max_concurrent
        self.default_max_message_rate = default_max_message_rate
        self.default_max_workspace_bytes = default_max_workspace_bytes
        
        self._lock = asyncio.Lock()
        self._current_concurrent: Dict[str, int] = defaultdict(int)
        self._rate_buckets: Dict[str, RateLimitBucket] = {}
        self._workspace_sizes: Dict[str, int] = defaultdict(int)
        
        # Metrics
        self._reject_count = defaultdict(int)
        self._total_checks = 0
    
    async def get_quota(self, agent_id: str) -> AgentQuota:
        """Get quota for an agent, creating default if not exists."""
        quota = await self.store.get_quota(agent_id)
        
        if not quota:
            quota = AgentQuota(
                agent_id=agent_id,
                max_concurrent_tasks=self.default_max_concurrent,
                max_message_rate=self.default_max_message_rate,
                max_workspace_bytes=self.default_max_workspace_bytes,
            )
            await self.store.save_quota(quota)
        
        # Update current usage
        quota.current_concurrent = self._current_concurrent.get(agent_id, 0)
        quota.current_message_rate = self._get_current_rate(agent_id)
        quota.current_workspace_bytes = self._workspace_sizes.get(agent_id, 0)
        
        return quota
    
    async def set_quota(
        self,
        agent_id: str,
        max_concurrent_tasks: Optional[int] = None,
        max_message_rate: Optional[int] = None,
        max_workspace_bytes: Optional[int] = None,
    ) -> AgentQuota:
        """Set quota for an agent."""
        quota = await self.get_quota(agent_id)
        
        if max_concurrent_tasks is not None:
            quota.max_concurrent_tasks = max_concurrent_tasks
        if max_message_rate is not None:
            quota.max_message_rate = max_message_rate
        if max_workspace_bytes is not None:
            quota.max_workspace_bytes = max_workspace_bytes
        
        quota.updated_at = datetime.now()
        
        await self.store.save_quota(quota)
        logger.info(f"Updated quota for {agent_id}: {quota}")
        
        return quota
    
    async def check_concurrent(self, agent_id: str) -> None:
        """
        Check if agent can start a new concurrent task.
        
        Raises:
            QuotaExceededError: If concurrent task limit exceeded
        """
        self._total_checks += 1
        quota = await self.get_quota(agent_id)
        
        current = self._current_concurrent[agent_id]
        if current >= quota.max_concurrent_tasks:
            self._reject_count[f"{agent_id}:concurrent"] += 1
            raise QuotaExceededError(
                f"Concurrent tasks limit exceeded: {current}/{quota.max_concurrent_tasks}",
                quota_type="concurrent",
                limit=quota.max_concurrent_tasks,
                current=current,
            )
    
    async def increment_concurrent(self, agent_id: str) -> int:
        """Increment concurrent task count. Returns new count."""
        async with self._lock:
            self._current_concurrent[agent_id] += 1
            return self._current_concurrent[agent_id]
    
    async def decrement_concurrent(self, agent_id: str) -> int:
        """Decrement concurrent task count. Returns new count."""
        async with self._lock:
            self._current_concurrent[agent_id] = max(
                0, self._current_concurrent[agent_id] - 1
            )
            return self._current_concurrent[agent_id]
    
    def _get_current_rate(self, agent_id: str) -> float:
        """Get current message rate for an agent."""
        bucket = self._rate_buckets.get(agent_id)
        if not bucket:
            return 0.0
        
        now = time.monotonic()
        cutoff = now - 1.0  # 1 second window
        
        # Remove old requests
        while bucket.requests and bucket.requests[0] < cutoff:
            bucket.requests.popleft()
        
        return len(bucket.requests)
    
    def _refill_bucket(self, bucket: RateLimitBucket, rate: float) -> None:
        """Refill token bucket based on elapsed time."""
        now = time.monotonic()
        elapsed = now - bucket.last_refill
        
        # Add tokens based on rate
        tokens_to_add = elapsed * rate
        bucket.tokens = min(rate, bucket.tokens + tokens_to_add)
        bucket.last_refill = now
    
    async def check_rate_limit(self, agent_id: str) -> None:
        """
        Check if agent can send a message.
        
        Raises:
            QuotaExceededError: If message rate limit exceeded
        """
        self._total_checks += 1
        quota = await self.get_quota(agent_id)
        
        # Get or create bucket
        if agent_id not in self._rate_buckets:
            self._rate_buckets[agent_id] = RateLimitBucket(
                tokens=float(quota.max_message_rate),
                last_refill=time.monotonic(),
            )
        
        bucket = self._rate_buckets[agent_id]
        self._refill_bucket(bucket, float(quota.max_message_rate))
        
        # Record request
        now = time.monotonic()
        bucket.requests.append(now)
        
        # Check if over limit
        if len(bucket.requests) > quota.max_message_rate:
            self._reject_count[f"{agent_id}:rate"] += 1
            raise QuotaExceededError(
                f"Message rate limit exceeded: {len(bucket.requests)}/{quota.max_message_rate}/s",
                quota_type="rate",
                limit=quota.max_message_rate,
                current=len(bucket.requests),
                retry_after=1.0,
            )
    
    async def record_message(self, agent_id: str) -> None:
        """Record a message sent by an agent."""
        if agent_id not in self._rate_buckets:
            quota = await self.get_quota(agent_id)
            self._rate_buckets[agent_id] = RateLimitBucket(
                tokens=float(quota.max_message_rate),
                last_refill=time.monotonic(),
            )
        
        bucket = self._rate_buckets[agent_id]
        self._refill_bucket(bucket, (await self.get_quota(agent_id)).max_message_rate)
        
        now = time.monotonic()
        bucket.requests.append(now)
    
    async def check_workspace_size(self, agent_id: str, additional_bytes: int = 0) -> None:
        """
        Check if agent's workspace is within size limit.
        
        Raises:
            QuotaExceededError: If workspace size limit exceeded
        """
        self._total_checks += 1
        quota = await self.get_quota(agent_id)
        
        current_size = self._workspace_sizes.get(agent_id, 0)
        new_size = current_size + additional_bytes
        
        if new_size > quota.max_workspace_bytes:
            self._reject_count[f"{agent_id}:workspace"] += 1
            raise QuotaExceededError(
                f"Workspace size limit exceeded: {new_size}/{quota.max_workspace_bytes} bytes",
                quota_type="workspace",
                limit=quota.max_workspace_bytes,
                current=new_size,
            )
    
    async def set_workspace_size(self, agent_id: str, size: int) -> None:
        """Set agent's current workspace size."""
        self._workspace_sizes[agent_id] = size
        await self.check_workspace_size(agent_id)
    
    async def update_workspace_size(self, agent_id: str, delta: int) -> int:
        """Update agent's workspace size by delta. Returns new size."""
        async with self._lock:
            current = self._workspace_sizes.get(agent_id, 0)
            new_size = max(0, current + delta)
            self._workspace_sizes[agent_id] = new_size
            return new_size
    
    async def submit_task(self, agent_id: str) -> None:
        """
        Submit a task for an agent (checks all quotas).
        
        Raises:
            QuotaExceededError: If any quota exceeded
        """
        await self.check_concurrent(agent_id)
        await self.check_rate_limit(agent_id)
        await self.increment_concurrent(agent_id)
    
    async def complete_task(self, agent_id: str) -> None:
        """Mark a task as complete for an agent."""
        await self.decrement_concurrent(agent_id)
    
    async def release_task(self, agent_id: str) -> None:
        """Release task without completion (failure case)."""
        await self.decrement_concurrent(agent_id)
    
    async def list_quotas(self) -> List[Dict[str, Any]]:
        """List all agent quotas with current usage."""
        quotas = await self.store.list_quotas()
        
        result = []
        for quota in quotas:
            quota.current_concurrent = self._current_concurrent.get(quota.agent_id, 0)
            quota.current_message_rate = self._get_current_rate(quota.agent_id)
            quota.current_workspace_bytes = self._workspace_sizes.get(quota.agent_id, 0)
            result.append(quota.to_dict())
        
        return result
    
    async def get_agent_usage(self, agent_id: str) -> Dict[str, Any]:
        """Get current usage statistics for an agent."""
        quota = await self.get_quota(agent_id)
        
        return {
            "agent_id": agent_id,
            "concurrent": {
                "current": self._current_concurrent.get(agent_id, 0),
                "limit": quota.max_concurrent_tasks,
                "usage_percent": round(
                    self._current_concurrent.get(agent_id, 0) / max(1, quota.max_concurrent_tasks) * 100,
                    1
                ),
            },
            "rate": {
                "current": round(self._get_current_rate(agent_id), 2),
                "limit": quota.max_message_rate,
                "usage_percent": round(
                    self._get_current_rate(agent_id) / max(1, quota.max_message_rate) * 100,
                    1
                ),
            },
            "workspace": {
                "current": self._workspace_sizes.get(agent_id, 0),
                "limit": quota.max_workspace_bytes,
                "usage_percent": round(
                    self._workspace_sizes.get(agent_id, 0) / max(1, quota.max_workspace_bytes) * 100,
                    1
                ),
            },
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get quota enforcement metrics."""
        total_rejects = sum(self._reject_count.values())
        
        return {
            "total_checks": self._total_checks,
            "total_rejects": total_rejects,
            "rejects_by_type": dict(self._reject_count),
            "active_agents": len(self._current_concurrent),
            "rate_limited_agents": len(self._rate_buckets),
            "default_max_concurrent": self.default_max_concurrent,
            "default_max_message_rate": self.default_max_message_rate,
            "default_max_workspace_bytes": self.default_max_workspace_bytes,
        }
