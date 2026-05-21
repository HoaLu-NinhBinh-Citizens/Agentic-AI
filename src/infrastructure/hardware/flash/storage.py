"""Storage implementations for Flash Transaction storage.

Provides SQLite and LMDB-based storage backends.
"""

from __future__ import annotations

import aiosqlite
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SQLiteFlashTransactionStorage:
    """SQLite-based storage for flash transactions.
    
    Provides persistent storage for flash transaction history
    and resume states.
    """
    
    def __init__(self, db_path: str) -> None:
        """Initialize storage.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None
    
    async def initialize(self) -> None:
        """Initialize database and create tables."""
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
        
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS resume_states (
                transaction_id TEXT PRIMARY KEY,
                firmware_hash TEXT NOT NULL,
                firmware_size INTEGER,
                last_sector_written INTEGER DEFAULT 0,
                last_offset_in_sector INTEGER DEFAULT 0,
                total_bytes_written INTEGER DEFAULT 0,
                verified_sectors TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (transaction_id) REFERENCES flash_transactions(transaction_id)
            )
        """)
        
        await self._db.commit()
    
    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None
    
    async def save_transaction(self, transaction: dict) -> None:
        """Save transaction to database."""
        if not self._db:
            raise RuntimeError("Database not initialized")
        
        await self._db.execute("""
            INSERT OR REPLACE INTO flash_transactions
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            transaction.get("transaction_id"),
            transaction.get("target_name"),
            transaction.get("target_id"),
            transaction.get("old_firmware_hash"),
            transaction.get("new_firmware_hash"),
            transaction.get("new_firmware_version"),
            transaction.get("new_firmware_size"),
            transaction.get("status"),
            transaction.get("created_at"),
            transaction.get("started_at"),
            transaction.get("completed_at"),
            transaction.get("rollback_snapshot_id"),
            transaction.get("resume_state"),
            transaction.get("error_code"),
            transaction.get("error_message"),
            transaction.get("error_details"),
            transaction.get("bytes_written", 0),
            transaction.get("sectors_erased", 0),
            transaction.get("duration_ms", 0),
            transaction.get("target_slot"),
            transaction.get("previous_slot"),
        ))
        await self._db.commit()
    
    async def load_transaction(self, transaction_id: str) -> dict | None:
        """Load transaction from database."""
        if not self._db:
            raise RuntimeError("Database not initialized")
        
        cursor = await self._db.execute(
            "SELECT * FROM flash_transactions WHERE transaction_id = ?",
            (transaction_id,),
        )
        row = await cursor.fetchone()
        
        if not row:
            return None
        
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))
    
    async def save_resume_state(self, state: dict) -> None:
        """Save resume state to database."""
        if not self._db:
            raise RuntimeError("Database not initialized")
        
        await self._db.execute("""
            INSERT OR REPLACE INTO resume_states
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            state.get("transaction_id"),
            state.get("firmware_hash"),
            state.get("firmware_size"),
            state.get("last_sector_written", 0),
            state.get("last_offset_in_sector", 0),
            state.get("total_bytes_written", 0),
            json.dumps(state.get("verified_sectors", {})),
            state.get("created_at"),
            state.get("updated_at"),
        ))
        await self._db.commit()
    
    async def load_resume_state(self, transaction_id: str) -> dict | None:
        """Load resume state from database."""
        if not self._db:
            raise RuntimeError("Database not initialized")
        
        cursor = await self._db.execute(
            "SELECT * FROM resume_states WHERE transaction_id = ?",
            (transaction_id,),
        )
        row = await cursor.fetchone()
        
        if not row:
            return None
        
        columns = [desc[0] for desc in cursor.description]
        result = dict(zip(columns, row))
        
        if "verified_sectors" in result and isinstance(result["verified_sectors"], str):
            result["verified_sectors"] = json.loads(result["verified_sectors"])
        
        return result
    
    async def delete_resume_state(self, transaction_id: str) -> bool:
        """Delete resume state from database."""
        if not self._db:
            raise RuntimeError("Database not initialized")
        
        cursor = await self._db.execute(
            "DELETE FROM resume_states WHERE transaction_id = ?",
            (transaction_id,),
        )
        await self._db.commit()
        return cursor.rowcount > 0


class LMDBFlashTransactionStorage:
    """LMDB-based storage for high-performance transaction storage.
    
    Provides fast key-value storage for flash transactions
    and resume states.
    """
    
    def __init__(self, db_path: str, map_size: int = 100 * 1024 * 1024) -> None:
        """Initialize storage.
        
        Args:
            db_path: Path to LMDB database directory
            map_size: Maximum database size in bytes
        """
        self.db_path = db_path
        self.map_size = map_size
        self._env: Any = None
    
    async def initialize(self) -> None:
        """Initialize LMDB environment."""
        import lmdb
        import os
        
        os.makedirs(self.db_path, exist_ok=True)
        self._env = lmdb.open(self.db_path, map_size=self.map_size)
    
    async def close(self) -> None:
        """Close LMDB environment."""
        if self._env:
            self._env.close()
            self._env = None
    
    async def save_transaction(self, transaction: dict) -> None:
        """Save transaction to LMDB."""
        if not self._env:
            raise RuntimeError("LMDB not initialized")
        
        tx_id = transaction.get("transaction_id", "")
        
        with self._env.begin(write=True) as txn:
            txn.put(
                f"tx:{tx_id}".encode(),
                json.dumps(transaction, default=str).encode(),
            )
    
    async def load_transaction(self, transaction_id: str) -> dict | None:
        """Load transaction from LMDB."""
        if not self._env:
            raise RuntimeError("LMDB not initialized")
        
        with self._env.begin() as txn:
            data = txn.get(f"tx:{transaction_id}".encode())
            if data:
                return json.loads(data.decode())
        return None
    
    async def save_resume_state(self, state: dict) -> None:
        """Save resume state to LMDB."""
        if not self._env:
            raise RuntimeError("LMDB not initialized")
        
        tx_id = state.get("transaction_id", "")
        
        with self._env.begin(write=True) as txn:
            txn.put(
                f"resume:{tx_id}".encode(),
                json.dumps(state, default=str).encode(),
            )
    
    async def load_resume_state(self, transaction_id: str) -> dict | None:
        """Load resume state from LMDB."""
        if not self._env:
            raise RuntimeError("LMDB not initialized")
        
        with self._env.begin() as txn:
            data = txn.get(f"resume:{transaction_id}".encode())
            if data:
                return json.loads(data.decode())
        return None
    
    async def delete_resume_state(self, transaction_id: str) -> bool:
        """Delete resume state from LMDB."""
        if not self._env:
            raise RuntimeError("LMDB not initialized")
        
        with self._env.begin(write=True) as txn:
            result = txn.delete(f"resume:{transaction_id}".encode())
            return result
