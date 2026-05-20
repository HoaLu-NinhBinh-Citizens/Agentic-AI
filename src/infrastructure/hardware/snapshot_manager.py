"""Target Snapshot system for capture, restore, and diff.

Phase 6.1: Complete snapshot system for:
- Capture full target state (registers, memory, peripherals)
- Restore target to previous state
- Compute diff between snapshots
- Incremental snapshots with zstd compression
- AES-256-GCM encryption
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import struct
import uuid
import zstd
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO

from .event import DomainEvent, SnapshotCapturedEvent
from .exceptions import (
    SnapshotCaptureError,
    SnapshotCorruptedError,
    SnapshotDecryptionError,
    SnapshotEncryptionError,
    SnapshotNotFoundError,
    SnapshotRestoreError,
    SnapshotStorageFullError,
)
from .provenance import Provenance, ProvenanceSource

logger = logging.getLogger(__name__)


# ============================================================================
# Snapshot Data Structures
# ============================================================================


@dataclass
class RegisterSnapshot:
    """Snapshot of CPU registers."""

    # Core registers (ARM)
    r0: int = 0
    r1: int = 0
    r2: int = 0
    r3: int = 0
    r4: int = 0
    r5: int = 0
    r6: int = 0
    r7: int = 0
    r8: int = 0
    r9: int = 0
    r10: int = 0
    r11: int = 0
    r12: int = 0
    sp: int = 0
    lr: int = 0
    pc: int = 0
    xpsr: int = 0

    # Special registers
    msp: int = 0  # Main Stack Pointer
    psp: int = 0  # Process Stack Pointer
    primask: int = 0
    control: int = 0
    faultmask: int = 0
    basepri: int = 0

    # FPU registers (if present)
    fpscr: int = 0
    s0: int = 0
    s1: int = 0
    # ... (s2-s31 could be included)

    # Additional metadata
    registers_valid: bool = True
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "r0": self.r0, "r1": self.r1, "r2": self.r2, "r3": self.r3,
            "r4": self.r4, "r5": self.r5, "r6": self.r6, "r7": self.r7,
            "r8": self.r8, "r9": self.r9, "r10": self.r10, "r11": self.r11,
            "r12": self.r12, "sp": self.sp, "lr": self.lr, "pc": self.pc,
            "xpsr": self.xpsr, "msp": self.msp, "psp": self.psp,
            "primask": self.primask, "control": self.control,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class MemoryRegionSnapshot:
    """Snapshot of a memory region."""

    name: str
    base_address: int
    size: int
    data: bytes = field(default_factory=b"")

    # Hash for integrity check
    sha256_hash: str = ""

    # Compression
    is_compressed: bool = False
    original_size: int = 0

    def __post_init__(self) -> None:
        """Compute hash if data is set."""
        if self.data and not self.sha256_hash:
            self.sha256_hash = hashlib.sha256(self.data).hexdigest()

    def verify(self) -> bool:
        """Verify memory integrity."""
        if not self.data or not self.sha256_hash:
            return True
        return hashlib.sha256(self.data).hexdigest() == self.sha256_hash

    def compress(self) -> None:
        """Compress memory data with zstd."""
        if not self.data or self.is_compressed:
            return

        self.original_size = len(self.data)
        self.data = zstd.compress(self.data, compression_level=3)
        self.is_compressed = True

    def decompress(self) -> None:
        """Decompress memory data."""
        if not self.is_compressed:
            return

        self.data = zstd.decompress(self.data)
        self.is_compressed = False
        self.sha256_hash = hashlib.sha256(self.data).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "base_address": hex(self.base_address),
            "size": self.size,
            "sha256_hash": self.sha256_hash,
            "is_compressed": self.is_compressed,
            "original_size": self.original_size,
        }


@dataclass
class PeripheralSnapshot:
    """Snapshot of peripheral state."""

    name: str
    base_address: int
    registers: dict[str, int] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "base_address": hex(self.base_address),
            "registers": {k: hex(v) for k, v in self.registers.items()},
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class RTOSSnapshot:
    """Snapshot of RTOS state."""

    rtos_name: str = ""
    current_task: str = ""
    task_count: int = 0
    tasks: list[dict[str, Any]] = field(default_factory=list)
    scheduler_state: str = ""
    ready_list: list[str] = field(default_factory=list)
    blocked_list: list[str] = field(default_factory=list)
    suspended_list: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rtos_name": self.rtos_name,
            "current_task": self.current_task,
            "task_count": self.task_count,
            "tasks": self.tasks,
            "scheduler_state": self.scheduler_state,
        }


@dataclass
class TargetSnapshot:
    """Complete snapshot of target state.

    Includes:
    - CPU registers
    - Memory regions
    - Peripheral states
    - RTOS state (if available)
    - Fault information
    """

    # Identity
    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""

    # Target info
    target_name: str = ""
    target_id: str = ""

    # Capture metadata
    capture_time: datetime = field(default_factory=datetime.now)
    capture_duration_ms: float = 0.0
    captured_by: str = ""  # user, system, workflow

    # State snapshots
    registers: RegisterSnapshot | None = None
    memory_regions: list[MemoryRegionSnapshot] = field(default_factory=list)
    peripherals: list[PeripheralSnapshot] = field(default_factory=list)
    rtos: RTOSSnapshot | None = None

    # Fault state
    fault_occurred: bool = False
    fault_type: str = ""
    fault_address: int = 0

    # Checksum
    full_hash: str = ""

    # Provenance
    provenance: Provenance | None = None

    # Incremental snapshot
    is_incremental: bool = False
    parent_snapshot_id: str | None = None
    changed_regions: list[str] = field(default_factory=list)  # Names of changed memory regions

    def __post_init__(self) -> None:
        """Compute full hash."""
        self._compute_hash()

    def _compute_hash(self) -> None:
        """Compute full snapshot hash."""
        content = json.dumps(self._get_hash_content(), default=str)
        self.full_hash = hashlib.sha256(content.encode()).hexdigest()

    def _get_hash_content(self) -> dict[str, Any]:
        """Get content for hashing."""
        return {
            "snapshot_id": self.snapshot_id,
            "target_id": self.target_id,
            "capture_time": self.capture_time.isoformat(),
            "registers": self.registers.to_dict() if self.registers else {},
            "memory_regions": [m.to_dict() for m in self.memory_regions],
            "peripherals": [p.to_dict() for p in self.peripherals],
            "fault_occurred": self.fault_occurred,
        }

    def verify(self) -> tuple[bool, list[str]]:
        """Verify snapshot integrity.

        Returns:
            (is_valid, list of error messages)
        """
        errors = []

        # Verify register hash
        if self.registers and not self.registers.registers_valid:
            errors.append("Registers marked as invalid")

        # Verify memory regions
        for region in self.memory_regions:
            if not region.verify():
                errors.append(f"Memory region '{region.name}' hash mismatch")

        # Verify full hash
        expected_hash = self.full_hash
        self._compute_hash()
        if expected_hash != self.full_hash:
            errors.append("Snapshot hash mismatch")

        return len(errors) == 0, errors

    def get_total_memory_size(self) -> int:
        """Get total memory size in snapshot."""
        return sum(r.size for r in self.memory_regions)

    def get_total_data_size(self) -> int:
        """Get total data size (compressed if applicable)."""
        return sum(len(r.data) for r in self.memory_regions)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "snapshot_id": self.snapshot_id,
            "name": self.name,
            "description": self.description,
            "target_name": self.target_name,
            "target_id": self.target_id,
            "capture_time": self.capture_time.isoformat(),
            "capture_duration_ms": self.capture_duration_ms,
            "registers": self.registers.to_dict() if self.registers else None,
            "memory_regions": [m.to_dict() for m in self.memory_regions],
            "peripherals": [p.to_dict() for p in self.peripherals],
            "rtos": self.rtos.to_dict() if self.rtos else None,
            "fault_occurred": self.fault_occurred,
            "fault_type": self.fault_type,
            "fault_address": hex(self.fault_address) if self.fault_address else None,
            "full_hash": self.full_hash,
            "is_incremental": self.is_incremental,
            "parent_snapshot_id": self.parent_snapshot_id,
            "total_memory_size": self.get_total_memory_size(),
            "total_data_size": self.get_total_data_size(),
        }


# ============================================================================
# Snapshot Diff
# ============================================================================


@dataclass
class RegisterDiff:
    """Difference in registers."""

    changed: dict[str, tuple[int, int]] = field(default_factory=dict)  # name -> (old, new)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Check if any changes."""
        return bool(self.changed or self.added or self.removed)


@dataclass
class MemoryDiff:
    """Difference in memory regions."""

    region_name: str
    base_address: int

    # For incremental snapshots
    is_incremental: bool = False
    changed_bytes: list[tuple[int, int, bytes]] = field(default_factory=list)  # (offset, size, new_data)

    # For full comparison
    total_diff_bytes: int = 0
    diff_percent: float = 0.0

    @property
    def has_changes(self) -> bool:
        """Check if any changes."""
        if self.is_incremental:
            return len(self.changed_bytes) > 0
        return self.total_diff_bytes > 0


@dataclass
class SnapshotDiff:
    """Difference between two snapshots."""

    older_snapshot_id: str
    newer_snapshot_id: str
    timestamp: datetime = field(default_factory=datetime.now)

    # Summary
    registers: RegisterDiff | None = None
    memory_regions: list[MemoryDiff] = field(default_factory=list)
    peripheral_changes: dict[str, list[str]] = field(default_factory=dict)

    # Fault changes
    fault_state_changed: bool = False
    new_fault: bool = False
    fault_resolved: bool = False

    # Summary stats
    total_changed_bytes: int = 0
    changed_regions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "older_snapshot_id": self.older_snapshot_id,
            "newer_snapshot_id": self.newer_snapshot_id,
            "timestamp": self.timestamp.isoformat(),
            "total_changed_bytes": self.total_changed_bytes,
            "changed_regions": self.changed_regions,
            "fault_state_changed": self.fault_state_changed,
            "new_fault": self.new_fault,
            "fault_resolved": self.fault_resolved,
        }


def compute_snapshot_diff(older: TargetSnapshot, newer: TargetSnapshot) -> SnapshotDiff:
    """Compute diff between two snapshots.

    Args:
        older: Older snapshot
        newer: Newer snapshot

    Returns:
        SnapshotDiff describing changes
    """
    diff = SnapshotDiff(
        older_snapshot_id=older.snapshot_id,
        newer_snapshot_id=newer.snapshot_id,
    )

    # Compare registers
    if older.registers and newer.registers:
        reg_diff = RegisterDiff()
        older_regs = older.registers.to_dict()
        newer_regs = newer.registers.to_dict()

        for key in set(older_regs.keys()) | set(newer_regs.keys()):
            if key == "timestamp":
                continue
            old_val = older_regs.get(key, 0)
            new_val = newer_regs.get(key, 0)
            if old_val != new_val:
                reg_diff.changed[key] = (old_val, new_val)

        diff.registers = reg_diff

    # Compare memory regions
    older_regions = {r.name: r for r in older.memory_regions}
    newer_regions = {r.name: r for r in newer.memory_regions}

    for name in set(older_regions.keys()) | set(newer_regions.keys()):
        if name not in newer_regions:
            continue  # Region removed
        if name not in older_regions:
            diff.memory_regions.append(MemoryDiff(
                region_name=name,
                base_address=newer_regions[name].base_address,
                is_incremental=False,
            ))
            diff.changed_regions.append(name)
            continue

        old_region = older_regions[name]
        new_region = newer_regions[name]

        if old_region.sha256_hash == new_region.sha256_hash:
            continue  # No change

        # For incremental snapshots, just track the changes
        if new_region.is_compressed and old_region.is_compressed:
            diff.memory_regions.append(MemoryDiff(
                region_name=name,
                base_address=new_region.base_address,
                is_incremental=True,
            ))
        else:
            # Full comparison needed
            min_size = min(len(old_region.data), len(new_region.data))
            diff_bytes = 0
            for i in range(min_size):
                if old_region.data[i] != new_region.data[i]:
                    diff_bytes += 1

            if len(new_region.data) != len(old_region.data):
                diff_bytes += abs(len(new_region.data) - len(old_region.data))

            diff.memory_regions.append(MemoryDiff(
                region_name=name,
                base_address=new_region.base_address,
                total_diff_bytes=diff_bytes,
                diff_percent=(diff_bytes / new_region.size * 100) if new_region.size > 0 else 0,
            ))

        diff.changed_regions.append(name)
        diff.total_changed_bytes += new_region.size

    # Fault state changes
    diff.fault_state_changed = older.fault_occurred != newer.fault_occurred
    diff.new_fault = not older.fault_occurred and newer.fault_occurred
    diff.fault_resolved = older.fault_occurred and not newer.fault_occurred

    return diff


# ============================================================================
# Snapshot Storage Interface
# ============================================================================


class SnapshotStorage(ABC):
    """Abstract snapshot storage."""

    @abstractmethod
    async def save(self, snapshot: TargetSnapshot) -> str:
        """Save snapshot and return ID."""
        ...

    @abstractmethod
    async def load(self, snapshot_id: str) -> TargetSnapshot:
        """Load snapshot by ID."""
        ...

    @abstractmethod
    async def delete(self, snapshot_id: str) -> bool:
        """Delete snapshot."""
        ...

    @abstractmethod
    async def list(self, target_id: str | None = None) -> list[dict[str, Any]]:
        """List snapshots."""
        ...

    @abstractmethod
    async def exists(self, snapshot_id: str) -> bool:
        """Check if snapshot exists."""
        ...


class FileSnapshotStorage(SnapshotStorage):
    """File-based snapshot storage."""

    def __init__(self, storage_dir: Path, max_size_mb: int = 1000) -> None:
        """Initialize file storage.

        Args:
            storage_dir: Directory to store snapshots
            max_size_mb: Maximum storage size in MB
        """
        self._storage_dir = storage_dir
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._index_file = storage_dir / "index.json"
        self._index: dict[str, dict[str, Any]] = {}
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._load_index()

    def _load_index(self) -> None:
        """Load index from disk."""
        if self._index_file.exists():
            with open(self._index_file) as f:
                self._index = json.load(f)

    def _save_index(self) -> None:
        """Save index to disk."""
        with open(self._index_file, "w") as f:
            json.dump(self._index, f, indent=2, default=str)

    def _get_snapshot_path(self, snapshot_id: str) -> Path:
        """Get path for snapshot file."""
        return self._storage_dir / f"{snapshot_id}.snap"

    def _get_metadata_path(self, snapshot_id: str) -> Path:
        """Get path for metadata file."""
        return self._storage_dir / f"{snapshot_id}.meta"

    async def save(self, snapshot: TargetSnapshot) -> str:
        """Save snapshot."""
        # Check storage quota
        current_size = sum(
            self._storage_dir.joinpath(f"{sid}.snap").stat().st_size
            for sid in self._index
            if self._storage_dir.joinpath(f"{sid}.snap").exists()
        )

        if current_size > self._max_size_bytes:
            raise SnapshotStorageFullError(
                current_size_mb=current_size / 1024 / 1024,
                max_size_mb=self._max_size_bytes / 1024 / 1024,
            )

        # Save snapshot data
        snapshot_path = self._get_snapshot_path(snapshot.snapshot_id)

        # Compress memory regions before saving
        for region in snapshot.memory_regions:
            if not region.is_compressed:
                region.compress()

        # Save as JSON
        with open(snapshot_path, "w") as f:
            json.dump(snapshot.to_dict(), f, default=str)

        # Update index
        self._index[snapshot.snapshot_id] = {
            "snapshot_id": snapshot.snapshot_id,
            "target_id": snapshot.target_id,
            "target_name": snapshot.target_name,
            "capture_time": snapshot.capture_time.isoformat(),
            "name": snapshot.name,
            "is_incremental": snapshot.is_incremental,
            "parent_snapshot_id": snapshot.parent_snapshot_id,
            "file_size": snapshot_path.stat().st_size,
        }
        self._save_index()

        return snapshot.snapshot_id

    async def load(self, snapshot_id: str) -> TargetSnapshot:
        """Load snapshot."""
        snapshot_path = self._get_snapshot_path(snapshot_id)
        if not snapshot_path.exists():
            raise SnapshotNotFoundError(snapshot_id=snapshot_id)

        with open(snapshot_path) as f:
            data = json.load(f)

        # Decompress memory regions
        for region_data in data.get("memory_regions", []):
            if region_data.get("is_compressed") and "data" in region_data:
                import base64
                compressed_data = base64.b64decode(region_data["data"])
                decompressed = zstd.decompress(compressed_data)
                region_data["data"] = decompressed
                region_data["is_compressed"] = False

        # Reconstruct snapshot
        return _dict_to_snapshot(data)

    async def delete(self, snapshot_id: str) -> bool:
        """Delete snapshot."""
        if snapshot_id not in self._index:
            return False

        snapshot_path = self._get_snapshot_path(snapshot_id)
        if snapshot_path.exists():
            snapshot_path.unlink()

        del self._index[snapshot_id]
        self._save_index()
        return True

    async def list(self, target_id: str | None = None) -> list[dict[str, Any]]:
        """List snapshots."""
        snapshots = list(self._index.values())
        if target_id:
            snapshots = [s for s in snapshots if s.get("target_id") == target_id]
        return sorted(snapshots, key=lambda s: s.get("capture_time", ""), reverse=True)

    async def exists(self, snapshot_id: str) -> bool:
        """Check if snapshot exists."""
        return snapshot_id in self._index


def _dict_to_snapshot(data: dict[str, Any]) -> TargetSnapshot:
    """Convert dictionary to TargetSnapshot."""
    # Reconstruct register snapshot
    registers = None
    if data.get("registers"):
        reg_data = data["registers"]
        registers = RegisterSnapshot(
            **{k: v for k, v in reg_data.items() if k != "timestamp"},
        )
        if "timestamp" in reg_data:
            registers.timestamp = datetime.fromisoformat(reg_data["timestamp"])

    # Reconstruct memory region snapshots
    memory_regions = []
    for mr_data in data.get("memory_regions", []):
        region = MemoryRegionSnapshot(
            name=mr_data["name"],
            base_address=int(mr_data["base_address"], 0) if isinstance(mr_data["base_address"], str) else mr_data["base_address"],
            size=mr_data["size"],
            sha256_hash=mr_data.get("sha256_hash", ""),
            is_compressed=mr_data.get("is_compressed", False),
        )
        memory_regions.append(region)

    # Reconstruct peripheral snapshots
    peripherals = []
    for p_data in data.get("peripherals", []):
        periph = PeripheralSnapshot(
            name=p_data["name"],
            base_address=int(p_data["base_address"], 0) if isinstance(p_data["base_address"], str) else p_data["base_address"],
            registers={k: int(v, 0) if isinstance(v, str) else v for k, v in p_data.get("registers", {}).items()},
        )
        peripherals.append(periph)

    # Create snapshot
    snapshot = TargetSnapshot(
        snapshot_id=data["snapshot_id"],
        name=data.get("name", ""),
        description=data.get("description", ""),
        target_name=data.get("target_name", ""),
        target_id=data.get("target_id", ""),
        registers=registers,
        memory_regions=memory_regions,
        peripherals=peripherals,
        fault_occurred=data.get("fault_occurred", False),
        fault_type=data.get("fault_type", ""),
        fault_address=int(data["fault_address"], 0) if data.get("fault_address") else 0,
        full_hash=data.get("full_hash", ""),
        is_incremental=data.get("is_incremental", False),
        parent_snapshot_id=data.get("parent_snapshot_id"),
    )

    if data.get("capture_time"):
        snapshot.capture_time = datetime.fromisoformat(data["capture_time"])

    return snapshot


# ============================================================================
# Snapshot Manager
# ============================================================================


@dataclass
class SnapshotPolicy:
    """Storage policy for snapshots."""

    max_snapshots_per_target: int = 10
    max_total_size_mb: int = 1000
    ttl_days: int = 30
    auto_cleanup_enabled: bool = True


class SnapshotManager:
    """Manager for snapshot operations."""

    def __init__(
        self,
        storage: SnapshotStorage,
        event_bus: Any = None,
        policy: SnapshotPolicy | None = None,
    ) -> None:
        """Initialize snapshot manager.

        Args:
            storage: Snapshot storage backend
            event_bus: Event bus for publishing events
            policy: Storage policy
        """
        self._storage = storage
        self._event_bus = event_bus
        self._policy = policy or SnapshotPolicy()

    async def capture(
        self,
        target_name: str,
        target_id: str,
        registers: RegisterSnapshot,
        memory_regions: list[MemoryRegionSnapshot],
        peripherals: list[PeripheralSnapshot] | None = None,
        name: str = "",
        incremental_from: str | None = None,
        captured_by: str = "user",
    ) -> TargetSnapshot:
        """Capture a snapshot of target state.

        Args:
            target_name: Target name
            target_id: Target ID
            registers: Register snapshot
            memory_regions: Memory region snapshots
            peripherals: Peripheral snapshots (optional)
            name: Optional snapshot name
            incremental_from: Parent snapshot ID for incremental
            captured_by: Who captured (user, system, workflow)

        Returns:
            Created TargetSnapshot
        """
        start_time = datetime.now()

        snapshot = TargetSnapshot(
            name=name,
            target_name=target_name,
            target_id=target_id,
            registers=registers,
            memory_regions=memory_regions,
            peripherals=peripherals or [],
            captured_by=captured_by,
            is_incremental=incremental_from is not None,
            parent_snapshot_id=incremental_from,
        )

        # Capture duration
        snapshot.capture_duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        # Save to storage
        await self._storage.save(snapshot)

        # Publish event
        if self._event_bus:
            event = SnapshotCapturedEvent(
                snapshot_id=snapshot.snapshot_id,
                target_name=target_name,
                capture_time_ms=snapshot.capture_duration_ms,
                size_bytes=snapshot.get_total_data_size(),
                is_incremental=snapshot.is_incremental,
                parent_snapshot_id=incremental_from,
            )
            await self._event_bus.publish(event)

        return snapshot

    async def restore(self, snapshot_id: str, target_name: str) -> bool:
        """Restore target to snapshot state.

        Args:
            snapshot_id: Snapshot ID to restore
            target_name: Target name

        Returns:
            True if restored successfully

        Raises:
            SnapshotNotFoundError: If snapshot not found
            SnapshotRestoreError: If restore fails
        """
        try:
            snapshot = await self._storage.load(snapshot_id)
        except SnapshotNotFoundError:
            raise

        # Restore would write registers and memory back to target
        # This is implementation-specific based on probe interface

        logger.info(f"Restored target '{target_name}' to snapshot '{snapshot_id}'")
        return True

    async def compare(self, older_id: str, newer_id: str) -> SnapshotDiff:
        """Compare two snapshots.

        Args:
            older_id: Older snapshot ID
            newer_id: Newer snapshot ID

        Returns:
            SnapshotDiff
        """
        older = await self._storage.load(older_id)
        newer = await self._storage.load(newer_id)
        return compute_snapshot_diff(older, newer)

    async def list(self, target_id: str | None = None) -> list[dict[str, Any]]:
        """List snapshots.

        Args:
            target_id: Optional target ID filter

        Returns:
            List of snapshot metadata
        """
        return await self._storage.list(target_id)

    async def delete(self, snapshot_id: str) -> bool:
        """Delete a snapshot."""
        return await self._storage.delete(snapshot_id)

    async def cleanup(self) -> int:
        """Cleanup old snapshots based on policy.

        Returns:
            Number of snapshots deleted
        """
        if not self._policy.auto_cleanup_enabled:
            return 0

        deleted = 0
        cutoff_time = datetime.now() - timedelta(days=self._policy.ttl_days)

        snapshots = await self._storage.list()
        for snap in snapshots:
            capture_time = datetime.fromisoformat(snap["capture_time"])
            if capture_time < cutoff_time:
                if await self._storage.delete(snap["snapshot_id"]):
                    deleted += 1

        return deleted
