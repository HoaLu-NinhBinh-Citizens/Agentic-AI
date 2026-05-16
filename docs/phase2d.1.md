# Phase 2D.1: Observability Hardening & Security

**Status**: Implementation Complete
**Date**: 2026-05-16

## Overview

Phase 2D.1 addresses remaining weaknesses from Phase 2D implementation, focusing on security hardening and operational improvements for observability.

## Key Features

### 1. PII/Redaction Filter for Logs

Automatically masks sensitive fields in logged arguments.

**File**: `src/shared/logging.py`

```python
def redact_sensitive_data(obj, redacted_fields=None):
    """Redact sensitive fields from data structures."""
```

**Default Redacted Fields**:
- `password`, `token`, `secret`, `api_key`, `authorization`
- `private_key`, `access_token`, `refresh_token`, `session_token`
- `bearer`, `credential`, `passwd`, `pwd`

**Features**:
- Recursive scanning of nested dicts and lists
- Case-insensitive field matching
- Configurable via YAML
- Applied before JSON serialization

### 2. Rolling Time Window for Circuit Breaker

Replaces absolute failure counter with sliding window.

**File**: `src/infrastructure/resilience/circuit_breaker.py`

```python
class CircuitBreaker:
    def __init__(self, name, failure_threshold=5, window_seconds=60,
                 timeout_seconds=60, ...):
        self._failure_timestamps: deque = deque()
        self.window_seconds = window_seconds
```

**Features**:
- Sliding time window based on timestamps
- Automatic expiration of old failures
- More accurate error rate measurement
- Circuit resets when error rate drops below threshold

### 3. Log Rotation

Rotating log files to prevent disk overflow.

**File**: `src/shared/logging.py`

```python
import logging.handlers

def setup_logging(..., file_path=None, max_bytes=10*1024*1024, backup_count=5):
    """Configure logging with optional file rotation."""
    handler = logging.handlers.RotatingFileHandler(
        file_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
    )
```

**Features**:
- Size-based rotation (default 10MB)
- Configurable backup count (default 5)
- Automatic directory creation
- Console fallback when no file specified

### 4. Event Loop Health Check

Background monitoring for event loop responsiveness.

**File**: `src/infrastructure/observability/health.py`

```python
class EventLoopHealth:
    def __init__(self, max_lag_seconds=5.0):
        self._last_heartbeat = time.monotonic()
        asyncio.create_task(self._heartbeat())

    def is_alive(self) -> bool:
        lag = time.monotonic() - self._last_heartbeat
        return lag < self._max_lag
```

**Features**:
- Heartbeat updates every second
- Configurable max lag threshold (default 5s)
- Integrated into `/ready` endpoint
- Returns 503 if event loop stalled

### 5. Dynamic Log Level Endpoint

HTTP endpoint to change logging level at runtime.

**File**: `src/interfaces/server/api/admin.py`

```python
@router.post("/admin/loglevel")
async def change_log_level(level: str, token: str = Depends(verify_admin_token)):
    """Change logging level at runtime."""
    new_level = set_log_level(level_upper)
    return {"status": "ok", "level": new_level}
```

**Endpoints**:
- `POST /admin/loglevel` - Change log level
- `GET /admin/loglevel` - Get current level
- `GET /admin/status` - Admin API status

**Security**:
- Token-protected via `X-Admin-Token` header
- Token from `ADMIN_API_TOKEN` environment variable

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI Server                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ /health  │  │ /ready   │  │ /metrics │  │ /admin/* │      │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘      │
└─────────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────────────────────────────────────────────┐
│                    Event Loop Health Monitor                      │
│  - Heartbeat every 1 second                                      │
│  - Max lag check in /ready                                       │
└──────────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────────────────────────────────────────────┐
│                    Structured Logging (JSON)                      │
│  - Redaction filter                                             │
│  - Log rotation                                                 │
│  - Correlation IDs                                              │
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
    file: "./logs/ai_support.log"
    max_bytes: 10485760
    backup_count: 5
    redacted_fields:
      - password
      - token
      - secret
      - api_key
      - authorization
      - private_key
      - access_token
      - refresh_token

  health:
    readiness_check_interval_seconds: 30
    include_degraded_in_ready: true
    event_loop_max_lag_seconds: 5

  metrics:
    enabled: true
    endpoint: /metrics
    buckets: [0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]

  circuit_breaker:
    failure_threshold: 5
    window_seconds: 60
    timeout_seconds: 60
    transient_error_codes:
      - "MCP_ERROR"
      - "TIMEOUT"
      - "CONNECTION_REFUSED"
      - "CONNECTION_ERROR"

  admin:
    enabled: true
    token_env_var: ADMIN_API_TOKEN
```

## Component Map

| Component | File | Description |
|-----------|------|-------------|
| redact_sensitive_data | `src/shared/logging.py` | PII redaction |
| StructuredJsonFormatter | `src/shared/logging.py` | JSON logging with redaction |
| setup_logging | `src/shared/logging.py` | Log rotation setup |
| get_current_log_level | `src/shared/logging.py` | Get log level |
| set_log_level | `src/shared/logging.py` | Set log level |
| EventLoopHealth | `src/infrastructure/observability/health.py` | Loop monitoring |
| CircuitBreaker | `src/infrastructure/resilience/circuit_breaker.py` | Sliding window CB |
| admin router | `src/interfaces/server/api/admin.py` | Dynamic log level API |

## Testing

**Unit Tests**:
- `tests/integration/test_observability_pipeline.py` - 20 tests

**Test Coverage**:
- Redaction filter tests (5 tests)
- Circuit breaker sliding window tests (3 tests)
- Event loop health tests (2 tests)
- Dynamic log level tests (3 tests)
- Metrics integration tests (2 tests)
- Observability pipeline tests (3 tests)
- Health checker with event loop tests (2 tests)

## Definition of Done

- [x] Redaction filter masks configured fields in all JSON logs
- [x] Circuit breaker uses sliding time window (failure count over last window_seconds)
- [x] Log rotation enabled via configuration
- [x] /ready check includes event loop heartbeat; returns 503 if stalled
- [x] /admin/loglevel endpoint allows runtime log level change (token-protected)
- [x] Integration test for observability pipeline passes
- [x] All existing Phase 2D tests still pass (no regression)

## Non-Goals (Phase 3+)

- Persistent metrics storage
- OpenTelemetry / tracing
- Full PII detection using ML
- Distributed circuit breaker coordination
- External log aggregation configuration
- Full authentication/authorization

## Changes from Phase 2D

### Modified Files

1. **`src/shared/logging.py`**
   - Added `redact_sensitive_data()` function
   - Added `DEFAULT_REDACTED_FIELDS` constant
   - Updated `StructuredJsonFormatter` to apply redaction
   - Updated `setup_logging()` with rotation support
   - Added `get_current_log_level()` and `set_log_level()` functions

2. **`src/infrastructure/resilience/circuit_breaker.py`**
   - Added `window_seconds` parameter
   - Replaced `_failure_count` with `_failure_timestamps` deque
   - Added `_failure_count_in_window()` method
   - Renamed `timeout` to `timeout_seconds`

3. **`src/infrastructure/observability/health.py`**
   - Added `EventLoopHealth` class
   - Updated `HealthChecker` with event loop monitoring
   - Added `event_loop_healthy` and `event_loop_lag_seconds` to report

4. **`tests/unit/test_circuit_breaker.py`**
   - Updated parameter name from `timeout` to `timeout_seconds`

### New Files

1. **`src/interfaces/server/api/admin.py`**
   - Admin API endpoints for dynamic log level adjustment

2. **`tests/integration/test_observability_pipeline.py`**
   - Comprehensive observability pipeline tests

### Configuration Updates

- Added `file`, `max_bytes`, `backup_count` to logging
- Added `redacted_fields` to logging
- Added `event_loop_max_lag_seconds` to health
- Added `window_seconds` to circuit_breaker
- Added `admin` section with `enabled` and `token_env_var`
