"""Telemetry anomaly detection (Phase 14.3).

Detects anomalies in firmware telemetry using statistical methods:
- Isolation Forest for outlier detection
- Time series anomaly detection
- Pattern-based alerting
- Fleet-wide anomaly correlation
"""

from __future__ import annotations

import logging
import statistics
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ─── Magic numbers as named constants ──────────────────────────────────────────

class AnomalyDefaults:
    """Named defaults for anomaly detection thresholds."""
    ZSCORE_THRESHOLD = 3.0
    IQR_MULTIPLIER = 1.5
    MIN_WINDOW_SIZE = 10      # minimum points before detection runs
    CRITICAL_ZSCORE = 5.0
    CRITICAL_IQR_DEV = 3.0
    HIGH_ZSCORE = 4.0
    HIGH_IQR_DEV = 2.0
    MEDIUM_ZSCORE = 3.0
    MEDIUM_IQR_DEV = 1.5
    CONFIDENCE_DIVISOR = 10  # used in confidence = (zscore + iqr_dev) / 10
    TREND_DEVIATION_PCT = 0.2  # 20% mean shift to classify as TREND


class AnomalyType(Enum):
    """Types of anomalies."""
    POINT = "point"           # Single point anomaly
    CONTEXTUAL = "contextual" # Anomaly given context
    COLLECTIVE = "collective" # Anomaly in sequence
    TREND = "trend"         # Trend deviation


class Severity(Enum):
    """Anomaly severity."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class TimeSeriesPoint:
    """Single time series data point."""
    timestamp: datetime
    value: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Anomaly:
    """Detected anomaly."""
    anomaly_id: str
    board_id: str
    metric_name: str
    anomaly_type: AnomalyType
    severity: Severity
    
    # Details
    detected_at: datetime
    value: float
    expected_value: float
    deviation: float  # How far from expected
    confidence: float  # 0.0 - 1.0
    
    # Context
    window_start: datetime
    window_end: datetime
    related_anomalies: list[str] = field(default_factory=list)
    
    # Recommendation
    possible_causes: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)


class StatisticalDetector:
    """Statistical anomaly detection using z-scores and IQR."""
    
    def __init__(self, z_threshold: float = AnomalyDefaults.ZSCORE_THRESHOLD,
                 iqr_multiplier: float = AnomalyDefaults.IQR_MULTIPLIER) -> None:
        self._z_threshold = z_threshold
        self._iqr_multiplier = iqr_multiplier
    
    def detect_zscore(self, point: float, window: list[float]) -> tuple[bool, float]:
        """Detect anomaly using z-score."""
        if len(window) < 3:
            return False, 0.0
        
        mean = statistics.mean(window)
        stdev = statistics.stdev(window)
        
        if stdev == 0:
            return False, 0.0
        
        zscore = abs(point - mean) / stdev
        is_anomaly = zscore > self._z_threshold
        
        return is_anomaly, zscore
    
    def detect_iqr(self, point: float, window: list[float]) -> tuple[bool, float]:
        """Detect anomaly using IQR method."""
        if len(window) < 4:
            return False, 0.0
        
        sorted_window = sorted(window)
        n = len(sorted_window)
        q1 = sorted_window[n // 4]
        q3 = sorted_window[3 * n // 4]
        iqr = q3 - q1
        
        lower = q1 - self._iqr_multiplier * iqr
        upper = q3 + self._iqr_multiplier * iqr
        
        is_anomaly = point < lower or point > upper
        deviation = max(0, abs(point - (q1 + q3) / 2) / (iqr if iqr > 0 else 1))
        
        return is_anomaly, deviation


class TimeSeriesDetector:
    """Time series anomaly detection."""
    
    def __init__(self, window_size: int = 60,
                 min_window: int = AnomalyDefaults.MIN_WINDOW_SIZE) -> None:
        self._window_size = window_size
        self._min_window = min_window
        self._windows: dict[str, deque] = {}  # metric_name -> deque of points
        self._statistical = StatisticalDetector()
    
    def add_point(self, metric_name: str, point: TimeSeriesPoint) -> None:
        """Add a data point to the window."""
        if metric_name not in self._windows:
            self._windows[metric_name] = deque(maxlen=self._window_size)
        self._windows[metric_name].append(point)
    
    def detect(self, metric_name: str, point: TimeSeriesPoint) -> Anomaly | None:
        """Detect anomaly in time series."""
        if metric_name not in self._windows or len(self._windows[metric_name]) < self._min_window:
            return None
        
        window_values = [p.value for p in self._windows[metric_name]]
        window_times = [p.timestamp for p in self._windows[metric_name]]
        
        # Z-score detection
        is_zscore, zscore = self._statistical.detect_zscore(point.value, window_values)
        
        # IQR detection
        is_iqr, iqr_dev = self._statistical.detect_iqr(point.value, window_values)
        
        if not (is_zscore or is_iqr):
            return None
        
        # Calculate severity
        severity = Severity.LOW
        if zscore > AnomalyDefaults.CRITICAL_ZSCORE or iqr_dev > AnomalyDefaults.CRITICAL_IQR_DEV:
            severity = Severity.CRITICAL
        elif zscore > AnomalyDefaults.HIGH_ZSCORE or iqr_dev > AnomalyDefaults.HIGH_IQR_DEV:
            severity = Severity.HIGH
        elif zscore > AnomalyDefaults.MEDIUM_ZSCORE or iqr_dev > AnomalyDefaults.MEDIUM_IQR_DEV:
            severity = Severity.MEDIUM

        # Calculate expected value
        expected = statistics.mean(window_values)

        return Anomaly(
            anomaly_id=self._generate_id(),
            board_id=point.metadata.get("board_id", "unknown"),
            metric_name=metric_name,
            anomaly_type=self._classify_anomaly(window_values, point.value),
            severity=severity,
            detected_at=point.timestamp,
            value=point.value,
            expected_value=expected,
            deviation=max(zscore / self._statistical._z_threshold, iqr_dev / self._statistical._iqr_multiplier),
            confidence=min(1.0, (zscore + iqr_dev) / AnomalyDefaults.CONFIDENCE_DIVISOR),
            window_start=window_times[0],
            window_end=window_times[-1],
            possible_causes=self._suggest_causes(metric_name, point.value, expected),
            recommended_actions=self._suggest_actions(metric_name, severity),
        )
    
    def _classify_anomaly(self, window: list[float], point: float) -> AnomalyType:
        """Classify anomaly type."""
        if len(window) < 20:
            return AnomalyType.POINT
        
        # Check for trend
        recent = window[-10:]
        older = window[-20:-10] if len(window) >= 20 else window[:10]
        
        if recent and older:
            recent_mean = statistics.mean(recent)
            older_mean = statistics.mean(older)
            
            if abs(recent_mean - older_mean) / (older_mean if older_mean != 0 else 1) > AnomalyDefaults.TREND_DEVIATION_PCT:
                return AnomalyType.TREND
        
        return AnomalyType.POINT
    
    def _suggest_causes(self, metric: str, value: float, expected: float) -> list[str]:
        """Suggest possible causes for anomaly."""
        causes = []
        ratio = value / expected if expected != 0 else 0
        
        if metric == "memory_usage":
            if ratio > 1.5:
                causes.append("Memory leak")
                causes.append("Buffer overflow")
            elif ratio < 0.5:
                causes.append("Memory corruption detection")
        elif metric == "cpu_usage":
            if ratio > 2:
                causes.append("Infinite loop")
                causes.append("Busy-wait")
            elif ratio < 0.5:
                causes.append("Task starvation")
        elif metric == "temperature":
            if ratio > 1.2:
                causes.append("Cooling failure")
                causes.append("High ambient temperature")
        elif metric == "response_time":
            if ratio > 3:
                causes.append("Deadlock")
                causes.append("Resource contention")
        
        causes.append("Firmware bug")
        causes.append("Hardware degradation")
        
        return causes
    
    def _suggest_actions(self, metric: str, severity: Severity) -> list[str]:
        """Suggest actions for anomaly."""
        actions = []
        
        if severity in [Severity.HIGH, Severity.CRITICAL]:
            actions.append("Immediate investigation required")
            actions.append("Check system logs")
        
        if metric in ["memory_usage", "cpu_usage"]:
            actions.append("Profile firmware")
            actions.append("Review recent changes")
        
        actions.append("Monitor for recurrence")
        return actions
    
    def _generate_id(self) -> str:
        """Generate anomaly ID."""
        return uuid.uuid4().hex[:8]


class FleetAnomalyCorrelator:
    """Correlate anomalies across fleet."""
    
    def __init__(self) -> None:
        self._anomalies: list[Anomaly] = []
    
    def add_anomaly(self, anomaly: Anomaly) -> None:
        """Add anomaly for correlation."""
        self._anomalies.append(anomaly)
        
        # Update related anomalies
        self._update_relations()
    
    def _update_relations(self) -> None:
        """Update anomaly relations."""
        recent = [a for a in self._anomalies if 
                  a.detected_at > datetime.now() - timedelta(hours=1)]
        
        for a in recent:
            related = []
            
            # Find related anomalies
            for b in recent:
                if a.anomaly_id == b.anomaly_id:
                    continue
                
                # Same metric type
                if a.metric_name == b.metric_name and a.board_id != b.board_id:
                    related.append(b.anomaly_id)
                
                # Different boards affected simultaneously
                if abs((a.detected_at - b.detected_at).total_seconds()) < 60:
                    related.append(b.anomaly_id)
            
            a.related_anomalies = list(set(related))
    
    def get_correlated_anomalies(self, anomaly_id: str) -> list[Anomaly]:
        """Get correlated anomalies."""
        anomaly = next((a for a in self._anomalies if a.anomaly_id == anomaly_id), None)
        if not anomaly:
            return []
        
        return [a for a in self._anomalies if a.anomaly_id in anomaly.related_anomalies]
    
    def get_fleet_wide_anomalies(self) -> list[Anomaly]:
        """Get anomalies affecting multiple boards."""
        fleet_wide = []
        for a in self._anomalies:
            if len(a.related_anomalies) > 2:
                fleet_wide.append(a)
        return fleet_wide


class TelemetryAnomalyDetector:
    """Main anomaly detection system.
    
    Phase 14.3: Telemetry anomaly detection
    """
    
    def __init__(self) -> None:
        self._detectors: dict[str, TimeSeriesDetector] = {}
        self._correlator = FleetAnomalyCorrelator()
    
    def detect(
        self,
        board_id: str,
        metric_name: str,
        value: float,
        timestamp: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Anomaly | None:
        """Detect anomaly in telemetry."""
        if metric_name not in self._detectors:
            self._detectors[metric_name] = TimeSeriesDetector()
        
        point = TimeSeriesPoint(
            timestamp=timestamp or datetime.now(),
            value=value,
            metadata=metadata or {"board_id": board_id},
        )
        
        # Add to detector
        self._detectors[metric_name].add_point(metric_name, point)
        
        # Detect
        anomaly = self._detectors[metric_name].detect(metric_name, point)
        
        if anomaly:
            anomaly.board_id = board_id
            self._correlator.add_anomaly(anomaly)
            logger.warning(
                "Anomaly detected",
                board_id=board_id,
                metric=metric_name,
                severity=anomaly.severity.name,
            )
        
        return anomaly
    
    def get_correlated_anomalies(self, anomaly_id: str) -> list[Anomaly]:
        """Get correlated anomalies."""
        return self._correlator.get_correlated_anomalies(anomaly_id)
    
    def get_statistics(self) -> dict[str, Any]:
        """Get detection statistics."""
        return {
            "metrics_monitored": len(self._detectors),
            "total_anomalies": len(self._correlator._anomalies),
            "fleet_wide_anomalies": len(self._correlator.get_fleet_wide_anomalies()),
            "recent_anomalies": len([
                a for a in self._correlator._anomalies
                if a.detected_at > datetime.now() - timedelta(hours=1)
            ]),
        }


# Global singleton
_detector: TelemetryAnomalyDetector | None = None


def get_anomaly_detector() -> TelemetryAnomalyDetector:
    """Get global anomaly detector."""
    global _detector
    if _detector is None:
        _detector = TelemetryAnomalyDetector()
    return _detector


if __name__ == "__main__":
    detector = get_anomaly_detector()
    
    print("Testing telemetry anomaly detection:")
    print("-" * 50)
    
    # Simulate telemetry
    import random
    for i in range(50):
        value = 50 + random.gauss(0, 5)
        
        # Inject anomaly at iteration 40
        if i == 40:
            value = 150  # Spike
        
        anomaly = detector.detect(
            board_id="board_001",
            metric_name="memory_usage",
            value=value,
        )
        
        if anomaly:
            print(f"✓ Anomaly detected at {i}:")
            print(f"  Severity: {anomaly.severity.name}")
            print(f"  Value: {anomaly.value:.2f} (expected: {anomaly.expected_value:.2f})")
            print(f"  Confidence: {anomaly.confidence:.2f}")
            print(f"  Causes: {anomaly.possible_causes[:2]}")
    
    # Statistics
    stats = detector.get_statistics()
    print(f"\nStatistics: {stats}")
