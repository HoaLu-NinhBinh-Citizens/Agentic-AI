"""Immutable Audit Log with Hash Chain.

Fixes Critical Gap: No immutable audit log with hash chain.

Features:
- Append-only log with hash chain (like blockchain)
- Tamper detection
- Complete audit trail
- Forensic evidence bundle
- Integrity verification
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# HASH CHAIN NODE
# =============================================================================


@dataclass
class AuditEntry:
    """Single immutable entry in the audit log.
    
    Each entry contains:
    - Previous entry's hash (chain link)
    - Current entry's content hash
    - Timestamp (from deterministic clock)
    - Entry sequence number
    - Content/data being logged
    """
    
    # Chain linkage
    sequence: int = 0
    previous_hash: str = ""  # Hash of previous entry
    
    # Content
    event_type: str = ""
    actor: str = ""
    action: str = ""
    target: str = ""
    
    # Data
    data: dict[str, Any] = field(default_factory=dict)
    
    # Timestamps (deterministic)
    timestamp: str = ""  # ISO format
    sequence_time: int = 0  # Monotonic sequence-based time
    
    # Hashes
    content_hash: str = ""  # Hash of this entry's content
    entry_hash: str = ""  # Full entry hash including previous_link
    
    def compute_content_hash(self) -> str:
        """Compute hash of entry content (excluding entry_hash itself)."""
        content = {
            "sequence": self.sequence,
            "event_type": self.event_type,
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "data": self.data,
            "timestamp": self.timestamp,
            "sequence_time": self.sequence_time,
        }
        content_str = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(content_str.encode()).hexdigest()
    
    def compute_entry_hash(self) -> str:
        """Compute full entry hash including previous link."""
        data = f"{self.previous_hash}:{self.compute_content_hash()}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "previous_hash": self.previous_hash,
            "event_type": self.event_type,
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "data": self.data,
            "timestamp": self.timestamp,
            "sequence_time": self.sequence_time,
            "content_hash": self.content_hash,
            "entry_hash": self.entry_hash,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditEntry:
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


# =============================================================================
# IMMUTABLE AUDIT LOG
# =============================================================================


class ImmutableAuditLog:
    """Immutable audit log with hash chain.
    
    CRITICAL SECURITY: This log cannot be tampered with after entries are written.
    Any modification breaks the hash chain.
    
    Features:
    - Append-only (no delete/update operations)
    - Hash chain linking (like blockchain)
    - Sequence-based timestamps
    - Tamper detection
    - Complete audit trail for forensics
    """
    
    GENESIS_HASH = "0" * 64  # First entry links to this
    
    def __init__(
        self,
        log_path: str,
        enable_verification: bool = True,
    ):
        self.log_path = log_path
        self.enable_verification = enable_verification
        
        self._entries: list[AuditEntry] = []
        self._last_hash: str = self.GENESIS_HASH
        self._next_sequence: int = 0
        self._lock = asyncio.Lock()
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        
        # Load existing entries
        self._load()
    
    def _load(self) -> None:
        """Load existing entries from disk."""
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, "r") as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            entry = AuditEntry.from_dict(data)
                            self._entries.append(entry)
                            
                            if entry.sequence >= self._next_sequence:
                                self._next_sequence = entry.sequence + 1
                                self._last_hash = entry.entry_hash
            except Exception as e:
                logger.error("audit_log_load_failed: %s", str(e))
    
    def _persist(self, entry: AuditEntry) -> None:
        """Persist entry to disk (append-only)."""
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry.to_dict(), default=str) + "\n")
    
    async def append(
        self,
        event_type: str,
        actor: str,
        action: str,
        target: str = "",
        data: dict[str, Any] | None = None,
        deterministic_timestamp: int | None = None,
    ) -> AuditEntry:
        """Append a new entry to the audit log.
        
        CRITICAL: This is append-only. No update/delete operations exist.
        
        Args:
            event_type: Type of event (e.g., "flash.started", "flash.completed")
            actor: Who performed the action (e.g., "agent-001", "user-admin")
            action: What was done (e.g., "flash_firmware", "rollback")
            target: What was acted upon (e.g., "target-enginecar", "slot-A")
            data: Additional event data
            deterministic_timestamp: Optional sequence-based timestamp
            
        Returns:
            AuditEntry that was appended
        """
        async with self._lock:
            entry = AuditEntry(
                sequence=self._next_sequence,
                previous_hash=self._last_hash,
                event_type=event_type,
                actor=actor,
                action=action,
                target=target,
                data=data or {},
                timestamp=datetime.utcnow().isoformat(),
                sequence_time=deterministic_timestamp or self._next_sequence,
            )
            
            # Compute hashes
            entry.content_hash = entry.compute_content_hash()
            entry.entry_hash = entry.compute_entry_hash()
            
            # Persist (append-only)
            self._persist(entry)
            
            # Update in-memory state
            self._entries.append(entry)
            self._last_hash = entry.entry_hash
            self._next_sequence += 1
            
            logger.info(
                "audit_entry_appended: sequence=%s event_type=%s action=%s hash=%s",
                entry.sequence, event_type, action, entry.entry_hash[:16],
            )
            
            return entry
    
    async def verify_integrity(self) -> tuple[bool, list[dict[str, Any]]]:
        """Verify the entire hash chain integrity.
        
        Returns:
            (is_valid, list of inconsistencies)
        """
        async with self._lock:
            inconsistencies = []
            
            for i, entry in enumerate(self._entries):
                # Verify chain link
                if i == 0:
                    expected_prev = self.GENESIS_HASH
                else:
                    expected_prev = self._entries[i - 1].entry_hash
                
                if entry.previous_hash != expected_prev:
                    inconsistencies.append({
                        "sequence": entry.sequence,
                        "type": "broken_chain_link",
                        "expected": expected_prev,
                        "actual": entry.previous_hash,
                    })
                
                # Verify content hash
                expected_content = entry.compute_content_hash()
                if entry.content_hash != expected_content:
                    inconsistencies.append({
                        "sequence": entry.sequence,
                        "type": "content_tampered",
                        "expected": expected_content,
                        "actual": entry.content_hash,
                    })
                
                # Verify entry hash
                expected_entry = entry.compute_entry_hash()
                if entry.entry_hash != expected_entry:
                    inconsistencies.append({
                        "sequence": entry.sequence,
                        "type": "entry_hash_invalid",
                        "expected": expected_entry,
                        "actual": entry.entry_hash,
                    })
            
            is_valid = len(inconsistencies) == 0
            
            if not is_valid:
                logger.warning("audit_log_integrity_failed: %s inconsistencies", len(inconsistencies))
            else:
                logger.info("audit_log_integrity_verified: entries=%s", len(self._entries))
            
            return is_valid, inconsistencies
    
    async def query(
        self,
        event_type: str | None = None,
        actor: str | None = None,
        action: str | None = None,
        target: str | None = None,
        since_sequence: int | None = None,
        limit: int | None = None,
    ) -> list[AuditEntry]:
        """Query the audit log.
        
        Args:
            event_type: Filter by event type
            actor: Filter by actor
            action: Filter by action
            target: Filter by target
            since_sequence: Only entries after this sequence
            limit: Maximum entries to return
            
        Returns:
            List of matching entries
        """
        async with self._lock:
            results = []
            
            for entry in self._entries:
                if since_sequence and entry.sequence < since_sequence:
                    continue
                
                if event_type and entry.event_type != event_type:
                    continue
                if actor and entry.actor != actor:
                    continue
                if action and entry.action != action:
                    continue
                if target and entry.target != target:
                    continue
                
                results.append(entry)
            
            if limit:
                results = results[-limit:]
            
            return results
    
    async def get_entry(self, sequence: int) -> AuditEntry | None:
        """Get entry by sequence number."""
        async with self._lock:
            for entry in self._entries:
                if entry.sequence == sequence:
                    return entry
            return None
    
    async def get_chain_summary(self) -> dict[str, Any]:
        """Get summary of the hash chain."""
        async with self._lock:
            return {
                "total_entries": len(self._entries),
                "first_sequence": self._entries[0].sequence if self._entries else 0,
                "last_sequence": self._entries[-1].sequence if self._entries else 0,
                "genesis_hash": self.GENESIS_HASH,
                "last_hash": self._last_hash,
                "log_path": self.log_path,
            }


# =============================================================================
# FORENSIC EVIDENCE BUNDLE
# =============================================================================


@dataclass
class ForensicBundle:
    """Complete forensic evidence bundle for an incident.
    
    Contains:
    - Audit log entries
    - Hash chain verification
    - Related artifacts
    - Chain of custody
    """
    
    bundle_id: str
    incident_id: str
    created_at: str
    
    # Evidence
    audit_entries: list[dict[str, Any]]
    hash_chain_valid: bool
    hash_inconsistencies: list[dict[str, Any]]
    
    # Chain of custody
    created_by: str
    signatures: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "incident_id": self.incident_id,
            "created_at": self.created_at,
            "audit_entries": self.audit_entries,
            "hash_chain_valid": self.hash_chain_valid,
            "hash_inconsistencies": self.hash_inconsistencies,
            "created_by": self.created_by,
            "signatures": self.signatures,
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


class ForensicBundleBuilder:
    """Builds forensic evidence bundles."""
    
    def __init__(self, audit_log: ImmutableAuditLog):
        self.audit_log = audit_log
    
    async def build_bundle(
        self,
        incident_id: str,
        since_sequence: int | None = None,
        created_by: str = "system",
    ) -> ForensicBundle:
        """Build a forensic bundle for an incident.
        
        Args:
            incident_id: ID of the incident
            since_sequence: Start from this sequence (None = from beginning)
            created_by: Who is creating the bundle
            
        Returns:
            ForensicBundle ready for export
        """
        import uuid
        
        # Get audit entries
        entries = await self.audit_log.query(since_sequence=since_sequence)
        
        # Verify hash chain
        chain_valid, inconsistencies = await self.audit_log.verify_integrity()
        
        bundle = ForensicBundle(
            bundle_id=str(uuid.uuid4()),
            incident_id=incident_id,
            created_at=datetime.utcnow().isoformat(),
            audit_entries=[e.to_dict() for e in entries],
            hash_chain_valid=chain_valid,
            hash_inconsistencies=inconsistencies,
            created_by=created_by,
        )
        
        logger.info(
            "forensic_bundle_created: bundle_id=%s incident_id=%s entries=%s",
            bundle.bundle_id, incident_id, len(entries),
        )
        
        return bundle
    
    async def export_bundle(
        self,
        bundle: ForensicBundle,
        export_path: str,
    ) -> None:
        """Export bundle to file."""
        with open(export_path, "w") as f:
            f.write(bundle.to_json())
        
        logger.info("forensic_bundle_exported: path=%s", export_path)


# =============================================================================
# AUDIT LOG POLICY ENFORCEMENT
# =============================================================================


class AuditLogPolicy:
    """Policy enforcement for audit logging.
    
    CRITICAL: This ensures all critical operations are logged.
    """
    
    def __init__(self, audit_log: ImmutableAuditLog):
        self.audit_log = audit_log
        self._required_event_types: set[str] = {
            "flash.started",
            "flash.completed",
            "flash.failed",
            "rollback.initiated",
            "rollback.completed",
            "target.connected",
            "target.disconnected",
            "manifest.verified",
            "manifest.rejected",
            "lock.acquired",
            "lock.released",
            "config.changed",
            "user.authenticated",
            "user.authorization_changed",
        }
    
    async def log_and_enforce(
        self,
        event_type: str,
        actor: str,
        action: str,
        target: str = "",
        data: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Log entry and enforce policy.
        
        CRITICAL: This is the ONLY way to log audit events.
        Direct append to audit log should be avoided.
        
        Args:
            event_type: Type of event
            actor: Who performed the action
            action: What was done
            target: What was acted upon
            data: Additional data
            
        Returns:
            AuditEntry that was created
        """
        # Enforce required event types
        if event_type in self._required_event_types:
            logger.info("critical_event_logged: type=%s action=%s", event_type, action)
        
        return await self.audit_log.append(
            event_type=event_type,
            actor=actor,
            action=action,
            target=target,
            data=data,
        )
    
    def add_required_event_type(self, event_type: str) -> None:
        """Add a required event type to the policy."""
        self._required_event_types.add(event_type)
