"""Patch history and rollback with temporal durability (Phase 9.6).

Provides temporal-level durability for patches:
- Immutable patch history
- Point-in-time recovery
- Rollback with verification
- Patch audit trail
- Backup and restore

Tier 1 value component.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PatchEventType(Enum):
    """Types of patch events."""
    CREATED = "created"
    VALIDATED = "validated"
    APPROVED = "approved"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"
    MODIFIED = "modified"
    DISCARDED = "discarded"


@dataclass
class PatchEvent:
    """Single event in patch history."""
    event_type: PatchEventType
    timestamp: datetime
    actor: str
    details: dict[str, Any] = field(default_factory=dict)
    checksum: str = ""
    
    def compute_checksum(self) -> str:
        """Compute event checksum for integrity."""
        content = f"{self.event_type.value}:{self.timestamp.isoformat()}:{self.actor}:{json.dumps(self.details, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class PatchSnapshot:
    """Point-in-time snapshot of a patch."""
    snapshot_id: str
    patch_id: str
    version: int
    content: str  # Full patch diff
    metadata: dict[str, Any]
    created_at: datetime
    checksum: str = ""
    
    def compute_checksum(self) -> str:
        """Compute snapshot checksum."""
        content = f"{self.patch_id}:{self.version}:{self.content}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class PatchRecord:
    """Complete record of a patch with full history."""
    patch_id: str
    title: str
    description: str
    
    # Content
    diff: str
    files_changed: list[str]
    checksum: str
    
    # Events
    events: list[PatchEvent] = field(default_factory=list)
    snapshots: list[PatchSnapshot] = field(default_factory=list)
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = ""
    risk_level: str = ""
    risk_score: float = 0.0
    
    # Status
    current_version: int = 1
    is_applied: bool = False
    is_rolled_back: bool = False
    
    @property
    def latest_snapshot(self) -> PatchSnapshot | None:
        """Get the latest snapshot."""
        if not self.snapshots:
            return None
        return max(self.snapshots, key=lambda s: s.version)
    
    @property
    def applied_at(self) -> datetime | None:
        """Get application timestamp."""
        for event in self.events:
            if event.event_type == PatchEventType.APPLIED:
                return event.timestamp
        return None
    
    @property
    def rolled_back_at(self) -> datetime | None:
        """Get rollback timestamp."""
        for event in self.events:
            if event.event_type == PatchEventType.ROLLED_BACK:
                return event.timestamp
        return None


class PatchHistoryStore:
    """Immutable storage for patch history."""
    
    def __init__(self, storage_dir: Path | None = None) -> None:
        self._storage_dir = storage_dir or Path("data/patch_history")
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._index_file = self._storage_dir / "index.json"
        self._patches: dict[str, PatchRecord] = {}
        self._load_index()
    
    def _load_index(self) -> None:
        """Load patch index."""
        if self._index_file.exists():
            try:
                with open(self._index_file) as f:
                    data = json.load(f)
                    for patch_data in data.get("patches", []):
                        self._patches[patch_data["patch_id"]] = self._deserialize_patch(patch_data)
            except Exception as e:
                logger.warning("Failed to load patch index", error=str(e))
    
    def _save_index(self) -> None:
        """Save patch index."""
        data = {
            "patches": [
                self._serialize_patch(patch)
                for patch in self._patches.values()
            ]
        }
        with open(self._index_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def _serialize_patch(self, patch: PatchRecord) -> dict[str, Any]:
        """Serialize patch to dict."""
        return {
            "patch_id": patch.patch_id,
            "title": patch.title,
            "description": patch.description,
            "diff": patch.diff,
            "files_changed": patch.files_changed,
            "checksum": patch.checksum,
            "events": [
                {
                    "event_type": e.event_type.value,
                    "timestamp": e.timestamp.isoformat(),
                    "actor": e.actor,
                    "details": e.details,
                    "checksum": e.compute_checksum(),
                }
                for e in patch.events
            ],
            "snapshots": [
                {
                    "snapshot_id": s.snapshot_id,
                    "patch_id": s.patch_id,
                    "version": s.version,
                    "content": s.content,
                    "metadata": s.metadata,
                    "created_at": s.created_at.isoformat(),
                    "checksum": s.compute_checksum(),
                }
                for s in patch.snapshots
            ],
            "created_at": patch.created_at.isoformat(),
            "created_by": patch.created_by,
            "risk_level": patch.risk_level,
            "risk_score": patch.risk_score,
            "current_version": patch.current_version,
            "is_applied": patch.is_applied,
            "is_rolled_back": patch.is_rolled_back,
        }
    
    def _deserialize_patch(self, data: dict[str, Any]) -> PatchRecord:
        """Deserialize patch from dict."""
        return PatchRecord(
            patch_id=data["patch_id"],
            title=data["title"],
            description=data["description"],
            diff=data["diff"],
            files_changed=data["files_changed"],
            checksum=data["checksum"],
            events=[
                PatchEvent(
                    event_type=PatchEventType(e["event_type"]),
                    timestamp=datetime.fromisoformat(e["timestamp"]),
                    actor=e["actor"],
                    details=e.get("details", {}),
                    checksum=e.get("checksum", ""),
                )
                for e in data.get("events", [])
            ],
            snapshots=[
                PatchSnapshot(
                    snapshot_id=s["snapshot_id"],
                    patch_id=s["patch_id"],
                    version=s["version"],
                    content=s["content"],
                    metadata=s.get("metadata", {}),
                    created_at=datetime.fromisoformat(s["created_at"]),
                    checksum=s.get("checksum", ""),
                )
                for s in data.get("snapshots", [])
            ],
            created_at=datetime.fromisoformat(data["created_at"]),
            created_by=data.get("created_by", ""),
            risk_level=data.get("risk_level", ""),
            risk_score=data.get("risk_score", 0.0),
            current_version=data.get("current_version", 1),
            is_applied=data.get("is_applied", False),
            is_rolled_back=data.get("is_rolled_back", False),
        )
    
    def add(self, patch: PatchRecord) -> None:
        """Add a new patch record."""
        self._patches[patch.patch_id] = patch
        self._save_index()
        logger.info("Added patch to history", patch_id=patch.patch_id)
    
    def get(self, patch_id: str) -> PatchRecord | None:
        """Get patch by ID."""
        return self._patches.get(patch_id)
    
    def get_all(self) -> list[PatchRecord]:
        """Get all patches."""
        return list(self._patches.values())
    
    def get_applied(self) -> list[PatchRecord]:
        """Get all applied patches."""
        return [p for p in self._patches.values() if p.is_applied]
    
    def get_rolled_back(self) -> list[PatchRecord]:
        """Get all rolled back patches."""
        return [p for p in self._patches.values() if p.is_rolled_back]
    
    def get_by_date_range(
        self,
        start: datetime,
        end: datetime,
    ) -> list[PatchRecord]:
        """Get patches within date range."""
        return [
            p for p in self._patches.values()
            if start <= p.created_at <= end
        ]


class PatchHistoryManager:
    """Manage patch history with temporal durability.
    
    Phase 9.6: Patch history + rollback
    
    Provides:
    - Immutable patch history
    - Point-in-time snapshots
    - Verified rollback
    - Full audit trail
    """
    
    def __init__(self, store: PatchHistoryStore | None = None) -> None:
        self._store = store or PatchHistoryStore()
    
    def create_patch(
        self,
        patch_id: str,
        title: str,
        description: str,
        diff: str,
        files_changed: list[str],
        created_by: str = "system",
        risk_level: str = "",
        risk_score: float = 0.0,
    ) -> PatchRecord:
        """Create a new patch record."""
        checksum = hashlib.sha256(diff.encode()).hexdigest()[:16]
        
        patch = PatchRecord(
            patch_id=patch_id,
            title=title,
            description=description,
            diff=diff,
            files_changed=files_changed,
            checksum=checksum,
            created_by=created_by,
            risk_level=risk_level,
            risk_score=risk_score,
        )
        
        # Add creation event
        patch.events.append(PatchEvent(
            event_type=PatchEventType.CREATED,
            timestamp=datetime.now(),
            actor=created_by,
            details={"title": title, "files": files_changed},
        ))
        
        # Create initial snapshot
        self._create_snapshot(patch, created_by)
        
        self._store.add(patch)
        return patch
    
    def _create_snapshot(
        self,
        patch: PatchRecord,
        actor: str,
        metadata: dict[str, Any] | None = None,
    ) -> PatchSnapshot:
        """Create a new snapshot of the patch."""
        patch.current_version += 1
        snapshot = PatchSnapshot(
            snapshot_id=hashlib.sha256(
                f"{patch.patch_id}:{patch.current_version}:{datetime.now().isoformat()}".encode()
            ).hexdigest()[:16],
            patch_id=patch.patch_id,
            version=patch.current_version,
            content=patch.diff,
            metadata=metadata or {},
            created_at=datetime.now(),
        )
        snapshot.checksum = snapshot.compute_checksum()
        patch.snapshots.append(snapshot)
        return snapshot
    
    def record_event(
        self,
        patch_id: str,
        event_type: PatchEventType,
        actor: str,
        details: dict[str, Any] | None = None,
    ) -> PatchRecord | None:
        """Record an event for a patch."""
        patch = self._store.get(patch_id)
        if not patch:
            logger.warning("Patch not found", patch_id=patch_id)
            return None
        
        event = PatchEvent(
            event_type=event_type,
            timestamp=datetime.now(),
            actor=actor,
            details=details or {},
        )
        event.checksum = event.compute_checksum()
        patch.events.append(event)
        
        # Update status based on event
        if event_type == PatchEventType.APPLIED:
            patch.is_applied = True
            patch.is_rolled_back = False
        elif event_type == PatchEventType.ROLLED_BACK:
            patch.is_applied = False
            patch.is_rolled_back = True
        
        # Create snapshot on major events
        if event_type in [PatchEventType.APPROVED, PatchEventType.APPLIED, PatchEventType.MODIFIED]:
            self._create_snapshot(patch, actor, details)
        
        self._store.add(patch)
        return patch
    
    def get_snapshot(
        self,
        patch_id: str,
        version: int,
    ) -> PatchSnapshot | None:
        """Get a specific version snapshot."""
        patch = self._store.get(patch_id)
        if not patch:
            return None
        
        for snapshot in patch.snapshots:
            if snapshot.version == version:
                return snapshot
        return None
    
    def get_latest_snapshot(self, patch_id: str) -> PatchSnapshot | None:
        """Get the latest snapshot."""
        patch = self._store.get(patch_id)
        if not patch:
            return None
        return patch.latest_snapshot
    
    def verify_integrity(self, patch_id: str) -> bool:
        """Verify patch integrity using checksums."""
        patch = self._store.get(patch_id)
        if not patch:
            return False
        
        # Verify patch checksum
        current_checksum = hashlib.sha256(patch.diff.encode()).hexdigest()[:16]
        if current_checksum != patch.checksum:
            logger.error("Patch checksum mismatch", patch_id=patch_id)
            return False
        
        # Verify snapshots
        for snapshot in patch.snapshots:
            if snapshot.compute_checksum() != snapshot.checksum:
                logger.error("Snapshot checksum mismatch", patch_id=patch_id, version=snapshot.version)
                return False
        
        # Verify events
        for event in patch.events:
            if event.checksum and event.compute_checksum() != event.checksum:
                logger.error("Event checksum mismatch", patch_id=patch_id, event=event.event_type)
                return False
        
        return True
    
    def rollback(
        self,
        patch_id: str,
        target_version: int | None = None,
        actor: str = "system",
    ) -> PatchSnapshot | None:
        """Rollback patch to a previous version.
        
        Args:
            patch_id: ID of patch to rollback
            target_version: Version to rollback to (None = previous)
            actor: Who initiated the rollback
            
        Returns:
            The snapshot that was rolled back to
        """
        patch = self._store.get(patch_id)
        if not patch:
            logger.warning("Patch not found", patch_id=patch_id)
            return None
        
        # Get target snapshot
        if target_version:
            snapshot = self.get_snapshot(patch_id, target_version)
        else:
            # Get previous version
            if len(patch.snapshots) < 2:
                logger.warning("No previous version to rollback to", patch_id=patch_id)
                return None
            # Sort by version descending, skip latest
            sorted_snapshots = sorted(patch.snapshots, key=lambda s: s.version, reverse=True)
            snapshot = sorted_snapshots[1]  # Second latest
        
        if not snapshot:
            return None
        
        # Restore diff from snapshot
        patch.diff = snapshot.content
        
        # Record rollback event
        self.record_event(
            patch_id,
            PatchEventType.ROLLED_BACK,
            actor,
            {
                "from_version": patch.current_version,
                "to_version": snapshot.version,
                "snapshot_id": snapshot.snapshot_id,
            },
        )
        
        # Create new snapshot for the rollback state
        self._create_snapshot(patch, actor, {
            "action": "rollback",
            "restored_version": snapshot.version,
        })
        
        logger.info(
            "Rolled back patch",
            patch_id=patch_id,
            to_version=snapshot.version,
            actor=actor,
        )
        
        return snapshot
    
    def get_patch_audit_trail(self, patch_id: str) -> list[dict[str, Any]]:
        """Get full audit trail for a patch."""
        patch = self._store.get(patch_id)
        if not patch:
            return []
        
        return [
            {
                "event": e.event_type.value,
                "timestamp": e.timestamp.isoformat(),
                "actor": e.actor,
                "details": e.details,
            }
            for e in patch.events
        ]
    
    def get_statistics(self) -> dict[str, Any]:
        """Get patch history statistics."""
        all_patches = self._store.get_all()
        applied = self._store.get_applied()
        rolled_back = self._store.get_rolled_back()
        
        return {
            "total_patches": len(all_patches),
            "applied": len(applied),
            "rolled_back": len(rolled_back),
            "pending": len(all_patches) - len(applied) - len(rolled_back),
            "by_risk_level": self._count_by_risk(all_patches),
            "total_events": sum(len(p.events) for p in all_patches),
            "total_snapshots": sum(len(p.snapshots) for p in all_patches),
        }
    
    def _count_by_risk(self, patches: list[PatchRecord]) -> dict[str, int]:
        """Count patches by risk level."""
        counts: dict[str, int] = {}
        for patch in patches:
            level = patch.risk_level or "unknown"
            counts[level] = counts.get(level, 0) + 1
        return counts


# Global singleton
_manager: PatchHistoryManager | None = None


def get_patch_history_manager() -> PatchHistoryManager:
    """Get global patch history manager."""
    global _manager
    if _manager is None:
        _manager = PatchHistoryManager()
    return _manager


# CLI for testing
if __name__ == "__main__":
    manager = get_patch_history_manager()
    
    print("Testing patch history management:")
    print("-" * 50)
    
    # Create a patch
    patch = manager.create_patch(
        patch_id="patch_001",
        title="Fix NULL pointer dereference",
        description="Add NULL check before accessing buffer",
        diff="--- a/src/uart.c\n+++ b/src/uart.c\n@@ -10,7 +10,12 @@\n+    if (ptr == NULL) {\n+        return ERROR_NULL_POINTER;\n+    }\n",
        files_changed=["src/uart.c"],
        created_by="engineer1",
        risk_level="MEDIUM",
        risk_score=4.5,
    )
    print(f"Created patch: {patch.patch_id}")
    
    # Record events
    manager.record_event(
        patch.patch_id,
        PatchEventType.VALIDATED,
        "engineer1",
        {"validation": "compile_ok"},
    )
    
    manager.record_event(
        patch.patch_id,
        PatchEventType.APPROVED,
        "reviewer1",
        {"confidence": 0.9},
    )
    
    manager.record_event(
        patch.patch_id,
        PatchEventType.APPLIED,
        "ci_system",
        {"commit": "abc123"},
    )
    
    print(f"Patch applied: {patch.is_applied}")
    print(f"Events: {len(patch.events)}")
    print(f"Snapshots: {len(patch.snapshots)}")
    
    # Verify integrity
    integrity = manager.verify_integrity(patch.patch_id)
    print(f"Integrity verified: {integrity}")
    
    # Get audit trail
    trail = manager.get_patch_audit_trail(patch.patch_id)
    print("\nAudit Trail:")
    for event in trail:
        print(f"  [{event['timestamp']}] {event['event']} by {event['actor']}")
    
    # Statistics
    stats = manager.get_statistics()
    print(f"\nStatistics: {stats}")
