"""Sticky execution with worker cache - Phase 5B v10.

Implements sticky execution for workflow affinity:
- StickyWorkerCache: Caches workflow state
- StickyExecutionManager: Manages sticky execution
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class WorkflowCacheEntry:
    """Cached workflow state entry."""
    workflow_id: str
    state: dict
    events: list[dict]
    worker_id: str
    cached_at: int = field(default_factory=lambda: int(time.time()))
    last_accessed: int = field(default_factory=lambda: int(time.time()))
    version: int = 0


class StickyWorkerCache:
    """Worker-side cache for workflow state.
    
    Caches workflow state to avoid full replay on each task.
    """
    
    def __init__(
        self,
        max_cache_size: int = 10000,
        cache_ttl_seconds: int = 60,
    ):
        self._cache: dict[str, WorkflowCacheEntry] = {}
        self._max_size = max_cache_size
        self._ttl = cache_ttl_seconds
        self._access_order: list[str] = []
    
    async def put(
        self,
        workflow_id: str,
        state: dict,
        events: list[dict],
        worker_id: str,
    ) -> None:
        """Cache workflow state.
        
        Args:
            workflow_id: Workflow identifier
            state: Workflow state
            events: Events
            worker_id: Worker caching this
        """
        if len(self._cache) >= self._max_size:
            await self._evict_lru()
        
        entry = WorkflowCacheEntry(
            workflow_id=workflow_id,
            state=state,
            events=events,
            worker_id=worker_id,
        )
        
        self._cache[workflow_id] = entry
        self._update_access_order(workflow_id)
    
    async def get(self, workflow_id: str) -> Optional[WorkflowCacheEntry]:
        """Get cached workflow state.
        
        Args:
            workflow_id: Workflow identifier
            
        Returns:
            Cached entry or None
        """
        entry = self._cache.get(workflow_id)
        
        if entry:
            if self._is_expired(entry):
                await self.invalidate(workflow_id)
                return None
            
            entry.last_accessed = int(time.time())
            self._update_access_order(workflow_id)
        
        return entry
    
    def _is_expired(self, entry: WorkflowCacheEntry) -> bool:
        """Check if cache entry is expired."""
        age = int(time.time()) - entry.cached_at
        return age > self._ttl
    
    def _update_access_order(self, workflow_id: str) -> None:
        """Update LRU access order."""
        if workflow_id in self._access_order:
            self._access_order.remove(workflow_id)
        self._access_order.append(workflow_id)
    
    async def _evict_lru(self) -> None:
        """Evict least recently used entry."""
        if not self._access_order:
            return
        
        lru_id = self._access_order.pop(0)
        if lru_id in self._cache:
            del self._cache[lru_id]
    
    async def invalidate(self, workflow_id: str) -> None:
        """Invalidate a cache entry.
        
        Args:
            workflow_id: Workflow to invalidate
        """
        if workflow_id in self._cache:
            del self._cache[workflow_id]
        if workflow_id in self._access_order:
            self._access_order.remove(workflow_id)
    
    async def invalidate_worker(self, worker_id: str) -> int:
        """Invalidate all entries for a worker.
        
        Args:
            worker_id: Worker to invalidate
            
        Returns:
            Number of entries invalidated
        """
        to_remove = [
            wf_id for wf_id, entry in self._cache.items()
            if entry.worker_id == worker_id
        ]
        
        for wf_id in to_remove:
            await self.invalidate(wf_id)
        
        return len(to_remove)
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "ttl_seconds": self._ttl,
        }


class StickyExecutionManager:
    """Manages sticky execution of workflows.
    
    Routes workflow tasks to the same worker that has
    the cached state, reducing replay overhead.
    """
    
    def __init__(
        self,
        cache: StickyWorkerCache,
        default_sticky_timeout_seconds: int = 60,
    ):
        self._cache = cache
        self._default_timeout = default_sticky_timeout_seconds
        self._sticky_workflows: dict[str, str] = {}
    
    async def start_sticky(
        self,
        workflow_id: str,
        worker_id: str,
        state: dict,
        events: list[dict],
        timeout_seconds: Optional[int] = None,
    ) -> None:
        """Start sticky execution for a workflow.
        
        Args:
            workflow_id: Workflow identifier
            worker_id: Worker to sticky to
            state: Workflow state
            events: Events
            timeout_seconds: Sticky timeout
        """
        await self._cache.put(workflow_id, state, events, worker_id)
        
        timeout = timeout_seconds or self._default_timeout
        expires_at = int(time.time()) + timeout
        
        self._sticky_workflows[workflow_id] = worker_id
    
    async def get_sticky_worker(
        self,
        workflow_id: str,
    ) -> Optional[str]:
        """Get the sticky worker for a workflow.
        
        Args:
            workflow_id: Workflow identifier
            
        Returns:
            Worker ID or None
        """
        return self._sticky_workflows.get(workflow_id)
    
    async def is_sticky(self, workflow_id: str) -> bool:
        """Check if workflow is sticky.
        
        Args:
            workflow_id: Workflow identifier
            
        Returns:
            True if workflow is sticky
        """
        return workflow_id in self._sticky_workflows
    
    async def get_cached_state(
        self,
        workflow_id: str,
    ) -> Optional[WorkflowCacheEntry]:
        """Get cached state for a workflow.
        
        Args:
            workflow_id: Workflow identifier
            
        Returns:
            Cached entry or None
        """
        entry = await self._cache.get(workflow_id)
        
        if entry:
            sticky_worker = self._sticky_workflows.get(workflow_id)
            
            if sticky_worker and entry.worker_id == sticky_worker:
                return entry
        
        return None
    
    async def end_sticky(self, workflow_id: str) -> None:
        """End sticky execution for a workflow.
        
        Args:
            workflow_id: Workflow identifier
        """
        self._sticky_workflows.pop(workflow_id, None)
        await self._cache.invalidate(workflow_id)
    
    async def transfer_sticky(
        self,
        workflow_id: str,
        from_worker: str,
        to_worker: str,
    ) -> bool:
        """Transfer sticky ownership to another worker.
        
        Args:
            workflow_id: Workflow identifier
            from_worker: Current owner
            to_worker: New owner
            
        Returns:
            True if transfer succeeded
        """
        current = self._sticky_workflows.get(workflow_id)
        
        if current != from_worker:
            return False
        
        entry = await self._cache.get(workflow_id)
        
        if not entry:
            return False
        
        await self._cache.put(
            workflow_id,
            entry.state,
            entry.events,
            to_worker,
        )
        
        self._sticky_workflows[workflow_id] = to_worker
        
        return True
    
    def get_sticky_workflows(self, worker_id: str) -> list[str]:
        """Get all workflows sticky to a worker.
        
        Args:
            worker_id: Worker identifier
            
        Returns:
            List of workflow IDs
        """
        return [
            wf_id for wf_id, wid in self._sticky_workflows.items()
            if wid == worker_id
        ]


class WorkflowAffinityRouter:
    """Routes tasks based on workflow affinity.
    
    Prefers routing tasks to workers with cached state.
    """
    
    def __init__(
        self,
        sticky_manager: StickyExecutionManager,
        workers: dict[str, dict],
    ):
        self._sticky = sticky_manager
        self._workers = workers
    
    async def get_preferred_worker(
        self,
        workflow_id: str,
    ) -> Optional[str]:
        """Get the preferred worker for a workflow.
        
        Args:
            workflow_id: Workflow identifier
            
        Returns:
            Preferred worker ID or None
        """
        return await self._sticky.get_sticky_worker(workflow_id)
    
    async def route_task(
        self,
        workflow_id: str,
        available_workers: list[str],
    ) -> Optional[str]:
        """Route a task to an appropriate worker.
        
        Prefers:
        1. Sticky worker (with cached state)
        2. Any available worker
        
        Args:
            workflow_id: Workflow identifier
            available_workers: List of available worker IDs
            
        Returns:
            Selected worker ID or None
        """
        sticky_worker = await self.get_preferred_worker(workflow_id)
        
        if sticky_worker and sticky_worker in available_workers:
            return sticky_worker
        
        cached = await self._sticky.get_cached_state(workflow_id)
        if cached and cached.worker_id in available_workers:
            return cached.worker_id
        
        return available_workers[0] if available_workers else None
