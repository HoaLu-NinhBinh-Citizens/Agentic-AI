"""Tests for ROI metrics."""

import pytest
from src.application.evaluation.roi_metrics import ROITracker


class TestROITracker:
    def test_tracker_creation(self):
        tracker = ROITracker()
        assert tracker is not None

    def test_update_metrics(self):
        tracker = ROITracker()
        
        tracker.update_metrics(
            total_users=100,
            active_users=75,
            hours_saved_debugging=50,
            hours_saved_maintenance=30,
            incidents_prevented=5,
            bugs_caught=20,
            patches_approved=10,
            patches_suggested=12,
        )

    def test_calculate_roi(self):
        tracker = ROITracker()
        
        tracker.update_metrics(
            total_users=50,
            active_users=40,
        )
        
        roi = tracker.calculate_roi(period_days=30)
        assert roi.adoption.total_users == 50

    def test_generate_report(self):
        tracker = ROITracker()
        
        tracker.update_metrics(
            total_users=100,
            active_users=80,
        )
        
        report = tracker.generate_report()
        assert "adoption" in report
        assert "roi" in report

    def test_get_dashboard_data(self):
        tracker = ROITracker()
        
        tracker.update_metrics(
            total_users=50,
            active_users=40,
            hours_saved_debugging=100,
        )
        
        data = tracker.get_dashboard_data()
        assert "kpis" in data
