"""
Break-Glass Alert, DR Metrics, and Cost Chargeback.

Break-Glass Alert:
- Immediate alerting when emergency tokens are created/used
- Webhook notifications to Slack, PagerDuty, etc.

DR Metrics:
- Track RTO/RPO for disaster recovery
- Compare with SLO targets
- Alert on violations

Cost Chargeback:
- Track costs by tenant, team, project
- Generate reports for finance
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============== BREAK-GLASS ALERT ==============

class BreakGlassAction(str, Enum):
    """Break-glass actions."""
    CREATED = "created"
    USED = "used"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass
class BreakGlassEvent:
    """Break-glass event data."""
    token_id: str
    requester: str
    reason: str
    action: BreakGlassAction
    duration_seconds: int
    timestamp: datetime
    source_ip: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BreakGlassToken:
    """Break-glass emergency token."""
    token_id: str
    created_by: str
    reason: str
    created_at: datetime
    expires_at: datetime
    revoked: bool = False
    used_count: int = 0


class BreakGlassAlert:
    """
    Break-glass alerting system.
    
    Sends immediate alerts when:
    - Emergency tokens are created
    - Emergency tokens are used
    - Emergency tokens expire
    
    Webhook integrations for Slack, PagerDuty, etc.
    """
    
    def __init__(
        self,
        webhook_url: Optional[str] = None,
        alert_on_use: bool = True,
        alert_on_create: bool = True,
    ):
        self.webhook_url = webhook_url
        self.alert_on_use = alert_on_use
        self.alert_on_create = alert_on_create
        
        # Active tokens
        self._tokens: Dict[str, BreakGlassToken] = {}
        
        # Event history
        self._events: List[BreakGlassEvent] = []
        
        # Webhook handlers
        self._webhook_handlers: List[Callable] = []
        
        # Alert handlers
        self._alert_handlers: List[Callable] = []
        
        self._lock = asyncio.Lock()
    
    def register_webhook_handler(self, handler: Callable) -> None:
        """Register webhook handler."""
        self._webhook_handlers.append(handler)
    
    def register_alert_handler(self, handler: Callable) -> None:
        """Register alert handler."""
        self._alert_handlers.append(handler)
    
    async def create_token(
        self,
        requester: str,
        reason: str,
        duration_seconds: int = 3600,
        source_ip: Optional[str] = None,
    ) -> str:
        """Create break-glass token."""
        token_id = f"bg_{uuid.uuid4().hex[:16]}"
        
        token = BreakGlassToken(
            token_id=token_id,
            created_by=requester,
            reason=reason,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=duration_seconds),
        )
        
        async with self._lock:
            self._tokens[token_id] = token
        
        # Log event
        event = BreakGlassEvent(
            token_id=token_id,
            requester=requester,
            reason=reason,
            action=BreakGlassAction.CREATED,
            duration_seconds=duration_seconds,
            timestamp=datetime.now(),
            source_ip=source_ip,
        )
        self._events.append(event)
        
        # Alert
        if self.alert_on_create:
            await self._send_alert(event)
        
        logger.warning(f"Break-glass token {token_id} created by {requester}: {reason}")
        return token_id
    
    async def use_token(
        self,
        token_id: str,
        user: str,
        source_ip: Optional[str] = None,
    ) -> bool:
        """Use break-glass token."""
        async with self._lock:
            token = self._tokens.get(token_id)
            
            if not token:
                logger.warning(f"Break-glass token {token_id} not found")
                return False
            
            if token.revoked:
                logger.warning(f"Break-glass token {token_id} is revoked")
                return False
            
            if datetime.now() > token.expires_at:
                logger.warning(f"Break-glass token {token_id} is expired")
                return False
        
        # Log usage
        async with self._lock:
            token.used_count += 1
        
        event = BreakGlassEvent(
            token_id=token_id,
            requester=user,
            reason="",
            action=BreakGlassAction.USED,
            duration_seconds=0,
            timestamp=datetime.now(),
            source_ip=source_ip,
        )
        self._events.append(event)
        
        # Alert
        if self.alert_on_use:
            await self._send_alert(event)
        
        logger.warning(f"Break-glass token {token_id} used by {user}")
        return True
    
    async def revoke_token(self, token_id: str, revoked_by: str) -> bool:
        """Revoke break-glass token."""
        async with self._lock:
            token = self._tokens.get(token_id)
            if not token:
                return False
            
            token.revoked = True
        
        event = BreakGlassEvent(
            token_id=token_id,
            requester=revoked_by,
            reason="",
            action=BreakGlassAction.REVOKED,
            duration_seconds=0,
            timestamp=datetime.now(),
        )
        self._events.append(event)
        
        await self._send_alert(event)
        return True
    
    async def _send_alert(self, event: BreakGlassEvent) -> None:
        """Send alert via webhooks and handlers."""
        # Build alert payload
        payload = {
            "type": "break_glass",
            "event": {
                "token_id": event.token_id,
                "action": event.action.value,
                "requester": event.requester,
                "reason": event.reason,
                "duration_seconds": event.duration_seconds,
                "timestamp": event.timestamp.isoformat(),
                "source_ip": event.source_ip,
            },
        }
        
        # Call webhook handlers
        for handler in self._webhook_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(payload)
                else:
                    handler(payload)
            except Exception as e:
                logger.error(f"Webhook handler failed: {e}")
        
        # Call alert handlers
        for handler in self._alert_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Alert handler failed: {e}")
    
    async def get_token(self, token_id: str) -> Optional[BreakGlassToken]:
        """Get token info."""
        return self._tokens.get(token_id)
    
    async def get_events(
        self,
        limit: int = 100,
    ) -> List[BreakGlassEvent]:
        """Get recent events."""
        return sorted(
            self._events,
            key=lambda e: e.timestamp,
            reverse=True
        )[:limit]
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get break-glass metrics."""
        active = sum(
            1 for t in self._tokens.values()
            if not t.revoked and datetime.now() < t.expires_at
        )
        
        return {
            "total_tokens": len(self._tokens),
            "active_tokens": active,
            "total_events": len(self._events),
            "webhook_url_set": self.webhook_url is not None,
        }


# ============== DR METRICS ==============

@dataclass
class DRRestoreRecord:
    """Disaster recovery restore record."""
    snapshot_id: str
    start_time: datetime
    end_time: Optional[datetime]
    data_loss_seconds: int
    target_rto_seconds: int
    target_rpo_seconds: int
    status: str  # in_progress, completed, failed
    alert_sent: bool = False


class DRMetrics:
    """
    Disaster recovery metrics tracking.
    
    Tracks:
    - RTO (Recovery Time Objective): Time to restore service
    - RPO (Recovery Point Objective): Data loss duration
    
    Compares actual values against targets.
    Sends alerts when SLOs are violated.
    """
    
    def __init__(
        self,
        rto_target_seconds: int = 300,
        rpo_target_seconds: int = 60,
        alert_on_violation: bool = True,
    ):
        self.rto_target_seconds = rto_target_seconds
        self.rpo_target_seconds = rpo_target_seconds
        self.alert_on_violation = alert_on_violation
        
        # Restore records
        self._records: Dict[str, DRRestoreRecord] = {}
        
        # Alert handlers
        self._alert_handlers: List[Callable] = []
        
        self._lock = asyncio.Lock()
    
    def register_alert_handler(self, handler: Callable) -> None:
        """Register alert handler."""
        self._alert_handlers.append(handler)
    
    async def start_restore(
        self,
        snapshot_id: str,
        data_loss_seconds: int = 0,
    ) -> str:
        """Start a restore operation."""
        async with self._lock:
            record = DRRestoreRecord(
                snapshot_id=snapshot_id,
                start_time=datetime.now(),
                end_time=None,
                data_loss_seconds=data_loss_seconds,
                target_rto_seconds=self.rto_target_seconds,
                target_rpo_seconds=self.rpo_target_seconds,
                status="in_progress",
            )
            self._records[snapshot_id] = record
        
        logger.info(f"DR restore started: {snapshot_id}")
        return snapshot_id
    
    async def complete_restore(
        self,
        snapshot_id: str,
        data_loss_seconds: Optional[int] = None,
    ) -> Optional[DRRestoreRecord]:
        """Complete a restore operation."""
        async with self._lock:
            record = self._records.get(snapshot_id)
            if not record:
                return None
            
            record.end_time = datetime.now()
            if data_loss_seconds is not None:
                record.data_loss_seconds = data_loss_seconds
            record.status = "completed"
        
        # Calculate actual RTO
        rto_seconds = (record.end_time - record.start_time).total_seconds()
        rpo_violated = record.data_loss_seconds > self.rpo_target_seconds
        rto_violated = rto_seconds > self.rto_target_seconds
        
        # Alert on violation
        if self.alert_on_violation and (rto_violated or rpo_violated):
            record.alert_sent = True
            await self._send_violation_alert(record, rto_seconds)
        
        logger.info(
            f"DR restore completed: {snapshot_id}, "
            f"RTO: {rto_seconds:.1f}s (target: {self.rto_target_seconds}s), "
            f"RPO: {record.data_loss_seconds}s (target: {self.rpo_target_seconds}s)"
        )
        
        return record
    
    async def fail_restore(self, snapshot_id: str) -> bool:
        """Mark restore as failed."""
        async with self._lock:
            record = self._records.get(snapshot_id)
            if not record:
                return False
            
            record.end_time = datetime.now()
            record.status = "failed"
            record.alert_sent = True
        
        await self._send_failure_alert(record)
        return True
    
    async def _send_violation_alert(
        self,
        record: DRRestoreRecord,
        actual_rto: float,
    ) -> None:
        """Send violation alert."""
        rpo_violated = record.data_loss_seconds > self.rpo_target_seconds
        rto_violated = actual_rto > self.rto_target_seconds
        
        payload = {
            "type": "dr_violation",
            "snapshot_id": record.snapshot_id,
            "rto_actual_seconds": actual_rto,
            "rto_target_seconds": self.rto_target_seconds,
            "rpo_actual_seconds": record.data_loss_seconds,
            "rpo_target_seconds": self.rpo_target_seconds,
            "violations": {
                "rto": rto_violated,
                "rpo": rpo_violated,
            },
            "timestamp": datetime.now().isoformat(),
        }
        
        for handler in self._alert_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(payload)
                else:
                    handler(payload)
            except Exception as e:
                logger.error(f"DR alert handler failed: {e}")
    
    async def _send_failure_alert(self, record: DRRestoreRecord) -> None:
        """Send restore failure alert."""
        payload = {
            "type": "dr_failure",
            "snapshot_id": record.snapshot_id,
            "status": "failed",
            "timestamp": datetime.now().isoformat(),
        }
        
        for handler in self._alert_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(payload)
                else:
                    handler(payload)
            except Exception as e:
                logger.error(f"DR alert handler failed: {e}")
    
    async def get_record(self, snapshot_id: str) -> Optional[DRRestoreRecord]:
        """Get restore record."""
        return self._records.get(snapshot_id)
    
    async def get_recent_records(self, limit: int = 10) -> List[DRRestoreRecord]:
        """Get recent restore records."""
        records = sorted(
            self._records.values(),
            key=lambda r: r.start_time,
            reverse=True
        )
        return records[:limit]
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get DR metrics."""
        completed = [
            r for r in self._records.values()
            if r.status == "completed"
        ]
        
        in_progress = sum(
            1 for r in self._records.values()
            if r.status == "in_progress"
        )
        
        failed = sum(
            1 for r in self._records.values()
            if r.status == "failed"
        )
        
        # Calculate average RTO
        avg_rto = 0.0
        if completed:
            rtos = []
            for r in completed:
                if r.end_time:
                    rtos.append((r.end_time - r.start_time).total_seconds())
            if rtos:
                avg_rto = sum(rtos) / len(rtos)
        
        # Count violations
        rto_violations = sum(
            1 for r in completed
            if r.end_time and (r.end_time - r.start_time).total_seconds() > self.rto_target_seconds
        )
        rpo_violations = sum(
            1 for r in completed
            if r.data_loss_seconds > self.rpo_target_seconds
        )
        
        return {
            "total_restores": len(self._records),
            "completed": len(completed),
            "in_progress": in_progress,
            "failed": failed,
            "rto_target_seconds": self.rto_target_seconds,
            "rpo_target_seconds": self.rpo_target_seconds,
            "avg_rto_seconds": avg_rto,
            "rto_violations": rto_violations,
            "rpo_violations": rpo_violations,
        }


# ============== COST CHARGEBACK ==============

@dataclass
class CostRecord:
    """Cost record for chargeback."""
    tenant_id: str
    team_id: Optional[str]
    project_id: Optional[str]
    cost_usd: float
    resource_type: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


class ChargebackReporter:
    """
    Cost chargeback reporting.
    
    Tracks costs by:
    - Tenant
    - Team
    - Project
    - Resource type
    
    Generates reports for finance.
    """
    
    def __init__(
        self,
        enabled: bool = True,
        export_formats: Optional[List[str]] = None,
    ):
        self.enabled = enabled
        self.export_formats = export_formats or ["csv", "json"]
        
        # Cost records
        self._records: List[CostRecord] = []
        
        # Cost per dimension
        self._costs_by_tenant: Dict[str, float] = {}
        self._costs_by_team: Dict[str, float] = {}
        self._costs_by_project: Dict[str, float] = {}
        self._costs_by_resource: Dict[str, float] = {}
        
        self._lock = asyncio.Lock()
    
    async def record_cost(
        self,
        tenant_id: str,
        cost_usd: float,
        resource_type: str,
        team_id: Optional[str] = None,
        project_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a cost."""
        record = CostRecord(
            tenant_id=tenant_id,
            team_id=team_id,
            project_id=project_id,
            cost_usd=cost_usd,
            resource_type=resource_type,
            timestamp=datetime.now(),
            metadata=metadata or {},
        )
        
        async with self._lock:
            self._records.append(record)
            
            # Update aggregations
            self._costs_by_tenant[tenant_id] = (
                self._costs_by_tenant.get(tenant_id, 0) + cost_usd
            )
            
            if team_id:
                self._costs_by_team[team_id] = (
                    self._costs_by_team.get(team_id, 0) + cost_usd
                )
            
            if project_id:
                self._costs_by_project[project_id] = (
                    self._costs_by_project.get(project_id, 0) + cost_usd
                )
            
            self._costs_by_resource[resource_type] = (
                self._costs_by_resource.get(resource_type, 0) + cost_usd
            )
    
    async def get_chargeback_report(
        self,
        tenant_id: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        group_by: str = "tenant",
    ) -> Dict[str, Any]:
        """Generate chargeback report."""
        async with self._lock:
            records = self._records
            
            # Filter by tenant
            if tenant_id:
                records = [r for r in records if r.tenant_id == tenant_id]
            
            # Filter by time
            if start:
                records = [r for r in records if r.timestamp >= start]
            if end:
                records = [r for r in records if r.timestamp <= end]
            
            # Group
            if group_by == "tenant":
                groups = {}
                for r in records:
                    groups[r.tenant_id] = groups.get(r.tenant_id, 0) + r.cost_usd
            elif group_by == "team":
                groups = {}
                for r in records:
                    if r.team_id:
                        groups[r.team_id] = groups.get(r.team_id, 0) + r.cost_usd
            elif group_by == "project":
                groups = {}
                for r in records:
                    if r.project_id:
                        groups[r.project_id] = groups.get(r.project_id, 0) + r.cost_usd
            elif group_by == "resource":
                groups = {}
                for r in records:
                    groups[r.resource_type] = groups.get(r.resource_type, 0) + r.cost_usd
            else:
                groups = {"total": sum(r.cost_usd for r in records)}
            
            total_cost = sum(r.cost_usd for r in records)
            
            return {
                "report_type": f"chargeback_by_{group_by}",
                "period_start": start.isoformat() if start else None,
                "period_end": end.isoformat() if end else None,
                "total_cost_usd": total_cost,
                "grouped_costs": groups,
                "record_count": len(records),
            }
    
    async def export_csv(
        self,
        tenant_id: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> str:
        """Export report as CSV."""
        async with self._lock:
            records = self._records
            
            if tenant_id:
                records = [r for r in records if r.tenant_id == tenant_id]
            if start:
                records = [r for r in records if r.timestamp >= start]
            if end:
                records = [r for r in records if r.timestamp <= end]
        
        lines = ["tenant_id,team_id,project_id,cost_usd,resource_type,timestamp"]
        for r in records:
            lines.append(
                f"{r.tenant_id},{r.team_id or ''},{r.project_id or ''},"
                f"{r.cost_usd:.4f},{r.resource_type},{r.timestamp.isoformat()}"
            )
        
        return "\n".join(lines)
    
    async def export_json(
        self,
        tenant_id: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> str:
        """Export report as JSON."""
        report = await self.get_chargeback_report(
            tenant_id=tenant_id,
            start=start,
            end=end,
            group_by="tenant",
        )
        
        import json
        return json.dumps(report, indent=2)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get chargeback metrics."""
        total_cost = sum(r.cost_usd for r in self._records)
        
        return {
            "enabled": self.enabled,
            "total_cost_usd": total_cost,
            "record_count": len(self._records),
            "tracked_tenants": len(self._costs_by_tenant),
            "tracked_teams": len(self._costs_by_team),
            "tracked_projects": len(self._costs_by_project),
            "resource_types": list(self._costs_by_resource.keys()),
        }
