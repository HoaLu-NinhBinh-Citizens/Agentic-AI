"""SQLite Flash Transaction Store.

Infrastructure implementation of FlashTransactionStore using aiosqlite.
Follows Clean Architecture: this is the infrastructure layer, not the domain.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

import aiosqlite

from src.domain.hardware.flash.flash_transaction import (
    FlashTransaction,
    TransactionStatus,
)
from src.domain.ports.flash_persistence import FlashTransactionStore

logger = logging.getLogger(__name__)


class SQLiteFlashTransactionStore(FlashTransactionStore):
    """SQLite-backed flash transaction store.
    
    Implements FlashTransactionStore interface using aiosqlite.
    Handles all SQLite-specific logic including table creation, query building, etc.
    """
    
    def __init__(self, db_path: str) -> None:
        """Initialize the store.
        
        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """Initialize database and create tables."""
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS flash_transactions (
                transaction_id TEXT PRIMARY KEY,
                target_name TEXT NOT NULL,
                target_id TEXT,
                lock_epoch INTEGER DEFAULT 0,
                lock_owner_id TEXT,
                lock_acquired INTEGER DEFAULT 0,
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
        await self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_target 
            ON flash_transactions(target_name)
        """)
        await self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_status 
            ON flash_transactions(status)
        """)
        await self._conn.commit()
        logger.info("SQLiteFlashTransactionStore initialized at %s", self._db_path)
    
    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("SQLiteFlashTransactionStore closed")
    
    async def save_transaction(self, transaction: FlashTransaction) -> None:
        """Save or update a flash transaction."""
        async with self._lock:
            if not self._conn:
                raise RuntimeError("Store not initialized")
            
            await self._conn.execute("""
                INSERT OR REPLACE INTO flash_transactions
                (transaction_id, target_name, target_id, lock_epoch, lock_owner_id, lock_acquired,
                 old_firmware_hash, new_firmware_hash,
                 new_firmware_version, new_firmware_size, status, created_at, started_at,
                 completed_at, rollback_snapshot_id, resume_state, error_code, error_message,
                 error_details, bytes_written, sectors_erased, duration_ms, target_slot, previous_slot)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                transaction.transaction_id,
                transaction.target_name,
                transaction.target_id,
                transaction.lock_epoch,
                transaction.lock_owner_id,
                1 if transaction.lock_acquired else 0,
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
            await self._conn.commit()
    
    async def load_transaction(self, transaction_id: str) -> FlashTransaction | None:
        """Load a transaction by ID."""
        async with self._lock:
            if not self._conn:
                return None
            
            cursor = await self._conn.execute(
                "SELECT * FROM flash_transactions WHERE transaction_id = ?",
                (transaction_id,),
            )
            row = await cursor.fetchone()
            
            if not row:
                return None
            
            return self._row_to_transaction(row)
    
    async def get_pending_transaction(
        self,
        target_name: str,
    ) -> FlashTransaction | None:
        """Get pending transaction for target."""
        async with self._lock:
            if not self._conn:
                return None
            
            cursor = await self._conn.execute(
                """
                SELECT * FROM flash_transactions
                WHERE target_name = ? AND status IN ('flashing', 'verifying', 'pending')
                ORDER BY created_at DESC LIMIT 1
                """,
                (target_name,),
            )
            row = await cursor.fetchone()
            
            if row:
                return self._row_to_transaction(row)
            return None
    
    async def list_transactions(
        self,
        target_name: str | None = None,
        status: TransactionStatus | None = None,
        limit: int = 100,
    ) -> list[FlashTransaction]:
        """List transactions with optional filters."""
        async with self._lock:
            if not self._conn:
                return []
            
            query = "SELECT * FROM flash_transactions WHERE 1=1"
            params: list[Any] = []
            
            if target_name:
                query += " AND target_name = ?"
                params.append(target_name)
            
            if status:
                query += " AND status = ?"
                params.append(status.value)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor = await self._conn.execute(query, params)
            rows = await cursor.fetchall()
            
            return [self._row_to_transaction(row) for row in rows]
    
    def _row_to_transaction(self, row: aiosqlite.Row) -> FlashTransaction:
        """Convert a database row to a FlashTransaction."""
        data = dict(row)
        
        return FlashTransaction(
            transaction_id=data["transaction_id"],
            target_name=data["target_name"],
            target_id=data.get("target_id", ""),
            lock_epoch=int(data.get("lock_epoch", 0) or 0),
            lock_owner_id=data.get("lock_owner_id", "") or "",
            lock_acquired=bool(int(data.get("lock_acquired", 0) or 0)),
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
