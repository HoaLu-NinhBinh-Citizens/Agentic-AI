"""SLO and Error Budget management (Phase 13.3).

Provides SLO definition and error budget tracking:
- SLO configuration
- Error budget calculation
- Burn rate alerts
- Budget consumption tracking
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SLOStatus(Enum):
    """SLO health status."""
    HEALTHY = "healthy"
    AT_RISK = "at_risk"
    BREACHING = "breaching"


class AlertLevel(Enum):
    """Alert levels for SLO."""
    NONE = "none"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class SLOTarget:
    """SLO target definition."""
    slo_id: str
    name: str
    metric_type: str  # availability, latency, quality
    
    # Targets
    target_value: float  # e.g., 0.999 for 99.9%
    window_days: int = 30
    
    # Thresholds
    burn_rate_threshold: float = 14.4  # Fast burn rate
    at_risk_threshold: float = 0.8  # 80% of budget consumed


@dataclass
class SLODataPoint:
    """Single SLO data point."""
    timestamp: datetime
    good_events: int
    total_events: int
    
    @property
    def success_rate(self) -> float:
        if self.total_events == 0:
            return 1.0
        return self.good_events / self.total_events


@dataclass
class ErrorBudget:
    """Error budget state."""
    total_budget: float
    consumed: float
    remaining: float
    
    @property
    def consumption_percentage(self) -> float:
        if self.total_budget == 0:
            return 0.0
        return (self.consumed / self.total_budget) * 100
    
    @property
    def is_exhausted(self) -> bool:
        return self.remaining <= 0


@dataclass
class BurnRateAlert:
    """Burn rate alert."""
    alert_level: AlertLevel
    slo_id: str
    burn_rate: float
    budget_consumed_percentage: float
    estimated_time_to_exhaustion: timedelta | None


class SLOManager:
    """SLO and error budget manager.
    
    Phase 13.3: Error budget & SLO
    """
    
    def __init__(self) -> None:
        self._slos: dict[str, SLOTarget] = {}
        self._data_points: dict[str, list[SLODataPoint]] = {}
        self._alerts: list[BurnRateAlert] = []
    
    def register_slo(self, slo: SLOTarget) -> None:
        """Register SLO target."""
        self._slos[slo.slo_id] = slo
        self._data_points[slo.slo_id] = []
        logger.info("SLO registered", slo_id=slo.slo_id, target=slo.target_value)
    
    def record_events(
        self,
        slo_id: str,
        good_events: int,
        total_events: int,
    ) -> None:
        """Record SLO events."""
        if slo_id not in self._slos:
            return
        
        point = SLODataPoint(
            timestamp=datetime.now(),
            good_events=good_events,
            total_events=total_events,
        )
        self._data_points[slo_id].append(point)
        
        # Keep only window data
        window_start = datetime.now() - timedelta(days=self._slos[slo_id].window_days)
        self._data_points[slo_id] = [
            p for p in self._data_points[slo_id]
            if p.timestamp >= window_start
        ]
    
    def calculate_budget(self, slo_id: str) -> ErrorBudget | None:
        """Calculate error budget."""
        slo = self._slos.get(slo_id)
        if not slo:
            return None
        
        data_points = self._data_points.get(slo_id, [])
        if not data_points:
            return ErrorBudget(total_budget=0, consumed=0, remaining=0)
        
        # Calculate total events and good events
        total_events = sum(p.total_events for p in data_points)
        good_events = sum(p.good_events for p in data_points)
        
        # Error budget = total allowed errors
        error_budget = total_events * (1 - slo.target_value)
        errors_consumed = total_events - good_events
        
        return ErrorBudget(
            total_budget=error_budget,
            consumed=errors_consumed,
            remaining=max(0, error_budget - errors_consumed),
        )
    
    def calculate_burn_rate(
        self,
        slo_id: str,
        window_hours: int = 1,
    ) -> float | None:
        """Calculate burn rate (errors consumed / expected consumption)."""
        slo = self._slos.get(slo_id)
        if not slo:
            return None
        
        data_points = self._data_points.get(slo_id, [])
        if not data_points:
            return 0.0
        
        # Filter to window
        window_start = datetime.now() - timedelta(hours=window_hours)
        recent = [p for p in data_points if p.timestamp >= window_start]
        
        if not recent:
            return 0.0
        
        # Calculate actual error rate
        total = sum(p.total_events for p in recent)
        errors = sum(p.total_events - p.good_events for p in recent)
        
        if total == 0:
            return 0.0
        
        actual_error_rate = errors / total
        allowed_error_rate = 1 - slo.target_value
        
        if allowed_error_rate == 0:
            return 0.0
        
        # Burn rate = how fast we're consuming budget vs time
        return actual_error_rate / allowed_error_rate
    
    def check_alerts(self, slo_id: str) -> BurnRateAlert | None:
        """Check for burn rate alerts."""
        slo = self._slos.get(slo_id)
        if not slo:
            return None
        
        burn_rate = self.calculate_burn_rate(slo_id)
        if burn_rate is None:
            return None
        
        budget = self.calculate_budget(slo_id)
        if not budget:
            return None
        
        consumed_pct = budget.consumption_percentage
        
        # Determine alert level
        if consumed_pct >= 100:
            level = AlertLevel.CRITICAL
        elif consumed_pct >= slo.at_risk_threshold * 100:
            level = AlertLevel.WARNING
        else:
            level = AlertLevel.NONE
        
        # Calculate time to exhaustion
        exhaustion_time = None
        if burn_rate > 1:
            hours_remaining = budget.remaining / ((burn_rate - 1) * (budget.total_budget / (30 * 24)))
            exhaustion_time = timedelta(hours=hours_remaining) if hours_remaining > 0 else timedelta(0)
        
        alert = BurnRateAlert(
            alert_level=level,
            slo_id=slo_id,
            burn_rate=burn_rate,
            budget_consumed_percentage=consumed_pct,
            estimated_time_to_exhaustion=exhaustion_time,
        )
        
        if level != AlertLevel.NONE:
            self._alerts.append(alert)
            logger.warning(
                "SLO alert",
                slo_id=slo_id,
                level=level.value,
                burn_rate=burn_rate,
            )
        
        return alert
    
    def get_slo_status(self, slo_id: str) -> SLOStatus | None:
        """Get SLO health status."""
        budget = self.calculate_budget(slo_id)
        if not budget:
            return None
        
        if budget.is_exhausted:
            return SLOStatus.BREACHING
        elif budget.consumption_percentage >= 80:
            return SLOStatus.AT_RISK
        else:
            return SLOStatus.HEALTHY
    
    def get_summary(self) -> dict[str, Any]:
        """Get SLO summary."""
        summary = {
            "total_slos": len(self._slos),
            "healthy": 0,
            "at_risk": 0,
            "breaching": 0,
            "active_alerts": 0,
        }
        
        for slo_id in self._slos:
            status = self.get_slo_status(slo_id)
            if status == SLOStatus.HEALTHY:
                summary["healthy"] += 1
            elif status == SLOStatus.AT_RISK:
                summary["at_risk"] += 1
            elif status == SLOStatus.BREACHING:
                summary["breaching"] += 1
        
        summary["active_alerts"] = len([a for a in self._alerts if a.alert_level != AlertLevel.NONE])
        
        return summary


# Global manager
_slo_manager: SLOManager | None = None


def get_slo_manager() -> SLOManager:
    """Get global SLO manager."""
    global _slo_manager
    if _slo_manager is None:
        _slo_manager = SLOManager()
    return _slo_manager


if __name__ == "__main__":
    manager = get_slo_manager()
    
    # Register SLO (99.9% availability)
    slo = SLOTarget(
        slo_id="debug_availability",
        name="Debug Service Availability",
        metric_type="availability",
        target_value=0.999,  # 99.9%
        window_days=30,
    )
    manager.register_slo(slo)
    
    # Simulate events (99.8% success rate - slightly below target)
    for _ in range(100):
        manager.record_events("debug_availability", good_events=998, total_events=1000)
    
    # Check budget
    budget = manager.calculate_budget("debug_availability")
    if budget:
        print("Error Budget")
        print("=" * 40)
        print(f"Total budget: {budget.total_budget:.1f} errors")
        print(f"Consumed: {budget.consumed:.1f}")
        print(f"Remaining: {budget.remaining:.1f}")
        print(f"Consumption: {budget.consumption_percentage:.1f}%")
    
    # Check burn rate
    burn_rate = manager.calculate_burn_rate("debug_availability")
    print(f"\nBurn rate: {burn_rate:.2f}x")
    
    # Check alerts
    alert = manager.check_alerts("debug_availability")
    if alert:
        print(f"Alert: {alert.alert_level.value}")
        print(f"Time to exhaustion: {alert.estimated_time_to_exhaustion}")
    
    # Status
    status = manager.get_slo_status("debug_availability")
    print(f"\nSLO Status: {status.value if status else 'Unknown'}")
    
    # Summary
    summary = manager.get_summary()
    print(f"\nSummary: {summary}")
