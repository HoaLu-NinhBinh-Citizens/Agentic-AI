"""Event log integrity (hash chain, tamper detection) - Phase 5B v10.

Implements event log integrity:
- HashChainValidator: Validates hash chain
- EventIntegrityManager: Manages event integrity
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class EventIntegrityInfo:
    """Integrity information for an event."""
    event_id: str
    sequence: int
    previous_hash: str
    event_hash: str
    timestamp: int
    verified: bool = False


@dataclass
class IntegrityCheckResult:
    """Result of integrity check."""
    valid: bool
    broken_at: Optional[int] = None
    errors: list[str] = field(default_factory=list)


class HashChainValidator:
    """Validates hash chain integrity of event logs.
    
    Each event contains a hash of the previous event,
    creating a tamper-evident chain.
    """
    
    def __init__(
        self,
        hash_algorithm: str = "sha256",
    ):
        self._algorithm = hash_algorithm
    
    def compute_hash(self, data: Any) -> str:
        """Compute hash of data.
        
        Args:
            data: Data to hash
            
        Returns:
            Hash hex string
        """
        content = str(data).encode('utf-8')
        
        if self._algorithm == "sha256":
            return hashlib.sha256(content).hexdigest()
        elif self._algorithm == "sha384":
            return hashlib.sha384(content).hexdigest()
        elif self._algorithm == "sha512":
            return hashlib.sha512(content).hexdigest()
        else:
            return hashlib.sha256(content).hexdigest()
    
    def compute_event_hash(
        self,
        event_id: str,
        sequence: int,
        event_type: str,
        event_data: dict,
    ) -> str:
        """Compute hash for an event.
        
        Args:
            event_id: Event identifier
            sequence: Sequence number
            event_type: Event type
            event_data: Event data
            
        Returns:
            Event hash
        """
        content = f"{event_id}:{sequence}:{event_type}:{str(event_data)}"
        return self.compute_hash(content)
    
    def verify_event_hash(
        self,
        event: dict,
    ) -> bool:
        """Verify an event's hash matches its content.
        
        Args:
            event: Event dictionary
            
        Returns:
            True if hash is valid
        """
        event_hash = event.get("event_hash", "")
        computed = self.compute_event_hash(
            event_id=event.get("event_id", ""),
            sequence=event.get("sequence", 0),
            event_type=event.get("event_type", ""),
            event_data=event.get("data", {}),
        )
        
        return event_hash == computed
    
    def verify_chain(
        self,
        events: list[dict],
    ) -> IntegrityCheckResult:
        """Verify entire event chain.
        
        Args:
            events: List of events in order
            
        Returns:
            Integrity check result
        """
        if not events:
            return IntegrityCheckResult(valid=True)
        
        previous_hash = "genesis"
        
        for i, event in enumerate(events):
            event_previous_hash = event.get("previous_hash", "")
            
            if event_previous_hash != previous_hash:
                return IntegrityCheckResult(
                    valid=False,
                    broken_at=i,
                    errors=[f"Chain broken at event {i}: previous hash mismatch"],
                )
            
            event_hash = event.get("event_hash", "")
            computed = self.compute_event_hash(
                event_id=event.get("event_id", ""),
                sequence=event.get("sequence", 0),
                event_type=event.get("event_type", ""),
                event_data=event.get("data", {}),
            )
            
            if event_hash != computed:
                return IntegrityCheckResult(
                    valid=False,
                    broken_at=i,
                    errors=[f"Event hash mismatch at event {i}"],
                )
            
            previous_hash = event_hash
        
        return IntegrityCheckResult(valid=True)
    
    def verify_tamper_detection(
        self,
        original_events: list[dict],
        modified_events: list[dict],
    ) -> list[int]:
        """Detect which events were tampered with.
        
        Args:
            original_events: Original event chain
            modified_events: Potentially modified event chain
            
        Returns:
            List of sequence numbers that were modified
        """
        tampered = []
        
        for i, (orig, mod) in enumerate(zip(original_events, modified_events)):
            orig_hash = orig.get("event_hash", "")
            mod_hash = mod.get("event_hash", "")
            
            if orig_hash != mod_hash:
                tampered.append(orig.get("sequence", i))
        
        return tampered


class EventIntegrityManager:
    """Manages event log integrity.
    
    Provides:
    - Hash chain computation and storage
    - Integrity verification
    - Tamper detection
    """
    
    def __init__(
        self,
        validator: Optional[HashChainValidator] = None,
        audit_interval_hours: int = 24,
    ):
        self._validator = validator or HashChainValidator()
        self._audit_interval = audit_interval_hours * 3600
        self._last_audit: dict[str, int] = {}
    
    def compute_event_chain(
        self,
        workflow_id: str,
        events: list[dict],
    ) -> list[dict]:
        """Compute hash chain for events.
        
        Args:
            workflow_id: Workflow identifier
            events: Events to chain
            
        Returns:
            Events with hash chain computed
        """
        previous_hash = self._get_genesis_hash(workflow_id)
        
        chained = []
        for i, event in enumerate(events):
            event_hash = self._validator.compute_event_hash(
                event_id=event.get("event_id", f"{workflow_id}_event_{i}"),
                sequence=i,
                event_type=event.get("event_type", ""),
                event_data=event.get("data", {}),
            )
            
            chained_event = event.copy()
            chained_event["sequence"] = i
            chained_event["previous_hash"] = previous_hash
            chained_event["event_hash"] = event_hash
            chained_event["timestamp"] = int(time.time())
            
            chained.append(chained_event)
            previous_hash = event_hash
        
        return chained
    
    def _get_genesis_hash(self, workflow_id: str) -> str:
        """Get genesis hash for a workflow."""
        return self._validator.compute_hash(f"genesis:{workflow_id}")
    
    def verify_workflow_chain(
        self,
        workflow_id: str,
        events: list[dict],
    ) -> IntegrityCheckResult:
        """Verify integrity of a workflow's event chain.
        
        Args:
            workflow_id: Workflow identifier
            events: Events to verify
            
        Returns:
            Integrity check result
        """
        if not events:
            return IntegrityCheckResult(valid=True)
        
        expected_genesis = self._get_genesis_hash(workflow_id)
        first_previous = events[0].get("previous_hash", "")
        
        if first_previous != expected_genesis:
            return IntegrityCheckResult(
                valid=False,
                broken_at=0,
                errors=["Genesis hash mismatch"],
            )
        
        return self._validator.verify_chain(events)
    
    async def verify_and_report(
        self,
        workflow_id: str,
        events: list[dict],
    ) -> IntegrityCheckResult:
        """Verify chain and record audit.
        
        Args:
            workflow_id: Workflow identifier
            events: Events to verify
            
        Returns:
            Integrity check result
        """
        result = self.verify_workflow_chain(workflow_id, events)
        
        self._last_audit[workflow_id] = int(time.time())
        
        return result
    
    def get_last_audit_time(self, workflow_id: str) -> Optional[int]:
        """Get timestamp of last integrity audit."""
        return self._last_audit.get(workflow_id)
    
    def is_audit_due(self, workflow_id: str) -> bool:
        """Check if audit is due.
        
        Args:
            workflow_id: Workflow identifier
            
        Returns:
            True if audit is due
        """
        last = self._last_audit.get(workflow_id, 0)
        return (int(time.time()) - last) > self._audit_interval


class EventStoreWithIntegrity:
    """Event store with built-in integrity.
    
    Wraps an event store with hash chain support.
    """
    
    def __init__(
        self,
        base_store: dict,
        integrity_manager: EventIntegrityManager,
    ):
        self._store = base_store
        self._integrity = integrity_manager
        self._metadata: dict[str, dict] = {}
    
    async def append_event(
        self,
        workflow_id: str,
        event: dict,
    ) -> dict:
        """Append an event with integrity hash.
        
        Args:
            workflow_id: Workflow identifier
            event: Event data
            
        Returns:
            Event with hash chain
        """
        if workflow_id not in self._store:
            self._store[workflow_id] = []
        
        events = self._store[workflow_id]
        
        if events:
            previous_hash = events[-1].get("event_hash", "")
        else:
            previous_hash = self._integrity._get_genesis_hash(workflow_id)
        
        import uuid
        
        event_hash = self._integrity._validator.compute_event_hash(
            event_id=event.get("event_id", str(uuid.uuid4())),
            sequence=len(events),
            event_type=event.get("event_type", ""),
            event_data=event.get("data", {}),
        )
        
        chained_event = {
            **event,
            "event_id": event.get("event_id", str(uuid.uuid4())),
            "sequence": len(events),
            "previous_hash": previous_hash,
            "event_hash": event_hash,
            "timestamp": int(time.time()),
        }
        
        self._store[workflow_id].append(chained_event)
        
        return chained_event
    
    async def get_events(
        self,
        workflow_id: str,
    ) -> list[dict]:
        """Get all events for a workflow."""
        return self._store.get(workflow_id, [])
    
    async def verify_integrity(
        self,
        workflow_id: str,
    ) -> IntegrityCheckResult:
        """Verify integrity of workflow events."""
        events = await self.get_events(workflow_id)
        return self._integrity.verify_workflow_chain(workflow_id, events)
