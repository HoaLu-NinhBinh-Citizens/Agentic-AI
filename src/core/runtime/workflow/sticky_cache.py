"""Sticky Worker Cache - Phase 5A (v6).

Workflow affinity cache for performance optimization.
Sticky execution runs workflow on the same worker that handled it before.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class StickyBinding:
    """Binding between workflow and worker for sticky execution."""
    workflow_id: str
    worker_id: str
    
    # Lease
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0
    last_heartbeat_at: float = field(default_factory=time.time)
    
    # State
    is_stale: bool = False
    cache_hits: int = 0


class StickyWorkerCache:
    """Cache for sticky workflow execution.
    
    Sticky execution improves performance by running workflow
    on the same worker that handled it before. This allows
    the worker to use cached state and avoid replay overhead.
    
    Features:
    - Workflow affinity (same worker for same workflow)
    - Configurable timeout
    - LRU eviction when cache is full
    - Worker death handling with automatic reassignment
    - Ownership transfer between workers
    """
    
    def __init__(
        self,
        sticky_enabled: bool = True,
        sticky_timeout_seconds: int = 10,
        max_cache_size: int = 10000,
        eviction_policy: str = "lru",
    ):
        self.sticky_enabled = sticky_enabled
        self.sticky_timeout_seconds = sticky_timeout_seconds
        self.max_cache_size = max_cache_size
        self.eviction_policy = eviction_policy
        
        # In-memory cache
        self._bindings: dict[str, StickyBinding] = {}
        self._access_order: list[str] = []  # For LRU
        self._lock = asyncio.Lock()
        
        # Metrics
        self._total_hits: int = 0
        self._total_misses: int = 0
    
    async def get_binding(
        self,
        workflow_id: str,
    ) -> Optional[StickyBinding]:
        """Get sticky binding for workflow.
        
        Args:
            workflow_id: Workflow ID to look up.
            
        Returns:
            StickyBinding if found and valid, None otherwise.
        """
        if not self.sticky_enabled:
            return None
        
        async with self._lock:
            binding = self._bindings.get(workflow_id)
            
            if binding is None:
                self._total_misses += 1
                return None
            
            # Check if binding is valid
            if binding.is_stale:
                self._total_misses += 1
                return None
            
            if binding.expires_at <= time.time():
                # Binding expired
                del self._bindings[workflow_id]
                self._access_order.remove(workflow_id)
                self._total_misses += 1
                return None
            
            # Valid binding - update metrics and LRU
            binding.cache_hits += 1
            self._total_hits += 1
            self._update_lru(workflow_id)
            
            return binding
    
    async def set_binding(
        self,
        workflow_id: str,
        worker_id: str,
    ) -> StickyBinding:
        """Create sticky binding for workflow to worker.
        
        Args:
            workflow_id: Workflow ID.
            worker_id: Worker ID to bind to.
            
        Returns:
            Created StickyBinding.
        """
        if not self.sticky_enabled:
            return None
        
        async with self._lock:
            binding = StickyBinding(
                workflow_id=workflow_id,
                worker_id=worker_id,
                expires_at=time.time() + self.sticky_timeout_seconds,
            )
            self._bindings[workflow_id] = binding
            self._update_lru(workflow_id)
            self._evict_if_needed()
            
            logger.debug(
                f"Created sticky binding: workflow={workflow_id[:8]}... "
                f"worker={worker_id[:8]}... "
                f"(timeout={self.sticky_timeout_seconds}s)"
            )
            
            return binding
    
    async def refresh_binding(
        self,
        workflow_id: str,
    ) -> bool:
        """Refresh binding timeout (worker heartbeat).
        
        Args:
            workflow_id: Workflow ID.
            
        Returns:
            True if binding was refreshed, False if not found.
        """
        if not self.sticky_enabled:
            return False
        
        async with self._lock:
            binding = self._bindings.get(workflow_id)
            if binding and not binding.is_stale:
                binding.expires_at = time.time() + self.sticky_timeout_seconds
                binding.last_heartbeat_at = time.time()
                return True
            return False
    
    async def invalidate(
        self,
        workflow_id: str,
    ) -> bool:
        """Invalidate cache entry for workflow.
        
        Args:
            workflow_id: Workflow ID to invalidate.
            
        Returns:
            True if entry was invalidated, False if not found.
        """
        async with self._lock:
            if workflow_id in self._bindings:
                del self._bindings[workflow_id]
                if workflow_id in self._access_order:
                    self._access_order.remove(workflow_id)
                logger.debug(f"Invalidated sticky binding: workflow={workflow_id[:8]}...")
                return True
            return False
    
    async def invalidate_all(
        self,
        worker_id: str,
    ) -> list[str]:
        """Invalidate all bindings for worker (e.g., worker death).
        
        Args:
            worker_id: Worker ID to invalidate.
            
        Returns:
            List of workflow IDs that were invalidated.
        """
        invalidated = []
        
        async with self._lock:
            for workflow_id, binding in list(self._bindings.items()):
                if binding.worker_id == worker_id:
                    binding.is_stale = True
                    invalidated.append(workflow_id)
        
        if invalidated:
            logger.warning(
                f"Worker {worker_id[:8]}... died, invalidated "
                f"{len(invalidated)} sticky bindings"
            )
        
        return invalidated
    
    async def handle_worker_death(
        self,
        worker_id: str,
    ) -> list[str]:
        """Handle worker death: invalidate bindings, return affected workflows.
        
        This should be called when a worker is detected as dead
        (e.g., via heartbeat timeout or explicit shutdown).
        
        Args:
            worker_id: Worker ID that died.
            
        Returns:
            List of workflow IDs that need reassignment.
        """
        invalidated = await self.invalidate_all(worker_id)
        
        # Return workflow IDs for re-scheduling
        return list(self._bindings.keys()) if not invalidated else invalidated
    
    async def transfer_ownership(
        self,
        workflow_id: str,
        from_worker: str,
        to_worker: str,
    ) -> bool:
        """Transfer workflow ownership to new worker.
        
        Used for load balancing or when a worker needs to
        release some workflows.
        
        Args:
            workflow_id: Workflow ID to transfer.
            from_worker: Current worker ID.
            to_worker: New worker ID.
            
        Returns:
            True if transfer succeeded, False if not found or worker mismatch.
        """
        async with self._lock:
            binding = self._bindings.get(workflow_id)
            if binding is None:
                return False
            
            if binding.worker_id != from_worker:
                logger.warning(
                    f"Cannot transfer workflow {workflow_id[:8]}...: "
                    f"current worker {binding.worker_id[:8]}... != "
                    f"expected {from_worker[:8]}..."
                )
                return False
            
            binding.worker_id = to_worker
            binding.last_heartbeat_at = time.time()
            
            logger.info(
                f"Transferred workflow {workflow_id[:8]}... "
                f"from {from_worker[:8]}... to {to_worker[:8]}..."
            )
            
            return True
    
    async def get_worker_workflows(
        self,
        worker_id: str,
    ) -> list[str]:
        """Get all workflow IDs bound to a worker.
        
        Args:
            worker_id: Worker ID.
            
        Returns:
            List of workflow IDs.
        """
        async with self._lock:
            return [
                wf_id for wf_id, binding in self._bindings.items()
                if binding.worker_id == worker_id and not binding.is_stale
            ]
    
    async def get_stats(self) -> dict:
        """Get cache statistics.
        
        Returns:
            Dict with cache stats.
        """
        async with self._lock:
            total = self._total_hits + self._total_misses
            hit_rate = self._total_hits / total if total > 0 else 0.0
            
            return {
                "sticky_enabled": self.sticky_enabled,
                "cache_size": len(self._bindings),
                "max_cache_size": self.max_cache_size,
                "total_hits": self._total_hits,
                "total_misses": self._total_misses,
                "hit_rate": hit_rate,
                "eviction_policy": self.eviction_policy,
            }
    
    def _update_lru(self, workflow_id: str) -> None:
        """Update LRU order."""
        if workflow_id in self._access_order:
            self._access_order.remove(workflow_id)
        self._access_order.append(workflow_id)
    
    def _evict_if_needed(self) -> None:
        """Evict oldest entries if cache is full."""
        while len(self._bindings) > self.max_cache_size:
            if self._access_order:
                oldest = self._access_order.pop(0)
                if oldest in self._bindings:
                    del self._bindings[oldest]
                    logger.debug(f"Evicted workflow {oldest[:8]}... from sticky cache")


class StickyCacheInterface:
    """Interface for external cache backend (Redis, etc.).
    
    Implement this for distributed sticky cache.
    """
    
    async def get_binding(self, workflow_id: str) -> Optional[dict]:
        """Get binding from external store."""
        raise NotImplementedError()
    
    async def set_binding(
        self,
        workflow_id: str,
        worker_id: str,
        ttl_seconds: int,
    ) -> bool:
        """Set binding in external store."""
        raise NotImplementedError()
    
    async def delete_binding(self, workflow_id: str) -> bool:
        """Delete binding from external store."""
        raise NotImplementedError()
    
    async def get_worker_bindings(self, worker_id: str) -> list[str]:
        """Get all bindings for a worker."""
        raise NotImplementedError()
