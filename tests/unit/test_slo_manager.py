"""Tests for SLO manager."""

import pytest
from src.infrastructure.observability.slo_manager import (
    SLOManager,
    SLOTarget,
    SLOStatus,
)


class TestSLOManager:
    def test_manager_creation(self):
        manager = SLOManager()
        assert manager is not None

    def test_register_slo(self):
        manager = SLOManager()
        slo = SLOTarget(
            slo_id="availability",
            name="Debug Service Availability",
            metric_type="availability",
            target_value=0.999,
        )
        manager.register_slo(slo)

    def test_record_events(self):
        manager = SLOManager()
        slo = SLOTarget(
            slo_id="test",
            name="Test SLO",
            metric_type="availability",
            target_value=0.99,
        )
        manager.register_slo(slo)
        
        manager.record_events("test", good_events=990, total_events=1000)

    def test_calculate_budget(self):
        manager = SLOManager()
        slo = SLOTarget(
            slo_id="test",
            name="Test",
            metric_type="availability",
            target_value=0.99,
        )
        manager.register_slo(slo)
        manager.record_events("test", good_events=990, total_events=1000)
        
        budget = manager.calculate_budget("test")
        assert budget is not None

    def test_get_slo_status(self):
        manager = SLOManager()
        slo = SLOTarget(
            slo_id="test",
            name="Test",
            metric_type="availability",
            target_value=0.999,
        )
        manager.register_slo(slo)
        manager.record_events("test", good_events=999, total_events=1000)
        
        status = manager.get_slo_status("test")
        assert status in [SLOStatus.HEALTHY, SLOStatus.AT_RISK, SLOStatus.BREACHING]

    def test_get_summary(self):
        manager = SLOManager()
        summary = manager.get_summary()
        assert "total_slos" in summary
