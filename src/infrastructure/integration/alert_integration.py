"""Integration with Jira, Slack, Teams (Phase 14.5).

Provides integration with external tools:
- Jira ticket creation
- Slack notifications
- Teams webhooks
- Alert routing
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TicketPriority(Enum):
    """Ticket priority."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NotificationChannel(Enum):
    """Notification channels."""
    SLACK = "slack"
    TEAMS = "teams"
    EMAIL = "email"
    WEBHOOK = "webhook"


@dataclass
class Ticket:
    """Jira ticket."""
    ticket_id: str
    title: str
    description: str
    priority: TicketPriority
    labels: list[str] = field(default_factory=list)
    assignee: str = ""
    status: str = "Open"
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Notification:
    """Notification message."""
    channel: NotificationChannel
    title: str
    message: str
    severity: str = "info"  # info, warning, error, critical
    metadata: dict[str, Any] = field(default_factory=dict)


class JiraClient:
    """Jira integration."""
    
    def __init__(self, config: dict[str, str] | None = None) -> None:
        self._config = config or {}
        self._base_url = self._config.get("jira_url", "https://jira.example.com")
        self._project = self._config.get("project", "AISUPPORT")
    
    def create_ticket(
        self,
        title: str,
        description: str,
        priority: TicketPriority,
        labels: list[str] | None = None,
    ) -> Ticket:
        """Create Jira ticket."""
        import hashlib
        ticket_id = f"{self._project}-{hashlib.md5(title.encode()).hexdigest()[:6].upper()}"
        
        ticket = Ticket(
            ticket_id=ticket_id,
            title=title,
            description=description,
            priority=priority,
            labels=labels or [],
        )
        
        logger.info("Jira ticket created", ticket_id=ticket_id)
        return ticket
    
    def update_ticket(
        self,
        ticket_id: str,
        status: str | None = None,
        assignee: str | None = None,
    ) -> bool:
        """Update Jira ticket."""
        logger.info("Jira ticket updated", ticket_id=ticket_id)
        return True
    
    def add_comment(self, ticket_id: str, comment: str) -> bool:
        """Add comment to ticket."""
        logger.info("Comment added", ticket_id=ticket_id)
        return True


class SlackClient:
    """Slack integration."""
    
    def __init__(self, webhook_url: str | None = None) -> None:
        self._webhook_url = webhook_url or ""
        self._channel = ""
    
    def send_message(
        self,
        text: str,
        channel: str = "",
        severity: str = "info",
    ) -> bool:
        """Send Slack message."""
        # In real implementation, would use Slack SDK or webhook
        logger.info("Slack message sent", channel=channel, severity=severity)
        return True
    
    def send_alert(
        self,
        title: str,
        message: str,
        severity: str = "warning",
    ) -> bool:
        """Send alert to Slack."""
        formatted = f"*{severity.upper()}:* {title}\n{message}"
        return self.send_message(formatted, severity=severity)


class TeamsClient:
    """Microsoft Teams integration."""
    
    def __init__(self, webhook_url: str | None = None) -> None:
        self._webhook_url = webhook_url or ""
    
    def send_message(
        self,
        title: str,
        message: str,
        severity: str = "info",
    ) -> bool:
        """Send Teams message."""
        # In real implementation, would use webhook
        logger.info("Teams message sent", title=title)
        return True
    
    def send_card(
        self,
        title: str,
        facts: list[dict[str, str]],
        severity: str = "info",
    ) -> bool:
        """Send adaptive card to Teams."""
        logger.info("Teams card sent", title=title)
        return True


class IntegrationRouter:
    """Routes alerts to appropriate channels."""
    
    def __init__(self) -> None:
        self._jira = JiraClient()
        self._slack = SlackClient()
        self._teams = TeamsClient()
    
    def create_ticket(
        self,
        title: str,
        description: str,
        priority: TicketPriority,
        labels: list[str] | None = None,
    ) -> Ticket:
        """Create ticket based on priority."""
        if priority in [TicketPriority.CRITICAL, TicketPriority.HIGH]:
            return self._jira.create_ticket(title, description, priority, labels)
        return None
    
    def notify(
        self,
        channel: NotificationChannel,
        title: str,
        message: str,
        severity: str = "info",
    ) -> bool:
        """Send notification to channel."""
        if channel == NotificationChannel.SLACK:
            return self._slack.send_alert(title, message, severity)
        elif channel == NotificationChannel.TEAMS:
            return self._teams.send_message(title, message, severity)
        return False
    
    def broadcast(
        self,
        title: str,
        message: str,
        severity: str = "info",
    ) -> None:
        """Broadcast to all channels."""
        self._slack.send_alert(title, message, severity)
        self._teams.send_message(title, message, severity)


class AlertIntegration:
    """Alert integration manager.
    
    Phase 14.5: Jira, Slack, Teams integration - Auto ticket
    """
    
    def __init__(self) -> None:
        self._router = IntegrationRouter()
        self._rules: list[dict] = []
    
    def add_rule(
        self,
        name: str,
        condition: str,
        action: str,
        channel: NotificationChannel,
    ) -> None:
        """Add routing rule."""
        self._rules.append({
            "name": name,
            "condition": condition,
            "action": action,
            "channel": channel,
        })
    
    def process_alert(
        self,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Process alert and route."""
        results = {
            "ticket": None,
            "notifications": [],
        }
        
        # Create ticket for high severity
        priority_map = {
            "critical": TicketPriority.CRITICAL,
            "high": TicketPriority.HIGH,
            "medium": TicketPriority.MEDIUM,
            "low": TicketPriority.LOW,
        }
        priority = priority_map.get(severity, TicketPriority.MEDIUM)
        
        if severity in ["critical", "high"]:
            ticket = self._router.create_ticket(
                title=f"[{severity.upper()}] {title}",
                description=message,
                priority=priority,
                labels=[alert_type, severity],
            )
            results["ticket"] = ticket.ticket_id
        
        # Send notifications
        channel = NotificationChannel.SLACK
        self._router.notify(channel, title, message, severity)
        results["notifications"].append(channel.value)
        
        logger.info("Alert processed", type=alert_type, severity=severity)
        return results
    
    def create_ticket_from_alert(
        self,
        alert_type: str,
        severity: str,
        title: str,
        description: str,
    ) -> Ticket | None:
        """Create ticket from alert."""
        priority_map = {
            "critical": TicketPriority.CRITICAL,
            "high": TicketPriority.HIGH,
            "medium": TicketPriority.MEDIUM,
            "low": TicketPriority.LOW,
        }
        priority = priority_map.get(severity, TicketPriority.MEDIUM)
        
        return self._router.create_ticket(
            title=title,
            description=description,
            priority=priority,
            labels=[alert_type],
        )


# Global integration
_alert_integration: AlertIntegration | None = None


def get_alert_integration() -> AlertIntegration:
    """Get global alert integration."""
    global _alert_integration
    if _alert_integration is None:
        _alert_integration = AlertIntegration()
    return _alert_integration


if __name__ == "__main__":
    integration = get_alert_integration()
    
    # Process alert
    result = integration.process_alert(
        alert_type="hardware_failure",
        severity="high",
        title="Board board_001 failed",
        message="Multiple errors detected on board_001",
    )
    
    print("Alert Integration")
    print("=" * 40)
    print(f"Ticket created: {result['ticket']}")
    print(f"Notifications sent: {result['notifications']}")
