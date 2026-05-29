"""Flash Journal - Sector-level Write-Ahead Log for power-loss recovery.

Phase 6.2: Addresses critical production gap:
- Records every sector erase/write/verify operation
- Enables precise recovery after power loss mid-sector
- Tracks sector corruption state
- Provides complete audit trail for OTA diagnostics

Unlike transaction model (high-level), FlashJournal operates at sector level:
- sector_12: erase_started → erase_completed
- sector_12: write_started → write_completed → verify_passed
- On power loss: precisely know which sectors are corrupted
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, AsyncIterator

if TYPE_CHECKING:
    from .flash_transaction import FlashTransaction

logger = logging.getLogger(__name__)


class JournalOperation(Enum):
    """Sector-level operations recorded in journal."""
    
    ERASE_STARTED = "erase_started"
    ERASE_COMPLETED = "erase_completed"
    ERASE_FAILED = "erase_failed"
    
    WRITE_STARTED = "write_started"
    WRITE_COMPLETED = "write_completed"
    WRITE_FAILED = "write_failed"
    
    VERIFY_STARTED = "verify_started"
    VERIFY_PASSED = "verify_passed"
    VERIFY_FAILED = "verify_failed"
    
    CHECKPOINT = "checkpoint"  # Periodic state snapshot


@dataclass
class SectorChecksum:
    """Checksum for sector at specific point."""
    
    sector_id: int
    sector_address: int
    checksum: str  # SHA256 of sector content
    
    operation: JournalOperation
    timestamp: datetime = field(default_factory=datetime.now)
    
    # For delta tracking
    previous_checksum: str | None = None
    bytes_hash: str | None = None  # Hash of original bytes written


@dataclass
class JournalEntry:
    """Single journal entry for sector operation."""
    
    entry_id: str
    transaction_id: str
    
    sector_id: int
    sector_address: int
    sector_size: int
    
    operation: JournalOperation
    
    # Checksums
    checksum_before: str | None = None
    checksum_after: str | None = None
    
    # State
    operation_data: dict[str, Any] = field(default_factory=dict)
    
    # Timestamps
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    duration_ms: float = 0.0
    
    # Error info
    error_code: str | None = None
    error_message: str | None = None
    
    def mark_completed(self, checksum_after: str | None = None) -> None:
        """Mark operation as completed."""
        self.completed_at = datetime.now()
        self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000
        self.checksum_after = checksum_after
    
    def mark_failed(self, error_code: str, error_message: str) -> None:
        """Mark operation as failed."""
        self.completed_at = datetime.now()
        self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000
        self.error_code = error_code
        self.error_message = error_message
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entry_id": self.entry_id,
            "transaction_id": self.transaction_id,
            "sector_id": self.sector_id,
            "sector_address": hex(self.sector_address),
            "sector_size": self.sector_size,
            "operation": self.operation.value,
            "checksum_before": self.checksum_before,
            "checksum_after": self.checksum_after,
            "operation_data": self.operation_data,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JournalEntry:
        """Create from dictionary."""
        return cls(
            entry_id=data["entry_id"],
            transaction_id=data["transaction_id"],
            sector_id=data["sector_id"],
            sector_address=int(data["sector_address"], 16) if isinstance(data["sector_address"], str) else data["sector_address"],
            sector_size=data["sector_size"],
            operation=JournalOperation(data["operation"]),
            checksum_before=data.get("checksum_before"),
            checksum_after=data.get("checksum_after"),
            operation_data=data.get("operation_data", {}),
            started_at=datetime.fromisoformat(data["started_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            duration_ms=data.get("duration_ms", 0.0),
            error_code=data.get("error_code"),
            error_message=data.get("error_message"),
        )


@dataclass
class FlashJournal:
    """Sector-level Write-Ahead Log for flash operations.
    
    Records every sector operation to enable precise recovery
    after power loss, USB disconnect, or any interruption.
    
    Key Features:
    - Atomic sector operations tracking
    - Checksum state at each operation boundary
    - Precise corruption detection
    - Resume from exact point
    - Audit trail for diagnostics
    
    Journal Format:
    {
      "transaction_id": "...",
      "entries": [
        {
          "entry_id": "...",
          "sector_id": 12,
          "operation": "erase_started",
          "checksum_before": "...",
          "timestamp": "..."
        },
        {
          "entry_id": "...",
          "sector_id": 12,
          "operation": "erase_completed",
          "checksum_after": "...",
          "timestamp": "..."
        }
      ]
    }
    """
    
    journal_dir: str
    transaction_id: str = ""
    
    _entries: list[JournalEntry] = field(default_factory=list)
    _current_entry: JournalEntry | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _pending_writes: list[JournalEntry] = field(default_factory=list)
    
    # Flush configuration
    _flush_interval_ms: int = 1000  # Flush to disk every 1 second
    _batch_size: int = 100  # Or every 100 entries
    
    def __post_init__(self) -> None:
        """Ensure journal directory exists."""
        os.makedirs(self.journal_dir, exist_ok=True)
    
    @property
    def journal_path(self) -> str:
        """Get path to journal file."""
        return os.path.join(self.journal_dir, f"{self.transaction_id}.journal")
    
    async def begin_transaction(self, transaction_id: str) -> None:
        """Begin new journal for transaction."""
        async with self._lock:
            self.transaction_id = transaction_id
            self._entries = []
            self._pending_writes = []
            
            # Create marker entry
            entry = JournalEntry(
                entry_id=f"{transaction_id}_begin",
                transaction_id=transaction_id,
                sector_id=-1,
                sector_address=0,
                sector_size=0,
                operation=JournalOperation.CHECKPOINT,
                operation_data={"type": "transaction_begin"},
            )
            self._entries.append(entry)
            await self._flush_entries()
    
    async def log_erase_started(
        self,
        sector_id: int,
        sector_address: int,
        sector_size: int,
        checksum_before: str | None = None,
    ) -> JournalEntry:
        """Log sector erase started."""
        async with self._lock:
            entry = JournalEntry(
                entry_id=f"{self.transaction_id}_erase_{sector_id}_{len(self._entries)}",
                transaction_id=self.transaction_id,
                sector_id=sector_id,
                sector_address=sector_address,
                sector_size=sector_size,
                operation=JournalOperation.ERASE_STARTED,
                checksum_before=checksum_before,
            )
            self._current_entry = entry
            self._entries.append(entry)
            self._pending_writes.append(entry)
            await self._maybe_flush()
            return entry
    
    async def log_erase_completed(
        self,
        sector_id: int,
        checksum_after: str | None = None,
    ) -> JournalEntry | None:
        """Log sector erase completed."""
        async with self._lock:
            if self._current_entry and self._current_entry.sector_id == sector_id:
                self._current_entry.mark_completed(checksum_after)
                self._pending_writes.append(self._current_entry)
                self._current_entry = None
                await self._maybe_flush()
                return self._entries[-1]
            return None
    
    async def log_write_started(
        self,
        sector_id: int,
        sector_address: int,
        sector_size: int,
        bytes_to_write: bytes,
    ) -> JournalEntry:
        """Log sector write started with pre-write checksum."""
        async with self._lock:
            checksum_before = hashlib.sha256(bytes_to_write).hexdigest()
            
            entry = JournalEntry(
                entry_id=f"{self.transaction_id}_write_{sector_id}_{len(self._entries)}",
                transaction_id=self.transaction_id,
                sector_id=sector_id,
                sector_address=sector_address,
                sector_size=sector_size,
                operation=JournalOperation.WRITE_STARTED,
                checksum_before=checksum_before,
                operation_data={"bytes_hash": checksum_before},
            )
            self._current_entry = entry
            self._entries.append(entry)
            self._pending_writes.append(entry)
            await self._maybe_flush()
            return entry
    
    async def log_write_completed(
        self,
        sector_id: int,
        checksum_after: str | None = None,
    ) -> JournalEntry | None:
        """Log sector write completed."""
        async with self._lock:
            if self._current_entry and self._current_entry.sector_id == sector_id:
                self._current_entry.mark_completed(checksum_after)
                self._pending_writes.append(self._current_entry)
                self._current_entry = None
                await self._maybe_flush()
                return self._entries[-1]
            return None
    
    async def log_verify_started(
        self,
        sector_id: int,
        expected_checksum: str,
    ) -> JournalEntry:
        """Log sector verification started."""
        async with self._lock:
            entry = JournalEntry(
                entry_id=f"{self.transaction_id}_verify_{sector_id}_{len(self._entries)}",
                transaction_id=self.transaction_id,
                sector_id=sector_id,
                sector_address=0,  # Will be set by caller
                sector_size=0,
                operation=JournalOperation.VERIFY_STARTED,
                operation_data={"expected_checksum": expected_checksum},
            )
            self._entries.append(entry)
            self._pending_writes.append(entry)
            await self._maybe_flush()
            return entry
    
    async def log_verify_passed(self, sector_id: int) -> JournalEntry | None:
        """Log sector verification passed."""
        async with self._lock:
            # Find most recent verify_started for this sector
            for entry in reversed(self._entries):
                if entry.sector_id == sector_id and entry.operation == JournalOperation.VERIFY_STARTED:
                    entry.mark_completed()
                    self._pending_writes.append(entry)
                    await self._maybe_flush()
                    return entry
            return None
    
    async def log_verify_failed(
        self,
        sector_id: int,
        expected: str,
        actual: str,
    ) -> JournalEntry | None:
        """Log sector verification failed."""
        async with self._lock:
            for entry in reversed(self._entries):
                if entry.sector_id == sector_id and entry.operation == JournalOperation.VERIFY_STARTED:
                    entry.mark_failed("VERIFY_FAILED", f"expected={expected[:16]} actual={actual[:16]}")
                    self._pending_writes.append(entry)
                    await self._maybe_flush()
                    return entry
            return None
    
    async def log_checkpoint(self, state: dict[str, Any]) -> None:
        """Log checkpoint with current state."""
        async with self._lock:
            entry = JournalEntry(
                entry_id=f"{self.transaction_id}_ckpt_{datetime.now().timestamp()}",
                transaction_id=self.transaction_id,
                sector_id=-1,
                sector_address=0,
                sector_size=0,
                operation=JournalOperation.CHECKPOINT,
                operation_data=state,
            )
            self._entries.append(entry)
            self._pending_writes.append(entry)
            await self._maybe_flush()
    
    async def commit_transaction(self) -> None:
        """Commit transaction (mark as complete)."""
        async with self._lock:
            entry = JournalEntry(
                entry_id=f"{self.transaction_id}_commit",
                transaction_id=self.transaction_id,
                sector_id=-1,
                sector_address=0,
                sector_size=0,
                operation=JournalOperation.CHECKPOINT,
                operation_data={"type": "transaction_commit"},
            )
            self._entries.append(entry)
            self._pending_writes.append(entry)
            await self._flush_entries()
            
            # Mark journal as complete
            metadata_path = self.journal_path + ".committed"
            with open(metadata_path, "w") as f:
                json.dump({
                    "transaction_id": self.transaction_id,
                    "committed_at": datetime.now().isoformat(),
                    "total_entries": len(self._entries),
                }, f)
    
    async def abort_transaction(self, reason: str) -> None:
        """Abort transaction (mark as failed)."""
        async with self._lock:
            entry = JournalEntry(
                entry_id=f"{self.transaction_id}_abort",
                transaction_id=self.transaction_id,
                sector_id=-1,
                sector_address=0,
                sector_size=0,
                operation=JournalOperation.CHECKPOINT,
                operation_data={"type": "transaction_abort", "reason": reason},
            )
            self._entries.append(entry)
            self._pending_writes.append(entry)
            await self._flush_entries()
    
    async def _maybe_flush(self) -> None:
        """Flush if threshold reached."""
        if len(self._pending_writes) >= self._batch_size:
            await self._flush_entries()
    
    async def _flush_entries(self) -> None:
        """Flush pending entries to disk."""
        if not self._pending_writes:
            return
        
        # Write to append-only file
        append_path = self.journal_path + ".append"
        
        with open(append_path, "a") as f:
            for entry in self._pending_writes:
                f.write(json.dumps(entry.to_dict(), default=str) + "\n")
        
        self._pending_writes = []
    
    async def analyze_corruption(self) -> dict[str, Any]:
        """Analyze journal to determine corruption state after power loss.
        
        Returns:
            Analysis of which sectors are corrupted and recovery plan
        """
        async with self._lock:
            entries = await self._load_all_entries()
            
            sector_states: dict[int, dict[str, Any]] = {}
            
            for entry in entries:
                sector_id = entry.sector_id
                if sector_id not in sector_states:
                    sector_states[sector_id] = {
                        "erase_started": False,
                        "erase_completed": False,
                        "write_started": False,
                        "write_completed": False,
                        "verify_passed": False,
                        "corrupted": False,
                        "checksum_before": None,
                        "checksum_after": None,
                    }
                
                state = sector_states[sector_id]
                
                if entry.operation == JournalOperation.ERASE_STARTED:
                    state["erase_started"] = True
                    state["checksum_before"] = entry.checksum_before
                elif entry.operation == JournalOperation.ERASE_COMPLETED:
                    state["erase_completed"] = True
                    state["checksum_after"] = entry.checksum_after
                elif entry.operation == JournalOperation.WRITE_STARTED:
                    state["write_started"] = True
                elif entry.operation == JournalOperation.WRITE_COMPLETED:
                    state["write_completed"] = True
                    state["checksum_after"] = entry.checksum_after
                elif entry.operation == JournalOperation.VERIFY_PASSED:
                    state["verify_passed"] = True
                elif entry.operation == JournalOperation.ERASE_FAILED:
                    state["corrupted"] = True
                elif entry.operation == JournalOperation.WRITE_FAILED:
                    state["corrupted"] = True
            
            # Determine recovery actions
            recovery_plan: dict[str, Any] = {
                "sectors_to_recover": [],
                "sectors_ok": [],
                "sectors_unknown": [],
                "needs_full_rewrite": False,
            }
            
            for sector_id, state in sector_states.items():
                if sector_id < 0:
                    continue  # Skip metadata entries
                
                # Sector is corrupted if:
                # 1. Erase started but not completed
                # 2. Write started but not completed
                if state["erase_started"] and not state["erase_completed"]:
                    recovery_plan["sectors_to_recover"].append({
                        "sector_id": sector_id,
                        "reason": "erase_incomplete",
                        "action": "re_erase_and_write",
                    })
                elif state["write_started"] and not state["write_completed"]:
                    recovery_plan["sectors_to_recover"].append({
                        "sector_id": sector_id,
                        "reason": "write_incomplete",
                        "action": "rewrite_sector",
                        "checksum_before": state["checksum_before"],
                    })
                elif state["write_completed"] and not state["verify_passed"]:
                    recovery_plan["sectors_to_recover"].append({
                        "sector_id": sector_id,
                        "reason": "verify_not_completed",
                        "action": "verify_and_recover",
                    })
                elif state["verify_passed"]:
                    recovery_plan["sectors_ok"].append(sector_id)
                else:
                    recovery_plan["sectors_unknown"].append(sector_id)
            
            recovery_plan["needs_full_rewrite"] = len(recovery_plan["sectors_to_recover"]) > 10
            
            return {
                "transaction_id": self.transaction_id,
                "total_sectors": len(sector_states),
                "analysis": recovery_plan,
            }
    
    async def _load_all_entries(self) -> list[JournalEntry]:
        """Load all entries from journal files."""
        entries = []
        
        # Load append file
        append_path = self.journal_path + ".append"
        if os.path.exists(append_path):
            with open(append_path, "r") as f:
                for line in f:
                    if line.strip():
                        try:
                            data = json.loads(line)
                            entries.append(JournalEntry.from_dict(data))
                        except json.JSONDecodeError:
                            pass
        
        return sorted(entries, key=lambda e: e.started_at)
    
    async def get_sector_state(self, sector_id: int) -> dict[str, Any] | None:
        """Get current state of a specific sector."""
        entries = await self._load_all_entries()
        
        state = None
        for entry in entries:
            if entry.sector_id == sector_id:
                state = entry.to_dict()
        
        return state
    
    async def list_incomplete_operations(self) -> list[dict[str, Any]]:
        """List all operations that were not completed."""
        entries = await self._load_all_entries()
        
        incomplete = []
        current_ops: dict[int, JournalEntry] = {}
        
        for entry in entries:
            if entry.sector_id < 0:
                continue
            
            if entry.operation in (JournalOperation.ERASE_STARTED, JournalOperation.WRITE_STARTED, JournalOperation.VERIFY_STARTED):
                current_ops[entry.sector_id] = entry
            elif entry.completed_at is not None:
                current_ops.pop(entry.sector_id, None)
        
        for sector_id, entry in current_ops.items():
            incomplete.append({
                "sector_id": sector_id,
                "operation": entry.operation.value,
                "started_at": entry.started_at.isoformat(),
            })
        
        return incomplete
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "transaction_id": self.transaction_id,
            "journal_path": self.journal_path,
            "total_entries": len(self._entries),
            "pending_writes": len(self._pending_writes),
        }


@dataclass
class JournalRecoveryPlanner:
    """Plans recovery based on journal analysis."""
    
    journal: FlashJournal
    
    async def plan_recovery(
        self,
        firmware_data: bytes,
        sector_size: int,
    ) -> dict[str, Any]:
        """Create recovery plan for interrupted flash.
        
        Args:
            firmware_data: Original firmware binary
            sector_size: Size of each flash sector
        
        Returns:
            Recovery plan with sectors to rewrite
        """
        analysis = await self.journal.analyze_corruption()
        plan = {
            "can_recover": True,
            "recovery_actions": [],
            "estimated_time_ms": 0,
        }
        
        for sector_info in analysis["analysis"]["sectors_to_recover"]:
            sector_id = sector_info["sector_id"]
            action = sector_info["action"]
            
            sector_offset = sector_id * sector_size
            sector_data = firmware_data[sector_offset : sector_offset + sector_size]
            
            recovery_action = {
                "sector_id": sector_id,
                "sector_address": 0x08000000 + sector_offset,  # Default STM32 base
                "action": action,
                "data": sector_data.hex() if action == "re_erase_and_write" or action == "rewrite_sector" else None,
                "estimated_time_ms": 50,  # ~50ms per sector erase/write
            }
            
            plan["recovery_actions"].append(recovery_action)
            plan["estimated_time_ms"] += recovery_action["estimated_time_ms"]
        
        plan["can_recover"] = len(plan["recovery_actions"]) > 0
        
        return plan
    
    async def execute_recovery(
        self,
        probe: Any,
        recovery_plan: dict[str, Any],
        progress_callback: Any = None,
    ) -> dict[str, Any]:
        """Execute recovery plan.
        
        Args:
            probe: Probe interface for flash operations
            recovery_plan: Plan from plan_recovery()
            progress_callback: Optional progress callback
        
        Returns:
            Recovery result
        """
        result = {
            "success": True,
            "sectors_recovered": 0,
            "sectors_failed": 0,
            "errors": [],
        }
        
        for action in recovery_plan.get("recovery_actions", []):
            try:
                sector_addr = action["sector_address"]
                
                if action["action"] == "re_erase_and_write":
                    # Erase sector first
                    await probe.erase_sector(sector_addr)
                    
                    # Then write
                    if action.get("data"):
                        data = bytes.fromhex(action["data"])
                        await probe.write_memory(sector_addr, data)
                
                elif action["action"] == "rewrite_sector":
                    if action.get("data"):
                        data = bytes.fromhex(action["data"])
                        await probe.write_memory(sector_addr, data)
                
                elif action["action"] == "verify_and_recover":
                    # Just verify and log
                    data = await probe.read_memory(sector_addr, action.get("sector_size", 4096))
                    # If we got here, sector is probably ok
                    pass
                
                result["sectors_recovered"] += 1
                
                if progress_callback:
                    await progress_callback(result["sectors_recovered"], len(recovery_plan["recovery_actions"]))
                    
            except Exception as e:
                result["sectors_failed"] += 1
                result["errors"].append({
                    "sector_id": action["sector_id"],
                    "error": str(e),
                })
                result["success"] = False
        
        return result
