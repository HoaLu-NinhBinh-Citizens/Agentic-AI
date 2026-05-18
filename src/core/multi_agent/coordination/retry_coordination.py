"""
Global Retry Budget and Jitter Coordination.

Prevents retry storms through:
- Global retry budget
- Jitter coordination
- Exponential backoff with jitter
- Priority-aware dropping
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class RetryDecision(str, Enum):
    """Retry decision result."""
    ALLOW = "allow"
    DENY = "deny"
    DELAY = "delay"
    DROP = "drop"


@dataclass
class RetryBudget:
    """Retry budget configuration."""
    max_retries_per_task: int = 5
    max_retries_per_agent: int = 50
    max_retries_per_minute: int = 100
    global_max_retries_per_minute: int = 1000
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 60.0
    backoff_multiplier: float = 2.0
    jitter_percent: float = 0.2  # +/- 20% jitter


@dataclass
class RetryAttempt:
    """Record of a retry attempt."""
    task_id: str
    agent_id: str
    attempt: int
    timestamp: datetime
    delay_seconds: float
    jitter_applied: float


class RetryBudgetManager:
    """
    Manages global retry budgets to prevent retry storms.
    
    Features:
    - Per-task retry budgets
    - Per-agent retry budgets
    - Global retry rate limiting
    - Exponential backoff with jitter
    """
    
    def __init__(
        self,
        budget: Optional[RetryBudget] = None,
    ):
        self.budget = budget or RetryBudget()
        
        self._task_attempts: Dict[str, List[RetryAttempt]] = defaultdict(list)
        self._agent_attempts: Dict[str, List[RetryAttempt]] = defaultdict(list)
        self._global_attempts: List[RetryAttempt] = []
        self._lock = asyncio.Lock()
        
        # Callbacks for budget events
        self._denied_callbacks: List[Callable[[str, str, str], None]] = []
    
    def register_denied_callback(
        self,
        callback: Callable[[str, str, str], None],
    ) -> None:
        """Register callback for denied retries."""
        self._denied_callbacks.append(callback)
    
    async def can_retry(
        self,
        task_id: str,
        agent_id: str,
        current_attempt: int,
    ) -> tuple[RetryDecision, float]:
        """
        Check if a retry is allowed.
        
        Returns (decision, delay_seconds).
        """
        async with self._lock:
            now = datetime.now()
            minute_ago = now - timedelta(minutes=1)
            
            # Check task budget
            task_attempts = self._task_attempts.get(task_id, [])
            if len(task_attempts) >= self.budget.max_retries_per_task:
                await self._notify_denied(task_id, agent_id, "task_budget_exceeded")
                return RetryDecision.DENY, 0.0
            
            # Check agent budget
            agent_attempts = self._agent_attempts.get(agent_id, [])
            recent_agent = [a for a in agent_attempts if a.timestamp > minute_ago]
            if len(recent_agent) >= self.budget.max_retries_per_agent:
                await self._notify_denied(task_id, agent_id, "agent_budget_exceeded")
                return RetryDecision.DENY, 0.0
            
            # Check global budget
            recent_global = [a for a in self._global_attempts if a.timestamp > minute_ago]
            if len(recent_global) >= self.budget.global_max_retries_per_minute:
                await self._notify_denied(task_id, agent_id, "global_budget_exceeded")
                return RetryDecision.DENY, 0.0
            
            # Calculate delay with jitter
            delay = self._calculate_backoff(current_attempt)
            
            return RetryDecision.ALLOW, delay
    
    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate backoff delay with jitter."""
        # Exponential backoff
        delay = min(
            self.budget.backoff_max_seconds,
            self.budget.backoff_base_seconds * (self.budget.backoff_multiplier ** attempt)
        )
        
        # Add jitter
        jitter_range = delay * self.budget.jitter_percent
        jitter = random.uniform(-jitter_range, jitter_range)
        delay += jitter
        
        return max(0.1, delay)
    
    async def record_attempt(
        self,
        task_id: str,
        agent_id: str,
        attempt: int,
        delay_seconds: float,
    ) -> None:
        """Record a retry attempt."""
        async with self._lock:
            attempt_record = RetryAttempt(
                task_id=task_id,
                agent_id=agent_id,
                attempt=attempt,
                timestamp=datetime.now(),
                delay_seconds=delay_seconds,
                jitter_applied=delay_seconds - (
                    self.budget.backoff_base_seconds * (self.budget.backoff_multiplier ** attempt)
                ),
            )
            
            self._task_attempts[task_id].append(attempt_record)
            self._agent_attempts[agent_id].append(attempt_record)
            self._global_attempts.append(attempt_record)
            
            # Cleanup old attempts
            self._cleanup_old_attempts()
    
    def _cleanup_old_attempts(self) -> None:
        """Remove old attempt records."""
        cutoff = datetime.now() - timedelta(minutes=5)
        
        # Cleanup task attempts
        for task_id in list(self._task_attempts.keys()):
            self._task_attempts[task_id] = [
                a for a in self._task_attempts[task_id] if a.timestamp > cutoff
            ]
            if not self._task_attempts[task_id]:
                del self._task_attempts[task_id]
        
        # Cleanup agent attempts
        for agent_id in list(self._agent_attempts.keys()):
            self._agent_attempts[agent_id] = [
                a for a in self._agent_attempts[agent_id] if a.timestamp > cutoff
            ]
            if not self._agent_attempts[agent_id]:
                del self._agent_attempts[agent_id]
        
        # Cleanup global attempts
        self._global_attempts = [
            a for a in self._global_attempts if a.timestamp > cutoff
        ]
    
    async def _notify_denied(
        self,
        task_id: str,
        agent_id: str,
        reason: str,
    ) -> None:
        """Notify that a retry was denied."""
        logger.warning(f"Retry denied: task={task_id}, agent={agent_id}, reason={reason}")
        
        for callback in self._denied_callbacks:
            try:
                callback(task_id, agent_id, reason)
            except Exception as e:
                logger.error(f"Denied callback failed: {e}")
    
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get retry status for a task."""
        async with self._lock:
            attempts = self._task_attempts.get(task_id, [])
            
            return {
                "task_id": task_id,
                "attempt_count": len(attempts),
                "max_attempts": self.budget.max_retries_per_task,
                "remaining_attempts": self.budget.max_retries_per_task - len(attempts),
                "can_retry": len(attempts) < self.budget.max_retries_per_task,
                "attempts": [
                    {
                        "attempt": a.attempt,
                        "timestamp": a.timestamp.isoformat(),
                        "delay": a.delay_seconds,
                    }
                    for a in attempts[-5:]
                ],
            }
    
    async def get_agent_status(self, agent_id: str) -> Dict[str, Any]:
        """Get retry status for an agent."""
        async with self._lock:
            attempts = self._agent_attempts.get(agent_id, [])
            now = datetime.now()
            minute_ago = now - timedelta(minutes=1)
            recent = [a for a in attempts if a.timestamp > minute_ago]
            
            return {
                "agent_id": agent_id,
                "total_attempts": len(attempts),
                "attempts_last_minute": len(recent),
                "max_per_minute": self.budget.max_retries_per_agent,
                "remaining_this_minute": max(0, self.budget.max_retries_per_agent - len(recent)),
            }
    
    async def get_global_status(self) -> Dict[str, Any]:
        """Get global retry status."""
        async with self._lock:
            now = datetime.now()
            minute_ago = now - timedelta(minutes=1)
            recent = [a for a in self._global_attempts if a.timestamp > minute_ago]
            
            return {
                "attempts_last_minute": len(recent),
                "max_per_minute": self.budget.global_max_retries_per_minute,
                "remaining": max(0, self.budget.global_max_retries_per_minute - len(recent)),
                "tracked_tasks": len(self._task_attempts),
                "tracked_agents": len(self._agent_attempts),
            }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get retry metrics."""
        return {
            "global_attempts_last_minute": len([
                a for a in self._global_attempts
                if a.timestamp > datetime.now() - timedelta(minutes=1)
            ]),
            "tracked_tasks": len(self._task_attempts),
            "tracked_agents": len(self._agent_attempts),
            "budget": {
                "max_retries_per_task": self.budget.max_retries_per_task,
                "max_retries_per_agent": self.budget.max_retries_per_agent,
                "global_max_per_minute": self.budget.global_max_retries_per_minute,
            },
        }


class JitterCoordinator:
    """
    Coordinates jitter to prevent synchronized retries.
    
    When many agents fail simultaneously, they should retry at different times.
    This coordinator ensures jitter is applied to spread out retries.
    """
    
    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter_percent: float = 0.3,
    ):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter_percent = jitter_percent
        
        self._delay_history: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def calculate_delay(
        self,
        source_id: str,
        attempt: int,
        priority: int = 5,
    ) -> float:
        """
        Calculate delay with coordinated jitter.
        
        Higher priority = less delay.
        Higher attempt = more delay.
        """
        async with self._lock:
            # Calculate base delay
            base = min(self.max_delay, self.base_delay * (2 ** attempt))
            
            # Priority adjustment (1-10 scale)
            priority_factor = 1.0 - (priority - 1) / 10.0 * 0.5  # 0.5 to 1.0
            
            # Add jitter
            jitter_range = base * self.jitter_percent
            jitter = random.uniform(-jitter_range, jitter_range)
            
            # Spread based on source_id hash to reduce collision
            hash_factor = (hash(source_id) % 100) / 100.0 * 0.2 + 0.9  # 0.9 to 1.1
            
            delay = base * priority_factor * hash_factor + jitter
            delay = max(0.1, min(self.max_delay, delay))
            
            # Record for analysis
            self._delay_history[source_id].append(delay)
            if len(self._delay_history[source_id]) > 100:
                self._delay_history[source_id] = self._delay_history[source_id][-100:]
            
            return delay
    
    async def get_statistics(self, source_id: str) -> Dict[str, Any]:
        """Get jitter statistics for a source."""
        async with self._lock:
            delays = self._delay_history.get(source_id, [])
            
            if not delays:
                return {"source_id": source_id, "count": 0}
            
            return {
                "source_id": source_id,
                "count": len(delays),
                "avg_delay": sum(delays) / len(delays),
                "min_delay": min(delays),
                "max_delay": max(delays),
            }


class SystemOverloadProtection:
    """
    Prevents system-wide overload during cascading failures.
    
    Features:
    - Load shedding
    - Priority-based dropping
    - Backpressure propagation
    """
    
    def __init__(
        self,
        max_queue_depth: int = 10000,
        load_shed_threshold: float = 0.8,
        recovery_threshold: float = 0.5,
    ):
        self.max_queue_depth = max_queue_depth
        self.load_shed_threshold = load_shed_threshold
        self.recovery_threshold = recovery_threshold
        
        self._current_load = 0.0
        self._overload_since: Optional[datetime] = None
        self._lock = asyncio.Lock()
        
        # Priority thresholds
        self._priority_thresholds = {
            1: 0.1,  # Critical - always accept
            2: 0.2,  # High - accept until 20% load
            3: 0.3,  # Normal - accept until 30% load
            4: 0.5,  # Low - accept until 50% load
            5: 1.0,  # Background - accept until 100% load
        }
    
    async def update_load(self, queue_depth: int) -> None:
        """Update current system load."""
        async with self._lock:
            self._current_load = queue_depth / self.max_queue_depth
            
            if self._current_load >= self.load_shed_threshold:
                if self._overload_since is None:
                    self._overload_since = datetime.now()
            else:
                self._overload_since = None
    
    async def should_accept(
        self,
        priority: int = 3,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, str]:
        """
        Check if a request should be accepted.
        
        Returns (accepted, reason).
        """
        async with self._lock:
            # Critical priority always accepted
            if priority <= 1:
                return True, "critical_priority"
            
            # Check load
            threshold = self._priority_thresholds.get(priority, 1.0)
            
            if self._current_load >= threshold:
                return False, f"load_exceeded: {self._current_load:.1%} >= {threshold:.1%}"
            
            if self._current_load >= self.load_shed_threshold:
                # Check if overload is prolonged
                if self._overload_since:
                    duration = (datetime.now() - self._overload_since).total_seconds()
                    if duration > 60:  # 1 minute of overload
                        # Start dropping lower priority
                        if priority >= 4:
                            return False, f"prolonged_overload: {duration:.0f}s"
            
            return True, "accepted"
    
    async def get_drop_recommendation(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[str]:
        """
        Get list of message IDs that should be dropped.
        
        Returns IDs in order of preference to drop.
        """
        async with self._lock:
            if self._current_load < self.load_shed_threshold:
                return []
            
            # Sort by priority (highest number = lowest priority = drop first)
            sorted_messages = sorted(
                messages,
                key=lambda m: m.get("priority", 3),
                reverse=True,
            )
            
            # Calculate how many to drop
            target_load = self.recovery_threshold * self.max_queue_depth
            current = int(self._current_load * self.max_queue_depth)
            drop_count = current - target_load
            
            return [m["message_id"] for m in sorted_messages[:max(0, int(drop_count))]]
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get overload protection metrics."""
        return {
            "current_load": self._current_load,
            "load_percent": f"{self._current_load * 100:.1f}%",
            "is_overloaded": self._current_load >= self.load_shed_threshold,
            "overload_duration_seconds": (
                (datetime.now() - self._overload_since).total_seconds()
                if self._overload_since else 0
            ),
            "max_queue_depth": self.max_queue_depth,
            "shedding_threshold": f"{self.load_shed_threshold * 100:.0f}%",
        }
