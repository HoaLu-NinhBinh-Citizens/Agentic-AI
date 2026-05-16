# ADR-004: Best-Effort Cancellation (Phase 2C)

## Status

Accepted

## Context

Phase 2C implements true cancellation with cancellation tokens that propagate through the execution chain. However, due to platform limitations (especially on Windows), cancellation is best-effort rather than guaranteed.

### What We Implemented

Phase 2C provides cooperative cancellation:

1. **CancellationToken**: Async event-based token that can be checked and waited on
2. **ProcessHandle**: Abstraction for subprocess termination with terminate() and kill()
3. **cancel_call()**: Registry method that cancels tokens and terminates processes
4. **Middleware integration**: CancellationMiddleware ensures tokens exist on requests

### The Limitation

Despite our best efforts, cancellation is **best-effort** for several reasons:

1. **Windows subprocess behavior**: Windows processes may ignore termination signals
2. **External tool calls**: MCP tools may call external processes beyond our control
3. **Network I/O**: TCP connections don't have clean cancellation semantics
4. **Resource cleanup**: Some resources require deterministic cleanup that async can't guarantee

### Scenarios

| Scenario | Behavior |
|----------|----------|
| Cancel during PENDING | Immediate CANCELLED state |
| Cancel during RUNNING | Token cancelled, process terminated (best-effort) |
| Subprocess ignores SIGTERM | After 100ms, SIGKILL sent |
| Windows process ignores terminate | Process may continue until natural completion |
| Network timeout call | Socket may complete before cancellation takes effect |

## Decision

We accept best-effort cancellation as the Phase 2C behavior:

1. **Always provide cancellation tokens**: Tools should check `token.is_cancelled`
2. **Attempt graceful termination**: Try terminate() before kill()
3. **Use short grace period**: 100ms between terminate and kill
4. **Document the limitation**: Make users aware that cancellation may not be immediate
5. **Provide feedback**: Log when cancellation is requested vs completed

### Implementation Notes

```python
# Cancellation is cooperative - the executing code must check
if cancellation_token.is_cancelled:
    raise asyncio.CancelledError("Cancelled by user")

# Or wait for cancellation
try:
    await cancellation_token.wait()
except asyncio.CancelledError:
    raise  # Propagate cancellation
```

## Consequences

### Positive

1. **Resource cleanup**: Most cases, cancellation works and resources are freed
2. **Observable**: Clear state transitions show cancellation intent
3. **Extensible**: ProcessHandle abstraction allows future improvements
4. **Non-blocking**: Cancel doesn't block waiting for process exit

### Negative

1. **No guarantees**: Some processes may continue running
2. **Resource waste**: Cancelled operations may complete and waste resources
3. **Confusing state**: State shows CANCELLED but execution may have completed
4. **Platform differences**: Behavior differs between Windows/Linux

## Future Improvements (Deferred)

| Improvement | Phase | Notes |
|-------------|-------|-------|
| Watchdog/reaper process | 2D | Separate process to forcefully terminate |
| Process groups | 2D | Kill entire process group on cancellation |
| Container sandboxing | 4+ | Container provides clean termination |
| Cancellation protocol | 3+ | MCP protocol cancellation support |

## References

- Phase 2C specification
- Python asyncio cancellation
- PEP 479 (task cancellation)
- Windows Job Objects (for future improvement)
