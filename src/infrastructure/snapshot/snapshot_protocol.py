"""Snapshot Protocol - Decoupled interface for snapshot management.

Fixes Critical Gap: Flash Transaction ↔ Snapshot Manager tight coupling.

Features:
- Protocol/interface definition for snapshots
- Abstract snapshot operations
- Decoupled from concrete implementations
- Snapshot registry
- Factory pattern for snapshot creation
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
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)


# =============================================================================
# SNAPSHOT TYPES
# =============================================================================


class SnapshotType(Enum):
    """Types of snapshots."""
    
    FULL = auto()           # Complete state capture
    INCREMENTAL = auto()     # Delta from previous
    FIRMWARE = auto()        # Firmware-specific snapshot
    MEMORY = auto()          # Memory state
    REGISTRY = auto()        # Registry/configuration state
    WORKFLOW = auto()        # Workflow execution state


class SnapshotStatus(Enum):
    """Snapshot status."""
    
    CREATING = "creating"
    COMPLETE = "complete"
    FAILED = "failed"
    APPLIED = "applied"
    EXPIRED = "expired"


# =============================================================================
# SNAPSHOT INTERFACE (PROTOCOL)
# =============================================================================


class SnapshotManager(Protocol):
    """Protocol defining snapshot manager operations.
    
    CRITICAL: This decouples FlashTransaction from concrete implementations.
    
    All snapshot managers must implement this protocol.
    """
    
    async def create_snapshot(
        self,
        snapshot_type: SnapshotType,
        target_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create a snapshot. Returns snapshot ID."""
        ...
    
    async def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore from a snapshot."""
        ...
    
    async def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot."""
        ...
    
    async def list_snapshots(
        self,
        target_id: str | None = None,
        snapshot_type: SnapshotType | None = None,
    ) -> list[dict[str, Any]]:
        """List available snapshots."""
        ...
    
    async def get_snapshot_info(self, snapshot_id: str) -> dict[str, Any] | None:
        """Get snapshot metadata."""
        ...


# =============================================================================
# SNAPSHOT ENTRY
# =============================================================================


@dataclass
class SnapshotEntry:
    """Entry representing a snapshot.
    
    This is the standard format for all snapshots.
    """
    
    # Identity
    snapshot_id: str
    snapshot_type: SnapshotType
    
    # Target
    target_id: str = ""
    target_name: str = ""
    
    # Content
    content_hash: str = ""
    content_size: int = 0
    
    # Status
    status: SnapshotStatus = SnapshotStatus.CREATING
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    
    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)
    
    # Parent snapshot (for incremental)
    parent_snapshot_id: str | None = None
    
    # Verification
    checksum: str = ""
    signature: str = ""
    
    def compute_content_hash(self) -> str:
        """Compute hash of snapshot content."""
        content = {
            "snapshot_id": self.snapshot_id,
            "snapshot_type": self.snapshot_type.name,
            "target_id": self.target_id,
            "created_at": self.created_at.isoformat(),
        }
        return hashlib.sha256(
            json.dumps(content, sort_keys=True).encode()
        ).hexdigest()
    
    def is_valid(self) -> bool:
        """Check if snapshot is valid and usable."""
        return self.status == SnapshotStatus.COMPLETE
    
    def is_expired(self) -> bool:
        """Check if snapshot has expired."""
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return True
        return False
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_type": self.snapshot_type.name,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "content_hash": self.content_hash,
            "content_size": self.content_size,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": self.metadata,
            "parent_snapshot_id": self.parent_snapshot_id,
            "checksum": self.checksum,
        }


# =============================================================================
# SNAPSHOT REGISTRY
# =============================================================================


class SnapshotRegistry:
    """Registry for managing snapshots across the system.
    
    CRITICAL: This provides loose coupling between components.
    Components request snapshots through this registry,
    which dispatches to appropriate managers.
    """
    
    def __init__(self):
        self._managers: dict[SnapshotType, SnapshotManager] = {}
        self._snapshots: dict[str, SnapshotEntry] = {}
        self._lock = asyncio.Lock()
    
    def register_manager(
        self,
        snapshot_type: SnapshotType,
        manager: SnapshotManager,
    ) -> None:
        """Register a snapshot manager for a type."""
        self._managers[snapshot_type] = manager
        logger.info("snapshot_manager_registered: type=%s", snapshot_type.name)
    
    def get_manager(self, snapshot_type: SnapshotType) -> SnapshotManager | None:
        """Get manager for snapshot type."""
        return self._managers.get(snapshot_type)
    
    async def create_snapshot(
        self,
        snapshot_type: SnapshotType,
        target_id: str,
        target_name: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Create a snapshot using appropriate manager.
        
        Args:
            snapshot_type: Type of snapshot to create
            target_id: Target identifier
            target_name: Human-readable target name
            metadata: Additional metadata
            
        Returns:
            Snapshot ID or None if creation failed
        """
        import uuid
        
        async with self._lock:
            manager = self._managers.get(snapshot_type)
            if not manager:
                logger.error("no_manager_for_type: type=%s", snapshot_type.name)
                return None
            
            # Create snapshot entry
            snapshot_id = str(uuid.uuid4())
            entry = SnapshotEntry(
                snapshot_id=snapshot_id,
                snapshot_type=snapshot_type,
                target_id=target_id,
                target_name=target_name,
                metadata=metadata or {},
                status=SnapshotStatus.CREATING,
            )
            
            try:
                # Delegate to manager
                result_id = await manager.create_snapshot(
                    snapshot_type,
                    target_id,
                    metadata,
                )
                
                # Update entry
                entry.status = SnapshotStatus.COMPLETE
                entry.completed_at = datetime.utcnow()
                entry.content_hash = entry.compute_content_hash()
                
                self._snapshots[snapshot_id] = entry
                
                logger.info(
                    "snapshot_created: id=%s type=%s target=%s",
                    snapshot_id, snapshot_type.name, target_id,
                )
                
                return snapshot_id
                
            except Exception as e:
                entry.status = SnapshotStatus.FAILED
                logger.error("snapshot_creation_failed: type=%s error=%s", snapshot_type.name, str(e))
                return None
    
    async def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore from a snapshot."""
        async with self._lock:
            entry = self._snapshots.get(snapshot_id)
            if not entry:
                logger.error("snapshot_not_found: id=%s", snapshot_id)
                return False
            
            if not entry.is_valid():
                logger.error("snapshot_invalid: id=%s status=%s", snapshot_id, entry.status)
                return False
            
            manager = self._managers.get(entry.snapshot_type)
            if not manager:
                logger.error("no_manager_for_snapshot: id=%s", snapshot_id)
                return False
            
            try:
                result = await manager.restore_snapshot(snapshot_id)
                if result:
                    entry.status = SnapshotStatus.APPLIED
                return result
            except Exception as e:
                logger.error("snapshot_restore_failed: id=%s error=%s", snapshot_id, str(e))
                return False
    
    async def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot."""
        async with self._lock:
            entry = self._snapshots.get(snapshot_id)
            if not entry:
                return False
            
            manager = self._managers.get(entry.snapshot_type)
            if manager:
                try:
                    result = await manager.delete_snapshot(snapshot_id)
                    if result:
                        del self._snapshots[snapshot_id]
                    return result
                except Exception as e:
                    logger.error("snapshot_delete_failed: id=%s error=%s", snapshot_id, str(e))
                    return False
            
            del self._snapshots[snapshot_id]
            return True
    
    async def list_snapshots(
        self,
        target_id: str | None = None,
        snapshot_type: SnapshotType | None = None,
    ) -> list[SnapshotEntry]:
        """List snapshots, optionally filtered."""
        results = []
        
        for entry in self._snapshots.values():
            if target_id and entry.target_id != target_id:
                continue
            if snapshot_type and entry.snapshot_type != snapshot_type:
                continue
            if entry.is_expired():
                continue
            results.append(entry)
        
        return sorted(results, key=lambda e: e.created_at, reverse=True)
    
    async def get_snapshot_info(self, snapshot_id: str) -> SnapshotEntry | None:
        """Get snapshot info."""
        return self._snapshots.get(snapshot_id)
    
    async def cleanup_expired(self) -> int:
        """Remove expired snapshots."""
        async with self._lock:
            expired_ids = [
                sid for sid, entry in self._snapshots.items()
                if entry.is_expired()
            ]
            
            for sid in expired_ids:
                await self.delete_snapshot(sid)
            
            logger.info("expired_snapshots_cleaned: count=%s", len(expired_ids))
            return len(expired_ids)


# =============================================================================
# SNAPSHOT FACTORY
# =============================================================================


class SnapshotFactory:
    """Factory for creating snapshot managers.
    
    Provides dependency injection for snapshot managers.
    """
    
    _registry: SnapshotRegistry | None = None
    
    @classmethod
    def get_registry(cls) -> SnapshotRegistry:
        """Get global snapshot registry."""
        if cls._registry is None:
            cls._registry = SnapshotRegistry()
        return cls._registry
    
    @classmethod
    def create_manager(
        cls,
        manager_type: type,
        **kwargs,
    ) -> SnapshotManager:
        """Create a snapshot manager instance.
        
        Usage:
            manager = SnapshotFactory.create_manager(FirmwareSnapshotManager)
            registry.register_manager(SnapshotType.FIRMWARE, manager)
        """
        return manager_type(**kwargs)


# =============================================================================
# FLASH TRANSACTION INTEGRATION
# =============================================================================


class FlashTransactionSnapshotMixin:
    """Mixin for FlashTransaction to use snapshot protocol.
    
    This decouples FlashTransaction from concrete snapshot implementations.
    """
    
    def __init__(self):
        self._snapshot_registry = SnapshotFactory.get_registry()
    
    async def _create_pre_flash_snapshot(
        self,
        target_id: str,
        target_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Create pre-flash snapshot using registry.
        
        Returns snapshot ID for rollback.
        """
        return await self._snapshot_registry.create_snapshot(
            snapshot_type=SnapshotType.FIRMWARE,
            target_id=target_id,
            target_name=target_name,
            metadata={
                **(metadata or {}),
                "purpose": "pre_flash_rollback",
            },
        )
    
    async def _restore_from_snapshot(self, snapshot_id: str) -> bool:
        """Restore from snapshot using registry."""
        return await self._snapshot_registry.restore_snapshot(snapshot_id)
    
    async def _get_snapshot_info(self, snapshot_id: str) -> SnapshotEntry | None:
        """Get snapshot info."""
        return await self._snapshot_registry.get_snapshot_info(snapshot_id)
    
    async def _list_snapshots(
        self,
        target_id: str | None = None,
    ) -> list[SnapshotEntry]:
        """List available snapshots."""
        return await self._snapshot_registry.list_snapshots(
            target_id=target_id,
            snapshot_type=SnapshotType.FIRMWARE,
        )


# =============================================================================
# GLOBAL REGISTRY
# =============================================================================


_global_registry: SnapshotRegistry | None = None


def get_snapshot_registry() -> SnapshotRegistry:
    """Get global snapshot registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = SnapshotRegistry()
    return _global_registry
