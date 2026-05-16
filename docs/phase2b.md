# Phase 2B: Tool Execution Runtime

## Overview

Phase 2B builds on the MCP connectivity layer (Phase 2A) to enable actual tool execution. Clients can now invoke discovered MCP tools over WebSocket and receive structured results.

This phase establishes the foundation for all future execution features: cancellation, retry, streaming, distributed execution, and policy enforcement.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     WebSocket Handler (main.py)                   │
│  tool_call message → handle_tool_call() → ToolExecutionService   │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ToolExecutionService                          │
│  - Single entry point for tool execution                        │
│  - Handles orchestration and event broadcasting                 │
│  - Separates transport from execution logic                     │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                       ToolRegistry                               │
│  - Semaphore-based concurrency control                         │
│  - Timeout enforcement                                          │
│  - State machine transitions                                    │
└─────────────────────────────────────────────────────────────────┘
                    │                       │
                    ▼                       ▼
        ┌───────────────────┐   ┌───────────────────┐
        │   ToolTracker     │   │   ToolExecutor    │
        │  - Pending queue  │   │  - Abstract base  │
        │  - History        │   │  - MCP impl       │
        │  - Async lock     │   │  - Mock impl      │
        └───────────────────┘   └───────────────────┘
```

## State Machine

```
ToolCallState:

PENDING → RUNNING → COMPLETED (success)
                    ↘ FAILED (exception)
                    ↘ TIMED_OUT (timeout)

PENDING → CANCELLED (session deleted)

PENDING → ORPHANED (tracker closed without cleanup)
```

## Key Components

### 1. ToolCallState & ToolCallRecord (`src/domain/models/tool_call.py`)

State enum and record tracking for each tool call execution.

### 2. ToolTracker (`src/core/execution/tool_tracker.py`)

- Manages pending calls and execution history
- Async lock for thread safety
- Max history limit with FIFO eviction
- Orphan marking on close

### 3. ToolExecutor (`src/infrastructure/tool_execution/executor.py`)

- `ToolExecutor`: Abstract base class
- `MCPToolExecutor`: MCP implementation using MCPClientManager
- `MockToolExecutor`: For testing without real MCP

### 4. ToolRegistry (`src/core/agent/tool_registry.py`)

- Dispatch only (no business logic)
- Semaphore for concurrency control
- asyncio.wait_for for timeout
- Guaranteed cleanup via state transitions

### 5. ToolExecutionService (`src/application/orchestration/tool_execution/service.py`)

- Orchestration layer
- Broadcasts events: `tool_call_start`, `tool_call_result`, `tool_call_error`
- Session registry lookup
- Error normalization

## WebSocket Protocol

### Client → Server: tool_call

```json
{
  "type": "tool_call",
  "data": {
    "tool_name": "filesystem/read_file",
    "arguments": {"path": "/test.txt"},
    "call_id": "optional-custom-id",
    "trace_id": "optional-trace-id"
  }
}
```

### Server → Client: tool_call_start

```json
{
  "type": "tool_call_start",
  "data": {
    "call_id": "abc-123",
    "tool_name": "filesystem/read_file",
    "arguments": {"path": "/test.txt"},
    "trace_id": "trace-xyz"
  }
}
```

### Server → Client: tool_call_result

```json
{
  "type": "tool_call_result",
  "data": {
    "call_id": "abc-123",
    "tool_name": "filesystem/read_file",
    "content": [
      {"type": "text", "text": "file contents..."}
    ]
  }
}
```

### Server → Client: tool_call_error

```json
{
  "type": "tool_call_error",
  "data": {
    "call_id": "abc-123",
    "tool_name": "filesystem/read_file",
    "error": "Tool execution failed: ...",
    "code": "TOOL_NOT_FOUND"
  }
}
```

## Error Codes

| Code | Description |
|------|-------------|
| `TOOL_NOT_FOUND` | Requested tool doesn't exist |
| `TIMEOUT` | Tool execution exceeded timeout |
| `MCP_ERROR` | MCP server returned an error |
| `INVALID_ARGUMENTS` | Tool arguments validation failed |
| `TOO_MANY_CONCURRENT` | Concurrency limit exceeded |
| `SESSION_CLOSED` | Session was closed |
| `PERMISSION_DENIED` | Permission check failed |
| `INTERNAL_ERROR` | Unexpected internal error |

## Configuration

File: `configs/runtime/server.yaml`

```yaml
tool_execution:
  default_timeout_seconds: 30
  max_concurrent_tools_per_session: 5
  max_pending_calls_per_session: 20
  max_history_per_session: 100
  enable_trace_id: true
```

## Session Lifecycle Integration

On session creation:
1. Create `ToolTracker`
2. Create `MCPToolExecutor` (or `MockToolExecutor`)
3. Create `ToolRegistry`
4. Store in session manager

On session deletion:
1. Close `ToolRegistry` with `cancel_pending=True`
2. Mark pending calls as `CANCELLED`
3. Move records to history
4. Release all resources

## Testing

### Run All Phase 2B Tests

```bash
python -m pytest \
  tests/unit/test_tool_tracker.py \
  tests/unit/test_tool_executor.py \
  tests/unit/test_tool_registry.py \
  tests/unit/test_tool_call.py \
  tests/unit/test_tool_errors.py \
  tests/integration/test_phase2b_tool_execution.py \
  -v
```

### Run with Coverage

```bash
python -m pytest \
  tests/unit/test_tool_tracker.py \
  tests/unit/test_tool_executor.py \
  tests/unit/test_tool_registry.py \
  tests/unit/test_tool_call.py \
  tests/unit/test_tool_errors.py \
  tests/integration/test_phase2b_tool_execution.py \
  --cov=src \
  --cov-report=term-missing
```

## Logical Cancellation Debt

Phase 2B implements only **logical cancellation** - setting the state to `CANCELLED` does not abort the underlying MCP execution. The MCP subprocess or tool may continue running until completion.

True cancellation (ability to abort in-flight tool calls) is scheduled for Phase 2C. See [docs/adr/003-cancellation-debt.md](adr/003-cancellation-debt.md) for full documentation.

## Definition of Done

- [x] ToolCallState enum and ToolCallRecord dataclass implemented
- [x] ToolTracker manages pending/history with async lock
- [x] MCPToolExecutor calls MCPClientManager.call_tool()
- [x] ToolRegistry uses asyncio.Semaphore for concurrency control
- [x] ToolExecutionService handles orchestration; WebSocket handler is thin
- [x] Session deletion cancels pending calls (state → CANCELLED)
- [x] All tool calls have guaranteed cleanup via state transitions
- [x] Backpressure: configurable max_pending_calls (reject if exceeded)
- [x] Error normalization converts any exception to (code, message)
- [x] Security stub and trace_id fields present
- [x] All unit + integration tests pass (63 tests)
- [x] Code coverage ≥ 80% for Phase 2B modules
- [x] Architecture layer boundary tests pass
- [x] Documentation and ADR complete

## Non-Goals (Explicitly NOT in Phase 2B)

| Category | What NOT to implement |
|----------|----------------------|
| Cancellation | No cancel_tool message (Phase 2C) |
| Retry | No automatic retry (Phase 2C) |
| Streaming | No partial result streaming (Phase 3+) |
| Tool queuing | No queue beyond backpressure (Phase 2C) |
| Routing | No multi-server load balancing (Phase 2C) |
| Persistence | No saving tool history to DB (Phase 3) |
| Security | Only stub interfaces (Phase 3) |
| Distributed | No remote workers (Phase 9) |
