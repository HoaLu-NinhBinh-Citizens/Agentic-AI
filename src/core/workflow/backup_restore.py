"""Workflow Backup/Restore - State persistence for resumable workflows.

Provides:
- Workflow state snapshots
- Checkpoint management
- Crash recovery
- State rollback
- Version history

Usage:
    manager = WorkflowBackupManager(store_path="/var/lib/aisupport/workflows")
    await manager.save_checkpoint(workflow_id, state)
    restored = await manager.restore_checkpoint(workflow_id)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WorkflowCheckpoint:
    """Workflow checkpoint data."""
    workflow_id: str
    version: int
    state: dict[str, Any]
    created_at: str
    checksum: str
    parent_version: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "version": self.version,
            "state": self.state,
            "created_at": self.created_at,
            "checksum": self.checksum,
            "parent_version": self.parent_version,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowCheckpoint":
        return cls(**data)
    
    def compute_checksum(self) -> str:
        """Compute checksum of state for integrity verification."""
        content = json.dumps(self.state, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()


@dataclass
class WorkflowSnapshot:
    """Complete workflow snapshot for backup."""
    workflow_id: str
    checkpoints: list[WorkflowCheckpoint]
    current_version: int
    created_at: str
    archive_checksum: str
    
    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "checkpoints": [cp.to_dict() for cp in self.checkpoints],
            "current_version": self.current_version,
            "created_at": self.created_at,
            "archive_checksum": self.archive_checksum,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowSnapshot":
        return cls(
            workflow_id=data["workflow_id"],
            checkpoints=[WorkflowCheckpoint.from_dict(cp) for cp in data["checkpoints"]],
            current_version=data["current_version"],
            created_at=data["created_at"],
            archive_checksum=data["archive_checksum"],
        )


@dataclass
class RestoreResult:
    """Result of restore operation."""
    success: bool
    workflow_id: str
    restored_version: int | None = None
    error: str | None = None


class WorkflowBackupManager:
    """Manages workflow state backups and restores.
    
    Features:
    - Atomic checkpoint saves with fsync
    - Version history with parent links
    - Integrity verification via checksums
    - Automatic cleanup of old checkpoints
    - Cross-version state diff
    """
    
    def __init__(
        self,
        store_path: str | Path,
        max_checkpoints: int = 10,
        retention_days: int = 30,
    ):
        """
        Args:
            store_path: Directory for checkpoint storage
            max_checkpoints: Maximum checkpoints to keep per workflow
            retention_days: Days to retain checkpoints
        """
        self._store_path = Path(store_path)
        self._max_checkpoints = max_checkpoints
        self._retention_days = retention_days
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """Initialize the backup store."""
        self._store_path.mkdir(parents=True, exist_ok=True)
        logger.info("workflow_backup_initialized", path=str(self._store_path))
    
    def _get_workflow_dir(self, workflow_id: str) -> Path:
        """Get directory for a workflow's checkpoints."""
        return self._store_path / workflow_id[:2] / workflow_id
    
    def _get_checkpoint_path(self, workflow_id: str, version: int) -> Path:
        """Get path for a specific checkpoint."""
        return self._get_workflow_dir(workflow_id) / f"v{version:06d}.json"
    
    async def save_checkpoint(
        self,
        workflow_id: str,
        state: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowCheckpoint:
        """Save a workflow checkpoint atomically.
        
        Args:
            workflow_id: Unique workflow identifier
            state: Workflow state to save
            metadata: Optional metadata
            
        Returns:
            The created checkpoint
        """
        async with self._lock:
            workflow_dir = self._get_workflow_dir(workflow_id)
            workflow_dir.mkdir(parents=True, exist_ok=True)
            
            # Get current version
            current_version = await self._get_latest_version(workflow_id)
            new_version = current_version + 1
            
            # Create checkpoint
            checkpoint = WorkflowCheckpoint(
                workflow_id=workflow_id,
                version=new_version,
                state=state,
                created_at=datetime.now().isoformat(),
                checksum="",  # Will be computed
                parent_version=current_version if current_version > 0 else None,
                metadata=metadata or {},
            )
            
            # Compute checksum
            checkpoint.checksum = checkpoint.compute_checksum()
            
            # Write atomically
            temp_fd, temp_path = tempfile.mkstemp(
                dir=workflow_dir,
                suffix=".tmp",
                prefix=f"v{new_version:06d}_",
            )
            
            try:
                with os.fdopen(temp_fd, "w") as f:
                    json.dump(checkpoint.to_dict(), f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                
                # Atomic rename
                target_path = self._get_checkpoint_path(workflow_id, new_version)
                os.replace(temp_path, target_path)
                
                # Sync directory
                dir_fd = os.open(workflow_dir, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
                
                logger.info(
                    "checkpoint_saved",
                    workflow_id=workflow_id,
                    version=new_version,
                )
                
                # Cleanup old checkpoints
                await self._cleanup_old_checkpoints(workflow_id)
                
                return checkpoint
                
            except Exception as e:
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass
                raise
    
    async def _get_latest_version(self, workflow_id: str) -> int:
        """Get the latest checkpoint version for a workflow."""
        workflow_dir = self._get_workflow_dir(workflow_id)
        
        if not workflow_dir.exists():
            return 0
        
        max_version = 0
        for path in workflow_dir.glob("v*.json"):
            try:
                version = int(path.stem[1:])
                max_version = max(max_version, version)
            except ValueError:
                continue
        
        return max_version
    
    async def _cleanup_old_checkpoints(self, workflow_id: str) -> int:
        """Remove old checkpoints beyond max_checkpoints."""
        workflow_dir = self._get_workflow_dir(workflow_id)
        
        if not workflow_dir.exists():
            return 0
        
        # Get all checkpoints sorted by version
        checkpoints = []
        for path in workflow_dir.glob("v*.json"):
            try:
                version = int(path.stem[1:])
                checkpoints.append((version, path))
            except ValueError:
                continue
        
        checkpoints.sort(key=lambda x: x[0], reverse=True)
        
        # Remove oldest beyond max_checkpoints
        removed = 0
        for version, path in checkpoints[self._max_checkpoints:]:
            try:
                path.unlink()
                removed += 1
            except Exception as e:
                logger.warning("checkpoint_removal_failed", version=version, error=str(e))
        
        if removed > 0:
            logger.info("checkpoints_cleaned", workflow_id=workflow_id, removed=removed)
        
        return removed
    
    async def get_checkpoint(
        self,
        workflow_id: str,
        version: int | None = None,
    ) -> WorkflowCheckpoint | None:
        """Get a specific checkpoint or latest if version is None.
        
        Args:
            workflow_id: Workflow identifier
            version: Checkpoint version (None for latest)
            
        Returns:
            Checkpoint or None if not found
        """
        if version is None:
            version = await self._get_latest_version(workflow_id)
        
        if version <= 0:
            return None
        
        path = self._get_checkpoint_path(workflow_id, version)
        
        if not path.exists():
            return None
        
        try:
            with open(path, "r") as f:
                data = json.load(f)
            
            checkpoint = WorkflowCheckpoint.from_dict(data)
            
            # Verify checksum
            if checkpoint.checksum != checkpoint.compute_checksum():
                logger.error(
                    "checkpoint_checksum_mismatch",
                    workflow_id=workflow_id,
                    version=version,
                )
                return None
            
            return checkpoint
            
        except Exception as e:
            logger.error(
                "checkpoint_read_failed",
                workflow_id=workflow_id,
                version=version,
                error=str(e),
            )
            return None
    
    async def restore_checkpoint(
        self,
        workflow_id: str,
        version: int | None = None,
        verify_checksum: bool = True,
    ) -> RestoreResult:
        """Restore a workflow from checkpoint.
        
        Args:
            workflow_id: Workflow to restore
            version: Specific version or None for latest
            verify_checksum: Whether to verify state checksum
            
        Returns:
            RestoreResult with status
        """
        checkpoint = await self.get_checkpoint(workflow_id, version)
        
        if checkpoint is None:
            return RestoreResult(
                success=False,
                workflow_id=workflow_id,
                error=f"No checkpoint found for version {version}",
            )
        
        # Verify checksum
        if verify_checksum:
            expected = checkpoint.compute_checksum()
            if checkpoint.checksum != expected:
                return RestoreResult(
                    success=False,
                    workflow_id=workflow_id,
                    restored_version=checkpoint.version,
                    error="Checksum mismatch - checkpoint may be corrupted",
                )
        
        logger.info(
            "checkpoint_restored",
            workflow_id=workflow_id,
            version=checkpoint.version,
        )
        
        return RestoreResult(
            success=True,
            workflow_id=workflow_id,
            restored_version=checkpoint.version,
        )
    
    async def list_checkpoints(self, workflow_id: str) -> list[WorkflowCheckpoint]:
        """List all checkpoints for a workflow."""
        workflow_dir = self._get_workflow_dir(workflow_id)
        
        if not workflow_dir.exists():
            return []
        
        checkpoints = []
        for path in workflow_dir.glob("v*.json"):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                checkpoints.append(WorkflowCheckpoint.from_dict(data))
            except Exception:
                continue
        
        checkpoints.sort(key=lambda x: x.version)
        return checkpoints
    
    async def create_backup(
        self,
        workflow_id: str,
    ) -> WorkflowSnapshot | None:
        """Create a complete backup snapshot of a workflow.
        
        Args:
            workflow_id: Workflow to backup
            
        Returns:
            WorkflowSnapshot or None if no checkpoints
        """
        checkpoints = await self.list_checkpoints(workflow_id)
        
        if not checkpoints:
            return None
        
        latest = checkpoints[-1]
        
        # Create archive checksum
        archive_data = json.dumps(
            [cp.to_dict() for cp in checkpoints],
            sort_keys=True,
        )
        archive_checksum = hashlib.sha256(archive_data.encode()).hexdigest()
        
        snapshot = WorkflowSnapshot(
            workflow_id=workflow_id,
            checkpoints=checkpoints,
            current_version=latest.version,
            created_at=datetime.now().isoformat(),
            archive_checksum=archive_checksum,
        )
        
        # Save backup archive
        backup_dir = self._store_path / "_backups"
        backup_dir.mkdir(exist_ok=True)
        
        backup_path = backup_dir / f"{workflow_id}_{latest.version}.json"
        
        temp_fd, temp_path = tempfile.mkstemp(
            dir=backup_dir,
            suffix=".tmp",
        )
        
        try:
            with os.fdopen(temp_fd, "w") as f:
                json.dump(snapshot.to_dict(), f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            
            os.replace(temp_path, backup_path)
            
            logger.info(
                "workflow_backup_created",
                workflow_id=workflow_id,
                checkpoints=len(checkpoints),
                version=latest.version,
            )
            
            return snapshot
            
        except Exception as e:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            logger.error("backup_creation_failed", workflow_id=workflow_id, error=str(e))
            return None
    
    async def restore_from_backup(
        self,
        workflow_id: str,
        backup_version: int,
    ) -> RestoreResult:
        """Restore a workflow from a backup archive.
        
        Args:
            workflow_id: Workflow to restore
            backup_version: Version in backup to restore
            
        Returns:
            RestoreResult
        """
        backup_dir = self._store_path / "_backups"
        backup_path = backup_dir / f"{workflow_id}_{backup_version}.json"
        
        if not backup_path.exists():
            return RestoreResult(
                success=False,
                workflow_id=workflow_id,
                error=f"Backup not found for version {backup_version}",
            )
        
        try:
            with open(backup_path, "r") as f:
                data = json.load(f)
            
            snapshot = WorkflowSnapshot.from_dict(data)
            
            # Verify archive checksum
            archive_data = json.dumps(
                [cp.to_dict() for cp in snapshot.checkpoints],
                sort_keys=True,
            )
            expected = hashlib.sha256(archive_data.encode()).hexdigest()
            
            if snapshot.archive_checksum != expected:
                return RestoreResult(
                    success=False,
                    workflow_id=workflow_id,
                    error="Archive checksum mismatch",
                )
            
            # Restore checkpoints
            for checkpoint in snapshot.checkpoints:
                await self.save_checkpoint(
                    checkpoint.workflow_id,
                    checkpoint.state,
                    checkpoint.metadata,
                )
            
            logger.info(
                "workflow_restored_from_backup",
                workflow_id=workflow_id,
                checkpoints=len(snapshot.checkpoints),
            )
            
            return RestoreResult(
                success=True,
                workflow_id=workflow_id,
                restored_version=snapshot.current_version,
            )
            
        except Exception as e:
            logger.error(
                "backup_restore_failed",
                workflow_id=workflow_id,
                error=str(e),
            )
            return RestoreResult(
                success=False,
                workflow_id=workflow_id,
                error=str(e),
            )
    
    async def delete_workflow(self, workflow_id: str) -> bool:
        """Delete all checkpoints for a workflow."""
        workflow_dir = self._get_workflow_dir(workflow_id)
        
        if not workflow_dir.exists():
            return True
        
        try:
            shutil.rmtree(workflow_dir)
            logger.info("workflow_deleted", workflow_id=workflow_id)
            return True
        except Exception as e:
            logger.error("workflow_deletion_failed", workflow_id=workflow_id, error=str(e))
            return False
    
    async def get_workflow_history(
        self,
        workflow_id: str,
        from_version: int = 1,
    ) -> list[dict[str, Any]]:
        """Get version history for a workflow.
        
        Args:
            workflow_id: Workflow identifier
            from_version: Start from version
            
        Returns:
            List of version metadata
        """
        checkpoints = await self.list_checkpoints(workflow_id)
        
        history = []
        for cp in checkpoints:
            if cp.version < from_version:
                continue
            history.append({
                "version": cp.version,
                "created_at": cp.created_at,
                "parent_version": cp.parent_version,
                "has_metadata": bool(cp.metadata),
            })
        
        return history


# Global manager
_backup_manager: WorkflowBackupManager | None = None


def get_backup_manager(
    store_path: str | None = None,
    **kwargs,
) -> WorkflowBackupManager:
    """Get or create global backup manager."""
    global _backup_manager
    if _backup_manager is None:
        path = store_path or os.environ.get(
            "WORKFLOW_BACKUP_PATH",
            "/var/lib/aisupport/workflows",
        )
        _backup_manager = WorkflowBackupManager(path, **kwargs)
    return _backup_manager


if __name__ == "__main__":
    print("Workflow Backup Manager")
    print("=" * 40)
    print("State persistence for resumable workflows")
    print()
    print("Features:")
    print("  - Atomic checkpoint saves")
    print("  - Version history")
    print("  - Integrity verification")
    print("  - Backup archives")
    print("  - Crash recovery")
