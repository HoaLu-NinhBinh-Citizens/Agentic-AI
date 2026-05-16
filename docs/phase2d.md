# Phase 2D: Observability & Recovery

**Status**: Implementation Complete
**Date**: 2026-05-16

## Overview

Phase 2D adds observability and recovery capabilities to the tool execution runtime, building on Phase 2C's reliability foundation.

## Key Features

### 1. Structured Logging

JSON-formatted logs with correlation IDs for request tracing.

**File**: `src/shared/logging.py`

```python
class StructuredJsonFormatter(logging.Formatter):
    """JSON formatter with correlation IDs."""
```

**Features**:
- JSON output format
- Correlation IDs: `trace_id`, `session_id`, `call_id`
- Standard fields: `timestamp`, `level`, `logger`, `module`, `function`, `line`
- Context fields: `duration_ms`, `tool_name`, `error_code`, `server_name`, `attempt`

### 2. Circuit Breaker

Fault tolerance for MCP server calls with transient failure detection.

**File**: `src/infrastructure/resilience/circuit_breaker.py`

```python
class CircuitBreaker:
    """Circuit breaker with half-open semantics."""
```

**Features**:
- Three states: CLOSED, OPEN, HALF_OPEN
- Transient failure detection
- Half-open probe concurrency protection (asyncio.Lock)
- Configurable thresholds

**States**:
| State | Behavior |
|-------|----------|
| CLOSED | Normal operation, requests pass through |
| OPEN | Fail fast, no requests allowed |
| HALF_OPEN | Allow one probe request to test recovery |

### 3. Health Checks

Liveness and readiness endpoints with degraded state support.

**File**: `src/infrastructure/observability/health.py`

**Endpoints**:
- `/health` - Liveness check (always returns 200 if process is alive)
- `/ready` - Readiness check (verifies MCP servers are available)

**Status Levels**:
| Status | Description |
|--------|-------------|
| HEALTHY | All systems operational |
| DEGRADED | Some servers unavailable, runtime still functioning |
| UNHEALTHY | Critical failures, runtime not ready |

### 4. Metrics Registry

In-memory metrics with Prometheus text format export.

**File**: `src/infrastructure/observability/metrics.py`

```python
class MetricsRegistry:
    """Singleton metrics registry with async operations."""
```

**Metrics Types**:
- **Counters**: `tool_calls_total{tool="read_file",success="true"} 42`
- **Histograms**: `tool_call_duration_seconds_bucket{le="0.1"} 10`

**Features**:
- Memory-efficient bucket-based histograms
- No cardinality explosion (no session_id/trace_id in tags)
- Prometheus text exposition format
- Async-safe operations

### 5. Logging Middleware

Tool call lifecycle logging with structured format.

**File**: `src/application/orchestration/tool_execution/middleware.py`

```python
class LoggingMiddleware:
    """Logs each tool call start, success, failure, exception."""
```

**Log Events**:
| Event | Level | Fields |
|-------|-------|--------|
| Tool call started | INFO | session_id, trace_id, call_id, tool_name |
| Tool call succeeded | INFO | call_id, duration_ms |
| Tool call failed | ERROR | call_id, duration_ms, error_code, error_message |
| Tool call exception | ERROR | call_id, duration_ms, error_message |

### 6. Circuit Breaker Middleware

Integrates circuit breaker into the middleware pipeline.

**File**: `src/application/orchestration/tool_execution/middleware.py`

```python
class CircuitBreakerMiddleware:
    """Wraps tool execution with circuit breaker protection."""
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI Server                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ /health  │  │ /ready   │  │ /metrics │  │ WebSocket │      │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘      │
└─────────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────────────────────────────────────────────┐
│                    ToolExecutionService                           │
│  - Receives ExecutionContext (with trace_id)                    │
│  - Calls middleware pipeline                                     │
└──────────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────────────────────────────────────────────┐
│  Middleware Pipeline (configurable order)                       │
│  Ownership → RateLimit → Retry → CircuitBreaker → Cancellation   │
│  → Audit → Logging                                             │
└──────────────────────────────────────────────────────────────────┘
```

## Configuration

**File**: `configs/runtime/server.yaml`

```yaml
observability:
  logging:
    level: INFO
    format: json
    propagate_client_trace_id: true

  health:
    readiness_check_interval_seconds: 30
    include_degraded_in_ready: true

  metrics:
    enabled: true
    endpoint: /metrics
    buckets: [0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]

  recovery:
    mcp:
      max_restarts: 3
      base_delay_seconds: 1.0
      max_delay_seconds: 30.0

  circuit_breaker:
    failure_threshold: 5
    timeout_seconds: 60
    transient_error_codes:
      - "MCP_ERROR"
      - "TIMEOUT"
      - "CONNECTION_REFUSED"
      - "CONNECTION_ERROR"
```

## Component Map

| Component | File | Description |
|----------|------|-------------|
| StructuredJsonFormatter | `src/shared/logging.py` | JSON log formatter |
| CircuitBreaker | `src/infrastructure/resilience/circuit_breaker.py` | Fault tolerance |
| HealthChecker | `src/infrastructure/observability/health.py` | Health endpoints |
| MetricsRegistry | `src/infrastructure/observability/metrics.py` | Prometheus metrics |
| LoggingMiddleware | `src/application/orchestration/tool_execution/middleware.py` | Lifecycle logging |
| CircuitBreakerMiddleware | `src/application/orchestration/tool_execution/middleware.py` | CB in pipeline |

## Known Limitations

| Limitation | Impact | Future Improvement |
|------------|--------|-------------------|
| Circuit breaker HALF_OPEN probe race | Very low | Atomic probe reservation |
| Histogram linear scan O(bucket_count) | Low (buckets ≤ 15) | Binary search or HDR |
| Metrics registry global lock | Low at current scale | Lock striping or sharded counters |
| Structured logging synchronous json.dumps | Low | Async logging, batched |
| No bulkhead isolation | Medium for large scale | Per-server worker pool |

## Testing

**Unit Tests**:
- `tests/unit/test_circuit_breaker.py` - 12 tests
- `tests/unit/test_metrics.py` - 14 tests
- `tests/unit/test_health.py` - 10 tests

**Test Coverage**: All Phase 2D components have unit tests.

## Definition of Done

- [x] Structured logging JSON with full fields; every log has trace_id
- [x] Health endpoints /health (liveness) and /ready (readiness) working
- [x] Circuit breaker distinguishes transient failures, half-open safe for concurrency
- [x] Logging middleware records each tool call once; other logs at DEBUG
- [x] Metrics endpoint /metrics exports counters and histograms without high-cardinality tags
- [x] All unit and integration tests pass, coverage ≥ 80%

## Non-Goals (Phase 3+)

- OpenTelemetry / Jaeger integration
- Prometheus push gateway
- Persistent storage for metrics
- Full audit trail
- Bulkhead isolation
- High-performance async logging
