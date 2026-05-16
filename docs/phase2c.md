# Phase 2C: Reliability & Policy Layer

## Overview

Phase 2C builds on the tool execution runtime (Phase 2B) to create a reliable, policy-driven platform. It adds true cancellation, retry policies, rate limiting, and a configurable middleware pipeline.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     WebSocket Handler (main.py)                     │
│  tool_call message → handle_tool_call() → ToolExecutionService     │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Middleware Pipeline (Phase 2C)                     │
│  OwnershipMiddleware → RateLimitMiddleware → RetryMiddleware          │
│  → CancellationMiddleware → AuditMiddleware                           │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    ToolExecutionService                              │
│  - Single entry point for tool execution                           │
│  - Middleware pipeline integration                                  │
│  - Cancellation by call_id support                                  │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       ToolRegistry                                   │
│  - Semaphore-based concurrency control                             │
│  - Cancellation token propagation                                    │
│  - cancel_call() for true cancellation                             │
└─────────────────────────────────────────────────────────────────────┘
                    │                       │
                    ▼                       ▼
        ┌───────────────────┐   ┌───────────────────┐
        │   ToolTracker     │   │   ToolExecutor    │
        │  - State machine  │   │  - Abstract base  │
        │  - Cancellation   │   │  - MCP impl       │
        │    tokens         │   │  - Capabilities   │
        └───────────────────┘   └───────────────────┘
```

## New Components

### 1. CancellationToken (`src/core/execution/cancellation.py`)

Cooperative cancellation for async operations.

```python
from core.execution.cancellation import CancellationToken

token = CancellationToken()

# In executing code:
if token.is_cancelled:
    raise asyncio.CancelledError()

# Or wait for cancellation:
await token.wait()

# To cancel:
token.cancel()
```

### 2. ProcessHandle (`src/core/execution/cancellation.py`)

Abstraction for subprocess termination.

```python
from core.execution.cancellation import ProcessHandle, SubprocessHandle

# For asyncio subprocesses:
process = await asyncio.create_subprocess_exec(...)
handle = SubprocessHandle(process)
await handle.terminate()  # Graceful shutdown
await asyncio.sleep(0.1)
await handle.kill()       # Force kill
```

### 3. ExecutionRequest (`src/domain/models/execution.py`)

Mutable request object flowing through middleware.

```python
from domain.models.execution import ExecutionRequest, ExecutionContext

context = ExecutionContext(
    session_id="session-123",
    trace_id="trace-456",
    client_id="client-789",
)

request = ExecutionRequest(
    call_id="call-abc",
    tool_name="filesystem/read_file",
    arguments={"path": "/test.txt"},
    context=context,
)
```

### 4. Middleware Pipeline (`src/application/orchestration/tool_execution/middleware.py`)

Configurable middleware chain.

```python
from application.orchestration.tool_execution.middleware import (
    Pipeline,
    OwnershipMiddleware,
    RateLimitMiddleware,
    RetryMiddleware,
    CancellationMiddleware,
    AuditMiddleware,
)

# Default order:
pipeline = Pipeline([
    OwnershipMiddleware(),
    RateLimitMiddleware(rules),
    RetryMiddleware(max_attempts=3, jitter_factor=0.1),
    CancellationMiddleware(),
    AuditMiddleware(),
])

result = await pipeline.execute(request, final_handler)
```

### 5. RetryMiddleware

Exponential backoff with jitter, cancellation-aware.

```python
retry = RetryMiddleware(
    max_attempts=3,
    base_delay=1.0,
    max_delay=30.0,
    retryable_codes=["MCP_ERROR", "TIMEOUT"],
    jitter_factor=0.1,
)
```

### 6. RateLimitMiddleware

Sliding window rate limiting (in-memory).

```python
from dataclasses import dataclass

@dataclass
class RateLimitRules:
    per_session: RateLimitConfig = field(
        default_factory=lambda: RateLimitConfig(calls=10, period=60.0)
    )
    per_tool: dict[str, RateLimitConfig] = field(default_factory=dict)
```

## Key Features

### True Cancellation

```python
# Cancel a running call
success, message = await service.cancel_tool(
    session_id="session-123",
    call_id="call-abc",
    client_id="client-789",
)
```

### Ownership Verification

Only the initiating client can cancel their own calls:

```python
pending_record = await registry._tracker.get_pending_record(call_id)
if pending_record.client_id != client_id:
    return False, "Only the initiating client can cancel"
```

### Graceful Shutdown

Session deletion with configurable grace period:

```python
await session_manager.delete_session(
    session_id="session-123",
    grace_period=2.0,  # Wait 2s before force cleanup
)
```

## Configuration

### `configs/runtime/server.yaml`

```yaml
tool_execution:
  default_timeout_seconds: 30
  max_concurrent_tools_per_session: 5
  max_pending_calls_per_session: 20
  max_history_per_session: 100
  enable_trace_id: true

  retry:
    max_attempts: 3
    base_delay_seconds: 1.0
    max_delay_seconds: 30.0
    retryable_codes:
      - "MCP_ERROR"
      - "TIMEOUT"
    jitter_factor: 0.1

  rate_limits:
    per_session:
      calls: 10
      period: 60
    per_tool:
      "filesystem/read_file":
        calls: 30
        period: 60

  cancellation:
    grace_period_seconds: 2.0

  middleware_order:
    - "ownership"
    - "rate_limit"
    - "retry"
    - "cancellation"
    - "audit"
```

## Known Limitations

| Limitation | Impact | Future Phase |
|------------|--------|--------------|
| ExecutionRequest is mutable | Low | Phase 3 may introduce copy-on-write |
| Grace period uses asyncio.sleep | Low | Phase 2D may add task-aware waiting |
| Rate limiter state is in-memory | Medium | Phase 3 may add persistence |
| Retry does not enforce idempotency | Medium | Phase 3 may add idempotency keys |
| Cancellation is best-effort | High (documented) | Phase 2D may add watchdog |
| Capability model is metadata only | Low | Phase 3+ may use for scheduling |

See [docs/adr/004-cancellation-debt.md](adr/004-cancellation-debt.md) and [docs/adr/005-retry-idempotency.md](adr/005-retry-idempotency.md) for full documentation.

## Testing

### Run All Phase 2C Tests

```bash
python -m pytest \
  tests/unit/test_cancellation.py \
  tests/unit/test_middleware.py \
  tests/unit/test_rate_limiter.py \
  tests/unit/test_retry_middleware.py \
  tests/integration/test_phase2c_reliability.py \
  -v
```

### Run with Coverage

```bash
python -m pytest \
  tests/unit/test_cancellation.py \
  tests/unit/test_middleware.py \
  tests/unit/test_rate_limiter.py \
  tests/unit/test_retry_middleware.py \
  tests/integration/test_phase2c_reliability.py \
  --cov=src \
  --cov-report=term-missing
```

## Definition of Done

- [x] Unified ExecutionContext and ExecutionRequest used throughout pipeline
- [x] Cancellation by call_id works; client can cancel its own calls (best-effort)
- [x] Retry middleware is cancellation-aware, includes jitter, stops on token cancel
- [x] Rate limiting middleware enforces per-session and per-tool limits (in-memory)
- [x] Middleware pipeline order configurable; default order as recommended
- [x] Atomic transitions prevent race between completion and cancellation
- [x] Session deletion cancels all pending calls with configurable grace period
- [x] ProcessHandle abstraction for subprocess management
- [x] All tests pass; coverage ≥ 80%
- [x] Documentation includes known limitations

## Non-Goals (Explicitly NOT in Phase 2C)

| Category | What NOT to implement |
|----------|----------------------|
| Durable execution log | No saving to database (Phase 3) |
| Worker isolation | No container sandbox (Phase 4+) |
| Distributed execution | No remote workers (Phase 9) |
| Advanced scheduling | Only simple semaphore (Phase 3+) |
| Full authentication | Only ownership and rate limits |
| Production circuit breakers | Added later |
