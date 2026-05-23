"""Production Load Testing Framework.

Provides:
- k6 integration for HTTP/gRPC load testing
- pytest-benchmark integration for unit tests
- Realistic workload simulation
- Performance regression detection
- SLA validation
- Load test reporting

Usage:
    # CLI
    python -m src.infrastructure.testing.load_test run --scenario=normal_load
    
    # Programmatic
    runner = LoadTestRunner()
    results = await runner.run_scenario("flash_operations")
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class LoadTestScenario(Enum):
    """Predefined load test scenarios."""
    SMOKE = "smoke"  # Basic sanity test
    MICRO = "micro"  # Single operation stress
    NORMAL = "normal"  # Typical production load
    PEAK = "peak"  # Expected peak load
    SPIKE = "spike"  # Sudden traffic spike
    SUSTAINED = "sustained"  # Long duration stress
    CHAOS = "chaos"  # Load + failures


@dataclass
class LoadProfile:
    """Load profile configuration."""
    scenario: LoadTestScenario
    duration_seconds: int
    virtual_users: int
    spawn_rate: int  # Users per second
    think_time_seconds: float = 0.1
    
    # Thresholds
    max_response_time_ms: float = 1000.0
    max_error_rate_percent: float = 1.0
    target_throughput_rps: float = 100.0


@dataclass
class LoadTestMetrics:
    """Metrics from load test run."""
    scenario: str
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    
    # Request metrics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    error_rate_percent: float = 0.0
    
    # Latency metrics (ms)
    latency_min_ms: float = 0.0
    latency_max_ms: float = 0.0
    latency_avg_ms: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p90_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    
    # Throughput
    throughput_rps: float = 0.0
    
    # System metrics
    cpu_usage_percent: float = 0.0
    memory_usage_mb: float = 0.0
    
    # SLA compliance
    sla_met: bool = False
    sla_violations: list[str] = field(default_factory=list)


@dataclass
class LoadTestReport:
    """Complete load test report."""
    test_name: str
    profile: LoadProfile
    metrics: LoadTestMetrics
    passed: bool
    recommendations: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return {
            "test_name": self.test_name,
            "profile": {
                "scenario": self.profile.scenario.value,
                "duration_seconds": self.profile.duration_seconds,
                "virtual_users": self.profile.virtual_users,
                "spawn_rate": self.profile.spawn_rate,
            },
            "metrics": {
                "total_requests": self.metrics.total_requests,
                "error_rate_percent": self.metrics.error_rate_percent,
                "latency_avg_ms": self.metrics.latency_avg_ms,
                "latency_p99_ms": self.metrics.latency_p99_ms,
                "throughput_rps": self.metrics.throughput_rps,
            },
            "sla": {
                "met": self.metrics.sla_met,
                "violations": self.metrics.sla_violations,
            },
            "passed": self.passed,
            "recommendations": self.recommendations,
        }


class LoadTestRunner:
    """Runner for load tests.
    
    Usage:
        runner = LoadTestRunner()
        
        # Run predefined scenario
        results = await runner.run_scenario(
            "flash_operations",
            LoadTestScenario.PEAK,
        )
        
        # Check results
        if results.passed:
            print("Load test PASSED")
        else:
            print(f"SLA violations: {results.metrics.sla_violations}")
    """
    
    def __init__(self, output_dir: Path | None = None):
        self._output_dir = output_dir or Path("load_test_results")
        self._output_dir.mkdir(exist_ok=True)
        self._scenarios: dict[str, Callable] = {}
    
    def register_scenario(self, name: str, handler: Callable) -> None:
        """Register a custom test scenario.
        
        Args:
            name: Scenario name
            handler: Async function that executes the scenario
        """
        self._scenarios[name] = handler
        logger.info("scenario_registered", name=name)
    
    async def run_scenario(
        self,
        scenario_name: str,
        profile: LoadProfile | None = None,
    ) -> LoadTestReport:
        """Run a load test scenario.
        
        Args:
            scenario_name: Name of scenario to run
            profile: Load profile configuration
            
        Returns:
            LoadTestReport with results
        """
        if scenario_name not in self._scenarios:
            raise ValueError(f"Scenario not registered: {scenario_name}")
        
        # Default profile
        if profile is None:
            profile = LoadProfile(
                scenario=LoadTestScenario.NORMAL,
                duration_seconds=60,
                virtual_users=10,
                spawn_rate=2,
            )
        
        handler = self._scenarios[scenario_name]
        
        started_at = datetime.now()
        logger.info(
            "load_test_started",
            scenario=scenario_name,
            profile=profile.scenario.value,
            users=profile.virtual_users,
        )
        
        # Collect metrics
        metrics = await self._execute_load_test(handler, profile)
        
        ended_at = datetime.now()
        metrics.scenario = scenario_name
        metrics.started_at = started_at
        metrics.ended_at = ended_at
        metrics.duration_seconds = (ended_at - started_at).total_seconds()
        
        # Calculate SLA compliance
        self._check_sla(profile, metrics)
        
        # Generate report
        report = LoadTestReport(
            test_name=scenario_name,
            profile=profile,
            metrics=metrics,
            passed=metrics.sla_met,
        )
        
        # Save results
        await self._save_report(report)
        
        logger.info(
            "load_test_completed",
            scenario=scenario_name,
            passed=report.passed,
            error_rate=metrics.error_rate_percent,
        )
        
        return report
    
    async def _execute_load_test(
        self,
        handler: Callable,
        profile: LoadProfile,
    ) -> LoadTestMetrics:
        """Execute load test with metrics collection."""
        metrics = LoadTestMetrics(
            scenario=profile.scenario.value,
            started_at=datetime.now(),
            ended_at=datetime.now(),
            duration_seconds=profile.duration_seconds,
        )
        
        # Simulate virtual users
        latencies: list[float] = []
        errors = 0
        successes = 0
        
        async def virtual_user(user_id: int):
            nonlocal successes, errors
            
            iterations = profile.duration_seconds // profile.think_time_seconds
            
            for i in range(iterations):
                try:
                    start = time.perf_counter()
                    await handler(user_id, i)
                    latency_ms = (time.perf_counter() - start) * 1000
                    
                    latencies.append(latency_ms)
                    successes += 1
                    
                except Exception as e:
                    errors += 1
                    logger.debug("load_test_request_failed", user=user_id, error=str(e))
                
                # Think time
                await asyncio.sleep(profile.think_time_seconds)
        
        # Spawn users with rate limiting
        tasks = []
        for i in range(profile.virtual_users):
            tasks.append(asyncio.create_task(virtual_user(i)))
            
            # Rate limiting
            if (i + 1) % profile.spawn_rate == 0:
                await asyncio.sleep(1)
        
        # Wait for completion
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Calculate metrics
        metrics.total_requests = successes + errors
        metrics.successful_requests = successes
        metrics.failed_requests = errors
        metrics.error_rate_percent = (errors / metrics.total_requests * 100) if metrics.total_requests > 0 else 0
        
        # Latency percentiles
        if latencies:
            latencies.sort()
            n = len(latencies)
            metrics.latency_min_ms = min(latencies)
            metrics.latency_max_ms = max(latencies)
            metrics.latency_avg_ms = sum(latencies) / n
            metrics.latency_p50_ms = latencies[int(n * 0.50)]
            metrics.latency_p90_ms = latencies[int(n * 0.90)]
            metrics.latency_p95_ms = latencies[int(n * 0.95)]
            metrics.latency_p99_ms = latencies[int(n * 0.99)]
        
        # Throughput
        metrics.throughput_rps = metrics.total_requests / profile.duration_seconds
        
        return metrics
    
    def _check_sla(self, profile: LoadProfile, metrics: LoadTestMetrics) -> None:
        """Check SLA compliance."""
        violations = []
        
        # Error rate
        if metrics.error_rate_percent > profile.max_error_rate_percent:
            violations.append(
                f"Error rate {metrics.error_rate_percent:.2f}% exceeds "
                f"threshold {profile.max_error_rate_percent}%"
            )
        
        # Response time
        if metrics.latency_p99_ms > profile.max_response_time_ms:
            violations.append(
                f"P99 latency {metrics.latency_p99_ms:.0f}ms exceeds "
                f"threshold {profile.max_response_time_ms}ms"
            )
        
        # Throughput
        if metrics.throughput_rps < profile.target_throughput_rps * 0.8:
            violations.append(
                f"Throughput {metrics.throughput_rps:.0f} rps below "
                f"80% of target {profile.target_throughput_rps} rps"
            )
        
        metrics.sla_met = len(violations) == 0
        metrics.sla_violations = violations


class K6Loader:
    """K6 load test configuration generator.
    
    Generates k6 JavaScript scripts for advanced HTTP/gRPC testing.
    
    Usage:
        loader = K6Loader()
        loader.add_endpoint(
            path="/api/v1/flash",
            method="POST",
            weight=10,
        )
        script = loader.generate_script()
    """
    
    def __init__(self):
        self._endpoints: list[dict[str, Any]] = []
        self._options = {
            "vus": 10,
            "duration": "60s",
            "thresholds": {
                "http_req_duration": ["p(95)<500"],
                "http_req_failed": ["rate<0.01"],
            },
        }
    
    def add_endpoint(
        self,
        path: str,
        method: str = "GET",
        weight: int = 1,
        body: dict | None = None,
    ) -> "K6Loader":
        """Add endpoint to test."""
        self._endpoints.append({
            "path": path,
            "method": method,
            "weight": weight,
            "body": body,
        })
        return self
    
    def set_options(
        self,
        vus: int | None = None,
        duration: str | None = None,
        thresholds: dict | None = None,
    ) -> "K6Loader":
        """Set k6 options."""
        if vus:
            self._options["vus"] = vus
        if duration:
            self._options["duration"] = duration
        if thresholds:
            self._options["thresholds"].update(thresholds)
        return self
    
    def generate_script(self) -> str:
        """Generate k6 JavaScript script."""
        endpoints_json = json.dumps(self._endpoints, indent=2)
        options_json = json.dumps(self._options, indent=2)
        
        return f"""
import {{ Options }} from 'k6/options';
import {{ check, sleep }} from 'k6';

export const options: Options = {options_json};

const endpoints = {endpoints_json};

export default function() {{
    // Weighted random selection
    const totalWeight = endpoints.reduce((sum, e) => sum + e.weight, 0);
    let rand = Math.random() * totalWeight;
    
    for (const endpoint of endpoints) {{
        rand -= endpoint.weight;
        if (rand <= 0) {{
            const url = `http://localhost:8080${{endpoint.path}}`;
            
            const params = {{
                headers: {{
                    'Content-Type': 'application/json',
                }},
            }};
            
            if (endpoint.method === 'GET') {{
                const res = http.get(url, params);
                check(res, {{
                    'status is 200': (r) => r.status === 200,
                }});
            }} else if (endpoint.method === 'POST') {{
                const body = endpoint.body || {{}};
                const res = http.post(url, JSON.stringify(body), params);
                check(res, {{
                    'status is 200': (r) => r.status === 200,
                }});
            }}
            
            break;
        }}
    }}
    
    sleep(0.1);
}}
"""


class BenchmarkRunner:
    """pytest-benchmark integration for unit performance tests.
    
    Usage:
        # In test file
        def test_performance(benchmark):
            result = benchmark(my_function, arg1, arg2)
            assert result < 0.1  # 100ms threshold
    """
    
    @staticmethod
    def run_benchmark(func: Callable, *args, iterations: int = 100, **kwargs) -> dict[str, float]:
        """Run function multiple times and collect timing.
        
        Returns:
            Dict with mean, std, min, max times in seconds
        """
        import time
        
        times = []
        for _ in range(iterations):
            start = time.perf_counter()
            func(*args, **kwargs)
            elapsed = time.perf_counter() - start
            times.append(elapsed)
        
        return {
            "mean": sum(times) / len(times),
            "std": (sum((t - sum(times)/len(times))**2 for t in times) / len(times)) ** 0.5,
            "min": min(times),
            "max": max(times),
        }
    
    @staticmethod
    def compare_benchmarks(
        baseline: dict[str, float],
        current: dict[str, float],
        threshold_percent: float = 10.0,
    ) -> tuple[bool, list[str]]:
        """Compare two benchmark results.
        
        Returns (passed, list of regressions).
        """
        regressions = []
        
        for key in ["mean", "std", "max"]:
            baseline_val = baseline.get(key, 0)
            current_val = current.get(key, 0)
            
            if baseline_val > 0:
                change_percent = ((current_val - baseline_val) / baseline_val) * 100
                
                if change_percent > threshold_percent:
                    regressions.append(
                        f"{key}: {change_percent:+.1f}% regression "
                        f"({baseline_val*1000:.2f}ms -> {current_val*1000:.2f}ms)"
                    )
        
        return len(regressions) == 0, regressions


# CLI interface
async def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Load Testing Framework")
    subparsers = parser.add_subparsers(dest="command")
    
    # Run command
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--scenario", default="normal", help="Scenario name")
    run_parser.add_argument("--users", type=int, default=10, help="Virtual users")
    run_parser.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    
    args = parser.parse_args()
    
    if args.command == "run":
        runner = LoadTestRunner()
        
        # Register sample scenario
        async def sample_scenario(user_id: int, iteration: int):
            await asyncio.sleep(0.01)  # Simulate work
        
        runner.register_scenario(args.scenario, sample_scenario)
        
        profile = LoadProfile(
            scenario=LoadTestScenario.NORMAL,
            duration_seconds=args.duration,
            virtual_users=args.users,
            spawn_rate=args.users // 10,
        )
        
        report = await runner.run_scenario(args.scenario, profile)
        print(json.dumps(report.to_dict(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
