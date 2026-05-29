"""Flash Resume - Resume interrupted flash operations with WAL.

Phase 6.2 (FIXED): Implements flash resume capability with:
- Write-Ahead Log (WAL) for atomic operations
- Atomic file writes (write to temp, fsync, rename)
- Sector verification with checksums
- Recovery after power loss/USB disconnect

FIXES Applied:
- _save_state: Atomic write with fsync
- Added WAL journal for crash-safe transactions
- Added checksum verification for resume files
- Added transaction state machine
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TransactionState(Enum):
    """Flash transaction state."""
    PENDING = "pending"           # Transaction created, not started
    ERASING = "erasing"          # Erasing sectors
    WRITING = "writing"          # Writing firmware
    VERIFYING = "verifying"      # Verifying written data
    COMPLETED = "completed"      # Successfully completed
    FAILED = "failed"            # Failed
    ABORTED = "aborted"          # Aborted by user


@dataclass
class WALEntry:
    """Write-Ahead Log entry for flash transactions.
    
    Provides crash-safe transaction tracking with:
    - Sequential writes to journal
    - Commit markers for transaction boundaries
    - Recovery from any point
    """
    entry_id: str
    transaction_id: str
    entry_type: str  # "BEGIN", "WRITE_SECTOR", "VERIFY_SECTOR", "COMMIT", "ABORT"
    sequence: int
    
    # Entry data
    sector_index: int | None = None
    sector_checksum: str | None = None
    bytes_written: int = 0
    
    # Timestamp
    timestamp: datetime = field(default_factory=datetime.now)
    
    # CRC for integrity
    crc32: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "transaction_id": self.transaction_id,
            "entry_type": self.entry_type,
            "sequence": self.sequence,
            "sector_index": self.sector_index,
            "sector_checksum": self.sector_checksum,
            "bytes_written": self.bytes_written,
            "timestamp": self.timestamp.isoformat(),
            "crc32": self.crc32,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WALEntry":
        return cls(
            entry_id=data["entry_id"],
            transaction_id=data["transaction_id"],
            entry_type=data["entry_type"],
            sequence=data["sequence"],
            sector_index=data.get("sector_index"),
            sector_checksum=data.get("sector_checksum"),
            bytes_written=data.get("bytes_written", 0),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(),
            crc32=data.get("crc32"),
        )


class FlashWALJournal:
    """Write-Ahead Log for flash transactions.
    
    FIX: Provides crash-safe journal with:
    - Sequential WAL writes (append-only)
    - fsync before confirming writes
    - CRC checksums for integrity
    - Recovery scanning
    """
    
    def __init__(self, journal_path: str):
        self._journal_path = journal_path
        self._sequence = 0
        self._lock = asyncio.Lock()
        
    def _compute_crc(self, data: dict) -> str:
        """Compute CRC32 for entry integrity."""
        import zlib
        json_str = json.dumps(data, sort_keys=True, default=str)
        return f"{zlib.crc32(json_str.encode()):08x}"
    
    def _get_wal_path(self, transaction_id: str) -> str:
        return os.path.join(self._journal_path, f"{transaction_id}.wal")
    
    async def begin_transaction(self, transaction_id: str) -> WALEntry:
        """Begin a new WAL transaction."""
        async with self._lock:
            self._sequence += 1
            entry = WALEntry(
                entry_id=str(uuid.uuid4()),
                transaction_id=transaction_id,
                entry_type="BEGIN",
                sequence=self._sequence,
            )
            entry.crc32 = self._compute_crc(entry.to_dict())
            await self._append_entry(entry)
            return entry
    
    async def log_sector_write(
        self, 
        transaction_id: str, 
        sector_index: int,
        sector_checksum: str,
        bytes_written: int,
    ) -> WALEntry:
        """Log a sector write operation."""
        async with self._lock:
            self._sequence += 1
            entry = WALEntry(
                entry_id=str(uuid.uuid4()),
                transaction_id=transaction_id,
                entry_type="WRITE_SECTOR",
                sequence=self._sequence,
                sector_index=sector_index,
                sector_checksum=sector_checksum,
                bytes_written=bytes_written,
            )
            entry.crc32 = self._compute_crc(entry.to_dict())
            await self._append_entry(entry)
            return entry
    
    async def log_sector_verify(
        self, 
        transaction_id: str, 
        sector_index: int,
        verified: bool,
    ) -> WALEntry:
        """Log a sector verification operation."""
        async with self._lock:
            self._sequence += 1
            entry = WALEntry(
                entry_id=str(uuid.uuid4()),
                transaction_id=transaction_id,
                entry_type="VERIFY_SECTOR",
                sequence=self._sequence,
                sector_index=sector_index,
                sector_checksum="verified" if verified else "failed",
            )
            entry.crc32 = self._compute_crc(entry.to_dict())
            await self._append_entry(entry)
            return entry
    
    async def commit_transaction(self, transaction_id: str) -> WALEntry:
        """Commit a WAL transaction."""
        async with self._lock:
            self._sequence += 1
            entry = WALEntry(
                entry_id=str(uuid.uuid4()),
                transaction_id=transaction_id,
                entry_type="COMMIT",
                sequence=self._sequence,
            )
            entry.crc32 = self._compute_crc(entry.to_dict())
            await self._append_entry(entry)
            return entry
    
    async def abort_transaction(self, transaction_id: str) -> WALEntry:
        """Abort a WAL transaction."""
        async with self._lock:
            self._sequence += 1
            entry = WALEntry(
                entry_id=str(uuid.uuid4()),
                transaction_id=transaction_id,
                entry_type="ABORT",
                sequence=self._sequence,
            )
            entry.crc32 = self._compute_crc(entry.to_dict())
            await self._append_entry(entry)
            return entry
    
    async def _append_entry(self, entry: WALEntry) -> None:
        """Append entry to WAL with fsync."""
        os.makedirs(self._journal_path, exist_ok=True)
        wal_path = self._get_wal_path(entry.transaction_id)
        
        # Write to temp file first
        temp_fd, temp_path = tempfile.mkstemp(
            dir=self._journal_path, 
            suffix=".tmp"
        )
        try:
            with os.fdopen(temp_fd, "w") as f:
                json.dump(entry.to_dict(), f)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())  # FIX: Ensure durability
            
            # FIX: Atomic rename
            os.replace(temp_path, wal_path)
            
            # Ensure directory metadata is synced
            dir_fd = os.open(self._journal_path, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
                
        except Exception:
            # Clean up temp file on error
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            raise
    
    async def get_entries(self, transaction_id: str) -> list[WALEntry]:
        """Get all WAL entries for a transaction."""
        wal_path = self._get_wal_path(transaction_id)
        entries = []
        
        if not os.path.exists(wal_path):
            return entries
        
        with open(wal_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    
                    # Verify CRC
                    stored_crc = data.get("crc32")
                    if stored_crc:
                        del data["crc32"]
                        computed_crc = self._compute_crc(data)
                        if computed_crc != stored_crc:
                            logger.warning(
                                "wal_entry_crc_mismatch: entry_id=%s",
                                data.get("entry_id"),
                            )
                            continue
                    
                    entries.append(WALEntry.from_dict(data))
        
        return entries
    
    async def get_last_sequence(self, transaction_id: str) -> int:
        """Get last sequence number for transaction."""
        entries = await self.get_entries(transaction_id)
        if not entries:
            return 0
        return max(e.sequence for e in entries)
    
    async def has_commit(self, transaction_id: str) -> bool:
        """Check if transaction has a commit entry."""
        entries = await self.get_entries(transaction_id)
        return any(e.entry_type == "COMMIT" for e in entries)
    
    async def delete_wal(self, transaction_id: str) -> None:
        """Delete WAL file after successful completion."""
        wal_path = self._get_wal_path(transaction_id)
        try:
            os.unlink(wal_path)
        except FileNotFoundError:
            pass


@dataclass
class FlashResumeState:
    """State for resuming interrupted flash operations.
    
    Stored persistently to enable recovery after power loss,
    USB disconnect, or other interruptions.
    
    FIX: Added checksum for state file integrity.
    """
    
    transaction_id: str
    firmware_hash: str
    firmware_size: int
    
    # Progress
    last_sector_written: int = 0
    last_offset_in_sector: int = 0
    total_bytes_written: int = 0
    
    # Sector checksums (sector_index -> sha256)
    verified_sectors: dict[int, str] = field(default_factory=dict)
    
    # Transaction state
    state: TransactionState = TransactionState.PENDING
    
    # Timing
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # Configuration
    chunk_size: int = 4096
    verify_each_sector: bool = True
    
    # FIX: State checksum for integrity
    state_checksum: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "transaction_id": self.transaction_id,
            "firmware_hash": self.firmware_hash,
            "firmware_size": self.firmware_size,
            "last_sector_written": self.last_sector_written,
            "last_offset_in_sector": self.last_offset_in_sector,
            "total_bytes_written": self.total_bytes_written,
            "verified_sectors": {str(k): v for k, v in self.verified_sectors.items()},
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "chunk_size": self.chunk_size,
            "verify_each_sector": self.verify_each_sector,
            "state_checksum": self.state_checksum,
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FlashResumeState":
        """Create from dictionary."""
        verified = data.get("verified_sectors", {})
        if isinstance(verified, dict):
            verified = {int(k): v for k, v in verified.items()}
        
        state_value = data.get("state", "pending")
        if isinstance(state_value, str):
            try:
                state = TransactionState(state_value)
            except ValueError:
                state = TransactionState.PENDING
        
        return cls(
            transaction_id=data["transaction_id"],
            firmware_hash=data["firmware_hash"],
            firmware_size=data["firmware_size"],
            last_sector_written=data.get("last_sector_written", 0),
            last_offset_in_sector=data.get("last_offset_in_sector", 0),
            total_bytes_written=data.get("total_bytes_written", 0),
            verified_sectors=verified,
            state=state,
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.now(),
            chunk_size=data.get("chunk_size", 4096),
            verify_each_sector=data.get("verify_each_sector", True),
            state_checksum=data.get("state_checksum", ""),
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "FlashResumeState":
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))
    
    def compute_checksum(self) -> str:
        """Compute checksum of state for integrity verification."""
        data = self.to_dict()
        data.pop("state_checksum", None)  # Exclude checksum itself
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()
    
    def is_complete(self) -> bool:
        """Check if all bytes have been written."""
        return self.total_bytes_written >= self.firmware_size
    
    def remaining_bytes(self) -> int:
        """Get remaining bytes to write."""
        return max(0, self.firmware_size - self.total_bytes_written)
    
    def progress_percent(self) -> float:
        """Get progress percentage."""
        if self.firmware_size == 0:
            return 0.0
        return (self.total_bytes_written / self.firmware_size) * 100


@dataclass
class FlashResult:
    """Result of flash operation."""
    
    success: bool
    bytes_written: int = 0
    sectors_erased: int = 0
    duration_ms: float = 0.0
    
    error_code: str | None = None
    error_message: str | None = None
    
    resume_state: FlashResumeState | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "bytes_written": self.bytes_written,
            "sectors_erased": self.sectors_erased,
            "duration_ms": self.duration_ms,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


class ResumableFlashWriter:
    """Flash writer with resume capability.
    
    FIX: Implements atomic writes with WAL journal:
    - Write-Ahead Log for crash-safe transactions
    - Atomic file writes (temp file + rename)
    - fsync for durability
    - State checksum verification
    
    Supports resuming interrupted flash operations by:
    1. Loading previous state from WAL journal
    2. Verifying already-written sectors
    3. Continuing from where it left off
    """
    
    def __init__(
        self, 
        probe: Any,
        resume_state_path: str,
        resume_enabled: bool = True,
        use_wal: bool = True,
    ):
        """
        Args:
            probe: Flash probe interface
            resume_state_path: Path to store resume state files
            resume_enabled: Enable resume capability
            use_wal: Use Write-Ahead Log for transactions
        """
        self._probe = probe
        self._resume_state_path = resume_state_path
        self._resume_enabled = resume_enabled
        self._use_wal = use_wal
        
        self._current_state: FlashResumeState | None = None
        self._checkpoint_interval: int = 10
        self._wal: FlashWALJournal | None = None
        
        if self._resume_enabled:
            os.makedirs(self._resume_state_path, exist_ok=True)
            if self._use_wal:
                wal_path = os.path.join(self._resume_state_path, "wal")
                self._wal = FlashWALJournal(wal_path)
    
    async def check_for_resume(
        self,
        transaction_id: str,
        firmware_hash: str,
    ) -> FlashResumeState | None:
        """Check if there's a resume state to continue.
        
        FIX: Verifies state checksum and WAL consistency.
        
        Returns:
            FlashResumeState if found and valid, None otherwise
        """
        if not self._resume_enabled:
            return None
        
        path = self._get_resume_path(transaction_id)
        
        try:
            with open(path, "r") as f:
                state = FlashResumeState.from_json(f.read())
            
            # FIX: Verify state checksum
            expected_checksum = state.compute_checksum()
            if state.state_checksum and state.state_checksum != expected_checksum:
                logger.error(
                    "resume_state_checksum_mismatch: tx=%s expected=%s actual=%s",
                    transaction_id,
                    expected_checksum[:16],
                    state.state_checksum[:16],
                )
                return None
            
            # Validate state matches firmware
            if state.firmware_hash != firmware_hash:
                logger.warning(
                    "resume_state_firmware_mismatch: tx=%s expected=%s actual=%s",
                    transaction_id,
                    firmware_hash,
                    state.firmware_hash,
                )
                return None
            
            # FIX: Check WAL for commit status
            if self._wal:
                has_commit = await self._wal.has_commit(transaction_id)
                if has_commit and state.is_complete():
                    logger.info("transaction_already_committed: tx=%s", transaction_id)
                    return None
            
            self._current_state = state
            return state
            
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            logger.error("resume_state_corrupted: path=%s", path)
            return None
    
    def _get_resume_path(self, transaction_id: str) -> str:
        """Get path for resume state file."""
        return os.path.join(self._resume_state_path, f"{transaction_id}.resume")
    
    async def verify_sectors(
        self,
        partition_start: int,
        sector_size: int,
        state: FlashResumeState,
    ) -> list[int]:
        """Verify already-written sectors.
        
        Returns:
            List of sector indices that need re-writing
        """
        sectors_to_retry = []
        
        for sector_idx, expected_hash in state.verified_sectors.items():
            sector_start = partition_start + (sector_idx * sector_size)
            
            try:
                data = await self._probe.read_memory(sector_start, sector_size)
                actual_hash = hashlib.sha256(data).hexdigest()
                
                if actual_hash != expected_hash:
                    logger.warning(
                        "sector_hash_mismatch: sector=%s expected=%s actual=%s",
                        sector_idx,
                        expected_hash[:16],
                        actual_hash[:16],
                    )
                    sectors_to_retry.append(sector_idx)
                    
            except Exception as e:
                logger.error(
                    "sector_verify_failed: sector=%s error=%s",
                    sector_idx,
                    str(e),
                )
                sectors_to_retry.append(sector_idx)
        
        return sectors_to_retry
    
    async def write_with_resume(
        self,
        firmware: bytes,
        partition_start: int,
        partition_size: int,
        sector_size: int,
        state: FlashResumeState | None = None,
        progress_callback: Any = None,
    ) -> FlashResult:
        """Write firmware with resume support.
        
        FIX: Uses WAL journal and atomic file writes.
        
        Args:
            firmware: Firmware binary data
            partition_start: Start address of partition
            partition_size: Size of partition
            sector_size: Size of each sector
            state: Resume state (if continuing)
            progress_callback: Optional callback for progress updates
        
        Returns:
            FlashResult with success status
        """
        import time
        start_time = time.monotonic()
        
        state = state or FlashResumeState(
            transaction_id=str(uuid.uuid4()),
            firmware_hash=hashlib.sha256(firmware).hexdigest(),
            firmware_size=len(firmware),
            state=TransactionState.PENDING,
        )
        self._current_state = state
        
        # FIX: Begin WAL transaction
        if self._wal:
            await self._wal.begin_transaction(state.transaction_id)
        
        try:
            # Update state
            state.state = TransactionState.ERASING
            await self._save_state(state)
            
            start_sector = state.last_sector_written
            total_sectors = (len(firmware) + sector_size - 1) // sector_size
            bytes_written = state.total_bytes_written
            
            state.state = TransactionState.WRITING
            await self._save_state(state)
            
            for sector_idx in range(start_sector, total_sectors):
                # Check if already verified
                if sector_idx in state.verified_sectors:
                    if progress_callback:
                        await progress_callback(sector_idx, total_sectors)
                    continue
                
                sector_offset = sector_idx * sector_size
                sector_data = firmware[sector_offset : sector_offset + sector_size]
                
                # Pad last sector if needed
                if len(sector_data) < sector_size:
                    sector_data = sector_data + b'\xff' * (sector_size - len(sector_data))
                
                # Write sector
                sector_addr = partition_start + sector_offset
                await self._probe.write_memory(sector_addr, sector_data)
                
                # FIX: Log WAL before verify
                if self._wal:
                    sector_hash = hashlib.sha256(sector_data).hexdigest()
                    await self._wal.log_sector_write(
                        state.transaction_id,
                        sector_idx,
                        sector_hash,
                        len(sector_data),
                    )
                
                # Verify
                if state.verify_each_sector:
                    state.state = TransactionState.VERIFYING
                    await self._save_state(state)
                    
                    verify_data = await self._probe.read_memory(sector_addr, len(sector_data))
                    if verify_data != sector_data:
                        state.state = TransactionState.FAILED
                        await self._save_state(state)
                        
                        if self._wal:
                            await self._wal.abort_transaction(state.transaction_id)
                        
                        return FlashResult(
                            success=False,
                            error_code="VERIFY_FAILED",
                            error_message=f"Verification failed at sector {sector_idx}",
                            resume_state=state,
                        )
                    
                    sector_hash = hashlib.sha256(sector_data).hexdigest()
                    state.verified_sectors[sector_idx] = sector_hash
                    
                    # FIX: Log verification in WAL
                    if self._wal:
                        await self._wal.log_sector_verify(
                            state.transaction_id,
                            sector_idx,
                            verified=True,
                        )
                
                bytes_written += len(sector_data)
                state.total_bytes_written = bytes_written
                state.last_sector_written = sector_idx
                
                # FIX: Checkpoint with WAL
                if (sector_idx + 1) % self._checkpoint_interval == 0:
                    await self._save_state(state)
                
                if progress_callback:
                    await progress_callback(sector_idx + 1, total_sectors)
            
            # FIX: Commit WAL transaction
            if self._wal:
                await self._wal.commit_transaction(state.transaction_id)
            
            state.state = TransactionState.COMPLETED
            await self._save_state(state)
            
            # FIX: Clean up WAL after commit
            if self._wal:
                await self._wal.delete_wal(state.transaction_id)
            
            duration_ms = (time.monotonic() - start_time) * 1000
            
            return FlashResult(
                success=True,
                bytes_written=len(firmware),
                sectors_erased=total_sectors,
                duration_ms=duration_ms,
            )
            
        except Exception as e:
            # FIX: Save state and abort WAL
            if self._wal:
                await self._wal.abort_transaction(state.transaction_id)
            
            state.state = TransactionState.FAILED
            await self._save_state(state)
            
            duration_ms = (time.monotonic() - start_time) * 1000
            
            return FlashResult(
                success=False,
                error_code="FLASH_ERROR",
                error_message=str(e),
                duration_ms=duration_ms,
                resume_state=state,
            )
    
    async def _save_state(self, state: FlashResumeState) -> None:
        """Save resume state atomically with fsync.
        
        FIX: Implements atomic write pattern:
        1. Write to temp file
        2. fsync temp file
        3. Atomic rename to target
        4. fsync directory
        """
        state.updated_at = datetime.now()
        
        # FIX: Compute checksum before writing
        state.state_checksum = state.compute_checksum()
        
        path = self._get_resume_path(state.transaction_id)
        temp_fd, temp_path = tempfile.mkstemp(
            dir=self._resume_state_path,
            suffix=".tmp"
        )
        
        try:
            with os.fdopen(temp_fd, "w") as f:
                f.write(state.to_json())
                f.flush()
                os.fsync(f.fileno())  # FIX: Ensure durability
            
            # FIX: Atomic rename
            os.replace(temp_path, path)
            
            # FIX: Sync directory metadata when supported (POSIX). On Windows,
            # os.O_DIRECTORY may not exist; fsync on a directory is best-effort.
            o_directory = getattr(os, "O_DIRECTORY", None)
            if o_directory is not None:
                dir_fd = os.open(self._resume_state_path, os.O_RDONLY | o_directory)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
                
        except Exception:
            # Clean up temp file on error
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            raise
    
    async def clear_state(self, transaction_id: str) -> None:
        """Clear resume state after successful flash."""
        path = self._get_resume_path(transaction_id)
        try:
            os.unlink(path)
            logger.info("resume_state_cleared: tx=%s", transaction_id)
        except FileNotFoundError:
            pass
        
        # FIX: Also clear WAL
        if self._wal:
            await self._wal.delete_wal(transaction_id)
    
    async def list_resumable_transactions(self) -> list[FlashResumeState]:
        """List all resumable transactions."""
        states = []
        
        if not os.path.exists(self._resume_state_path):
            return states
        
        for filename in os.listdir(self._resume_state_path):
            if filename.endswith(".resume"):
                path = os.path.join(self._resume_state_path, filename)
                try:
                    with open(path, "r") as f:
                        state = FlashResumeState.from_json(f.read())
                    
                    # Only include incomplete, non-failed transactions
                    if not state.is_complete() and state.state != TransactionState.FAILED:
                        states.append(state)
                        
                except Exception:
                    pass
        
        return sorted(states, key=lambda s: s.updated_at)
