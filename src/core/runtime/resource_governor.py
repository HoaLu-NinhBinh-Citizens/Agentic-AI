"""
Runtime Resource Governor - Resource budget management

Manages shared resources like:
- LLM calls (max concurrent)
- Embedding requests (batching)
- GPU memory
- Token budgets

Usage:
    governor = ResourceGovernor()

    # Acquire resource
    async with governor.acquire("llm"):
        result = await call_llm()

    # Check availability
    if await governor.can_acquire("gpu"):
        await gpu_task()
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ResourceBudget:
    """Budget for a single resource."""

    name: str
    max_concurrent: int
    current: int = 0
    queue: list[asyncio.Event] = field(default_factory=list)
    waiters: int = 0


@dataclass
class ResourceAcquired:
    """Token returned when resource is acquired."""

    resource: str
    governor: "ResourceGovernor"

    async def __aenter__(self) -> None:
        pass

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.governor.release(self.resource)


class ResourceGovernor:
    """
    Manages resource budgets.

    Features:
    - Max concurrent slots per resource
    - Fair waiting queue
    - Async context manager support
    - Statistics

    Usage:
        governor = ResourceGovernor()

        # Simple acquire
        await governor.acquire("llm")
        try:
            result = await call_llm()
        finally:
            governor.release("llm")

        # Context manager (auto-release)
        async with governor.acquire("llm"):
            result = await call_llm()
    """

    def __init__(self):
        """Initialize resource governor."""
        self._budgets: dict[str, ResourceBudget] = {}
        self._lock = asyncio.Lock()

    def configure(
        self,
        name: str,
        max_concurrent: int,
    ) -> None:
        """
        Configure budget for a resource.

        Args:
            name: Resource name (e.g., "llm", "gpu", "embeddings")
            max_concurrent: Maximum concurrent uses
        """
        if name not in self._budgets:
            self._budgets[name] = ResourceBudget(name=name, max_concurrent=max_concurrent)
        else:
            self._budgets[name].max_concurrent = max_concurrent

    def get_budget(self, name: str) -> ResourceBudget | None:
        """Get budget for resource."""
        return self._budgets.get(name)

    async def acquire(
        self,
        resource: str,
        timeout: float | None = None,
    ) -> ResourceAcquired:
        """
        Acquire a resource slot.

        Args:
            resource: Resource name
            timeout: Max seconds to wait (None = wait forever)

        Returns:
            ResourceAcquired token

        Raises:
            TimeoutError: If timeout exceeded
        """
        budget = self._budgets.get(resource)
        if not budget:
            # Auto-configure if not exists
            budget = ResourceBudget(name=resource, max_concurrent=1)
            self._budgets[resource] = budget

        async with self._lock:
            if budget.current < budget.max_concurrent:
                budget.current += 1
                return ResourceAcquired(resource=resource, governor=self)

            # Need to wait
            event = asyncio.Event()
            budget.queue.append(event)
            budget.waiters += 1

        try:
            if timeout:
                await asyncio.wait_for(event.wait(), timeout=timeout)
            else:
                await event.wait()

            async with self._lock:
                budget.current += 1
                if budget.queue and budget.queue[0] is event:
                    budget.queue.pop(0)
                budget.waiters -= 1

            return ResourceAcquired(resource=resource, governor=self)

        except asyncio.TimeoutError:
            async with self._lock:
                if event in budget.queue:
                    budget.queue.remove(event)
                budget.waiters -= 1
            raise TimeoutError(f"Timeout acquiring resource: {resource}")

    async def release(self, resource: str) -> None:
        """
        Release a resource slot.

        Args:
            resource: Resource name
        """
        async with self._lock:
            budget = self._budgets.get(resource)
            if not budget:
                return

            budget.current = max(0, budget.current - 1)

            # Notify next waiter
            if budget.queue:
                budget.queue[0].set()

        logger.debug(
            f"Released {resource} (current={budget.current}/{budget.max_concurrent})"
        )

    async def can_acquire(self, resource: str) -> bool:
        """
        Check if resource is immediately available.

        Args:
            resource: Resource name

        Returns:
            True if slot available
        """
        budget = self._budgets.get(resource)
        if not budget:
            return True  # Unknown resource is available

        return budget.current < budget.max_concurrent

    def get_available(self, resource: str) -> int:
        """
        Get number of available slots.

        Args:
            resource: Resource name

        Returns:
            Number of free slots (0 if unknown)
        """
        budget = self._budgets.get(resource)
        if not budget:
            return 0

        return max(0, budget.max_concurrent - budget.current)

    def get_stats(self) -> dict[str, dict]:
        """
        Get statistics for all resources.

        Returns:
            Dict of resource stats
        """
        return {
            name: {
                "current": budget.current,
                "max": budget.max_concurrent,
                "available": budget.max_concurrent - budget.current,
                "utilization": budget.current / budget.max_concurrent
                if budget.max_concurrent > 0
                else 0,
                "waiting": len(budget.queue),
            }
            for name, budget in self._budgets.items()
        }

    async def wait_until_available(
        self,
        resource: str,
        check_interval: float = 0.1,
    ) -> None:
        """
        Wait until resource is available.

        Args:
            resource: Resource name
            check_interval: How often to check
        """
        while not await self.can_acquire(resource):
            await asyncio.sleep(check_interval)


# Pre-configured budgets
DEFAULT_BUDGETS = {
    "llm": 2,  # Max concurrent LLM calls
    "embeddings": 4,  # Max concurrent embedding requests
    "gpu": 1,  # GPU is exclusive
    "token_budget": 100000,  # Tokens per minute (approximate)
}


def create_default_governor() -> ResourceGovernor:
    """Create governor with default budgets."""
    governor = ResourceGovernor()
    for name, limit in DEFAULT_BUDGETS.items():
        governor.configure(name, limit)
    return governor


# Global governor
_governor: ResourceGovernor | None = None


def get_governor() -> ResourceGovernor:
    """Get or create default resource governor."""
    global _governor
    if _governor is None:
        _governor = create_default_governor()
    return _governor
