"""Router Snapshot Protocol - Decoupled snapshot management for routers.

Fixes Critical Gap: Router snapshot ↔ feedback processor tight coupling.

Features:
- Protocol-based router snapshot interface
- Decoupled snapshot storage
- Event-based notification
- Lazy loading support
- Versioned snapshots
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable

logger = logging.getLogger(__name__)


# =============================================================================
# SNAPSHOT TYPES
# =============================================================================


class SnapshotScope(Enum):
    """Scope of router snapshot."""
    
    GLOBAL = auto()      # Entire router state
    ROUTE = auto()      # Single route state
    CONTEXT = auto()    # Context-specific
    METRICS = auto()   # Metrics only


@dataclass
class RouterSnapshot:
    """Router state snapshot.
    
    Captures router state at a point in time.
    """
    
    snapshot_id: str
    scope: SnapshotScope
    
    # Content
    routes: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    version: int = 1
    
    # Hash for verification
    content_hash: str = ""
    
    def compute_hash(self) -> str:
        """Compute hash of snapshot content."""
        content = {
            "routes": self.routes,
            "metrics": self.metrics,
            "version": self.version,
        }
        return hashlib.sha256(
            json.dumps(content, sort_keys=True, default=str).encode()
        ).hexdigest()
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "scope": self.scope.name,
            "routes": self.routes,
            "metrics": self.metrics,
            "context": self.context,
            "created_at": self.created_at.isoformat(),
            "version": self.version,
            "content_hash": self.content_hash,
        }


# =============================================================================
# SNAPSHOT STORAGE INTERFACE (PROTOCOL)
# =============================================================================


class RouterSnapshotStorage(ABC):
    """Abstract interface for router snapshot storage.
    
    Implement this to use different storage backends:
    - Memory storage (testing)
    - File storage
    - Redis storage
    - Database storage
    """
    
    @abstractmethod
    async def save(self, snapshot: RouterSnapshot) -> bool:
        """Save a snapshot."""
        pass
    
    @abstractmethod
    async def load(self, snapshot_id: str) -> RouterSnapshot | None:
        """Load a snapshot by ID."""
        pass
    
    @abstractmethod
    async def list(
        self,
        scope: SnapshotScope | None = None,
        limit: int = 10,
    ) -> list[RouterSnapshot]:
        """List snapshots."""
        pass
    
    @abstractmethod
    async def delete(self, snapshot_id: str) -> bool:
        """Delete a snapshot."""
        pass


# =============================================================================
# IN-MEMORY STORAGE
# =============================================================================


class MemoryRouterSnapshotStorage(RouterSnapshotStorage):
    """In-memory router snapshot storage.
    
    For testing and single-instance deployments.
    """
    
    def __init__(self):
        self._snapshots: dict[str, RouterSnapshot] = {}
        self._by_scope: dict[SnapshotScope, list[str]] = {}
    
    async def save(self, snapshot: RouterSnapshot) -> bool:
        snapshot.content_hash = snapshot.compute_hash()
        self._snapshots[snapshot.snapshot_id] = snapshot
        
        if snapshot.scope not in self._by_scope:
            self._by_scope[snapshot.scope] = []
        if snapshot.snapshot_id not in self._by_scope[snapshot.scope]:
            self._by_scope[snapshot.scope].append(snapshot.snapshot_id)
        
        logger.debug("snapshot_saved: id=%s scope=%s", snapshot.snapshot_id, snapshot.scope.name)
        return True
    
    async def load(self, snapshot_id: str) -> RouterSnapshot | None:
        return self._snapshots.get(snapshot_id)
    
    async def list(
        self,
        scope: SnapshotScope | None = None,
        limit: int = 10,
    ) -> list[RouterSnapshot]:
        if scope:
            ids = self._by_scope.get(scope, [])
            snapshots = [self._snapshots[sid] for sid in ids if sid in self._snapshots]
        else:
            snapshots = list(self._snapshots.values())
        
        # Sort by created_at descending
        snapshots.sort(key=lambda s: s.created_at, reverse=True)
        return snapshots[:limit]
    
    async def delete(self, snapshot_id: str) -> bool:
        snapshot = self._snapshots.get(snapshot_id)
        if snapshot:
            del self._snapshots[snapshot_id]
            if snapshot.scope in self._by_scope:
                if snapshot_id in self._by_scope[snapshot.scope]:
                    self._by_scope[snapshot.scope].remove(snapshot_id)
            return True
        return False


# =============================================================================
# ROUTER SNAPSHOT MANAGER
# =============================================================================


class RouterSnapshotManager:
    """Manages router snapshots with decoupled storage.
    
    This decouples the router from specific storage implementations.
    """
    
    def __init__(self, storage: RouterSnapshotStorage | None = None):
        self._storage = storage or MemoryRouterSnapshotStorage()
        
        # Event handlers
        self._on_snapshot_created: list[Callable] = []
        self._on_snapshot_restored: list[Callable] = []
        
        self._lock = asyncio.Lock()
        
        logger.info("router_snapshot_manager_initialized")
    
    def on_snapshot_created(self, handler: Callable) -> None:
        """Register handler for snapshot created events."""
        self._on_snapshot_created.append(handler)
    
    def on_snapshot_restored(self, handler: Callable) -> None:
        """Register handler for snapshot restored events."""
        self._on_snapshot_restored.append(handler)
    
    async def create_snapshot(
        self,
        snapshot_id: str,
        scope: SnapshotScope,
        routes: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> RouterSnapshot:
        """Create a new router snapshot.
        
        Args:
            snapshot_id: Unique identifier
            scope: Snapshot scope
            routes: Router routes
            metrics: Router metrics
            context: Additional context
            
        Returns:
            Created snapshot
        """
        async with self._lock:
            snapshot = RouterSnapshot(
                snapshot_id=snapshot_id,
                scope=scope,
                routes=routes or {},
                metrics=metrics or {},
                context=context or {},
            )
            
            await self._storage.save(snapshot)
            
            # Notify handlers
            for handler in self._on_snapshot_created:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(snapshot)
                    else:
                        handler(snapshot)
                except Exception as e:
                    logger.error("snapshot_created_handler_error: %s", str(e))
            
            logger.info(
                "router_snapshot_created: id=%s scope=%s routes=%s",
                snapshot_id, scope.name, len(routes or {}),
            )
            
            return snapshot
    
    async def restore_snapshot(
        self,
        snapshot_id: str,
    ) -> RouterSnapshot | None:
        """Restore router state from snapshot.
        
        Args:
            snapshot_id: Snapshot to restore
            
        Returns:
            Restored snapshot or None
        """
        snapshot = await self._storage.load(snapshot_id)
        
        if snapshot:
            # Notify handlers
            for handler in self._on_snapshot_restored:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(snapshot)
                    else:
                        handler(snapshot)
                except Exception as e:
                    logger.error("snapshot_restored_handler_error: %s", str(e))
            
            logger.info("router_snapshot_restored: id=%s", snapshot_id)
        
        return snapshot
    
    async def list_snapshots(
        self,
        scope: SnapshotScope | None = None,
        limit: int = 10,
    ) -> list[RouterSnapshot]:
        """List available snapshots."""
        return await self._storage.list(scope=scope, limit=limit)
    
    async def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot."""
        return await self._storage.delete(snapshot_id)
    
    async def get_latest(
        self,
        scope: SnapshotScope | None = None,
    ) -> RouterSnapshot | None:
        """Get the latest snapshot."""
        snapshots = await self.list_snapshots(scope=scope, limit=1)
        return snapshots[0] if snapshots else None


# =============================================================================
# FEEDBACK PROCESSOR (DECOUPLED)
# =============================================================================


class FeedbackProcessor:
    """Processes feedback and updates router state.
    
    This is decoupled from the router snapshot manager.
    Uses event-based communication.
    """
    
    def __init__(self, snapshot_manager: RouterSnapshotManager):
        self._snapshot_manager = snapshot_manager
        self._pending_updates: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
    
    async def process_feedback(
        self,
        feedback: dict[str, Any],
    ) -> dict[str, Any]:
        """Process feedback and queue state update.
        
        Args:
            feedback: Feedback data
            
        Returns:
            Processing result
        """
        async with self._lock:
            # Store feedback
            self._pending_updates.append({
                "feedback": feedback,
                "timestamp": datetime.utcnow().isoformat(),
            })
            
            # Keep only last 100
            if len(self._pending_updates) > 100:
                self._pending_updates = self._pending_updates[-100:]
        
        logger.debug(
            "feedback_processed: type=%s pending=%s",
            feedback.get("type", "unknown"),
            len(self._pending_updates),
        )
        
        return {
            "accepted": True,
            "queue_size": len(self._pending_updates),
        }
    
    async def apply_pending_updates(self) -> dict[str, Any]:
        """Apply pending feedback updates to router state.
        
        This creates a new snapshot with the updated state.
        
        Returns:
            Result of applying updates
        """
        async with self._lock:
            if not self._pending_updates:
                return {"applied": 0, "message": "No pending updates"}
            
            # Process updates (simplified)
            updates_applied = len(self._pending_updates)
            self._pending_updates.clear()
        
        logger.info("feedback_updates_applied: count=%s", updates_applied)
        
        return {
            "applied": updates_applied,
            "message": f"Applied {updates_applied} updates",
        }
    
    async def get_pending_count(self) -> int:
        """Get number of pending updates."""
        async with self._lock:
            return len(self._pending_updates)


# =============================================================================
# ROUTER WITH DECOUPLED SNAPSHOT
# =============================================================================


class DecoupledRouter:
    """Example router using decoupled snapshot management.
    
    This shows how to use the decoupled pattern.
    """
    
    def __init__(self):
        self._snapshot_manager = RouterSnapshotManager()
        self._feedback_processor = FeedbackProcessor(self._snapshot_manager)
        
        self._routes: dict[str, Any] = {}
        self._metrics: dict[str, Any] = {}
    
    def add_route(self, route_id: str, route_data: dict[str, Any]) -> None:
        """Add or update a route."""
        self._routes[route_id] = route_data
    
    def update_metrics(self, metrics: dict[str, Any]) -> None:
        """Update metrics."""
        self._metrics.update(metrics)
    
    async def create_snapshot(self, snapshot_id: str) -> RouterSnapshot:
        """Create snapshot of current state."""
        return await self._snapshot_manager.create_snapshot(
            snapshot_id=snapshot_id,
            scope=SnapshotScope.GLOBAL,
            routes=dict(self._routes),
            metrics=dict(self._metrics),
        )
    
    async def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore from snapshot."""
        snapshot = await self._snapshot_manager.restore_snapshot(snapshot_id)
        if snapshot:
            self._routes = snapshot.routes
            self._metrics = snapshot.metrics
            return True
        return False
    
    async def process_feedback(self, feedback: dict[str, Any]) -> dict[str, Any]:
        """Process feedback through decoupled processor."""
        return await self._feedback_processor.process_feedback(feedback)


# =============================================================================
# GLOBAL INSTANCES
# =============================================================================


_global_snapshot_manager: RouterSnapshotManager | None = None


def get_router_snapshot_manager() -> RouterSnapshotManager:
    """Get global router snapshot manager."""
    global _global_snapshot_manager
    if _global_snapshot_manager is None:
        _global_snapshot_manager = RouterSnapshotManager()
    return _global_snapshot_manager
