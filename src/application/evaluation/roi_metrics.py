"""ROI metrics and business analytics (Phase 16.5).

Provides ROI tracking and business metrics:
- Adoption rate tracking
- Time saved metrics
- Cost savings calculation
- Value delivered measurement
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MetricPeriod(Enum):
    """Metric periods."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass
class AdoptionMetrics:
    """Adoption metrics."""
    total_users: int = 0
    active_users: int = 0
    new_users_period: int = 0
    churned_users_period: int = 0
    
    @property
    def active_rate(self) -> float:
        if self.total_users == 0:
            return 0.0
        return self.active_users / self.total_users


@dataclass
class TimeSaved:
    """Time saved metrics."""
    hours_debugging_saved: float = 0.0
    hours_maintenance_saved: float = 0.0
    hours_onboarding_saved: float = 0.0
    
    @property
    def total_hours(self) -> float:
        return self.hours_debugging_saved + self.hours_maintenance_saved + self.hours_onboarding_saved
    
    @property
    def value(self) -> float:
        # Value at $100/hour
        return self.total_hours * 100.0


@dataclass
class CostSavings:
    """Cost savings metrics."""
    hardware_failures_prevented: int = 0
    production_incidents_prevented: int = 0
    downtime_hours_saved: float = 0.0
    
    @property
    def estimated_savings(self) -> float:
        # $10k per incident, $50k per hour downtime
        return (
            self.hardware_failures_prevented * 5000 +
            self.production_incidents_prevented * 10000 +
            self.downtime_hours_saved * 50000
        )


@dataclass
class QualityMetrics:
    """Quality improvement metrics."""
    bugs_caught_early: int = 0
    tests_generated: int = 0
    patches_suggested: int = 0
    patches_approved: int = 0
    
    @property
    def approval_rate(self) -> float:
        if self.patches_suggested == 0:
            return 0.0
        return self.patches_approved / self.patches_suggested


@dataclass
class ROIMetrics:
    """Complete ROI metrics."""
    period_start: datetime
    period_end: datetime
    
    # Adoption
    adoption: AdoptionMetrics = field(default_factory=AdoptionMetrics)
    
    # Time saved
    time_saved: TimeSaved = field(default_factory=TimeSaved)
    
    # Cost savings
    cost_savings: CostSavings = field(default_factory=CostSavings)
    
    # Quality
    quality: QualityMetrics = field(default_factory=QualityMetrics)
    
    # Investment
    subscription_cost: float = 0.0
    implementation_cost: float = 0.0
    
    @property
    def total_value(self) -> float:
        return self.time_saved.value + self.cost_savings.estimated_savings
    
    @property
    def net_value(self) -> float:
        return self.total_value - self.subscription_cost - self.implementation_cost
    
    @property
    def roi_percentage(self) -> float:
        investment = self.subscription_cost + self.implementation_cost
        if investment == 0:
            return 0.0
        return (self.total_value - investment) / investment * 100


class MetricsCollector:
    """Collects metrics from various sources."""
    
    def __init__(self) -> None:
        self._metrics: list[ROIMetrics] = []
    
    def record_adoption(self, metrics: AdoptionMetrics) -> None:
        """Record adoption metrics."""
        pass
    
    def record_time_saved(self, hours: float, category: str) -> None:
        """Record time saved."""
        pass


class ROITracker:
    """ROI tracking and reporting.
    
    Phase 16.5: ROI metrics
    """
    
    def __init__(self) -> None:
        self._collector = MetricsCollector()
        self._current_metrics: dict[str, Any] = {}
    
    def update_metrics(
        self,
        total_users: int,
        active_users: int,
        hours_saved_debugging: float = 0,
        hours_saved_maintenance: float = 0,
        incidents_prevented: int = 0,
        bugs_caught: int = 0,
        patches_approved: int = 0,
        patches_suggested: int = 0,
    ) -> None:
        """Update current metrics."""
        self._current_metrics = {
            "total_users": total_users,
            "active_users": active_users,
            "hours_saved_debugging": hours_saved_debugging,
            "hours_saved_maintenance": hours_saved_maintenance,
            "incidents_prevented": incidents_prevented,
            "bugs_caught": bugs_caught,
            "patches_approved": patches_approved,
            "patches_suggested": patches_suggested,
            "updated_at": datetime.now(),
        }
        
        logger.info("Metrics updated", users=total_users, active=active_users)
    
    def calculate_roi(self, period_days: int = 30) -> ROIMetrics:
        """Calculate ROI metrics."""
        now = datetime.now()
        period_start = now - timedelta(days=period_days)
        
        # Build metrics from current data
        adoption = AdoptionMetrics(
            total_users=self._current_metrics.get("total_users", 0),
            active_users=self._current_metrics.get("active_users", 0),
        )
        
        time_saved = TimeSaved(
            hours_debugging_saved=self._current_metrics.get("hours_saved_debugging", 0),
            hours_maintenance_saved=self._current_metrics.get("hours_saved_maintenance", 0),
        )
        
        cost_savings = CostSavings(
            production_incidents_prevented=self._current_metrics.get("incidents_prevented", 0),
        )
        
        quality = QualityMetrics(
            bugs_caught_early=self._current_metrics.get("bugs_caught", 0),
            patches_approved=self._current_metrics.get("patches_approved", 0),
            patches_suggested=self._current_metrics.get("patches_suggested", 0),
        )
        
        # Assume monthly subscription cost
        subscription_cost = adoption.total_users * 99  # $99/user/month
        
        return ROIMetrics(
            period_start=period_start,
            period_end=now,
            adoption=adoption,
            time_saved=time_saved,
            cost_savings=cost_savings,
            quality=quality,
            subscription_cost=subscription_cost,
        )
    
    def generate_report(self, period_days: int = 30) -> dict[str, Any]:
        """Generate ROI report."""
        roi = self.calculate_roi(period_days)
        
        return {
            "period": f"Last {period_days} days",
            "period_start": roi.period_start.isoformat(),
            "period_end": roi.period_end.isoformat(),
            
            "adoption": {
                "total_users": roi.adoption.total_users,
                "active_users": roi.adoption.active_users,
                "active_rate": f"{roi.adoption.active_rate:.1%}",
            },
            
            "time_saved": {
                "debugging_hours": f"{roi.time_saved.hours_debugging_saved:.1f}",
                "maintenance_hours": f"{roi.time_saved.hours_maintenance_saved:.1f}",
                "total_hours": f"{roi.time_saved.total_hours:.1f}",
                "value": f"${roi.time_saved.value:,.0f}",
            },
            
            "cost_savings": {
                "incidents_prevented": roi.cost_savings.production_incidents_prevented,
                "estimated_savings": f"${roi.cost_savings.estimated_savings:,.0f}",
            },
            
            "quality": {
                "bugs_caught_early": roi.quality.bugs_caught_early,
                "patches_approved": roi.quality.patches_approved,
                "approval_rate": f"{roi.quality.approval_rate:.1%}",
            },
            
            "roi": {
                "total_value": f"${roi.total_value:,.0f}",
                "investment": f"${roi.subscription_cost:,.0f}",
                "net_value": f"${roi.net_value:,.0f}",
                "roi_percentage": f"{roi.roi_percentage:.0f}%",
            },
        }
    
    def get_dashboard_data(self) -> dict[str, Any]:
        """Get dashboard data for visualization."""
        report = self.generate_report()
        
        return {
            "kpis": {
                "total_users": self._current_metrics.get("total_users", 0),
                "active_rate": self._current_metrics.get("active_users", 0) / max(1, self._current_metrics.get("total_users", 1)),
                "hours_saved": self._current_metrics.get("hours_saved_debugging", 0) + self._current_metrics.get("hours_saved_maintenance", 0),
                "roi_percentage": self.calculate_roi().roi_percentage,
            },
            "trends": {
                "users_growth": [],
                "time_saved_trend": [],
                "cost_savings_trend": [],
            },
        }


# Global tracker
_roi_tracker: ROITracker | None = None


def get_roi_tracker() -> ROITracker:
    """Get global ROI tracker."""
    global _roi_tracker
    if _roi_tracker is None:
        _roi_tracker = ROITracker()
    return _roi_tracker


if __name__ == "__main__":
    tracker = get_roi_tracker()
    
    # Update with sample data
    tracker.update_metrics(
        total_users=50,
        active_users=35,
        hours_saved_debugging=120,
        hours_saved_maintenance=80,
        incidents_prevented=5,
        bugs_caught=25,
        patches_approved=8,
        patches_suggested=10,
    )
    
    # Generate report
    report = tracker.generate_report()
    
    print("ROI Report")
    print("=" * 50)
    print(f"Period: {report['period']}")
    print()
    print("Adoption:")
    print(f"  Total users: {report['adoption']['total_users']}")
    print(f"  Active rate: {report['adoption']['active_rate']}")
    print()
    print("Time Saved:")
    print(f"  Debugging: {report['time_saved']['debugging_hours']} hours")
    print(f"  Value: {report['time_saved']['value']}")
    print()
    print("ROI:")
    print(f"  Total value: {report['roi']['total_value']}")
    print(f"  ROI: {report['roi']['roi_percentage']}")
