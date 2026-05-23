"""Tests for alert integration."""

import pytest
from src.infrastructure.integration.alert_integration import (
    AlertIntegration,
    NotificationChannel,
    TicketPriority,
)


class TestAlertIntegration:
    def test_integration_creation(self):
        integration = AlertIntegration()
        assert integration is not None

    def test_add_rule(self):
        integration = AlertIntegration()
        
        integration.add_rule(
            name="Critical Alert",
            condition="severity == 'critical'",
            action="create_ticket",
            channel=NotificationChannel.SLACK,
        )

    def test_process_alert(self):
        integration = AlertIntegration()
        
        result = integration.process_alert(
            alert_type="hardware_failure",
            severity="high",
            title="Board Failed",
            message="Multiple errors detected",
        )
        
        assert "ticket" in result
        assert "notifications" in result

    def test_process_low_severity_alert(self):
        integration = AlertIntegration()
        
        result = integration.process_alert(
            alert_type="info",
            severity="low",
            title="Info Message",
            message="System running normally",
        )
        
        # Low severity should not create ticket
        assert result["ticket"] is None

    def test_create_ticket_from_alert(self):
        integration = AlertIntegration()
        
        ticket = integration.create_ticket_from_alert(
            alert_type="bug",
            severity="high",
            title="Bug Report",
            description="Bug description",
        )
        
        assert ticket is not None
        assert ticket.priority == TicketPriority.HIGH
