"""
Tests for Observability Module

Tests StructuredLogger, ConfigManager, Prometheus metrics.
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.observability import (
    StructuredLogger,
    LogContext,
    LogAggregator,
    LogLevel,
    LogFormat,
    get_logger,
    ConfigManager,
    MetricsCollector,
    Counter,
    Gauge,
    Histogram,
)


# =============================================================================
# StructuredLogger Tests
# =============================================================================

class TestLogLevel:
    """Test LogLevel enum."""

    def test_log_levels_exist(self):
        """Test log levels exist."""
        assert LogLevel.DEBUG.value == 10
        assert LogLevel.INFO.value == 20
        assert LogLevel.WARNING.value == 30
        assert LogLevel.ERROR.value == 40
        assert LogLevel.CRITICAL.value == 50


class TestStructuredLogger:
    """Test StructuredLogger functionality."""

    @pytest.fixture
    def logger(self):
        """Create a test logger."""
        return StructuredLogger(
            name="test_logger",
            level=LogLevel.DEBUG,
            format=LogFormat.JSON,
        )

    def test_logger_initialization(self, logger):
        """Test logger initializes correctly."""
        assert logger.name == "test_logger"
        assert logger.level == LogLevel.DEBUG
        assert logger.format == LogFormat.JSON

    def test_set_level(self, logger):
        """Test setting log level."""
        logger.set_level(LogLevel.WARNING)
        assert logger.level == LogLevel.WARNING

    def test_set_trace_id(self, logger):
        """Test setting trace ID."""
        trace_id = logger.set_trace_id("test-trace-123")
        assert trace_id == "test-trace-123"
        assert logger.get_trace_id() == "test-trace-123"

    def test_auto_generate_trace_id(self, logger):
        """Test auto-generation of trace ID."""
        trace_id = logger.set_trace_id()
        assert trace_id is not None
        assert len(trace_id) == 16  # UUID truncated

    def test_set_session_id(self, logger):
        """Test setting session ID."""
        session_id = logger.set_session_id("session-456")
        assert session_id == "session-456"
        assert logger.session_id == "session-456"

    def test_set_request_id(self, logger):
        """Test setting request ID."""
        request_id = logger.set_request_id("request-789")
        assert request_id == "request-789"
        assert logger.request_id == "request-789"

    def test_clear_context(self, logger):
        """Test clearing context."""
        logger.set_trace_id("test")
        logger.set_session_id("session")
        logger.set_request_id("request")

        logger.clear_context()

        assert logger.get_trace_id() is None
        assert logger.session_id is None
        assert logger.request_id is None

    def test_get_logger_function(self):
        """Test get_logger convenience function."""
        logger = get_logger("test_module")
        assert isinstance(logger, StructuredLogger)
        assert logger.name == "test_module"


class TestLogContext:
    """Test LogContext manager."""

    @pytest.fixture
    def logger(self):
        """Create a test logger."""
        return StructuredLogger(name="test", level=LogLevel.DEBUG)

    def test_context_enters(self, logger):
        """Test context manager enters."""
        ctx = LogContext(logger, trace_id="ctx-trace")
        assert ctx.trace_id == "ctx-trace"

    def test_context_sets_ids(self, logger):
        """Test context manager sets IDs on enter."""
        logger.set_trace_id("original")
        with LogContext(logger, trace_id="ctx-trace") as ctx:
            assert logger.get_trace_id() == "ctx-trace"

    def test_context_restores_ids(self, logger):
        """Test context manager restores previous IDs on exit."""
        logger.set_trace_id("original")
        with LogContext(logger, trace_id="ctx-trace"):
            pass
        assert logger.get_trace_id() == "original"


class TestLogAggregator:
    """Test LogAggregator."""

    def test_aggregator_initialization(self):
        """Test aggregator initializes correctly."""
        agg = LogAggregator(max_size=100)
        assert agg.max_size == 100
        assert len(agg) == 0

    def test_add_log(self):
        """Test adding logs to aggregator."""
        agg = LogAggregator(max_size=10)
        agg.add_log({"level": "info", "message": "test"})
        assert len(agg) == 1

    def test_flush(self):
        """Test flushing aggregator."""
        flushed = []

        agg = LogAggregator(max_size=10)
        agg.on_flush(lambda logs: flushed.extend(logs))

        agg.add_log({"level": "info", "message": "test1"})
        agg.add_log({"level": "info", "message": "test2"})
        agg.flush()

        assert len(flushed) == 2
        assert len(agg) == 0


# =============================================================================
# ConfigManager Tests
# =============================================================================

class TestConfigSource:
    """Test ConfigSource dataclass."""

    def test_source_creation(self):
        """Test creating a config source."""
        from src.observability import ConfigSource

        source = ConfigSource(
            name="test.yaml",
            path=Path("test.yaml"),
            priority=10,
        )
        assert source.name == "test.yaml"
        assert source.priority == 10


class TestConfigManager:
    """Test ConfigManager functionality."""

    @pytest.fixture
    def config(self):
        """Create a test config manager."""
        return ConfigManager()

    def test_config_initialization(self, config):
        """Test config initializes correctly."""
        assert config.env_prefix == "AI_SUPPORT_"
        assert isinstance(config._config, dict)

    def test_get_default(self, config):
        """Test getting default value."""
        value = config.get("nonexistent", "default")
        assert value == "default"

    def test_set_get(self, config):
        """Test setting and getting values."""
        config.set("database.host", "localhost")
        assert config.get("database.host") == "localhost"

    def test_nested_keys(self, config):
        """Test nested key access."""
        config.set("section.nested.value", 42)
        assert config.get("section.nested.value") == 42

    def test_delete(self, config):
        """Test deleting keys."""
        config.set("test.key", "value")
        assert config.get("test.key") == "value"

        result = config.delete("test.key")
        assert result is True
        assert config.get("test.key") is None

    def test_load_dict(self, config):
        """Test loading from dictionary."""
        data = {
            "database": {
                "host": "localhost",
                "port": 5432,
            },
            "debug": True,
        }
        config.load_dict(data, name="test_dict")

        assert config.get("database.host") == "localhost"
        assert config.get("database.port") == 5432
        assert config.get("debug") is True

    def test_keys(self, config):
        """Test getting all keys."""
        config.set("a.b.c", 1)
        config.set("a.b.d", 2)
        config.set("x.y", 3)

        keys = config.keys()
        assert "a.b.c" in keys
        assert "a.b.d" in keys
        assert "x.y" in keys

    def test_keys_with_prefix(self, config):
        """Test getting keys with prefix."""
        config.set("a.b.c", 1)
        config.set("x.y", 2)

        keys = config.keys(prefix="a")
        assert "a.b.c" in keys
        assert "x.y" not in keys

    def test_get_section(self, config):
        """Test getting entire section."""
        config.set("database.host", "localhost")
        config.set("database.port", 5432)

        section = config.get_section("database")
        assert section["host"] == "localhost"
        assert section["port"] == 5432

    def test_to_dict(self, config):
        """Test converting to dictionary."""
        config.set("a.b.c", 1)
        config_dict = config.to_dict()

        assert isinstance(config_dict, dict)
        assert config_dict["a"]["b"]["c"] == 1

    def test_on_change_callback(self, config):
        """Test change callbacks."""
        changes = []

        def on_change(change):
            changes.append(change)

        config.on_change(on_change)
        config.set("test.key", "value")

        assert len(changes) == 1
        assert changes[0].key == "test.key"
        assert changes[0].new_value == "value"

    def test_get_changes(self, config):
        """Test getting configuration changes."""
        before = datetime.now()
        config.set("key1", "value1")
        config.set("key2", "value2")

        changes = config.get_changes(since=before)
        assert len(changes) == 2
        assert changes[0].key == "key1"
        assert changes[1].key == "key2"

    @pytest.fixture
    def yaml_file(self, tmp_path):
        """Create a temporary YAML file."""
        yaml_path = tmp_path / "test_config.yaml"
        yaml_content = """
database:
  host: localhost
  port: 5432
  name: testdb

debug: true
timeout: 30
"""
        yaml_path.write_text(yaml_content)
        return yaml_path

    def test_load_yaml(self, config, yaml_file):
        """Test loading YAML file."""
        result = config.load_yaml(yaml_file)
        assert result is True
        assert config.get("database.host") == "localhost"
        assert config.get("database.port") == 5432
        assert config.get("debug") is True

    @pytest.fixture
    def json_file(self, tmp_path):
        """Create a temporary JSON file."""
        json_path = tmp_path / "test_config.json"
        json_data = {
            "server": {
                "host": "0.0.0.0",
                "port": 8080,
            },
            "logging": {
                "level": "info",
            },
        }
        json_path.write_text(json.dumps(json_data, indent=2))
        return json_path

    def test_load_json(self, config, json_file):
        """Test loading JSON file."""
        result = config.load_json(json_file)
        assert result is True
        assert config.get("server.host") == "0.0.0.0"
        assert config.get("server.port") == 8080

    def test_save_yaml(self, config, tmp_path):
        """Test saving to YAML."""
        config.set("test.key", "value")
        save_path = tmp_path / "saved.yaml"

        result = config.save(save_path, format="yaml")
        assert result is True
        assert save_path.exists()

    def test_save_json(self, config, tmp_path):
        """Test saving to JSON."""
        config.set("test.key", "value")
        save_path = tmp_path / "saved.json"

        result = config.save(save_path, format="json")
        assert result is True
        assert save_path.exists()


# =============================================================================
# Prometheus Metrics Tests
# =============================================================================

class TestMetricTypes:
    """Test metric type enums."""

    def test_metric_types_exist(self):
        """Test metric types exist."""
        from src.observability.prometheus_metrics import MetricType

        assert MetricType.COUNTER.value == "counter"
        assert MetricType.GAUGE.value == "gauge"
        assert MetricType.HISTOGRAM.value == "histogram"
        assert MetricType.SUMMARY.value == "summary"


class TestCounter:
    """Test Counter metric."""

    def test_counter_initialization(self):
        """Test counter initializes correctly."""
        counter = Counter("test_counter", "A test counter")
        assert counter._name == "test_counter"
        assert counter._total == 0.0

    def test_counter_inc(self):
        """Test counter increment."""
        counter = Counter("test_counter", "A test counter")
        counter.inc()
        assert counter.get() == 1.0

    def test_counter_inc_amount(self):
        """Test counter increment by amount."""
        counter = Counter("test_counter", "A test counter")
        counter.inc(5)
        assert counter.get() == 5.0

    def test_counter_multiple_inc(self):
        """Test multiple increments."""
        counter = Counter("test_counter", "A test counter")
        counter.inc()
        counter.inc()
        counter.inc(5)
        assert counter.get() == 7.0

    def test_counter_with_labels(self):
        """Test counter with labels."""
        counter = Counter("test_counter", "A test counter", labels=("method", "status"))
        counter.inc(method="GET", status="200")
        counter.inc(method="POST", status="201")

        assert counter.get(method="GET", status="200") == 1.0
        assert counter.get(method="POST", status="201") == 1.0
        assert counter.get(method="GET", status="404") == 0.0

    def test_counter_collect(self):
        """Test counter collection."""
        counter = Counter("test_counter", "A test counter")
        counter.inc(10)

        metric = counter.collect()
        assert metric.name == "test_counter"
        assert len(metric.samples) == 1
        assert metric.samples[0].value == 10.0


class TestGauge:
    """Test Gauge metric."""

    def test_gauge_initialization(self):
        """Test gauge initializes correctly."""
        gauge = Gauge("test_gauge", "A test gauge")
        assert gauge._name == "test_gauge"

    def test_gauge_set(self):
        """Test gauge set."""
        gauge = Gauge("test_gauge", "A test gauge")
        gauge.set(42.5)
        assert gauge.get() == 42.5

    def test_gauge_inc(self):
        """Test gauge increment."""
        gauge = Gauge("test_gauge", "A test gauge")
        gauge.inc()
        assert gauge.get() == 1.0

    def test_gauge_dec(self):
        """Test gauge decrement."""
        gauge = Gauge("test_gauge", "A test gauge")
        gauge.set(10)
        gauge.dec(3)
        assert gauge.get() == 7.0


class TestHistogram:
    """Test Histogram metric."""

    def test_histogram_initialization(self):
        """Test histogram initializes correctly."""
        hist = Histogram("test_histogram", "A test histogram")
        assert hist._name == "test_histogram"
        assert len(hist._buckets) > 0

    def test_histogram_observe(self):
        """Test histogram observation."""
        hist = Histogram("test_histogram", "A test histogram")
        hist.observe(0.05)
        hist.observe(0.1)
        hist.observe(0.5)

        metric = hist.collect()[0]
        assert metric.metric_type.value == "histogram"

    def test_histogram_custom_buckets(self):
        """Test histogram with custom buckets."""
        buckets = [0.1, 0.5, 1.0, 5.0]
        hist = Histogram("test_histogram", "A test histogram", buckets=buckets)
        assert hist._buckets == buckets


class TestMetricsCollector:
    """Test MetricsCollector."""

    @pytest.fixture
    def collector(self):
        """Create a test collector."""
        return MetricsCollector(namespace="test")

    def test_collector_initialization(self, collector):
        """Test collector initializes correctly."""
        assert collector.namespace == "test"

    def test_create_counter(self, collector):
        """Test creating a counter."""
        counter = collector.counter("requests", "Total requests")
        assert counter is not None
        assert isinstance(counter, Counter)

    def test_create_gauge(self, collector):
        """Test creating a gauge."""
        gauge = collector.gauge("memory_usage", "Memory usage in MB")
        assert gauge is not None
        assert isinstance(gauge, Gauge)

    def test_create_histogram(self, collector):
        """Test creating a histogram."""
        hist = collector.histogram("request_duration", "Request duration in seconds")
        assert hist is not None
        assert isinstance(hist, Histogram)

    def test_full_name(self, collector):
        """Test full metric name with namespace."""
        assert collector._full_name("test_metric") == "test_test_metric"

    def test_collect(self, collector):
        """Test collecting all metrics."""
        counter = collector.counter("test_counter", "Test counter")
        counter.inc()

        metrics = collector.collect()
        assert len(metrics) >= 1

    def test_to_prometheus_format(self, collector):
        """Test Prometheus format export."""
        counter = collector.counter("test_counter", "Test counter")
        counter.inc(5)

        output = collector.to_prometheus_format()
        assert "test_test_counter" in output
        assert "# HELP" in output
        assert "# TYPE" in output

    def test_to_json(self, collector):
        """Test JSON export."""
        counter = collector.counter("test_counter", "Test counter")
        counter.inc()

        output = collector.to_json()
        assert isinstance(output, list)
        assert len(output) >= 1


class TestTimer:
    """Test Timer context manager."""

    def test_timer_timing(self):
        """Test timer measures elapsed time."""
        from src.observability import Timer

        hist = Histogram("test_duration", "Test duration")
        hist.observe(0.001)  # Small value

        with Timer(hist):
            pass  # Should record 0 duration

        metric = hist.collect()[0]
        assert metric.metric_type.value == "histogram"


class TestGetMetrics:
    """Test global metrics getter."""

    def test_get_metrics_returns_collector(self):
        """Test get_metrics returns MetricsCollector."""
        from src.observability import get_metrics

        metrics = get_metrics()
        assert isinstance(metrics, MetricsCollector)
