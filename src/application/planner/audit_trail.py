"""Human audit trail - Phase 5B."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from .types import HumanAction, HumanAuditEntry


class HumanAuditStore:
    """Store interface for human audit entries."""
    
    async def save(self, entry: HumanAuditEntry) -> None:
        """Save an audit entry."""
        raise NotImplementedError
    
    async def get(self, action_id: str) -> Optional[HumanAuditEntry]:
        """Get an audit entry by ID."""
        raise NotImplementedError
    
    async def get_by_plan(
        self,
        plan_id: str,
    ) -> list[HumanAuditEntry]:
        """Get all entries for a plan."""
        raise NotImplementedError
    
    async def get_by_interrupt(
        self,
        interrupt_id: str,
    ) -> list[HumanAuditEntry]:
        """Get all entries for an interrupt."""
        raise NotImplementedError


class InMemoryHumanAuditStore(HumanAuditStore):
    """In-memory implementation of human audit store."""
    
    def __init__(self):
        self._entries: dict[str, HumanAuditEntry] = {}
        self._by_plan: dict[str, list[str]] = {}
        self._by_interrupt: dict[str, list[str]] = {}
    
    async def save(self, entry: HumanAuditEntry) -> None:
        """Save an audit entry."""
        self._entries[entry.action_id] = entry
        
        if entry.plan_id not in self._by_plan:
            self._by_plan[entry.plan_id] = []
        self._by_plan[entry.plan_id].append(entry.action_id)
        
        if entry.interrupt_id:
            if entry.interrupt_id not in self._by_interrupt:
                self._by_interrupt[entry.interrupt_id] = []
            self._by_interrupt[entry.interrupt_id].append(entry.action_id)
    
    async def get(self, action_id: str) -> Optional[HumanAuditEntry]:
        """Get an audit entry by ID."""
        return self._entries.get(action_id)
    
    async def get_by_plan(
        self,
        plan_id: str,
    ) -> list[HumanAuditEntry]:
        """Get all entries for a plan."""
        action_ids = self._by_plan.get(plan_id, [])
        return [
            self._entries[aid]
            for aid in action_ids
            if aid in self._entries
        ]
    
    async def get_by_interrupt(
        self,
        interrupt_id: str,
    ) -> list[HumanAuditEntry]:
        """Get all entries for an interrupt."""
        action_ids = self._by_interrupt.get(interrupt_id, [])
        return [
            self._entries[aid]
            for aid in action_ids
            if aid in self._entries
        ]


class HumanAuditTrail:
    """Human-in-the-loop audit trail.
    
    Records all human interactions with plans including
    resume, cancel, approve, and reject actions.
    """
    
    def __init__(
        self,
        store: HumanAuditStore,
        include_source_ip: bool = True,
    ):
        self._store = store
        self._include_ip = include_source_ip
    
    async def log_action(
        self,
        plan_id: str,
        action: HumanAction,
        approved_by: str,
        interrupt_id: Optional[str] = None,
        reason: Optional[str] = None,
        source_ip: Optional[str] = None,
    ) -> HumanAuditEntry:
        """Log a human action.
        
        Args:
            plan_id: Plan identifier
            action: The action performed
            approved_by: User who performed the action
            interrupt_id: Optional interrupt ID
            reason: Optional reason for action
            source_ip: Optional source IP address
            
        Returns:
            The created audit entry
        """
        if not self._include_ip:
            source_ip = None
        
        entry = HumanAuditEntry(
            action_id=str(uuid.uuid4()),
            plan_id=plan_id,
            interrupt_id=interrupt_id,
            action=action,
            approved_by=approved_by,
            approved_at=int(datetime.utcnow().timestamp()),
            reason=reason,
            source_ip=source_ip,
        )
        
        await self._store.save(entry)
        
        return entry
    
    async def log_resume(
        self,
        plan_id: str,
        approved_by: str,
        interrupt_id: str,
        user_input: Optional[dict] = None,
        reason: Optional[str] = None,
        source_ip: Optional[str] = None,
    ) -> HumanAuditEntry:
        """Log a resume action.
        
        Args:
            plan_id: Plan identifier
            approved_by: User who resumed
            interrupt_id: Interrupt ID being resumed
            user_input: Optional user input provided
            reason: Optional reason
            source_ip: Optional source IP
            
        Returns:
            The audit entry
        """
        entry_data = {
            "plan_id": plan_id,
            "interrupt_id": interrupt_id,
            "reason": reason,
            "user_input_provided": user_input is not None,
        }
        
        return await self.log_action(
            plan_id=plan_id,
            action=HumanAction.RESUME,
            approved_by=approved_by,
            interrupt_id=interrupt_id,
            reason=reason,
            source_ip=source_ip,
        )
    
    async def log_cancel(
        self,
        plan_id: str,
        approved_by: str,
        interrupt_id: Optional[str] = None,
        reason: Optional[str] = None,
        source_ip: Optional[str] = None,
    ) -> HumanAuditEntry:
        """Log a cancel action."""
        return await self.log_action(
            plan_id=plan_id,
            action=HumanAction.CANCEL,
            approved_by=approved_by,
            interrupt_id=interrupt_id,
            reason=reason,
            source_ip=source_ip,
        )
    
    async def log_approve(
        self,
        plan_id: str,
        approved_by: str,
        reason: Optional[str] = None,
        source_ip: Optional[str] = None,
    ) -> HumanAuditEntry:
        """Log an approve action."""
        return await self.log_action(
            plan_id=plan_id,
            action=HumanAction.APPROVE,
            approved_by=approved_by,
            reason=reason,
            source_ip=source_ip,
        )
    
    async def log_reject(
        self,
        plan_id: str,
        approved_by: str,
        reason: Optional[str] = None,
        source_ip: Optional[str] = None,
    ) -> HumanAuditEntry:
        """Log a reject action."""
        return await self.log_action(
            plan_id=plan_id,
            action=HumanAction.REJECT,
            approved_by=approved_by,
            reason=reason,
            source_ip=source_ip,
        )
    
    async def log_escalate(
        self,
        plan_id: str,
        approved_by: str,
        interrupt_id: Optional[str] = None,
        reason: Optional[str] = None,
        source_ip: Optional[str] = None,
    ) -> HumanAuditEntry:
        """Log an escalate action."""
        return await self.log_action(
            plan_id=plan_id,
            action=HumanAction.ESCALATE,
            approved_by=approved_by,
            interrupt_id=interrupt_id,
            reason=reason,
            source_ip=source_ip,
        )
    
    async def get_plan_audit_trail(
        self,
        plan_id: str,
    ) -> list[HumanAuditEntry]:
        """Get audit trail for a plan.
        
        Args:
            plan_id: Plan identifier
            
        Returns:
            List of audit entries in chronological order
        """
        entries = await self._store.get_by_plan(plan_id)
        return sorted(entries, key=lambda e: e.approved_at)
    
    async def get_interrupt_audit_trail(
        self,
        interrupt_id: str,
    ) -> list[HumanAuditEntry]:
        """Get audit trail for an interrupt.
        
        Args:
            interrupt_id: Interrupt identifier
            
        Returns:
            List of audit entries
        """
        entries = await self._store.get_by_interrupt(interrupt_id)
        return sorted(entries, key=lambda e: e.approved_at)
    
    async def get_recent_actions(
        self,
        limit: int = 100,
    ) -> list[HumanAuditEntry]:
        """Get recent actions across all plans."""
        if not isinstance(self._store, InMemoryHumanAuditStore):
            return []
        
        entries = list(self._store._entries.values())
        entries.sort(key=lambda e: e.approved_at, reverse=True)
        
        return entries[:limit]


class AuditTrailReporter:
    """Generates reports from audit trail."""
    
    def __init__(self, trail: HumanAuditTrail):
        self._trail = trail
    
    async def generate_summary(
        self,
        plan_id: str,
    ) -> dict:
        """Generate a summary report for a plan.
        
        Args:
            plan_id: Plan identifier
            
        Returns:
            Summary dictionary
        """
        entries = await self._trail.get_plan_audit_trail(plan_id)
        
        action_counts = {}
        users = set()
        
        for entry in entries:
            action = entry.action.value
            action_counts[action] = action_counts.get(action, 0) + 1
            users.add(entry.approved_by)
        
        return {
            "plan_id": plan_id,
            "total_actions": len(entries),
            "action_counts": action_counts,
            "unique_users": len(users),
            "first_action": entries[0].approved_at if entries else None,
            "last_action": entries[-1].approved_at if entries else None,
        }
    
    async def generate_user_report(
        self,
        user_id: str,
    ) -> dict:
        """Generate a report for a specific user."""
        if not isinstance(self._trail._store, InMemoryHumanAuditStore):
            return {}
        
        entries = [
            e for e in self._trail._store._entries.values()
            if e.approved_by == user_id
        ]
        
        action_counts = {}
        plans = set()
        
        for entry in entries:
            action = entry.action.value
            action_counts[action] = action_counts.get(action, 0) + 1
            plans.add(entry.plan_id)
        
        return {
            "user_id": user_id,
            "total_actions": len(entries),
            "action_counts": action_counts,
            "plans_touched": len(plans),
        }
