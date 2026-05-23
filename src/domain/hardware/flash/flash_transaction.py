"""Flash Transaction Model - Firmware flash with transaction support and rollback.

Phase 6.2: Implements transaction model for firmware flash operations with:
- Transaction tracking (pending, flashing, verifying, committed, failed, rolled_back)
- Pre-flash snapshot integration (Phase 6.1)
- Automatic rollback on failure
- Partial flash detection
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .event import DomainEvent

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
    """
    
    db_path: str
    snapshot_manager: Any = None  # Phase 6.1 SnapshotManager
    event_bus: Any = None       # Phase 6.1 EventBus
    
    _db: Any = field(default=None, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    
    async def initialize(self) -> None:
        """Initialize database and create tables."""
        import aiosqlite
        
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS flash_transactions (
                transaction_id TEXT PRIMARY KEY,
                target_name TEXT NOT NULL,
                target_id TEXT,
                old_firmware_hash TEXT,
                new_firmware_hash TEXT NOT NULL,
                new_firmware_version TEXT,
                new_firmware_size INTEGER,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                rollback_snapshot_id TEXT,
                resume_state TEXT,
                error_code TEXT,
                error_message TEXT,
                error_details TEXT,
                bytes_written INTEGER DEFAULT 0,
                sectors_erased INTEGER DEFAULT 0,
                duration_ms REAL DEFAULT 0,
                target_slot TEXT,
                previous_slot TEXT
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_target 
            ON flash_transactions(target_name)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_status 
            ON flash_transactions(status)
        """)
        await self._db.commit()
    
    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None
    
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
            
            await self._save_transaction(transaction)
            return transaction
    
    async def start_transaction(self, transaction_id: str) -> FlashTransaction | None:
        """Mark transaction as started (flashing)."""
        async with self._lock:
            transaction = await self._load_transaction(transaction_id)
            if not transaction:
                return None
            
            transaction.status = TransactionStatus.FLASHING
            transaction.started_at = datetime.now()
            await self._save_transaction(transaction)
            
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
            transaction = await self._load_transaction(transaction_id)
            if transaction:
                transaction.bytes_written = bytes_written
                transaction.sectors_erased = sectors_erased
                if resume_state:
                    transaction.resume_state = resume_state
                await self._save_transaction(transaction)
    
    async def verify_transaction(self, transaction_id: str) -> bool:
        """Mark transaction as verifying."""
        async with self._lock:
            transaction = await self._load_transaction(transaction_id)
            if not transaction:
                return False
            
            transaction.status = TransactionStatus.VERIFYING
            await self._save_transaction(transaction)
            return True
    
    async def commit_transaction(self, transaction_id: str) -> FlashTransaction | None:
        """Commit transaction after successful verification."""
        async with self._lock:
            transaction = await self._load_transaction(transaction_id)
            if not transaction:
                return None
            
            transaction.status = TransactionStatus.COMMITTED
            transaction.completed_at = datetime.now()
            transaction.duration_ms = transaction.duration_seconds() * 1000
            await self._save_transaction(transaction)
            
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
            transaction = await self._load_transaction(transaction_id)
            if not transaction:
                return None
            
            transaction.status = TransactionStatus.FAILED
            transaction.completed_at = datetime.now()
            transaction.error_code = error_code
            transaction.error_message = error_message
            transaction.error_details = error_details or {}
            transaction.duration_ms = transaction.duration_seconds() * 1000
            await self._save_transaction(transaction)
            
            await self._publish_event("flash.transaction.failed", transaction)
            return transaction
    
    async def rollback_transaction(
        self,
        transaction_id: str,
        reason: str = "",
    ) -> bool:
        """Rollback transaction using pre-flash snapshot (Phase 6.1)."""
        async with self._lock:
            transaction = await self._load_transaction(transaction_id)
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
                await self._save_transaction(transaction)
                
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
        if not self._db:
            return None
        
        cursor = await self._db.execute(
            """
            SELECT transaction_id FROM flash_transactions
            WHERE target_name = ? AND status IN ('flashing', 'verifying', 'pending')
            ORDER BY created_at DESC LIMIT 1
            """,
            (target_name,),
        )
        row = await cursor.fetchone()
        
        if row:
            return await self._load_transaction(row[0])
        return None
    
    async def get_transaction(self, transaction_id: str) -> FlashTransaction | None:
        """Get transaction by ID."""
        return await self._load_transaction(transaction_id)
    
    async def list_transactions(
        self,
        target_name: str | None = None,
        status: TransactionStatus | None = None,
        limit: int = 100,
    ) -> list[FlashTransaction]:
        """List transactions with optional filters."""
        if not self._db:
            return []
        
        query = "SELECT transaction_id FROM flash_transactions WHERE 1=1"
        params: list[Any] = []
        
        if target_name:
            query += " AND target_name = ?"
            params.append(target_name)
        
        if status:
            query += " AND status = ?"
            params.append(status.value)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        
        transactions = []
        for row in rows:
            tx = await self._load_transaction(row[0])
            if tx:
                transactions.append(tx)
        
        return transactions
    
    async def _save_transaction(self, transaction: FlashTransaction) -> None:
        """Save transaction to database."""
        if not self._db:
            return
        
        await self._db.execute("""
            INSERT OR REPLACE INTO flash_transactions
            (transaction_id, target_name, target_id, old_firmware_hash, new_firmware_hash,
             new_firmware_version, new_firmware_size, status, created_at, started_at,
             completed_at, rollback_snapshot_id, resume_state, error_code, error_message,
             error_details, bytes_written, sectors_erased, duration_ms, target_slot, previous_slot)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            transaction.transaction_id,
            transaction.target_name,
            transaction.target_id,
            transaction.old_firmware_hash,
            transaction.new_firmware_hash,
            transaction.new_firmware_version,
            transaction.new_firmware_size,
            transaction.status.value,
            transaction.created_at.isoformat(),
            transaction.started_at.isoformat() if transaction.started_at else None,
            transaction.completed_at.isoformat() if transaction.completed_at else None,
            transaction.rollback_snapshot_id,
            json.dumps(transaction.resume_state) if transaction.resume_state else None,
            transaction.error_code,
            transaction.error_message,
            json.dumps(transaction.error_details),
            transaction.bytes_written,
            transaction.sectors_erased,
            transaction.duration_ms,
            transaction.target_slot,
            transaction.previous_slot,
        ))
        await self._db.commit()
    
    async def _load_transaction(self, transaction_id: str) -> FlashTransaction | None:
        """Load transaction from database."""
        if not self._db:
            return None
        
        cursor = await self._db.execute(
            "SELECT * FROM flash_transactions WHERE transaction_id = ?",
            (transaction_id,),
        )
        row = await cursor.fetchone()
        
        if not row:
            return None
        
        columns = [desc[0] for desc in cursor.description]
        data = dict(zip(columns, row))
        
        return FlashTransaction(
            transaction_id=data["transaction_id"],
            target_name=data["target_name"],
            target_id=data.get("target_id", ""),
            old_firmware_hash=data.get("old_firmware_hash", ""),
            new_firmware_hash=data["new_firmware_hash"],
            new_firmware_version=data.get("new_firmware_version", ""),
            new_firmware_size=data.get("new_firmware_size", 0),
            status=TransactionStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            started_at=datetime.fromisoformat(data["started_at"]) if data["started_at"] else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data["completed_at"] else None,
            rollback_snapshot_id=data.get("rollback_snapshot_id"),
            resume_state=json.loads(data["resume_state"]) if data.get("resume_state") else None,
            error_code=data.get("error_code"),
            error_message=data.get("error_message"),
            error_details=json.loads(data["error_details"]) if data.get("error_details") else {},
            bytes_written=data.get("bytes_written", 0),
            sectors_erased=data.get("sectors_erased", 0),
            duration_ms=data.get("duration_ms", 0),
            target_slot=data.get("target_slot"),
            previous_slot=data.get("previous_slot"),
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
