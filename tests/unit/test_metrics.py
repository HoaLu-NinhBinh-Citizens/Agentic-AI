"""Tests for metrics registry."""

import pytest
from infrastructure.observability.metrics import (
    SimpleHistogram,
    MetricsRegistry,
)


class TestSimpleHistogram:
    """Tests for SimpleHistogram."""

    def test_observe_adds_to_count(self):
        """Test that observe increments count."""
        hist = SimpleHistogram(buckets=[0.1, 0.5, 1.0])
        hist.observe(0.05)
        hist.observe(0.3)
        hist.observe(0.8)

        buckets, counts, total, count = hist.export()
        assert count == 3
        assert abs(total - 1.15) < 0.001

    def test_observe_buckets_correctly(self):
        """Test that observations are bucketed correctly."""
        hist = SimpleHistogram(buckets=[0.1, 0.5, 1.0])

        hist.observe(0.05)
        hist.observe(0.3)
        hist.observe(0.8)
        hist.observe(1.5)

        buckets, counts, total, count = hist.export()

        assert counts[0] == 1  # 0.05 <= 0.1
        assert counts[1] == 1  # 0.3 <= 0.5
        assert counts[2] == 1  # 0.8 <= 1.0
        assert counts[3] == 1  # 1.5 > 1.0 (+Inf)

    def test_no_memory_leak(self):
        """Test that histogram doesn't grow unbounded."""
        hist = SimpleHistogram(buckets=[0.1, 0.5, 1.0])

        for _ in range(10000):
            hist.observe(0.3)

        buckets, counts, total, count = hist.export()

        assert count == 10000
        assert len(buckets) == 3
        assert len(counts) == 4


class TestMetricsRegistry:
    """Tests for MetricsRegistry."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        MetricsRegistry.reset_instance()
        yield
        MetricsRegistry.reset_instance()

    @pytest.fixture
    def registry(self):
        """Get a fresh registry instance."""
        return MetricsRegistry.get_instance()

    @pytest.mark.asyncio
    async def test_inc_counter(self, registry):
        """Test counter increment."""
        await registry.inc_counter("test_counter", {"status": "success"})
        await registry.inc_counter("test_counter", {"status": "success"})

        value = await registry.get_counter("test_counter", {"status": "success"})
        assert value == 2

    @pytest.mark.asyncio
    async def test_inc_counter_with_tags(self, registry):
        """Test counter with different tags."""
        await registry.inc_counter("tool_calls", {"tool": "read", "success": "true"})
        await registry.inc_counter("tool_calls", {"tool": "read", "success": "false"})
        await registry.inc_counter("tool_calls", {"tool": "write", "success": "true"})

        assert await registry.get_counter("tool_calls", {"tool": "read", "success": "true"}) == 1
        assert await registry.get_counter("tool_calls", {"tool": "read", "success": "false"}) == 1
        assert await registry.get_counter("tool_calls", {"tool": "write", "success": "true"}) == 1

    @pytest.mark.asyncio
    async def test_observe_histogram(self, registry):
        """Test histogram observation."""
        await registry.observe_histogram("duration", 0.05, {"tool": "read"})
        await registry.observe_histogram("duration", 0.15, {"tool": "read"})

        output = await registry.export_text()

        assert "# TYPE duration histogram" in output
        assert 'tool="read"' in output

    @pytest.mark.asyncio
    async def test_export_text_format(self, registry):
        """Test Prometheus text format export."""
        await registry.inc_counter("requests_total", {"method": "GET", "status": "200"})
        await registry.observe_histogram("request_duration", 0.5, {"method": "GET"})

        output = await registry.export_text()

        assert "# HELP requests_total" in output
        assert "# TYPE requests_total counter" in output
        assert 'method="GET"' in output
        assert "# HELP request_duration" in output
        assert "# TYPE request_duration histogram" in output

    @pytest.mark.asyncio
    async def test_no_cardinality_explosion(self, registry):
        """Test that high-cardinality tags are handled."""
        for i in range(100):
            await registry.inc_counter(
                "requests",
                {"session_id": f"session-{i}"},
            )

        output = await registry.export_text()

        lines = output.split("\n")
        counter_lines = [l for l in lines if l.startswith("requests{")]
        assert len(counter_lines) == 100

    @pytest.mark.asyncio
    async def test_custom_buckets(self, registry):
        """Test custom histogram buckets."""
        custom_buckets = [0.01, 0.1, 1.0]
        registry.set_histogram_buckets("custom_duration", custom_buckets)

        await registry.observe_histogram(
            "custom_duration",
            0.5,
            {"endpoint": "/api"},
            buckets=custom_buckets,
        )

        output = await registry.export_text()
        assert 'le="0.1"' in output
        assert 'le="1.0"' in output

    @pytest.mark.asyncio
    async def test_clear(self, registry):
        """Test clearing all metrics."""
        await registry.inc_counter("test", {"label": "value"})
        await registry.observe_histogram("duration", 0.5, {"label": "value"})

        await registry.clear()

        output = await registry.export_text()
        assert output == ""


class TestNoCardinalityLeak:
    """Tests to ensure no cardinality explosion with high-cardinality labels."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        MetricsRegistry.reset_instance()
        yield
        MetricsRegistry.reset_instance()

    @pytest.mark.asyncio
    async def test_session_id_not_used_as_tag(self):
        """Verify that session_id is not stored in metrics."""
        registry = MetricsRegistry.get_instance()

        await registry.inc_counter("test", {"session_id": "abc123"})
        await registry.inc_counter("test", {"session_id": "def456"})

        output = await registry.export_text()

        lines = output.split("\n")
        metric_lines = [l for l in lines if l.startswith("test{")]

        assert len(metric_lines) == 2

    @pytest.mark.asyncio
    async def test_trace_id_not_used_as_tag(self):
        """Verify that trace_id is not stored in metrics."""
        registry = MetricsRegistry.get_instance()

        await registry.inc_counter("test", {"trace_id": "trace-1"})
        await registry.inc_counter("test", {"trace_id": "trace-2"})

        output = await registry.export_text()

        lines = output.split("\n")
        metric_lines = [l for l in lines if l.startswith("test{")]

        assert len(metric_lines) == 2
