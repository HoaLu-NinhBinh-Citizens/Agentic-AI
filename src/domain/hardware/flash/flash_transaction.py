"""Flash Transaction Model - Firmware flash with transaction support and rollback.

Phase 6.2: Implements transaction model for firmware flash operations with:
- Transaction tracking (pending, flashing, verifying, committed, failed, rolled_back)
- Pre-flash snapshot integration (Phase 6.1)
- Automatic rollback on failure
- Partial flash detection
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..event import DomainEvent
    from ...ports.flash_persistence import FlashTransactionStore

logger = logging.getLogger(__name__)


class TransactionStatus(Enum):
    """Flash transaction status."""
    
    PENDING = "pending"           # Created, not started
    FLASHING = "flashing"         # Flash in progress
    VERIFYING = "verifying"      # Verification in progress
    COMMITTED = "committed"       # Successfully completed
    FAILED = "failed"           # Flash failed
    ROLLED_BACK = "rolled_back"  # Rolled back to previous state
    INTERRUPTED = "interrupted"  # Flash was interrupted


@dataclass
class FlashTransaction:
    """Represents a firmware flash transaction.
    
    Tracks the complete lifecycle of a flash operation with rollback support.
    Integrates with Phase 6.1 snapshot system for rollback capability.
    """
    
    # Identity
    transaction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    target_name: str = ""
    target_id: str = ""

    # Lock fencing (P0)
    lock_epoch: int = 0
    lock_owner_id: str = ""
    lock_acquired: bool = False
    
    # Firmware tracking
    old_firmware_hash: str = ""
    new_firmware_hash: str = ""
    new_firmware_version: str = ""
    new_firmware_size: int = 0
    
    # Status
    status: TransactionStatus = TransactionStatus.PENDING
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    # Rollback support (Phase 6.1 integration)
    rollback_snapshot_id: str | None = None
    
    # Resume state
    resume_state: dict[str, Any] | None = None
    
    # Error handling
    error_code: str | None = None
    error_message: str | None = None
    error_details: dict[str, Any] = field(default_factory=dict)
    
    # Statistics
    bytes_written: int = 0
    sectors_erased: int = 0
    duration_ms: float = 0.0
    
    # Slot information (A/B layout)
    target_slot: str | None = None
    previous_slot: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "transaction_id": self.transaction_id,
            "target_name": self.target_name,
            "target_id": self.target_id,
            "lock_epoch": self.lock_epoch,
            "lock_owner_id": self.lock_owner_id,
            "lock_acquired": self.lock_acquired,
            "old_firmware_hash": self.old_firmware_hash,
            "new_firmware_hash": self.new_firmware_hash,
            "new_firmware_version": self.new_firmware_version,
            "new_firmware_size": self.new_firmware_size,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "rollback_snapshot_id": self.rollback_snapshot_id,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "bytes_written": self.bytes_written,
            "duration_ms": self.duration_ms,
            "target_slot": self.target_slot,
            "previous_slot": self.previous_slot,
        }
    
    def duration_seconds(self) -> float:
        """Get transaction duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        elif self.started_at:
            return (datetime.now() - self.started_at).total_seconds()
        return 0.0
    
    def is_terminal(self) -> bool:
        """Check if transaction is in terminal state."""
        return self.status in (
            TransactionStatus.COMMITTED,
            TransactionStatus.ROLLED_BACK,
        )
    
    def can_rollback(self) -> bool:
        """Check if transaction can be rolled back."""
        return (
            self.status in (TransactionStatus.FAILED, TransactionStatus.INTERRUPTED)
            and self.rollback_snapshot_id is not None
        )


@dataclass
class FlashTransactionManager:
    """Manages firmware flash transactions with rollback support.
    
    Key responsibilities:
    - Create transaction before flash
    - Update status during flash
    - Commit after verification
    - Automatic rollback on failure (using Phase 6.1 snapshots)
    
    This class is a domain component and does NOT depend on infrastructure.
    It receives a FlashTransactionStore via constructor injection.
    """
    
    store: FlashTransactionStore
    snapshot_manager: Any = None  # Phase 6.1 SnapshotManager
    event_bus: Any = None       # Phase 6.1 EventBus
    
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    
    async def initialize(self) -> None:
        """Initialize the store."""
        await self.store.initialize()
    
    async def close(self) -> None:
        """Close the store."""
        await self.store.close()
    
    async def create_transaction(
        self,
        target_name: str,
        target_id: str,
        new_firmware_hash: str,
        new_firmware_version: str,
        new_firmware_size: int,
        old_firmware_hash: str = "",
        target_slot: str | None = None,
    ) -> FlashTransaction:
        """Create a new flash transaction.
        
        Optionally captures pre-flash snapshot (Phase 6.1 integration).
        """
        async with self._lock:
            transaction = FlashTransaction(
                target_name=target_name,
                target_id=target_id,
                new_firmware_hash=new_firmware_hash,
                new_firmware_version=new_firmware_version,
                new_firmware_size=new_firmware_size,
                old_firmware_hash=old_firmware_hash,
                target_slot=target_slot,
            )
            
            # Capture pre-flash snapshot if snapshot_manager available
            if self.snapshot_manager:
                try:
                    # Import Phase 6.1 types
                    from ..snapshot_manager import RegisterSnapshot
                    
                    snapshot = await self.snapshot_manager.capture(
                        target_name=target_name,
                        target_id=target_id,
                        registers=RegisterSnapshot(),
                        memory_regions=[],
                        peripherals=[],
                        name=f"pre_flash_{transaction.transaction_id}",
                        captured_by="flash_transaction",
                    )
                    transaction.rollback_snapshot_id = snapshot.snapshot_id
                    logger.info(
                        "pre_flash_snapshot_captured",
                        transaction_id=transaction.transaction_id,
                        snapshot_id=snapshot.snapshot_id,
                    )
                except Exception as e:
                    logger.warning(
                        "pre_flash_snapshot_failed",
                        transaction_id=transaction.transaction_id,
                        error=str(e),
                    )
            
            await self.store.save_transaction(transaction)
            return transaction
    
    async def start_transaction(self, transaction_id: str) -> FlashTransaction | None:
        """Mark transaction as started (flashing)."""
        async with self._lock:
            transaction = await self.store.load_transaction(transaction_id)
            if not transaction:
                return None
            
            transaction.status = TransactionStatus.FLASHING
            transaction.started_at = datetime.now()
            await self.store.save_transaction(transaction)
            
            await self._publish_event("flash.transaction.started", transaction)
            return transaction
    
    async def update_progress(
        self,
        transaction_id: str,
        bytes_written: int,
        sectors_erased: int,
        resume_state: dict[str, Any] | None = None,
    ) -> None:
        """Update transaction progress."""
        async with self._lock:
            transaction = await self.store.load_transaction(transaction_id)
            if transaction:
                transaction.bytes_written = bytes_written
                transaction.sectors_erased = sectors_erased
                if resume_state:
                    transaction.resume_state = resume_state
                await self.store.save_transaction(transaction)
    
    async def verify_transaction(self, transaction_id: str) -> bool:
        """Mark transaction as verifying."""
        async with self._lock:
            transaction = await self.store.load_transaction(transaction_id)
            if not transaction:
                return False
            
            transaction.status = TransactionStatus.VERIFYING
            await self.store.save_transaction(transaction)
            return True
    
    async def commit_transaction(self, transaction_id: str) -> FlashTransaction | None:
        """Commit transaction after successful verification."""
        async with self._lock:
            transaction = await self.store.load_transaction(transaction_id)
            if not transaction:
                return None
            
            transaction.status = TransactionStatus.COMMITTED
            transaction.completed_at = datetime.now()
            transaction.duration_ms = transaction.duration_seconds() * 1000
            await self.store.save_transaction(transaction)
            
            await self._publish_event("flash.transaction.committed", transaction)
            logger.info(
                "flash_transaction_committed",
                transaction_id=transaction_id,
                duration_ms=transaction.duration_ms,
            )
            return transaction
    
    async def fail_transaction(
        self,
        transaction_id: str,
        error_code: str,
        error_message: str,
        error_details: dict[str, Any] | None = None,
    ) -> FlashTransaction | None:
        """Mark transaction as failed."""
        async with self._lock:
            transaction = await self.store.load_transaction(transaction_id)
            if not transaction:
                return None
            
            transaction.status = TransactionStatus.FAILED
            transaction.completed_at = datetime.now()
            transaction.error_code = error_code
            transaction.error_message = error_message
            transaction.error_details = error_details or {}
            transaction.duration_ms = transaction.duration_seconds() * 1000
            await self.store.save_transaction(transaction)
            
            await self._publish_event("flash.transaction.failed", transaction)
            return transaction
    
    async def rollback_transaction(
        self,
        transaction_id: str,
        reason: str = "",
    ) -> bool:
        """Rollback transaction using pre-flash snapshot (Phase 6.1)."""
        async with self._lock:
            transaction = await self.store.load_transaction(transaction_id)
            if not transaction or not transaction.can_rollback():
                return False
            
            if not self.snapshot_manager or not transaction.rollback_snapshot_id:
                logger.error(
                    "rollback_not_possible",
                    transaction_id=transaction_id,
                    reason="no_snapshot_or_manager",
                )
                return False
            
            try:
                # Restore from Phase 6.1 snapshot
                await self.snapshot_manager.restore(
                    snapshot_id=transaction.rollback_snapshot_id,
                    target_name=transaction.target_name,
                )
                
                transaction.status = TransactionStatus.ROLLED_BACK
                transaction.completed_at = datetime.now()
                transaction.error_message = f"Rolled back: {reason}"
                await self.store.save_transaction(transaction)
                
                await self._publish_event("flash.transaction.rolled_back", transaction)
                logger.info(
                    "flash_transaction_rolled_back",
                    transaction_id=transaction_id,
                    snapshot_id=transaction.rollback_snapshot_id,
                )
                return True
                
            except Exception as e:
                logger.exception(
                    "rollback_failed",
                    transaction_id=transaction_id,
                    error=str(e),
                )
                return False
    
    async def get_pending_transaction(
        self,
        target_name: str,
    ) -> FlashTransaction | None:
        """Get pending transaction for target (for resume detection)."""
        return await self.store.get_pending_transaction(target_name)
    
    async def get_transaction(self, transaction_id: str) -> FlashTransaction | None:
        """Get transaction by ID."""
        return await self.store.load_transaction(transaction_id)
    
    async def list_transactions(
        self,
        target_name: str | None = None,
        status: TransactionStatus | None = None,
        limit: int = 100,
    ) -> list[FlashTransaction]:
        """List transactions with optional filters."""
        return await self.store.list_transactions(
            target_name=target_name,
            status=status,
            limit=limit,
        )
    
    async def _publish_event(self, event_type: str, transaction: FlashTransaction) -> None:
        """Publish event to event bus (Phase 6.1)."""
        if self.event_bus:
            # Import here to avoid circular dependency
            from ..event import DomainEvent
            
            event = DomainEvent(
                event_type=event_type,
                source="flash_transaction_manager",
                data=transaction.to_dict(),
            )
            await self.event_bus.publish(event)


@dataclass
class PartialFlashDetector:
    """Detects partial flash operations after connection interruption.
    
    On reconnection, checks for transactions that were 'flashing' but
    never completed, indicating a partial flash occurred.
    """
    
    transaction_manager: FlashTransactionManager
    event_bus: Any = None
    
    async def check_on_reconnect(self, target_name: str) -> PartialFlashInfo | None:
        """Check for partial flash after target reconnection.
        
        Returns:
            PartialFlashInfo if partial flash detected, None otherwise
        """
        from datetime import timedelta
        
        # Get transaction that was in progress
        transaction = await self.transaction_manager.get_pending_transaction(target_name)
        
        if not transaction:
            return None
        
        # Check if transaction was old (stale)
        if transaction.started_at:
            stale_duration = datetime.now() - transaction.started_at
            if stale_duration < timedelta(minutes=5):
                # Too recent, might still be in progress
                return None
        
        # This is likely a partial flash
        partial_info = PartialFlashInfo(
            transaction_id=transaction.transaction_id,
            target_name=target_name,
            interrupted_at=transaction.started_at,
            bytes_written=transaction.bytes_written,
            resume_state=transaction.resume_state,
            old_firmware_hash=transaction.old_firmware_hash,
            new_firmware_hash=transaction.new_firmware_hash,
        )
        
        # Mark as interrupted
        await self.transaction_manager.fail_transaction(
            transaction_id=transaction.transaction_id,
            error_code="PARTIAL_FLASH",
            error_message="Flash operation was interrupted",
        )
        
        # Publish event
        if self.event_bus:
            from ..event import DomainEvent
            
            event = DomainEvent(
                event_type="flash.partial_detected",
                source="partial_flash_detector",
                data=partial_info.to_dict(),
            )
            await self.event_bus.publish(event)
        
        return partial_info


@dataclass
class PartialFlashInfo:
    """Information about a detected partial flash."""
    
    transaction_id: str
    target_name: str
    interrupted_at: datetime | None
    bytes_written: int
    resume_state: dict[str, Any] | None
    old_firmware_hash: str
    new_firmware_hash: str
    
    detected_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "transaction_id": self.transaction_id,
            "target_name": self.target_name,
            "interrupted_at": self.interrupted_at.isoformat() if self.interrupted_at else None,
            "bytes_written": self.bytes_written,
            "resume_state": self.resume_state,
            "old_firmware_hash": self.old_firmware_hash,
            "new_firmware_hash": self.new_firmware_hash,
            "detected_at": self.detected_at.isoformat(),
        }
