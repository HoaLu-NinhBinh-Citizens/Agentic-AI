"""Production SLA Monitoring Dashboard.

Real-time metrics collection and SLA validation.
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

# ============================================================================
# SLA Metrics Definitions
# ============================================================================

@dataclass
class SLADefinition:
    """SLA definition."""
    name: str
    target: float  # Target percentage (e.g., 99.9 for 99.9%)
    window: timedelta  # Measurement window
    description: str


# Default SLAs
DEFAULT_SLAS = {
    "availability": SLADefinition(
        name="availability",
        target=99.9,  # 99.9% uptime
        window=timedelta(days=30),
        description="System availability",
    ),
    "latency_p99": SLADefinition(
        name="latency_p99",
        target=99.0,  # 99% of requests under threshold
        window=timedelta(hours=1),
        description="P99 response time < 1s",
    ),
    "error_rate": SLADefinition(
        name="error_rate",
        target=99.5,  # 99.5% success rate
        window=timedelta(hours=1),
        description="Error rate < 0.5%",
    ),
    "flash_success": SLADefinition(
        name="flash_success",
        target=99.99,  # 99.99% for safety-critical
        window=timedelta(days=1),
        description="Flash operations success rate",
    ),
    "recovery_time": SLADefinition(
        name="recovery_time",
        target=95.0,  # 95% of recoveries under threshold
        window=timedelta(hours=24),
        description="Recovery time < 5 minutes",
    ),
}


# ============================================================================
# Metrics Collection
# ============================================================================

@dataclass
class MetricPoint:
    """A single metric data point."""
    timestamp: datetime
    value: float
    labels: dict[str, str] = field(default_factory=dict)


class SLAMetricsCollector:
    """Collects and aggregates SLA metrics.
    
    Usage:
        collector = SLAMetricsCollector()
        
        # Record metrics
        collector.record("latency", 150.5, labels={"endpoint": "/api/flash"})
        collector.record("error", 1.0, labels={"type": "timeout"})
        
        # Get current SLA status
        status = collector.get_sla_status("availability")
    """
    
    def __init__(self):
        self._metrics: dict[str, list[MetricPoint]] = {}
        self._counters: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
    
    def record(self, metric_name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Record a metric value."""
        if metric_name not in self._metrics:
            self._metrics[metric_name] = []
        
        self._metrics[metric_name].append(MetricPoint(
            timestamp=datetime.now(),
            value=value,
            labels=labels or {},
        ))
        
        # Keep only last 1 hour of data
        cutoff = datetime.now() - timedelta(hours=1)
        self._metrics[metric_name] = [
            m for m in self._metrics[metric_name] if m.timestamp > cutoff
        ]
    
    def increment(self, counter_name: str, value: float = 1.0) -> None:
        """Increment a counter."""
        self._counters[counter_name] = self._counters.get(counter_name, 0) + value
    
    def record_histogram(self, histogram_name: str, value: float) -> None:
        """Record a histogram value."""
        if histogram_name not in self._histograms:
            self._histograms[histogram_name] = []
        
        self._histograms[histogram_name].append(value)
        
        # Keep last 10000 values
        if len(self._histograms[histogram_name]) > 10000:
            self._histograms[histogram_name] = self._histograms[histogram_name][-10000:]
    
    def get_percentile(self, histogram_name: str, percentile: float) -> float:
        """Calculate percentile from histogram."""
        if histogram_name not in self._histograms:
            return 0.0
        
        values = sorted(self._histograms[histogram_name])
        if not values:
            return 0.0
        
        index = int(len(values) * percentile / 100)
        return values[min(index, len(values) - 1)]
    
    def get_sla_status(self, sla_name: str) -> dict[str, Any]:
        """Get current SLA status."""
        if sla_name not in DEFAULT_SLAS:
            return {"error": f"Unknown SLA: {sla_name}"}
        
        sla = DEFAULT_SLAS[sla_name]
        cutoff = datetime.now() - sla.window
        
        # Get metrics in window
        if sla_name not in self._metrics:
            return {
                "sla": sla_name,
                "target": sla.target,
                "current": 100.0,  # No data = 100%
                "status": "ok",
            }
        
        metrics = [m for m in self._metrics[sla_name] if m.timestamp > cutoff]
        
        if not metrics:
            return {
                "sla": sla_name,
                "target": sla.target,
                "current": 100.0,
                "status": "ok",
            }
        
        # Calculate current percentage
        if sla_name == "availability":
            # Calculate from uptime metric
            total = len(metrics)
            successes = sum(1 for m in metrics if m.value > 0)
            current = (successes / total * 100) if total > 0 else 100.0
        elif sla_name == "error_rate":
            # Calculate from error count
            errors = sum(m.value for m in metrics)
            total = self._counters.get("total_requests", 1)
            current = ((total - errors) / total * 100) if total > 0 else 100.0
        elif sla_name == "latency_p99":
            # Calculate from latency histogram
            p99 = self.get_percentile("latency", 99)
            current = 100.0 if p99 < 1000 else 0.0  # 1s threshold
        else:
            current = 100.0
        
        status = "ok" if current >= sla.target else "warning" if current >= sla.target - 0.1 else "critical"
        
        return {
            "sla": sla_name,
            "target": sla.target,
            "current": current,
            "status": status,
            "description": sla.description,
        }
    
    def get_all_sla_status(self) -> dict[str, Any]:
        """Get status of all SLAs."""
        return {
            name: self.get_sla_status(name)
            for name in DEFAULT_SLAS.keys()
        }
    
    def get_summary(self) -> dict[str, Any]:
        """Get overall SLA summary."""
        all_status = self.get_all_sla_status()
        
        ok_count = sum(1 for s in all_status.values() if s.get("status") == "ok")
        warning_count = sum(1 for s in all_status.values() if s.get("status") == "warning")
        critical_count = sum(1 for s in all_status.values() if s.get("status") == "critical")
        
        overall_status = "ok"
        if critical_count > 0:
            overall_status = "critical"
        elif warning_count > 0:
            overall_status = "warning"
        
        return {
            "overall_status": overall_status,
            "ok_count": ok_count,
            "warning_count": warning_count,
            "critical_count": critical_count,
            "total_count": len(DEFAULT_SLAS),
            "slas": all_status,
        }


# ============================================================================
# Dashboard
# ============================================================================

class SLADashboard:
    """Real-time SLA monitoring dashboard.
    
    Usage:
        dashboard = SLADashboard()
        
        # Update metrics
        dashboard.record_latency(endpoint="/api/flash", duration_ms=150)
        dashboard.record_error(error_type="timeout")
        dashboard.record_success(operation="flash_write")
        
        # Get current status
        status = dashboard.get_status()
        
        # Print dashboard
        dashboard.print_dashboard()
    """
    
    def __init__(self, collector: SLAMetricsCollector | None = None):
        self._collector = collector or SLAMetricsCollector()
        self._last_update = datetime.now()
    
    def record_latency(self, endpoint: str, duration_ms: float) -> None:
        """Record request latency."""
        self._collector.record("latency", duration_ms, labels={"endpoint": endpoint})
        self._collector.record_histogram("latency", duration_ms)
        self._collector.increment("total_requests")
    
    def record_error(self, error_type: str, count: float = 1.0) -> None:
        """Record an error."""
        self._collector.record("error", count, labels={"type": error_type})
        self._collector.increment(f"errors_{error_type}", count)
        self._collector.increment("total_errors", count)
    
    def record_success(self, operation: str) -> None:
        """Record a successful operation."""
        self._collector.increment(f"success_{operation}")
        self._collector.increment("total_successes")
    
    def record_flash_operation(self, success: bool, duration_ms: float) -> None:
        """Record a flash operation."""
        self._collector.record("flash_latency", duration_ms)
        self._collector.record_histogram("flash_latency", duration_ms)
        
        if success:
            self._collector.increment("flash_success")
        else:
            self._collector.increment("flash_failure")
            self._collector.record("error", 1.0, labels={"type": "flash_failure"})
    
    def record_agent_execution(self, success: bool, duration_ms: float) -> None:
        """Record agent execution."""
        self._collector.record("agent_latency", duration_ms)
        self._collector.record_histogram("agent_latency", duration_ms)
        
        if success:
            self._collector.increment("agent_success")
        else:
            self._collector.increment("agent_failure")
    
    def get_status(self) -> dict[str, Any]:
        """Get current SLA status."""
        return self._collector.get_summary()
    
    def get_metrics(self) -> dict[str, Any]:
        """Get detailed metrics."""
        collector = self._collector
        
        return {
            "timestamp": datetime.now().isoformat(),
            "counters": dict(collector._counters),
            "histograms": {
                "latency_p50": collector.get_percentile("latency", 50),
                "latency_p90": collector.get_percentile("latency", 90),
                "latency_p95": collector.get_percentile("latency", 95),
                "latency_p99": collector.get_percentile("latency", 99),
                "latency_p999": collector.get_percentile("latency", 99.9),
                "flash_latency_p99": collector.get_percentile("flash_latency", 99),
                "agent_latency_p99": collector.get_percentile("agent_latency", 99),
            },
            "sla": collector.get_all_sla_status(),
        }
    
    def print_dashboard(self) -> None:
        """Print dashboard to console."""
        status = self.get_status()
        metrics = self.get_metrics()
        
        print("\n" + "=" * 70)
        print("AI_SUPPORT SLA DASHBOARD")
        print("=" * 70)
        print(f"Updated: {metrics['timestamp']}")
        print()
        
        # Overall status
        overall = status["overall_status"]
        status_icon = "✅" if overall == "ok" else "⚠️" if overall == "warning" else "❌"
        
        print(f"{status_icon} Overall Status: {overall.upper()}")
        print()
        
        # SLA Status
        print("SLA STATUS:")
        print("-" * 50)
        
        for name, sla_status in status["slas"].items():
            target = sla_status.get("target", 0)
            current = sla_status.get("current", 0)
            sla_status_val = sla_status.get("status", "ok")
            
            icon = "✅" if sla_status_val == "ok" else "⚠️" if sla_status_val == "warning" else "❌"
            
            print(f"  {icon} {name:20} Target: {target:6.2f}% | Current: {current:6.2f}%")
        
        print()
        
        # Performance metrics
        print("PERFORMANCE METRICS:")
        print("-" * 50)
        
        h = metrics["histograms"]
        print(f"  Latency P50:  {h['latency_p50']:8.1f} ms")
        print(f"  Latency P90:  {h['latency_p90']:8.1f} ms")
        print(f"  Latency P95:  {h['latency_p95']:8.1f} ms")
        print(f"  Latency P99:  {h['latency_p99']:8.1f} ms")
        print(f"  Latency P99.9:{h['latency_p999']:8.1f} ms")
        print()
        
        # Counters
        print("COUNTERS:")
        print("-" * 50)
        
        c = metrics["counters"]
        print(f"  Total Requests:  {c.get('total_requests', 0):10.0f}")
        print(f"  Total Success:  {c.get('total_successes', 0):10.0f}")
        print(f"  Total Errors:   {c.get('total_errors', 0):10.0f}")
        print(f"  Flash Success:   {c.get('flash_success', 0):10.0f}")
        print(f"  Flash Failure:   {c.get('flash_failure', 0):10.0f}")
        print(f"  Agent Success:   {c.get('agent_success', 0):10.0f}")
        print(f"  Agent Failure:   {c.get('agent_failure', 0):10.0f}")
        
        # Calculate error rate
        total = c.get('total_requests', 0)
        errors = c.get('total_errors', 0)
        error_rate = (errors / total * 100) if total > 0 else 0
        print(f"  Error Rate:     {error_rate:8.2f}%")
        
        print("=" * 70)


# ============================================================================
# Continuous Monitoring
# ============================================================================

async def run_monitoring_loop(dashboard: SLADashboard, interval_seconds: int = 60):
    """Run continuous monitoring loop.
    
    Prints dashboard every interval_seconds.
    """
    while True:
        dashboard.print_dashboard()
        await asyncio.sleep(interval_seconds)


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    # Simulate metrics
    dashboard = SLADashboard()
    
    import random
    
    # Generate fake metrics
    for i in range(1000):
        dashboard.record_latency("/api/flash", random.uniform(50, 500))
        dashboard.record_latency("/api/agent", random.uniform(100, 1000))
        
        if random.random() < 0.01:  # 1% error rate
            dashboard.record_error("timeout")
        
        dashboard.record_success("flash_write")
        dashboard.record_agent_execution(success=random.random() > 0.02)
        dashboard.record_flash_operation(
            success=random.random() > 0.001,  # 0.1% flash failure
            duration_ms=random.uniform(100, 1000),
        )
    
    # Print dashboard
    dashboard.print_dashboard()
