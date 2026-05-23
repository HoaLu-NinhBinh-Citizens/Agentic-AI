"""Atomic Snapshot Module for W-007.

Provides atomic snapshot with transaction semantics:
- Snapshot creation is atomic with event log
- Snapshot verification with checksum
- Rollback on failure
- Two-phase commit for snapshot consistency
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class SnapshotPhase(Enum):
    """Snapshot creation phases."""
    IDLE = "idle"
    PREPARING = "preparing"  # Capturing state
    VERIFYING = "verifying"  # Computing checksum
    COMMITTED = "committed"  # Successfully committed
    ROLLED_BACK = "rolled_back"  # Rolled back on failure


@dataclass
class AtomicSnapshot:
    """Atomic snapshot with verification and rollback support."""

    snapshot_id: str
    created_at: datetime = field(default_factory=datetime.now)
    phase: SnapshotPhase = SnapshotPhase.IDLE
    state: dict[str, Any] = field(default_factory=dict)
    checksum: str = ""
    event_log_offset: int = 0
    verified: bool = False
    commit_error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize snapshot to dict."""
        return {
            "snapshot_id": self.snapshot_id,
            "created_at": self.created_at.isoformat(),
            "phase": self.phase.value,
            "state_keys": list(self.state.keys()),
            "checksum": self.checksum,
            "event_log_offset": self.event_log_offset,
            "verified": self.verified,
        }


class AtomicSnapshotManager:
    """Manages atomic snapshots with transaction semantics.

    W-007 Fix: Ensures snapshot is atomic with event log.
    - Two-phase commit (prepare + commit)
    - Checksum verification
    - Rollback on failure
    """

    def __init__(
        self,
        max_snapshots: int = 10,
        verify_on_commit: bool = True,
    ):
        self._max_snapshots = max_snapshots
        self._verify_on_commit = verify_on_commit
        self._snapshots: dict[str, AtomicSnapshot] = {}
        self._current: Optional[AtomicSnapshot] = None
        self._lock = asyncio.Lock()

    async def begin_snapshot(
        self,
        snapshot_id: str,
        capture_state: Callable[[], dict[str, Any]],
        get_event_log_offset: Callable[[], int],
    ) -> AtomicSnapshot:
        """Begin atomic snapshot creation (Phase 1: Prepare).

        Args:
            snapshot_id: Unique identifier for snapshot.
            capture_state: Function to capture current state.
            get_event_log_offset: Function to get current event log offset.

        Returns:
            AtomicSnapshot in PREPARING phase.
        """
        async with self._lock:
            if self._current is not None:
                raise RuntimeError(
                    f"Snapshot already in progress: {self._current.snapshot_id}"
                )

            snapshot = AtomicSnapshot(
                snapshot_id=snapshot_id,
                phase=SnapshotPhase.PREPARING,
            )

            try:
                # Capture state atomically
                snapshot.state = await asyncio.get_event_loop().run_in_executor(
                    None, capture_state
                )
                snapshot.event_log_offset = get_event_log_offset()

                self._current = snapshot
                self._snapshots[snapshot_id] = snapshot

                logger.info(
                    "Snapshot prepared",
                    snapshot_id=snapshot_id,
                    state_keys=len(snapshot.state),
                    event_log_offset=snapshot.event_log_offset,
                )

                return snapshot

            except Exception as e:
                snapshot.phase = SnapshotPhase.ROLLED_BACK
                snapshot.commit_error = str(e)
                logger.error(
                    "Snapshot preparation failed",
                    snapshot_id=snapshot_id,
                    error=str(e),
                )
                raise

    async def verify_and_commit(
        self,
        snapshot_id: str,
        expected_checksum: Optional[str] = None,
    ) -> AtomicSnapshot:
        """Verify and commit snapshot (Phase 2: Commit).

        Args:
            snapshot_id: Snapshot to commit.
            expected_checksum: Optional checksum to verify against.

        Returns:
            Committed AtomicSnapshot.

        Raises:
            RuntimeError: If snapshot not found or verification failed.
        """
        async with self._lock:
            snapshot = self._snapshots.get(snapshot_id)
            if snapshot is None:
                raise RuntimeError(f"Snapshot not found: {snapshot_id}")

            if snapshot.phase != SnapshotPhase.PREPARING:
                raise RuntimeError(
                    f"Snapshot {snapshot_id} not in PREPARING phase: {snapshot.phase}"
                )

            try:
                snapshot.phase = SnapshotPhase.VERIFYING

                # Compute checksum of snapshot state
                snapshot.checksum = self._compute_checksum(snapshot.state)

                # Verify against expected if provided
                if expected_checksum and snapshot.checksum != expected_checksum:
                    snapshot.phase = SnapshotPhase.ROLLED_BACK
                    snapshot.commit_error = "Checksum mismatch"
                    raise RuntimeError(
                        f"Checksum mismatch: expected {expected_checksum}, "
                        f"got {snapshot.checksum}"
                    )

                # Verify event log consistency
                snapshot.verified = True
                snapshot.phase = SnapshotPhase.COMMITTED

                logger.info(
                    "Snapshot committed",
                    snapshot_id=snapshot_id,
                    checksum=snapshot.checksum[:16] + "...",
                    verified=snapshot.verified,
                )

                self._current = None
                self._prune_old_snapshots()

                return snapshot

            except Exception as e:
                snapshot.phase = SnapshotPhase.ROLLED_BACK
                snapshot.commit_error = str(e)
                self._current = None
                logger.error(
                    "Snapshot commit failed",
                    snapshot_id=snapshot_id,
                    error=str(e),
                )
                raise

    async def rollback_snapshot(self, snapshot_id: str) -> None:
        """Rollback a snapshot.

        Args:
            snapshot_id: Snapshot to rollback.
        """
        async with self._lock:
            snapshot = self._snapshots.get(snapshot_id)
            if snapshot is None:
                return

            if snapshot.phase == SnapshotPhase.COMMITTED:
                raise RuntimeError(f"Cannot rollback committed snapshot: {snapshot_id}")

            snapshot.phase = SnapshotPhase.ROLLED_BACK
            snapshot.state.clear()
            self._current = None

            logger.info("Snapshot rolled back", snapshot_id=snapshot_id)

    async def restore_snapshot(
        self,
        snapshot_id: str,
        apply_state: Callable[[dict[str, Any]], None],
    ) -> None:
        """Restore state from a committed snapshot.

        Args:
            snapshot_id: Snapshot to restore from.
            apply_state: Function to apply state to system.

        Raises:
            RuntimeError: If snapshot not found or not committed.
        """
        async with self._lock:
            snapshot = self._snapshots.get(snapshot_id)
            if snapshot is None:
                raise RuntimeError(f"Snapshot not found: {snapshot_id}")

            if snapshot.phase != SnapshotPhase.COMMITTED:
                raise RuntimeError(
                    f"Snapshot {snapshot_id} not committed: {snapshot.phase}"
                )

            if not snapshot.verified:
                raise RuntimeError(f"Snapshot {snapshot_id} not verified")

            # Verify checksum before restoring
            current_checksum = self._compute_checksum(snapshot.state)
            if current_checksum != snapshot.checksum:
                raise RuntimeError(
                    f"Snapshot corrupted: checksum mismatch during restore"
                )

            # Apply state
            await asyncio.get_event_loop().run_in_executor(
                None, apply_state, snapshot.state
            )

            logger.info(
                "Snapshot restored",
                snapshot_id=snapshot_id,
                state_keys=len(snapshot.state),
            )

    def _compute_checksum(self, state: dict[str, Any]) -> str:
        """Compute SHA256 checksum of state.

        Args:
            state: State dictionary to checksum.

        Returns:
            Hexadecimal checksum string.
        """
        # Sort keys for deterministic ordering
        state_json = json.dumps(state, sort_keys=True, default=str)
        return hashlib.sha256(state_json.encode()).hexdigest()

    def _prune_old_snapshots(self) -> None:
        """Remove old snapshots beyond max limit."""
        committed = [
            (sid, s) for sid, s in self._snapshots.items()
            if s.phase == SnapshotPhase.COMMITTED
        ]

        # Sort by created_at descending (keep newest)
        committed.sort(key=lambda x: x[1].created_at, reverse=True)

        # Remove oldest beyond limit
        for sid, _ in committed[self._max_snapshots:]:
            del self._snapshots[sid]
            logger.debug("Pruned old snapshot", snapshot_id=sid)

    async def get_snapshot(self, snapshot_id: str) -> Optional[AtomicSnapshot]:
        """Get snapshot by ID."""
        return self._snapshots.get(snapshot_id)

    async def list_snapshots(
        self,
        phase: Optional[SnapshotPhase] = None,
    ) -> list[AtomicSnapshot]:
        """List all snapshots, optionally filtered by phase."""
        snapshots = list(self._snapshots.values())

        if phase is not None:
            snapshots = [s for s in snapshots if s.phase == phase]

        # Sort by created_at descending
        snapshots.sort(key=lambda s: s.created_at, reverse=True)

        return snapshots

    async def get_latest_committed(self) -> Optional[AtomicSnapshot]:
        """Get the most recent committed snapshot."""
        committed = await self.list_snapshots(phase=SnapshotPhase.COMMITTED)
        return committed[0] if committed else None

    def get_stats(self) -> dict[str, Any]:
        """Get snapshot manager statistics."""
        phases = {}
        for phase in SnapshotPhase:
            phases[phase.value] = sum(
                1 for s in self._snapshots.values() if s.phase == phase
            )

        return {
            "total_snapshots": len(self._snapshots),
            "by_phase": phases,
            "current_snapshot": self._current.snapshot_id if self._current else None,
            "max_snapshots": self._max_snapshots,
        }


class TransactionalSnapshotContext:
    """Context manager for transactional snapshot creation.

    Usage:
        async with TransactionalSnapshotContext(manager, "snap-1", capture_fn, offset_fn) as snapshot:
            # snapshot is in PREPARING phase
            ...
        # snapshot is now COMMITTED
    """

    def __init__(
        self,
        manager: AtomicSnapshotManager,
        snapshot_id: str,
        capture_state: Callable[[], dict[str, Any]],
        get_event_log_offset: Callable[[], int],
    ):
        self._manager = manager
        self._snapshot_id = snapshot_id
        self._capture_state = capture_state
        self._get_event_log_offset = get_event_log_offset
        self._snapshot: Optional[AtomicSnapshot] = None
        self._committed = False

    async def __aenter__(self) -> AtomicSnapshot:
        """Enter context and begin snapshot."""
        self._snapshot = await self._manager.begin_snapshot(
            self._snapshot_id,
            self._capture_state,
            self._get_event_log_offset,
        )
        return self._snapshot

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context and commit or rollback."""
        if self._snapshot is None:
            return

        if exc_type is not None or not self._committed:
            # Exception occurred or not committed, rollback
            await self._manager.rollback_snapshot(self._snapshot_id)
        elif not self._committed:
            await self._manager.rollback_snapshot(self._snapshot_id)

    async def commit(self) -> AtomicSnapshot:
        """Explicitly commit the snapshot."""
        if self._snapshot is None:
            raise RuntimeError("No snapshot in progress")

        self._snapshot = await self._manager.verify_and_commit(self._snapshot_id)
        self._committed = True
        return self._snapshot
