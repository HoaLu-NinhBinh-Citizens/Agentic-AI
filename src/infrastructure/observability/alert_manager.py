"""Monitoring and alerting (Phase 13.1).

Provides monitoring and alerting infrastructure:
- System metrics collection
- Alert rules and thresholds
- Alert routing to PagerDuty, Slack, etc.
- Alert escalation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """Alert status."""
    FIRING = "firing"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


@dataclass
class Alert:
    """Alert instance."""
    alert_id: str
    name: str
    severity: AlertSeverity
    message: str
    
    # Context
    source: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)
    
    # Timing
    created_at: datetime = field(default_factory=datetime.now)
    fired_at: datetime | None = None
    resolved_at: datetime | None = None
    
    # Status
    status: AlertStatus = AlertStatus.FIRING
    ack_by: str = ""
    resolved_by: str = ""
    
    # Escalation
    escalated: bool = False
    retry_count: int = 0


@dataclass
class AlertRule:
    """Alert rule definition."""
    name: str
    condition: Callable[[dict], bool]
    severity: AlertSeverity
    message_template: str
    labels: dict[str, str] = field(default_factory=dict)
    
    # Thresholds
    duration_seconds: int = 0  # 0 = instant
    evaluation_interval: int = 60
    
    # Routing
    routing_group: str = "default"
    cooldown_seconds: int = 300  # Don't fire again within this time


@dataclass
class MetricPoint:
    """Metric data point."""
    name: str
    value: float
    timestamp: datetime
    labels: dict[str, str] = field(default_factory=dict)


class AlertManager:
    """Main alert management system.
    
    Phase 13.1: Monitoring & alerting
    """
    
    def __init__(self) -> None:
        self._alerts: dict[str, Alert] = {}
        self._rules: list[AlertRule] = []
        self._metrics: dict[str, list[MetricPoint]] = {}
        self._handlers: dict[str, list[Callable]] = {
            "firing": [],
            "acknowledged": [],
            "resolved": [],
        }
        self._cooldowns: dict[str, datetime] = {}  # alert_name -> last_fired
    
    def register_rule(self, rule: AlertRule) -> None:
        """Register an alert rule."""
        self._rules.append(rule)
        logger.info("Registered alert rule", name=rule.name)
    
    def register_handler(self, event: str, handler: Callable) -> None:
        """Register alert handler."""
        if event in self._handlers:
            self._handlers[event].append(handler)
    
    def record_metric(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a metric value."""
        point = MetricPoint(
            name=name,
            value=value,
            timestamp=datetime.now(),
            labels=labels or {},
        )
        
        if name not in self._metrics:
            self._metrics[name] = []
        
        self._metrics[name].append(point)
        
        # Keep only last 1000 points per metric
        if len(self._metrics[name]) > 1000:
            self._metrics[name] = self._metrics[name][-1000:]
        
        # Evaluate rules
        self._evaluate_rules(name, point)
    
    def _evaluate_rules(self, metric_name: str, point: MetricPoint) -> None:
        """Evaluate alert rules for metric."""
        for rule in self._rules:
            if metric_name not in rule.message_template:
                continue
            
            try:
                # Build context
                context = {
                    "metric": point.name,
                    "value": point.value,
                    "labels": point.labels,
                    "timestamp": point.timestamp,
                }
                
                # Check cooldown
                last_fired = self._cooldowns.get(rule.name)
                if last_fired and (datetime.now() - last_fired).total_seconds() < rule.cooldown_seconds:
                    continue
                
                # Evaluate condition
                if rule.condition(context):
                    self._fire_alert(rule, point)
                    self._cooldowns[rule.name] = datetime.now()
                    
            except Exception as e:
                logger.error("Rule evaluation error", rule=rule.name, error=str(e))
    
    def _fire_alert(self, rule: AlertRule, point: MetricPoint) -> Alert:
        """Fire an alert."""
        import hashlib
        
        alert_id = hashlib.md5(f"{rule.name}:{point.timestamp}".encode()).hexdigest()[:12]
        
        alert = Alert(
            alert_id=alert_id,
            name=rule.name,
            severity=rule.severity,
            message=rule.message_template.format(**{
                "metric": point.name,
                "value": point.value,
                **point.labels,
            }),
            source=point.name,
            labels=rule.labels,
            fired_at=datetime.now(),
        )
        
        self._alerts[alert_id] = alert
        
        # Call handlers
        for handler in self._handlers["firing"]:
            try:
                handler(alert)
            except Exception as e:
                logger.error("Alert handler error", error=str(e))
        
        logger.log(
            logging.WARNING if alert.severity in [AlertSeverity.WARNING, AlertSeverity.ERROR] else logging.INFO,
            "Alert fired",
            name=alert.name,
            severity=alert.severity.value,
        )
        
        return alert
    
    def acknowledge(self, alert_id: str, ack_by: str) -> bool:
        """Acknowledge an alert."""
        if alert_id not in self._alerts:
            return False
        
        alert = self._alerts[alert_id]
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.ack_by = ack_by
        
        for handler in self._handlers["acknowledged"]:
            try:
                handler(alert)
            except Exception as e:
                logger.error("Alert handler error", error=str(e))
        
        return True
    
    def resolve(self, alert_id: str, resolved_by: str) -> bool:
        """Resolve an alert."""
        if alert_id not in self._alerts:
            return False
        
        alert = self._alerts[alert_id]
        alert.status = AlertStatus.RESOLVED
        alert.resolved_by = resolved_by
        alert.resolved_at = datetime.now()
        
        for handler in self._handlers["resolved"]:
            try:
                handler(alert)
            except Exception as e:
                logger.error("Alert handler error", error=str(e))
        
        return True
    
    def get_active_alerts(
        self,
        severity: AlertSeverity | None = None,
    ) -> list[Alert]:
        """Get active (firing) alerts."""
        alerts = [a for a in self._alerts.values() if a.status != AlertStatus.RESOLVED]
        
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        
        return sorted(alerts, key=lambda a: a.created_at, reverse=True)
    
    def get_metrics(self, name: str, minutes: int = 60) -> list[MetricPoint]:
        """Get recent metrics."""
        if name not in self._metrics:
            return []
        
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [m for m in self._metrics[name] if m.timestamp > cutoff]
    
    def get_statistics(self) -> dict[str, Any]:
        """Get alert statistics."""
        return {
            "total_alerts": len(self._alerts),
            "firing": len([a for a in self._alerts.values() if a.status == AlertStatus.FIRING]),
            "acknowledged": len([a for a in self._alerts.values() if a.status == AlertStatus.ACKNOWLEDGED]),
            "resolved": len([a for a in self._alerts.values() if a.status == AlertStatus.RESOLVED]),
            "metrics_tracked": len(self._metrics),
            "active_rules": len(self._rules),
        }


# Global singleton
_alert_manager: AlertManager | None = None


def get_alert_manager() -> AlertManager:
    """Get global alert manager."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager


if __name__ == "__main__":
    manager = get_alert_manager()
    
    # Define alert rule
    def high_error_rate(context: dict) -> bool:
        return context["value"] > 10
    
    manager.register_rule(AlertRule(
        name="high_error_rate",
        condition=high_error_rate,
        severity=AlertSeverity.ERROR,
        message_template="Error rate is {value}% (threshold: 10%)",
    ))
    
    # Record metrics
    import random
    for i in range(10):
        error_rate = 5 + random.gauss(0, 3)
        manager.record_metric("error_rate", error_rate)
        
        if i == 5:
            manager.record_metric("error_rate", 15)  # Spike
    
    # Check alerts
    active = manager.get_active_alerts()
    print(f"Active alerts: {len(active)}")
    for alert in active:
        print(f"  [{alert.severity.value}] {alert.name}: {alert.message}")
    
    # Statistics
    stats = manager.get_statistics()
    print(f"\nStatistics: {stats}")
