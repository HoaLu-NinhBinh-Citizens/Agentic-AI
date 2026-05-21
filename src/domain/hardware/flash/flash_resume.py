"""Flash Resume - Resume interrupted flash operations.

Phase 6.2: Implements flash resume capability:
- Resume state tracking
- Sector verification
- Recovery after power loss/USB disconnect
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FlashResumeState:
    """State for resuming interrupted flash operations.
    
    Stored persistently to enable recovery after power loss,
    USB disconnect, or other interruptions.
    """
    
    transaction_id: str
    firmware_hash: str
    firmware_size: int
    
    # Progress
    last_sector_written: int = 0
    last_offset_in_sector: int = 0
    total_bytes_written: int = 0
    
    # Sector checksums
    verified_sectors: dict[int, str] = field(default_factory=dict)
    
    # Timing
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # Configuration
    chunk_size: int = 4096
    verify_each_sector: bool = True
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "transaction_id": self.transaction_id,
            "firmware_hash": self.firmware_hash,
            "firmware_size": self.firmware_size,
            "last_sector_written": self.last_sector_written,
            "last_offset_in_sector": self.last_offset_in_sector,
            "total_bytes_written": self.total_bytes_written,
            "verified_sectors": self.verified_sectors,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "chunk_size": self.chunk_size,
            "verify_each_sector": self.verify_each_sector,
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FlashResumeState:
        """Create from dictionary."""
        return cls(
            transaction_id=data["transaction_id"],
            firmware_hash=data["firmware_hash"],
            firmware_size=data["firmware_size"],
            last_sector_written=data.get("last_sector_written", 0),
            last_offset_in_sector=data.get("last_offset_in_sector", 0),
            total_bytes_written=data.get("total_bytes_written", 0),
            verified_sectors=data.get("verified_sectors", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.now(),
            chunk_size=data.get("chunk_size", 4096),
            verify_each_sector=data.get("verify_each_sector", True),
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> FlashResumeState:
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))
    
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


@dataclass
class ResumableFlashWriter:
    """Flash writer with resume capability.
    
    Supports resuming interrupted flash operations by:
    1. Loading previous state from storage
    2. Verifying already-written sectors
    3. Continuing from where it left off
    """
    
    probe: Any  # ProbeInterface
    resume_state_path: str
    resume_enabled: bool = True
    
    _current_state: FlashResumeState | None = None
    _checkpoint_interval: int = 10  # Checkpoint every N sectors
    
    def __post_init__(self) -> None:
        """Ensure resume state directory exists."""
        if self.resume_enabled:
            os.makedirs(self.resume_state_path, exist_ok=True)
    
    async def check_for_resume(
        self,
        transaction_id: str,
        firmware_hash: str,
    ) -> FlashResumeState | None:
        """Check if there's a resume state to continue.
        
        Returns:
            FlashResumeState if found and valid, None otherwise
        """
        if not self.resume_enabled:
            return None
        
        path = os.path.join(self.resume_state_path, f"{transaction_id}.resume")
        
        try:
            with open(path, "r") as f:
                state = FlashResumeState.from_json(f.read())
            
            # Validate state matches firmware
            if state.firmware_hash != firmware_hash:
                logger.warning(
                    "resume_state_firmware_mismatch",
                    expected=firmware_hash,
                    actual=state.firmware_hash,
                )
                return None
            
            self._current_state = state
            return state
            
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            logger.error("resume_state_corrupted", path=path)
            return None
    
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
                data = await self.probe.read_memory(sector_start, sector_size)
                actual_hash = hashlib.sha256(data).hexdigest()
                
                if actual_hash != expected_hash:
                    logger.warning(
                        "sector_hash_mismatch",
                        sector=sector_idx,
                        expected=expected_hash[:16],
                        actual=actual_hash[:16],
                    )
                    sectors_to_retry.append(sector_idx)
                    
            except Exception as e:
                logger.error("sector_verify_failed", sector=sector_idx, error=str(e))
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
        )
        self._current_state = state
        
        start_sector = state.last_sector_written
        total_sectors = (len(firmware) + sector_size - 1) // sector_size
        bytes_written = state.total_bytes_written
        
        try:
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
                await self.probe.write_memory(sector_addr, sector_data)
                
                # Verify
                if state.verify_each_sector:
                    verify_data = await self.probe.read_memory(sector_addr, len(sector_data))
                    if verify_data != sector_data:
                        return FlashResult(
                            success=False,
                            error_code="VERIFY_FAILED",
                            error_message=f"Verification failed at sector {sector_idx}",
                            resume_state=state,
                        )
                    
                    sector_hash = hashlib.sha256(sector_data).hexdigest()
                    state.verified_sectors[sector_idx] = sector_hash
                
                bytes_written += len(sector_data)
                state.total_bytes_written = bytes_written
                state.last_sector_written = sector_idx
                
                # Checkpoint
                if (sector_idx + 1) % self._checkpoint_interval == 0:
                    await self._save_state(state)
                
                if progress_callback:
                    await progress_callback(sector_idx + 1, total_sectors)
            
            # Complete
            duration_ms = (time.monotonic() - start_time) * 1000
            
            return FlashResult(
                success=True,
                bytes_written=len(firmware),
                sectors_erased=total_sectors,
                duration_ms=duration_ms,
            )
            
        except Exception as e:
            # Save state for resume
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
        """Save resume state to disk."""
        state.updated_at = datetime.now()
        path = os.path.join(self.resume_state_path, f"{state.transaction_id}.resume")
        
        with open(path, "w") as f:
            f.write(state.to_json())
    
    async def clear_state(self, transaction_id: str) -> None:
        """Clear resume state after successful flash."""
        path = os.path.join(self.resume_state_path, f"{transaction_id}.resume")
        try:
            os.remove(path)
            logger.info("resume_state_cleared", transaction_id=transaction_id)
        except FileNotFoundError:
            pass
    
    async def list_resumable_transactions(self) -> list[FlashResumeState]:
        """List all resumable transactions."""
        states = []
        
        if not os.path.exists(self.resume_state_path):
            return states
        
        for filename in os.listdir(self.resume_state_path):
            if filename.endswith(".resume"):
                path = os.path.join(self.resume_state_path, filename)
                try:
                    with open(path, "r") as f:
                        state = FlashResumeState.from_json(f.read())
                    if not state.is_complete():
                        states.append(state)
                except Exception:
                    pass
        
        return sorted(states, key=lambda s: s.updated_at)
