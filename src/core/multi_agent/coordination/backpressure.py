"""
Backpressure Controller for Multi-Agent Coordination.

Provides rate limiting from coordinator to agents with 429 responses.
Uses sliding window for accurate rate tracking.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from src.core.multi_agent.coordination.types import BackpressureResponse

logger = logging.getLogger(__name__)


class BackpressureController:
    """
    Backpressure controller for multi-agent coordination.
    
    Monitors request rate from each agent and applies backpressure
    when rates exceed configured limits.
    
    Features:
    - Sliding window rate tracking
    - Configurable per-agent rate limits
    - 429 responses with Retry-After header
    - Per-tenant rate limiting option
    
    When an agent exceeds its rate limit:
    - Coordinator returns 429 Too Many Requests
    - Header Retry-After indicates when to retry
    - Agent should slow down its request rate
    """
    
    def __init__(
        self,
        rate_limit_per_agent: int = 200,
        window_seconds: int = 10,
        enable_per_tenant: bool = False,
        default_retry_after: float = 5.0,
    ):
        self.rate_limit_per_agent = rate_limit_per_agent
        self.window_seconds = window_seconds
        self.enable_per_tenant = enable_per_tenant
        self.default_retry_after = default_retry_after
        
        self._lock = asyncio.Lock()
        self._request_history: Dict[str, deque] = defaultdict(lambda: deque())
        self._agent_limits: Dict[str, int] = {}
        
        # Metrics
        self._total_checks = 0
        self._throttle_count = defaultdict(int)
        self._total_requests = defaultdict(int)
    
    def _get_key(self, agent_id: str, tenant_id: Optional[str] = None) -> str:
        """Get rate limit key for agent."""
        if self.enable_per_tenant and tenant_id:
            return f"{tenant_id}:{agent_id}"
        return agent_id
    
    def _cleanup_window(self, key: str) -> None:
        """Remove expired requests from window."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        
        history = self._request_history[key]
        while history and history[0] < cutoff:
            history.popleft()
    
    async def record_request(
        self,
        agent_id: str,
        tenant_id: Optional[str] = None,
    ) -> None:
        """
        Record a request from an agent.
        
        Args:
            agent_id: ID of the agent
            tenant_id: Optional tenant ID for per-tenant limiting
        """
        key = self._get_key(agent_id, tenant_id)
        
        async with self._lock:
            self._cleanup_window(key)
            self._request_history[key].append(time.monotonic())
            self._total_requests[key] += 1
    
    async def check_rate_limit(
        self,
        agent_id: str,
        tenant_id: Optional[str] = None,
    ) -> BackpressureResponse:
        """
        Check if agent is within rate limit.
        
        Args:
            agent_id: ID of the agent
            tenant_id: Optional tenant ID for per-tenant limiting
            
        Returns:
            BackpressureResponse indicating if limited and retry timing
        """
        self._total_checks += 1
        key = self._get_key(agent_id, tenant_id)
        
        async with self._lock:
            self._cleanup_window(key)
            
            count = len(self._request_history[key])
            limit = self._agent_limits.get(key, self.rate_limit_per_agent)
            
            now = time.monotonic()
            reset_time = now + self.window_seconds
            
            if count >= limit:
                self._throttle_count[key] += 1
                
                # Calculate retry-after
                oldest_in_window = self._request_history[key][0] if self._request_history[key] else now
                retry_after = max(
                    self.default_retry_after,
                    oldest_in_window + self.window_seconds - now,
                )
                
                logger.warning(
                    f"Rate limit exceeded for {key}: {count}/{limit}",
                    extra={"agent_id": agent_id, "limit": limit, "current": count}
                )
                
                return BackpressureResponse(
                    is_limited=True,
                    retry_after=retry_after,
                    limit=limit,
                    remaining=0,
                    reset_at=datetime.fromtimestamp(reset_time),
                )
            
            remaining = limit - count
            
            return BackpressureResponse(
                is_limited=False,
                retry_after=0.0,
                limit=limit,
                remaining=remaining,
                reset_at=datetime.fromtimestamp(reset_time),
            )
    
    async def set_agent_limit(
        self,
        agent_id: str,
        limit: int,
        tenant_id: Optional[str] = None,
    ) -> None:
        """
        Set custom rate limit for an agent.
        
        Args:
            agent_id: ID of the agent
            limit: New rate limit
            tenant_id: Optional tenant ID
        """
        key = self._get_key(agent_id, tenant_id)
        self._agent_limits[key] = limit
        logger.info(f"Set rate limit for {key}: {limit}")
    
    async def get_agent_stats(
        self,
        agent_id: str,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get rate limiting statistics for an agent.
        
        Args:
            agent_id: ID of the agent
            tenant_id: Optional tenant ID
            
        Returns:
            Statistics dictionary
        """
        key = self._get_key(agent_id, tenant_id)
        
        async with self._lock:
            self._cleanup_window(key)
            
            count = len(self._request_history[key])
            limit = self._agent_limits.get(key, self.rate_limit_per_agent)
            
            return {
                "agent_id": agent_id,
                "tenant_id": tenant_id,
                "current_rate": count,
                "limit": limit,
                "usage_percent": round(count / max(1, limit) * 100, 1),
                "throttle_count": self._throttle_count.get(key, 0),
                "total_requests": self._total_requests.get(key, 0),
                "window_seconds": self.window_seconds,
            }
    
    async def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all agents."""
        stats = {}
        
        async with self._lock:
            for key in self._request_history.keys():
                self._cleanup_window(key)
                
                count = len(self._request_history[key])
                limit = self._agent_limits.get(key, self.rate_limit_per_agent)
                
                agent_id = key.split(":", 1)[1] if ":" in key and self.enable_per_tenant else key
                tenant_id = key.split(":", 1)[0] if ":" in key and self.enable_per_tenant else None
                
                stats[key] = {
                    "agent_id": agent_id,
                    "tenant_id": tenant_id,
                    "current_rate": count,
                    "limit": limit,
                    "usage_percent": round(count / max(1, limit) * 100, 1),
                    "throttle_count": self._throttle_count.get(key, 0),
                    "total_requests": self._total_requests.get(key, 0),
                }
        
        return stats
    
    async def reset_agent(
        self,
        agent_id: str,
        tenant_id: Optional[str] = None,
    ) -> None:
        """
        Reset rate limiting state for an agent.
        
        Args:
            agent_id: ID of the agent
            tenant_id: Optional tenant ID
        """
        key = self._get_key(agent_id, tenant_id)
        
        async with self._lock:
            self._request_history[key].clear()
            logger.info(f"Reset rate limit state for {key}")
    
    async def reset_all(self) -> None:
        """Reset rate limiting state for all agents."""
        async with self._lock:
            self._request_history.clear()
            logger.info("Reset all rate limit state")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get backpressure metrics."""
        total_throttles = sum(self._throttle_count.values())
        total_requests = sum(self._total_requests.values())
        
        return {
            "total_checks": self._total_checks,
            "total_throttles": total_throttles,
            "total_requests": total_requests,
            "throttles_by_agent": dict(self._throttle_count),
            "tracked_agents": len(self._request_history),
            "rate_limit_per_agent": self.rate_limit_per_agent,
            "window_seconds": self.window_seconds,
            "enable_per_tenant": self.enable_per_tenant,
        }


class AdaptiveBackpressureController(BackpressureController):
    """
    Adaptive backpressure controller that adjusts limits based on system load.
    
    Features:
    - Dynamic rate limit adjustment
    - Load-based throttling
    - Gradual recovery when load decreases
    """
    
    def __init__(
        self,
        base_rate_limit: int = 200,
        window_seconds: int = 10,
        min_rate_limit: int = 10,
        max_rate_limit: int = 1000,
        load_threshold_high: float = 0.8,
        load_threshold_low: float = 0.3,
        adjustment_factor: float = 0.1,
    ):
        super().__init__(
            rate_limit_per_agent=base_rate_limit,
            window_seconds=window_seconds,
        )
        
        self.base_rate_limit = base_rate_limit
        self.min_rate_limit = min_rate_limit
        self.max_rate_limit = max_rate_limit
        self.load_threshold_high = load_threshold_high
        self.load_threshold_low = load_threshold_low
        self.adjustment_factor = adjustment_factor
        
        self._current_system_load = 0.0
        self._current_limit = base_rate_limit
    
    async def _adjust_limit(self) -> None:
        """Adjust rate limit based on system load."""
        # Count total requests across all agents
        total_requests = 0
        for history in self._request_history.values():
            self._cleanup_window("")
            total_requests += len(history)
        
        # Calculate load
        max_capacity = len(self._request_history) * self.base_rate_limit
        self._current_system_load = total_requests / max(1, max_capacity)
        
        # Adjust limit
        if self._current_system_load > self.load_threshold_high:
            # Reduce limit
            reduction = self._current_limit * self.adjustment_factor
            self._current_limit = max(self.min_rate_limit, self._current_limit - reduction)
        elif self._current_system_load < self.load_threshold_low:
            # Increase limit
            increase = self._current_limit * self.adjustment_factor
            self._current_limit = min(self.max_rate_limit, self._current_limit + increase)
        
        # Update all agent limits
        for key in self._request_history.keys():
            self._agent_limits[key] = int(self._current_limit)
    
    async def check_rate_limit(
        self,
        agent_id: str,
        tenant_id: Optional[str] = None,
    ) -> BackpressureResponse:
        """Check rate limit with adaptive adjustment."""
        await self._adjust_limit()
        return await super().check_rate_limit(agent_id, tenant_id)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get adaptive backpressure metrics."""
        metrics = super().get_metrics()
        metrics.update({
            "current_system_load": round(self._current_system_load, 3),
            "current_limit": self._current_limit,
            "base_rate_limit": self.base_rate_limit,
            "min_rate_limit": self.min_rate_limit,
            "max_rate_limit": self.max_rate_limit,
        })
        return metrics
