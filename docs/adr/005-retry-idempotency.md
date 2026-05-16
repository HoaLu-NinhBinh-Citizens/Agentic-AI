# ADR-005: Retry Idempotency Warning

## Status

Accepted

## Context

Phase 2C implements retry middleware with exponential backoff and jitter for failed tool calls. However, automatic retry is only safe for idempotent operations.

### What We Implemented

```python
class RetryMiddleware:
    async def handle(self, request, next_handler):
        for attempt in range(max_attempts):
            if token.is_cancelled:
                return CANCELLED
            result = await next_handler()
            if result.success:
                return result
            if result.error_code not in retryable_codes:
                return result  # Don't retry
            await asyncio.sleep(delay * (2 ** attempt) + jitter)
```

### The Problem

Retry is not safe for non-idempotent operations:

1. **write_file**: Retrying may write the file twice
2. **delete_file**: Retrying may fail (file already deleted)
3. **send_message**: Retrying may send the message twice
4. **database writes**: Retrying may cause duplicate records

### Example Failure

```
User calls: write_file("/data/config.json", content)
Server starts execution
Network timeout occurs
Retry executes: write_file("/data/config.json", content) AGAIN
Now config.json has been written twice (corruption)
```

### Current Safeguards

1. **Configurable codes**: retryable_codes is configurable
2. **Default conservative**: Default only retries MCP_ERROR and TIMEOUT
3. **Documentation**: This ADR warns about the limitation
4. **Idempotency assumed**: We assume users configure appropriately

## Decision

We accept the idempotency assumption with documentation:

1. **Document the limitation**: Make users aware of idempotency requirements
2. **Provide configuration**: Allow users to configure retryable_codes
3. **Conservative defaults**: Default to only retry transient errors
4. **Warn in documentation**: Phase 2C docs include idempotency warning

### Configuration Example

```yaml
# Safe for read operations
tool_execution:
  retry:
    retryable_codes:
      - "TIMEOUT"      # Network timeouts are safe to retry
      - "MCP_ERROR"    # MCP errors may be transient

# Dangerous for mixed operations
tool_execution:
  retry:
    retryable_codes:
      - "TIMEOUT"
      - "MCP_ERROR"
      - "write_file"   # DANGER: Will retry write operations
```

## Consequences

### Positive

1. **Simple implementation**: No complex idempotency key tracking
2. **User control**: Users configure what to retry
3. **Performance**: Can retry transient failures without user intervention
4. **Clear model**: Easy to understand and debug

### Negative

1. **User responsibility**: Users must configure carefully
2. **Silent corruption**: Non-idempotent retries may cause corruption
3. **No enforcement**: No way to detect or prevent dangerous retries
4. **Configuration burden**: Users must understand their tool idempotency

## Alternatives Considered

### 1. Idempotency Keys

Generate unique keys per request and track in execution log.

- Rejected because: Complex state management, deferred to Phase 3

### 2. Idempotency Classification

Classify tools as idempotent/non-idempotent in registry.

- Rejected because: Requires tool metadata, not always clear-cut

### 3. Ask User Confirmation

Prompt before retrying non-idempotent operations.

- Rejected because: Breaks automation, poor UX

## Future Improvements (Deferred)

| Improvement | Phase | Notes |
|-------------|-------|-------|
| Idempotency keys | 3 | Store request hash, track execution status |
| Tool classification | 3 | Metadata on tools indicating idempotency |
| Dead letter queue | 3 | Move non-idempotent failures to DLQ |
| Idempotency validation | 4+ | Validate retry won't cause side effects |

## References

- Phase 2C specification
- Retry pattern documentation
- Idempotency in REST APIs
- ATOMICITY in distributed systems
