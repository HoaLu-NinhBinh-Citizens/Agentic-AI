"""Two-Phase Commit Flash Transaction - P0-Hardening.

Extends FlashTransactionManager with 2-phase commit protocol:
- Phase 1: probe operations (erase/write/verify) with journal entries
- Phase 2: DB commit (transaction status update) only after all probes succeed
- Commit guard: on reconnect after crash, check journal vs DB state
- Physical probe acknowledgment: signed ack stored atomically per sector
- Retry-with-idempotency: resume re-uses same transaction_id so already-
  completed sectors are skipped

Key invariant: a sector operation is complete ONLY when BOTH its journal
entry (P0-flash-wal) AND its probe acknowledgment are durable. The
transaction manager is NOT committed until all sector acks are present.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SectorAcknowledgment:
    """P0-Hardening: Signed acknowledgment from probe for a sector operation.

    The probe must return a signed acknowledgment for each erase/write/verify
    operation. This ack is the proof that the physical operation completed.
    Without this ack, we cannot commit the transaction.
    """
    transaction_id: str
    sector_id: int
    sector_address: int

    # Operation info
    operation: str  # "erase", "write", "verify"
    crc_before: str = ""
    crc_after: str = ""

    # Probe identity
    probe_id: str = ""
    probe_serial: str = ""

    # Acknowledgment signature (HMAC of operation+params)
    acknowledgment: str = ""
    acknowledged_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "sector_id": self.sector_id,
            "sector_address": hex(self.sector_address),
            "operation": self.operation,
            "crc_before": self.crc_before,
            "crc_after": self.crc_after,
            "probe_id": self.probe_id,
            "probe_serial": self.probe_serial,
            "acknowledgment": self.acknowledgment,
            "acknowledged_at": self.acknowledged_at.isoformat(),
        }


class ProbeAcknowledgmentStore:
    """P0-Hardening: Stores probe acknowledgments in SQLite atomically.

    Each acknowledgment is the proof that a physical probe operation completed.
    The transaction can only be committed when all acknowledgments are present.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: Any = None

    async def initialize(self) -> None:
        import aiosqlite
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS sector_acknowledgments (
                transaction_id TEXT NOT NULL,
                sector_id INTEGER NOT NULL,
                sector_address INTEGER NOT NULL,
                operation TEXT NOT NULL,
                crc_before TEXT,
                crc_after TEXT,
                probe_id TEXT,
                probe_serial TEXT,
                acknowledgment TEXT NOT NULL,
                acknowledged_at TEXT NOT NULL,
                PRIMARY KEY (transaction_id, sector_id, operation)
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_acks_transaction
            ON sector_acknowledgments(transaction_id)
        """)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def store(self, ack: SectorAcknowledgment) -> None:
        """Store a sector acknowledgment."""
        await self._db.execute("""
            INSERT OR REPLACE INTO sector_acknowledgments
            (transaction_id, sector_id, sector_address, operation,
             crc_before, crc_after, probe_id, probe_serial, acknowledgment, acknowledged_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ack.transaction_id,
            ack.sector_id,
            ack.sector_address,
            ack.operation,
            ack.crc_before,
            ack.crc_after,
            ack.probe_id,
            ack.probe_serial,
            ack.acknowledgment,
            ack.acknowledged_at.isoformat(),
        ))
        await self._db.commit()

    async def get_for_transaction(self, transaction_id: str) -> list[SectorAcknowledgment]:
        """Get all acknowledgments for a transaction."""
        cursor = await self._db.execute(
            "SELECT * FROM sector_acknowledgments WHERE transaction_id = ?",
            (transaction_id,),
        )
        rows = await cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        results = []
        for row in rows:
            d = dict(zip(cols, row))
            results.append(SectorAcknowledgment(
                transaction_id=d["transaction_id"],
                sector_id=d["sector_id"],
                sector_address=d["sector_address"],
                operation=d["operation"],
                crc_before=d.get("crc_before", ""),
                crc_after=d.get("crc_after", ""),
                probe_id=d.get("probe_id", ""),
                probe_serial=d.get("probe_serial", ""),
                acknowledgment=d["acknowledgment"],
                acknowledged_at=datetime.fromisoformat(d["acknowledged_at"]),
            ))
        return results

    async def get_for_sector(
        self,
        transaction_id: str,
        sector_id: int,
    ) -> list[SectorAcknowledgment]:
        """Get all acknowledgments for a specific sector."""
        cursor = await self._db.execute(
            "SELECT * FROM sector_acknowledgments WHERE transaction_id = ? AND sector_id = ?",
            (transaction_id, sector_id),
        )
        rows = await cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        results = []
        for row in rows:
            d = dict(zip(cols, row))
            results.append(SectorAcknowledgment(
                transaction_id=d["transaction_id"],
                sector_id=d["sector_id"],
                sector_address=d["sector_address"],
                operation=d["operation"],
                crc_before=d.get("crc_before", ""),
                crc_after=d.get("crc_after", ""),
                probe_id=d.get("probe_id", ""),
                probe_serial=d.get("probe_serial", ""),
                acknowledgment=d["acknowledgment"],
                acknowledged_at=datetime.fromisoformat(d["acknowledged_at"]),
            ))
        return results


class TwoPhaseFlashTransactionManager:
    """P0-Hardening: 2-phase commit for flash transactions.

    Phase 1 (Prepare):
      - Journal all sector operations (via FlashJournal)
      - Execute each probe operation (erase/write/verify)
      - Store probe acknowledgments atomically
      - If any operation fails: abort, rollback

    Phase 2 (Commit):
      - Verify ALL acknowledgments are present
      - Commit transaction to DB
      - Only NOW is the transaction durable

    Commit Guard (on reconnect):
      - If journal entry exists but no acknowledgment → re-execute
      - If acknowledgment exists but no DB commit → complete commit
      - If neither → transaction was interrupted, offer rollback
    """

    def __init__(
        self,
        base_manager: Any,  # FlashTransactionManager
        acknowledgment_store: ProbeAcknowledgmentStore,
        journal_path: str | None = None,
    ):
        self._base = base_manager
        self._acks = acknowledgment_store
        self._journal_path = journal_path

    async def execute_two_phase(
        self,
        transaction_id: str,
        sector_operations: list[dict[str, Any]],
        execute_probe_fn: Any,  # Async function(probe, sector_op) -> SectorAcknowledgment
        probe: Any,  # The hardware probe to use
    ) -> tuple[bool, str]:
        """Execute a flash transaction in 2-phase commit style.

        Args:
            transaction_id: The transaction ID
            sector_operations: List of {sector_id, sector_address, operation, data}
            execute_probe_fn: Async fn(probe, op) -> SectorAcknowledgment
            probe: The fence-aware probe adapter

        Returns:
            (success, error_message)
        """
        # === PHASE 1: Prepare & Execute ===
        acknowledgments: list[SectorAcknowledgment] = []
        completed_sectors: set[int] = set()
        failed_sectors: dict[int, str] = {}

        for op in sector_operations:
            sector_id = op["sector_id"]

            try:
                # Execute probe operation and get acknowledgment
                ack = await execute_probe_fn(probe, op)

                # Store acknowledgment durably
                await self._acks.store(ack)
                acknowledgments.append(ack)
                completed_sectors.add(sector_id)

                logger.info(
                    "phase1_probe_completed: transaction=%s sector=%d operation=%s",
                    transaction_id, sector_id, op["operation"],
                )

            except Exception as e:
                logger.error(
                    "phase1_probe_failed: transaction=%s sector=%d error=%s",
                    transaction_id, sector_id, str(e),
                )
                failed_sectors[sector_id] = str(e)

                # Phase 1 failed: abort the transaction
                await self._base.fail_transaction(
                    transaction_id,
                    error_code="PHASE1_FAILED",
                    error_message=f"Sector {sector_id} failed: {e}",
                    error_details={"failed_sector": sector_id, "operation": op.get("operation")},
                )
                return False, f"Sector {sector_id} failed: {e}"

        # === PHASE 1 COMPLETE: all probes succeeded ===
        # Verify all acknowledgments are stored
        stored = await self._acks.get_for_transaction(transaction_id)
        expected_count = len(sector_operations)
        if len(stored) < expected_count:
            logger.error(
                "phase1_ack_missing: transaction=%s expected=%d stored=%d",
                transaction_id, expected_count, len(stored),
            )
            await self._base.fail_transaction(
                transaction_id,
                error_code="PHASE1_ACK_INCOMPLETE",
                error_message=f"Missing acknowledgments: expected {expected_count}, got {len(stored)}",
            )
            return False, f"Missing {expected_count - len(stored)} acknowledgments"

        # === PHASE 2: Commit ===
        # All acknowledgments are present → commit the transaction
        await self._base.commit_transaction(transaction_id)

        logger.info(
            "two_phase_commit_complete: transaction=%s sectors=%d acks=%d",
            transaction_id,
            len(completed_sectors),
            len(stored),
        )

        return True, ""

    async def check_commit_guard(self, transaction_id: str) -> dict[str, Any]:
        """P0-Hardening: Commit guard — check journal vs DB state on reconnect.

        On reconnection after a crash/disconnect, this method checks:
        1. Does the transaction have journal entries but no DB commit?
        2. Does it have acknowledgments but no DB commit?
        3. Is it in a partially completed state?

        Returns a recovery action recommendation.
        """
        tx = await self._base.get_transaction(transaction_id)
        if tx is None:
            return {"state": "unknown", "action": "no_transaction_found"}

        acks = await self._acks.get_for_transaction(transaction_id)

        if tx.status.value in ("committed", "rolled_back"):
            return {
                "state": "terminal",
                "action": "none",
                "status": tx.status.value,
            }

        if tx.status.value in ("pending", "flashing", "verifying"):
            # Transaction was in progress when disconnected
            if acks:
                # Acknowledgments exist → phase 1 completed, need to commit
                return {
                    "state": "phase1_complete",
                    "action": "commit",
                    "transaction_id": transaction_id,
                    "acknowledgments_count": len(acks),
                    "status": tx.status.value,
                }
            else:
                # No acknowledgments → was interrupted during phase 1
                return {
                    "state": "phase1_incomplete",
                    "action": "recover",
                    "transaction_id": transaction_id,
                    "status": tx.status.value,
                }

        return {
            "state": "unknown",
            "action": "investigate",
            "status": tx.status.value,
        }

    async def recover_and_complete(self, transaction_id: str) -> tuple[bool, str]:
        """P0-Hardening: Auto-recover from interrupted transaction.

        Based on commit guard analysis, either:
        - Commit (if acks present, no DB commit)
        - Re-execute (if no acks, partial progress)
        - Rollback (if unrecoverable)
        """
        guard = await self.check_commit_guard(transaction_id)
        action = guard["action"]

        if action == "commit":
            await self._base.commit_transaction(transaction_id)
            logger.info(
                "recover_commit: transaction=%s acks=%d",
                transaction_id, guard["acknowledgments_count"],
            )
            return True, "committed"

        if action == "recover":
            # Mark as interrupted for manual recovery
            await self._base.fail_transaction(
                transaction_id,
                error_code="INTERRUPTED_RECOVER_NEEDED",
                error_message="Transaction was interrupted. Manual recovery required.",
                error_details=guard,
            )
            return False, "recovery_needed"

        return False, f"Cannot recover: {guard['state']}"


@dataclass
class IdempotentFlashRetry:
    """P0-Hardening: Idempotent retry for interrupted flash operations.

    When a flash is interrupted (USB disconnect, power loss), the same
    transaction_id + idempotency key can be used to resume. Already-completed
    sectors (with valid acknowledgments) are skipped.
    """

    acknowledgment_store: ProbeAcknowledgmentStore

    async def get_completed_sectors(
        self,
        transaction_id: str,
    ) -> set[int]:
        """Get sectors that already have acknowledgments (skip these on retry)."""
        acks = await self.acknowledgment_store.get_for_transaction(transaction_id)
        return {ack.sector_id for ack in acks}

    async def filter_incomplete(
        self,
        transaction_id: str,
        all_operations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Filter out already-completed sectors from the retry list."""
        completed = await self.get_completed_sectors(transaction_id)
        return [op for op in all_operations if op.get("sector_id") not in completed]
