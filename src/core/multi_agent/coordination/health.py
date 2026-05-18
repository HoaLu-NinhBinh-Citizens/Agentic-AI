"""
Federated Health Propagator for Multi-Agent Coordination.

Aggregates sub-agent health status and reports to coordinator.
Handles offline detection and automatic task reassignment recommendations.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from src.core.multi_agent.coordination.types import (
    HealthStatus,
    SubAgentStatus,
    FederatedHealthReport,
)

logger = logging.getLogger(__name__)


class HealthStore:
    """Interface for health status storage."""
    
    async def save_sub_agent_status(
        self,
        federated_agent_id: str,
        status: SubAgentStatus,
    ) -> None:
        raise NotImplementedError
    
    async def get_sub_agent_status(
        self,
        federated_agent_id: str,
        sub_agent_id: str,
    ) -> Optional[SubAgentStatus]:
        raise NotImplementedError
    
    async def get_all_sub_agents(
        self,
        federated_agent_id: str,
    ) -> List[SubAgentStatus]:
        raise NotImplementedError
    
    async def save_federated_report(
        self,
        report: FederatedHealthReport,
    ) -> None:
        raise NotImplementedError
    
    async def get_federated_reports(
        self,
        federated_agent_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[FederatedHealthReport]:
        raise NotImplementedError


class InMemoryHealthStore(HealthStore):
    """In-memory implementation of HealthStore."""
    
    def __init__(self):
        self._sub_agent_status: Dict[str, Dict[str, SubAgentStatus]] = defaultdict(dict)
        self._federated_reports: List[FederatedHealthReport] = []
        self._lock = asyncio.Lock()
    
    async def save_sub_agent_status(
        self,
        federated_agent_id: str,
        status: SubAgentStatus,
    ) -> None:
        async with self._lock:
            self._sub_agent_status[federated_agent_id][status.agent_id] = status
    
    async def get_sub_agent_status(
        self,
        federated_agent_id: str,
        sub_agent_id: str,
    ) -> Optional[SubAgentStatus]:
        return self._sub_agent_status.get(federated_agent_id, {}).get(sub_agent_id)
    
    async def get_all_sub_agents(
        self,
        federated_agent_id: str,
    ) -> List[SubAgentStatus]:
        return list(self._sub_agent_status.get(federated_agent_id, {}).values())
    
    async def save_federated_report(
        self,
        report: FederatedHealthReport,
    ) -> None:
        async with self._lock:
            self._federated_reports.append(report)
            if len(self._federated_reports) > 1000:
                self._federated_reports = self._federated_reports[-1000:]
    
    async def get_federated_reports(
        self,
        federated_agent_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[FederatedHealthReport]:
        if federated_agent_id:
            return [
                r for r in self._federated_reports[-limit:]
                if r.federated_agent_id == federated_agent_id
            ]
        return self._federated_reports[-limit:]


@dataclass
class OfflineNotification:
    """Notification for sub-agent going offline."""
    federated_agent_id: str
    sub_agent_id: str
    last_heartbeat: datetime
    offline_duration_seconds: float
    recommended_action: str  # "reassign_tasks", "alert_supervisor", "both"
    tasks_to_reassign: List[str] = field(default_factory=list)


class FederatedHealthPropagator:
    """
    Federated health propagator for multi-agent coordination.
    
    Responsibilities:
    - Receive sub-agent status updates from federated agents
    - Detect offline sub-agents
    - Calculate federated health score
    - Trigger notifications for offline agents
    - Report to coordinator
    """
    
    def __init__(
        self,
        health_interval_seconds: int = 10,
        offline_threshold_seconds: int = 30,
        max_sub_agents: int = 100,
        store: Optional[HealthStore] = None,
        notification_callback: Optional[Callable[[OfflineNotification], None]] = None,
    ):
        self.health_interval_seconds = health_interval_seconds
        self.offline_threshold_seconds = offline_threshold_seconds
        self.max_sub_agents = max_sub_agents
        self.store = store or InMemoryHealthStore()
        self.notification_callback = notification_callback
        
        self._lock = asyncio.Lock()
        self._federated_agents: Dict[str, Dict[str, SubAgentStatus]] = defaultdict(dict)
        self._last_report_time: Dict[str, datetime] = {}
        self._offline_history: List[OfflineNotification] = []
    
    async def report_sub_agents_status(
        self,
        federated_agent_id: str,
        sub_agents: List[Dict[str, Any]],
    ) -> FederatedHealthReport:
        """
        Report sub-agent status from a federated agent.
        
        Args:
            federated_agent_id: ID of the federated agent
            sub_agents: List of sub-agent status dictionaries
            
        Returns:
            FederatedHealthReport with aggregated status
        """
        if len(sub_agents) > self.max_sub_agents:
            logger.warning(
                f"Too many sub-agents from {federated_agent_id}: {len(sub_agents)} > {self.max_sub_agents}"
            )
            sub_agents = sub_agents[:self.max_sub_agents]
        
        statuses = []
        offline_notifications = []
        
        for sa in sub_agents:
            last_heartbeat = sa.get("last_heartbeat")
            if isinstance(last_heartbeat, str):
                last_heartbeat = datetime.fromisoformat(last_heartbeat)
            elif not isinstance(last_heartbeat, datetime):
                last_heartbeat = datetime.now()
            
            status = SubAgentStatus(
                agent_id=sa["id"],
                status=HealthStatus(sa.get("status", "healthy")),
                last_heartbeat=last_heartbeat,
                error_count=sa.get("error_count", 0),
                task_count=sa.get("task_count", 0),
                metadata=sa.get("metadata", {}),
            )
            
            # Store status
            await self.store.save_sub_agent_status(federated_agent_id, status)
            
            # Check for offline
            if self._is_offline(status):
                notification = await self._create_offline_notification(federated_agent_id, status)
                if notification:
                    offline_notifications.append(notification)
                    self._offline_history.append(notification)
                    self._offline_history = self._offline_history[-100:]
            
            statuses.append(status)
        
        # Calculate health score
        health_score = self._calculate_health_score(statuses)
        
        report = FederatedHealthReport(
            federated_agent_id=federated_agent_id,
            sub_agents=statuses,
            timestamp=datetime.now(),
            health_score=health_score,
        )
        
        # Save report
        await self.store.save_federated_report(report)
        self._last_report_time[federated_agent_id] = datetime.now()
        
        # Send notifications
        for notification in offline_notifications:
            if self.notification_callback:
                await self._send_notification(notification)
        
        logger.info(
            f"Federated health report from {federated_agent_id}: "
            f"score={health_score:.2f}, sub_agents={len(statuses)}, "
            f"offline={len(offline_notifications)}"
        )
        
        return report
    
    async def report_single_sub_agent(
        self,
        federated_agent_id: str,
        sub_agent_id: str,
        status: HealthStatus,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SubAgentStatus:
        """
        Report status for a single sub-agent.
        
        Args:
            federated_agent_id: ID of the federated agent
            sub_agent_id: ID of the sub-agent
            status: Current health status
            metadata: Optional metadata
            
        Returns:
            SubAgentStatus
        """
        sub_status = SubAgentStatus(
            agent_id=sub_agent_id,
            status=status,
            last_heartbeat=datetime.now(),
            metadata=metadata or {},
        )
        
        await self.store.save_sub_agent_status(federated_agent_id, sub_status)
        
        # Check for offline transition
        if self._is_offline(sub_status):
            notification = await self._create_offline_notification(federated_agent_id, sub_status)
            if notification and self.notification_callback:
                await self._send_notification(notification)
        
        return sub_status
    
    async def get_federated_health(
        self,
        federated_agent_id: str,
    ) -> Dict[str, Any]:
        """
        Get aggregated health status for a federated agent.
        
        Args:
            federated_agent_id: ID of the federated agent
            
        Returns:
            Dictionary with health status and recommendations
        """
        sub_agents = await self.store.get_all_sub_agents(federated_agent_id)
        
        if not sub_agents:
            return {
                "federated_agent_id": federated_agent_id,
                "health_score": 0.0,
                "sub_agents": [],
                "offline_agents": [],
                "action_needed": False,
                "last_report": None,
            }
        
        offline_agents = [
            sa for sa in sub_agents
            if self._is_offline(sa)
        ]
        
        action_needed = any(
            self._is_offline(sa) and
            self._get_offline_duration(sa) > self.offline_threshold_seconds * 2
            for sa in sub_agents
        )
        
        return {
            "federated_agent_id": federated_agent_id,
            "health_score": self._calculate_health_score(sub_agents),
            "sub_agents": [sa.to_dict() for sa in sub_agents],
            "offline_agents": [
                {
                    **sa.to_dict(),
                    "action_needed": True,
                    "recommended_action": self._get_recommended_action(sa),
                }
                for sa in offline_agents
            ],
            "action_needed": action_needed,
            "last_report": self._last_report_time.get(federated_agent_id),
            "total_sub_agents": len(sub_agents),
            "healthy_count": sum(1 for sa in sub_agents if sa.status == HealthStatus.HEALTHY),
            "degraded_count": sum(1 for sa in sub_agents if sa.status == HealthStatus.DEGRADED),
            "offline_count": len(offline_agents),
        }
    
    async def get_all_federated_health(self) -> List[Dict[str, Any]]:
        """Get health status for all federated agents."""
        all_federated = set(self._federated_agents.keys())
        all_federated.update(
            sa.federated_agent_id
            for report in await self.store.get_federated_reports(limit=1000)
            for sa in report.sub_agents
        )
        
        results = []
        for fed_id in all_federated:
            health = await self.get_federated_health(fed_id)
            results.append(health)
        
        return results
    
    def _is_offline(self, status: SubAgentStatus) -> bool:
        """Check if a sub-agent is offline based on heartbeat."""
        if status.status == HealthStatus.OFFLINE:
            return True
        
        elapsed = (datetime.now() - status.last_heartbeat).total_seconds()
        return elapsed > self.offline_threshold_seconds
    
    def _get_offline_duration(self, status: SubAgentStatus) -> float:
        """Get how long a sub-agent has been offline."""
        elapsed = (datetime.now() - status.last_heartbeat).total_seconds()
        return max(0, elapsed - self.offline_threshold_seconds)
    
    def _calculate_health_score(self, sub_agents: List[SubAgentStatus]) -> float:
        """Calculate overall health score (0.0 to 1.0)."""
        if not sub_agents:
            return 0.0
        
        scores = []
        for sa in sub_agents:
            if sa.status == HealthStatus.HEALTHY:
                # Penalize slightly for old heartbeats
                elapsed = (datetime.now() - sa.last_heartbeat).total_seconds()
                age_factor = max(0.5, 1.0 - (elapsed / 300))  # Max penalty at 5 min
                scores.append(1.0 * age_factor)
            elif sa.status == HealthStatus.DEGRADED:
                scores.append(0.5)
            elif sa.status == HealthStatus.UNHEALTHY:
                scores.append(0.2)
            else:  # OFFLINE
                scores.append(0.0)
        
        return sum(scores) / len(scores)
    
    def _get_recommended_action(self, status: SubAgentStatus) -> str:
        """Get recommended action for an offline agent."""
        duration = self._get_offline_duration(status)
        
        if duration < self.offline_threshold_seconds * 2:
            return "monitor"
        elif duration < self.offline_threshold_seconds * 5:
            return "reassign_tasks"
        else:
            return "alert_supervisor"
    
    async def _create_offline_notification(
        self,
        federated_agent_id: str,
        status: SubAgentStatus,
    ) -> Optional[OfflineNotification]:
        """Create notification for offline sub-agent."""
        if not self._is_offline(status):
            return None
        
        duration = self._get_offline_duration(status)
        
        # Only notify once per offline event (not continuously)
        last_notification = next(
            (n for n in reversed(self._offline_history)
             if n.sub_agent_id == status.agent_id),
            None
        )
        
        if last_notification:
            # Don't spam notifications
            if (datetime.now() - self._last_report_time.get(federated_agent_id, datetime.min)).total_seconds() < 60:
                return None
        
        return OfflineNotification(
            federated_agent_id=federated_agent_id,
            sub_agent_id=status.agent_id,
            last_heartbeat=status.last_heartbeat,
            offline_duration_seconds=duration,
            recommended_action=self._get_recommended_action(status),
        )
    
    async def _send_notification(self, notification: OfflineNotification) -> None:
        """Send offline notification via callback."""
        try:
            if asyncio.iscoroutinefunction(self.notification_callback):
                await self.notification_callback(notification)
            else:
                self.notification_callback(notification)
            
            logger.warning(
                f"Sub-agent offline: {notification.sub_agent_id} "
                f"(federated: {notification.federated_agent_id}, "
                f"duration: {notification.offline_duration_seconds:.0f}s, "
                f"action: {notification.recommended_action})"
            )
        except Exception as e:
            logger.error(f"Failed to send offline notification: {e}")
    
    async def get_offline_history(
        self,
        federated_agent_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get history of offline notifications."""
        history = self._offline_history
        if federated_agent_id:
            history = [n for n in history if n.federated_agent_id == federated_agent_id]
        return [
            {
                "federated_agent_id": n.federated_agent_id,
                "sub_agent_id": n.sub_agent_id,
                "last_heartbeat": n.last_heartbeat.isoformat(),
                "offline_duration_seconds": n.offline_duration_seconds,
                "recommended_action": n.recommended_action,
            }
            for n in history[-limit:]
        ]
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get health propagator metrics."""
        total_federated = len(self._federated_agents)
        total_sub_agents = sum(len(agents) for agents in self._federated_agents.values())
        recent_offlines = len([
            n for n in self._offline_history
            if (datetime.now() - n.last_heartbeat).total_seconds() < 300
        ])
        
        return {
            "total_federated_agents": total_federated,
            "total_sub_agents": total_sub_agents,
            "recent_offline_events": recent_offlines,
            "offline_threshold_seconds": self.offline_threshold_seconds,
            "health_interval_seconds": self.health_interval_seconds,
        }
