# ADR-003: Logical Cancellation Debt

## Status

Accepted (Documented Debt)

## Context

Phase 2B implements tool execution runtime with state management for tool calls. During the design review, we identified that true cancellation (ability to abort in-flight tool executions) requires more complex infrastructure than initially scoped.

### What We Implemented

Phase 2B implements **logical cancellation** - the ability to mark a tool call as `CANCELLED` in the state machine:

```
PENDING → CANCELLED
RUNNING → CANCELLED
```

When a session is deleted or `ToolRegistry.close()` is called:
1. All pending calls are marked as `CANCELLED`
2. Their state transitions to terminal `CANCELLED` state
3. They are moved to history

### The Problem

The current implementation **does not abort the underlying MCP execution**. Consider this scenario:

```
Timeline:
T0: Client sends tool_call message
T1: Tool call starts execution (state → RUNNING)
T2: Client disconnects / session deleted
T3: Tool call state → CANCELLED (logical cancellation)
T4: Underlying MCP tool continues running...
T5: MCP tool completes (but state is already CANCELLED)
```

The MCP subprocess or tool may continue running until natural completion, even after we've marked the state as `CANCELLED`.

### Why This Is Acceptable Debt

1. **Non-critical for Phase 2B scope**: Phase 2B focuses on correct state management and execution foundations, not true cancellation.

2. **Low practical impact**: In most cases, MCP tool calls are I/O-bound (file system, HTTP requests) that complete quickly.

3. **Diagnostic value**: The `CANCELLED` state still provides valuable information about client intent and session lifecycle.

4. **Future extensibility**: The state machine is designed to support true cancellation when implemented.

## Decision

We accept this debt and document it for Phase 2C.

### Phase 2B Behavior

| Action | Result |
|--------|--------|
| Session deleted while tool is PENDING | State → CANCELLED immediately |
| Session deleted while tool is RUNNING | State → CANCELLED; MCP execution continues |
| `ToolRegistry.close()` called | All pending calls → CANCELLED |
| Client disconnects | Same as session deleted |

### What Phase 2C Should Implement

True cancellation requires:

1. **Cancellation token propagation**: Pass cancellation tokens through the execution chain
2. **MCP protocol support**: Use MCP protocol's cancellation mechanism (if available)
3. **Timeout per call**: Allow per-call timeout override
4. **Force kill option**: Ability to forcefully terminate long-running calls

## Consequences

### Positive

- Phase 2B scope is manageable and well-defined
- State machine correctly tracks intended vs actual outcomes
- Clear documentation for developers

### Negative

- Resource waste: Cancelled tool calls may continue using resources
- Confusion: State says CANCELLED but execution may have completed
- Requires Phase 2C work to fully resolve

## References

- Phase 2B specification
- Python asyncio cancellation patterns
- MCP protocol cancellation (future)

## Related Debt

This is one of several items deferred to Phase 2C or later:

| Item | Phase | Notes |
|------|-------|-------|
| True cancellation | 2C | Abort in-flight executions |
| Retry | 2C | Automatic retry with backoff |
| Tool queuing policy | 2C | Priority queue beyond backpressure |
| Multi-server routing | 2C | Load balancing across MCP servers |
| Persistence | 3 | Save tool history to database |
| Full security | 3 | Policy engine, permissions |
| Streaming results | 3+ | Partial result streaming |
| Distributed execution | 9 | Remote workers |
