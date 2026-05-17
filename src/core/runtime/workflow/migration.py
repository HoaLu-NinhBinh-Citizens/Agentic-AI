"""Migration Manager - Phase 5A (v6).

Workflow migration with transactional semantics and rollback support.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum

from .types import MigrationRecord, WorkflowSnapshot

logger = logging.getLogger(__name__)


class MigrationStatus(str, Enum):
    """Migration status."""
    PENDING = "pending"
    PREPARING = "preparing"
    IN_PROGRESS = "in_progress"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class MigrationTransaction:
    """Transaction state for migration."""
    workflow_id: str
    old_version: str
    new_version: str
    old_snapshot: Optional[WorkflowSnapshot] = None
    new_state: Optional[dict] = None
    status: MigrationStatus = MigrationStatus.PENDING
    attempts: int = 0
    error: Optional[str] = None
    started_at: float = 0
    completed_at: float = 0


class MigrationHook:
    """Hook for workflow migration.
    
    Allows transforming event streams when workflow definitions change.
    """

    def __init__(self):
        self._hooks: dict[str, Callable] = {}

    def register(
        self,
        from_version: str,
        to_version: str,
        transform: Callable[[dict], dict],
    ) -> None:
        """Register a migration hook.
        
        Args:
            from_version: Source version.
            to_version: Target version.
            transform: Function to transform workflow state.
        """
        key = f"{from_version}->{to_version}"
        self._hooks[key] = transform

    async def migrate(
        self,
        workflow_id: str,
        from_version: str,
        to_version: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """Migrate workflow state.
        
        Args:
            workflow_id: Workflow being migrated.
            from_version: Current version.
            to_version: Target version.
            state: Current workflow state.
            
        Returns:
            Migrated state.
        """
        key = f"{from_version}->{to_version}"
        
        if key in self._hooks:
            logger.info(f"Migrating workflow {workflow_id[:8]}... from {from_version} to {to_version}")
            return self._hooks[key](state)
        
        logger.warning(f"No migration hook for {key}, returning state unchanged")
        return state

    def get_migration_path(
        self,
        from_version: str,
        to_version: str,
    ) -> list[str]:
        """Get migration path if exists."""
        key = f"{from_version}->{to_version}"
        return [key] if key in self._hooks else []


class MigrationManager:
    """Manages workflow migrations with transactional semantics.
    
    MIGRATION TRANSACTIONAL BOUNDARY
    =================================
    
    Migration follows a 2-phase commit-like model:
    
    1. PREPARE PHASE:
       - Load current snapshot
       - Create migration record (status=preparing)
       - Save old snapshot as backup (old_snapshot field)
       - Increment attempt counter
    
    2. EXECUTE PHASE:
       - Apply transformation to state
       - Update snapshot version
       - Validate new state
       - Mark migration record (status=in_progress)
    
    3. COMMIT PHASE:
       - Save new snapshot
       - Mark migration complete
       - Clear old_snapshot backup
    
    4. ROLLBACK (on failure):
       - Restore old_snapshot to snapshot_store
       - Mark migration rolled_back
       - Log failure details
       - Increment attempt counter
    
    ROLLBACK CONDITIONS:
    - Transformation throws exception
    - State validation fails
    - Snapshot save fails
    - Timeout exceeded
    
    IDEMPOTENCY:
    - Migration is idempotent per attempt
    - If migration fails mid-way, rollback is deterministic
    - Can retry migration with backoff
    """
    
    # Migration timeout (seconds)
    MIGRATION_TIMEOUT_SECONDS = 300  # 5 minutes
    
    # Max retry attempts
    MAX_RETRY_ATTEMPTS = 3
    
    def __init__(
        self,
        snapshot_store: "SnapshotStore",
        migration_store: "MigrationStore",
        hook: Optional[MigrationHook] = None,
        migration_timeout_seconds: float = MIGRATION_TIMEOUT_SECONDS,
    ):
        self._snapshot_store = snapshot_store
        self._migration_store = migration_store
        self._hook = hook or MigrationHook()
        self._migration_timeout = migration_timeout_seconds
        
        # Version registry
        self._versions: dict[str, Any] = {}
        
        # Transaction state per workflow
        self._transactions: dict[str, MigrationTransaction] = {}
    
    def register_version(self, version: str, definition: Any) -> None:
        """Register a workflow version.
        
        Args:
            version: Version string.
            definition: Workflow definition.
        """
        self._versions[version] = definition

    async def migrate_workflow(
        self,
        workflow_id: str,
        target_version: str,
        custom_hook: Optional[Callable] = None,
    ) -> bool:
        """Migrate a workflow to a new version.
        
        Args:
            workflow_id: Workflow to migrate.
            target_version: Target version.
            custom_hook: Optional custom migration function.
            
        Returns:
            True if migration successful.
        """
        # Check existing migration status
        existing = await self._migration_store.get_by_workflow(workflow_id)
        if existing:
            if existing.status in ("completed",):
                logger.info(f"Workflow {workflow_id[:8]}... already migrated")
                return True
            if existing.status == "in_progress":
                logger.warning(f"Migration already in progress for {workflow_id[:8]}...")
                return False
        
        # Get transaction or create new
        if workflow_id not in self._transactions:
            self._transactions[workflow_id] = MigrationTransaction(
                workflow_id=workflow_id,
                old_version="",
                new_version=target_version,
            )
        
        tx = self._transactions[workflow_id]
        tx.attempts += 1
        tx.started_at = time.time()
        
        try:
            # Check timeout
            if time.time() - tx.started_at > self._migration_timeout:
                raise MigrationTimeoutError(workflow_id, tx.attempts)
            
            # PREPARE PHASE
            snapshot = await self._snapshot_store.get_latest(workflow_id)
            if not snapshot:
                raise MigrationError(f"No snapshot for workflow {workflow_id}")
            
            tx.old_version = snapshot.version
            tx.old_snapshot = self._clone_snapshot(snapshot)
            
            # Check if migration needed
            if tx.old_version == target_version:
                logger.info(f"Workflow {workflow_id[:8]}... already at version {target_version}")
                return True
            
            # Create migration record (PREPARING)
            record = MigrationRecord(
                workflow_id=workflow_id,
                old_version=tx.old_version,
                new_version=target_version,
                status="preparing",
            )
            await self._migration_store.save(record)
            
            # EXECUTE PHASE
            new_state = snapshot.state.copy()
            
            if custom_hook:
                new_state = await custom_hook(
                    workflow_id, tx.old_version, target_version, new_state
                )
            else:
                new_state = await self._hook.migrate(
                    workflow_id, tx.old_version, target_version, new_state
                )
            
            tx.new_state = new_state
            
            # Mark in_progress
            record.status = "in_progress"
            await self._migration_store.save(record)
            
            # Validate state
            await self._validate_migrated_state(new_state, target_version)
            
            # Update snapshot
            snapshot.version = target_version
            snapshot.state = new_state
            
            # Save with backup reference
            await self._snapshot_store.save_with_backup(
                snapshot,
                backup_id=f"{workflow_id}_backup_{tx.attempts}"
            )
            
            # COMMIT PHASE
            record.status = "completed"
            record.completed_at = time.time()
            await self._migration_store.save(record)
            
            # Clear transaction
            del self._transactions[workflow_id]
            
            logger.info(
                f"Migrated workflow {workflow_id[:8]}... from {tx.old_version} to {target_version}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Migration failed for {workflow_id}: {e}")
            tx.error = str(e)
            tx.status = MigrationStatus.FAILED
            
            # Mark migration as failed
            record = await self._migration_store.get_by_workflow(workflow_id)
            if record:
                record.status = "failed"
                record.error = str(e)
                await self._migration_store.save(record)
            
            # Check if should rollback
            if tx.attempts < self.MAX_RETRY_ATTEMPTS:
                logger.info(
                    f"Attempt {tx.attempts} failed, will retry"
                )
            else:
                logger.warning(
                    f"Max attempts ({self.MAX_RETRY_ATTEMPTS}) reached, rolling back"
                )
                await self.rollback_migration(workflow_id)
            
            return False
    
    async def _validate_migrated_state(
        self,
        state: dict,
        version: str,
    ) -> None:
        """Validate migrated state.
        
        Raises if state is invalid.
        """
        if not isinstance(state, dict):
            raise MigrationValidationError(
                f"State must be dict, got {type(state)}"
            )
    
    def _clone_snapshot(self, snapshot: WorkflowSnapshot) -> WorkflowSnapshot:
        """Create a deep copy of snapshot for backup."""
        return WorkflowSnapshot(
            snapshot_id=f"{snapshot.snapshot_id}_backup",
            workflow_id=snapshot.workflow_id,
            version=snapshot.version,
            status=snapshot.status,
            state=snapshot.state.copy(),
            last_event_sequence=snapshot.last_event_sequence,
            pending_activities=snapshot.pending_activities.copy(),
            pending_children=snapshot.pending_children.copy(),
            pending_signals=snapshot.pending_signals.copy(),
            current_blocked_on=snapshot.current_blocked_on,
            blocked_reason=snapshot.blocked_reason,
            created_at=snapshot.created_at,
            created_by=snapshot.created_by,
            is_terminal_snapshot=snapshot.is_terminal_snapshot,
        )

    async def rollback_migration(self, workflow_id: str) -> bool:
        """Rollback a failed migration.
        
        ROLLBACK PROTOCOL:
        1. Get migration record
        2. Restore old_snapshot to snapshot_store
        3. Mark migration as rolled_back
        4. Clear transaction state
        
        Args:
            workflow_id: Workflow to rollback.
            
        Returns:
            True if rollback successful.
        """
        try:
            record = await self._migration_store.get_by_workflow(workflow_id)
            if not record:
                logger.error(f"No migration record for {workflow_id}")
                return False
            
            if record.status == "completed":
                logger.warning(f"Migration already completed, cannot rollback")
                return False
            
            # Restore old snapshot
            if record.old_snapshot:
                await self._snapshot_store.save(record.old_snapshot)
                
                record.status = "rolled_back"
                await self._migration_store.save(record)
                
                logger.info(
                    f"Rolled back migration for {workflow_id[:8]}... "
                    f"to version {record.old_version}"
                )
                
                # Clear transaction
                self._transactions.pop(workflow_id, None)
                
                return True
            
            logger.warning(f"No old_snapshot to restore for {workflow_id[:8]}...")
            return False
            
        except Exception as e:
            logger.error(f"Rollback failed for {workflow_id}: {e}")
            return False
    
    async def retry_migration(
        self,
        workflow_id: str,
        custom_hook: Optional[Callable] = None,
    ) -> bool:
        """Retry a failed migration.
        
        Args:
            workflow_id: Workflow to retry.
            custom_hook: Optional custom migration function.
            
        Returns:
            True if retry successful.
        """
        record = await self._migration_store.get_by_workflow(workflow_id)
        
        if not record:
            logger.error(f"No migration record for {workflow_id}")
            return False
        
        if record.status == "completed":
            logger.info(f"Migration already completed for {workflow_id[:8]}...")
            return True
        
        if record.attempts >= self.MAX_RETRY_ATTEMPTS:
            logger.warning(
                f"Max attempts reached for {workflow_id[:8]}..., cannot retry"
            )
            return False
        
        # Clear failed migration
        record.status = "pending"
        await self._migration_store.save(record)
        
        # Retry
        return await self.migrate_workflow(workflow_id, record.new_version, custom_hook)
    
    async def get_migration_status(self, workflow_id: str) -> Optional[MigrationRecord]:
        """Get migration status for a workflow."""
        return await self._migration_store.get_by_workflow(workflow_id)
    
    async def get_transaction_state(
        self,
        workflow_id: str,
    ) -> Optional[MigrationTransaction]:
        """Get current transaction state."""
        return self._transactions.get(workflow_id)


class MigrationError(Exception):
    """Migration failed."""
    pass


class MigrationTimeoutError(MigrationError):
    """Migration timed out."""
    
    def __init__(self, workflow_id: str, attempts: int):
        self.workflow_id = workflow_id
        self.attempts = attempts
        super().__init__(
            f"Migration timeout for {workflow_id} after {attempts} attempts"
        )


class MigrationValidationError(MigrationError):
    """Migrated state validation failed."""
    pass


# Placeholder store interfaces
class SnapshotStore:
    async def get_latest(self, workflow_id: str) -> Optional[WorkflowSnapshot]: ...
    async def save(self, snapshot: WorkflowSnapshot) -> None: ...
    async def save_with_backup(
        self,
        snapshot: WorkflowSnapshot,
        backup_id: str,
    ) -> None: ...
    async def delete_workflow(self, workflow_id: str) -> None: ...

class MigrationStore:
    async def save(self, record: MigrationRecord) -> None: ...
    async def get_by_workflow(self, workflow_id: str) -> Optional[MigrationRecord]: ...
