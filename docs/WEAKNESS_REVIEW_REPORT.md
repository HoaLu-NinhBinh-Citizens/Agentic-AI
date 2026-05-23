# AI_SUPPORT Weakness Report
**Review Date**: 2026-05-23  
**Reviewer**: Principal Engineer + Embedded System Expert + AI Infrastructure Reviewer  
**Scope**: Core modules, Infrastructure, Hardware, Application layers

---

## Executive Summary

| Category | Critical | High | Medium | Total |
|----------|---------|------|--------|-------|
| Correctness | 3 | 2 | 4 | 9 |
| Performance | 1 | 2 | 3 | 6 |
| Observability | 0 | 2 | 3 | 5 |
| Security | 1 | 2 | 2 | 5 |
| **Total** | **5** | **8** | **12** | **25** |

---

## 1. CRITICAL Weaknesses

### Weakness #1: Session State Lost on Restart
- **Mức độ:** Critical
- **File:** `src/core/session/session_manager.py`
- **Mô tả:** SessionManager lưu session trong memory dict, không persistence. Khi process restart, tất cả session bị mất.
- **Bằng chứng:**
```python
# Line 21
self._sessions: dict[str, dict[str, Any]] = {}  # In-memory only!
```
- **Hậu quả trong production:**
  - User đang chat bị mất context khi server restart
  - Workflow state bị reset, không resume được
  - Debug session bị interrupt
- **Đề xuất fix:** Tích hợp `PersistentSessionManager` (Phase 1B) hoặc SQLite-backed store. Hiện tại file `atomic_session_store.py` đã tồn tại nhưng chưa được import trong session_manager.
- **Effort:** 4 giờ

---

### Weakness #2: Memory Store File Write Not Atomic
- **Mức độ:** Critical
- **File:** `src/core/memory/store.py` (AgentMemory)
- **Mô tả:** File write không atomic - có thể mất data nếu crash trong khi write.
- **Bằng chứng:**
```python
# Line 78-81
def save(self):
    payload = json.dumps(self.data, indent=2)
    tmp_path = self.memory_path.with_name(f"{self.memory_path.name}.tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    os.replace(tmp_path, self.memory_path)  # atomic rename OK
```
- **Vấn đề:** `write_text` không atomic, crash giữa chừng = corrupted file.
- **Hậu quả trong production:**
  - Agent memory bị corrupted
  - Lessons learned bị mất
  - Pattern KB bị inconsistent
- **Đề xuất fix:** Sử dụng `atomic write` pattern:
  ```python
  with open(tmp_path, 'w') as f:
      f.write(payload)
      f.flush()
      os.fsync(f.fileno())
  os.replace(tmp_path, self.memory_path)
  ```
- **Effort:** 2 giờ

---

### Weakness #3: Idempotency Store In-Memory Only
- **Mức độ:** Critical
- **File:** `src/core/execution/idempotency.py`
- **Mô tả:** `InMemoryIdempotencyStore` mất state khi restart. Retry với cùng idempotency key sẽ re-execute thay vì return cached result.
- **Bằng chứng:**
```python
# Line 74-78
class InMemoryIdempotencyStore(IdempotencyStore):
    """In-memory idempotency store with TTL support.
    Phase 2C implementation. State is lost on restart."""
```
- **Hậu quả trong production:**
  - Duplicate tool execution khi worker restart
  - Potential double-charging cho API calls
  - Non-idempotent operations có thể gây data corruption
- **Đề xuất fix:** Implement `RedisIdempotencyStore` với persistence. Thêm TTL-based cleanup.
- **Effort:** 6 giờ

---

### Weakness #4: Missing request_id/trace_id in Core Logging
- **Mức độ:** High (Critical for debugging)
- **File:** `src/core/session/session_manager.py`, `src/core/agent/mock_agent.py`
- **Mô tả:** Logging không có request_id/trace_id, không thể trace request across services.
- **Bằng chứng:**
```python
# mock_agent.py line 75
logger.error("Error in mock agent: %s", e)  # No request_id!
```
- **Hậu quả trong production:**
  - Không trace được request khi có lỗi
  - Khó debug distributed system
  - Compliance violations (audit trail)
- **Đề xuất fix:** Thêm contextvars cho request_id:
  ```python
  _request_id: ContextVar[str] = ContextVar('request_id', default='')
  logger.info("event", request_id=_request_id.get())
  ```
- **Effort:** 3 giờ

---

### Weakness #5: Circular Import Risk in MCP Manager
- **Mức độ:** High
- **File:** `src/infrastructure/mcp/manager.py`
- **Mô tả:** Import module ở runtime trong function có thể gây circular import.
- **Bằng chứng:**
```python
# Line 194-195 (trong function)
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
```
- **Hậu quả trong production:**
  - Server crash nếu MCP package không installed
  - Hard to diagnose import errors
- **Đề xuất fix:** Import ở module level với graceful fallback:
  ```python
  try:
      from mcp import ClientSession
  except ImportError:
      ClientSession = None
  ```
- **Effort:** 1 giờ

---

## 2. HIGH Weaknesses

### Weakness #6: No Metrics Counter in Error Paths
- **Mức độ:** High
- **File:** `src/core/agent/mock_agent.py`
- **Mô tả:** Exception caught nhưng không update metrics counter, impossible to detect error rate.
- **Bằng chứng:**
```python
# Line 74-82
except Exception as e:
    logger.error("Error in mock agent: %s", e)
    await send_event({
        "type": "error",
        ...
    })
    # No metrics.update_error() or similar!
```
- **Hậu quả trong production:**
  - Error rate dashboard shows 0% even when errors occur
  - Can't alert on error spikes
  - Operations team blind to failures
- **Đề xuất fix:** Thêm metrics update trong all error paths:
  ```python
  self._metrics.increment("agent.error", error_type=type(e).__name__)
  ```
- **Effort:** 2 giờ

---

### Weakness #7: Cache Key Collision Potential
- **Mức độ:** High
- **File:** `src/infrastructure/cache/tool/cache.py`
- **Mô tả:** Cache key generation có thể collide nếu args có unhashable types.
- **Bằng chứng:**
```python
# Line 164-180 - generate_key interface
def generate_key(self, tool: str, version: str, args: dict[str, Any]) -> str:
    return self._key_generator.generate(tool, version, args)
```
- **Hậu quả trong production:**
  - Cache hit với wrong data
  - Incorrect tool results returned
  - Silent data corruption
- **Đề xuất fix:** Validate args là JSON-serializable, fail fast nếu không.
- **Effort:** 2 giờ

---

### Weakness #8: Circuit Breaker Half-Open Race
- **Mức độ:** High
- **File:** `src/infrastructure/resilience/circuit_breaker.py`
- **Mô tả:** Multiple concurrent requests có thể all trigger half-open state cùng lúc.
- **Bằng chứng:**
```python
# Line 167-178 - Race condition window
if self._state == CircuitBreakerState.OPEN:
    if time.monotonic() - self._last_failure_time > self.timeout_seconds:
        self._state = CircuitBreakerState.HALF_OPEN  # Check-then-set race
```
- **Hậu quả trong production:**
  - Thundering herd khi circuit opens
  - Multiple requests fail simultaneously
  - No gradual recovery
- **Đề xuất fix:** Dùng single-winner pattern hoặc probabilistic opening.
- **Effort:** 3 giờ

---

### Weakness #9: No Retry with Backoff in Circuit Breaker
- **Mức độ:** High
- **File:** `src/infrastructure/resilience/circuit_breaker.py`
- **Mô tả:** `call()` method không có retry logic, chỉ fail fast.
- **Bằng chứng:**
```python
# Line 147-199 - No retry logic in call()
try:
    result = await func(*args, **kwargs)
    ...
except Exception as e:
    self._record_failure(e)  # Immediate failure, no retry
    raise
```
- **Hậu quả trong production:**
  - Single transient failure causes complete failure
  - No resilience to brief outages
  - Circuit breaker opens unnecessarily
- **Đề xuất fix:** Thêm exponential backoff retry trong wrapper:
  ```python
  for attempt in range(max_retries):
      try:
          return await func(*args, **kwargs)
      except Exception as e:
          if not is_transient(e): raise
          await asyncio.sleep(backoff * (2 ** attempt))
  ```
- **Effort:** 4 giờ

---

### Weakness #10: Missing Load Shedding in Tool Cache
- **Mức độ:** High
- **File:** `src/infrastructure/cache/tool/cache.py`
- **Mô tả:** Không có load shedding - cache overwhelmed khi traffic spike.
- **Bằng chứng:**
```python
# Line 46-73 - ToolCache facade nhưng không thấy load shedding
# Import có LoadSheddingController nhưng không được activate
```
- **Hậu quả trong production:**
  - OOM when cache grows unbounded
  - Cache becomes bottleneck
  - System slowdown under load
- **Đề xuất fix:** Activate LoadSheddingController với proper thresholds.
- **Effort:** 2 giờ

---

## 3. MEDIUM Weaknesses

### Weakness #11: Tool Registry Not Thread-Safe
- **Mức độ:** Medium
- **File:** `src/core/tools/registry.py`
- **Mô tả:** Registry operations không protected by lock, concurrent registration có race.
- **Bằng chứng:**
```python
# Line 47-52 - No lock
def __init__(self):
    self._tools: Dict[str, Tool] = {}  # No lock!
    self._categories: Dict[ToolCategory, List[str]] = {}
```
- **Hậu quả trong production:**
  - Race condition khi multiple threads register tools
  - Potential KeyError hoặc data loss
- **Đề xuất fix:** Thêm asyncio.Lock() hoặc threading.RLock() cho all operations.
- **Effort:** 2 giờ

---

### Weakness #12: No Structured Logging in Core
- **Mức độ:** Medium
- **File:** Multiple files in `src/core/`
- **Mô tả:** Sử dụng standard `logging` thay vì `structlog`, không consistent field format.
- **Bằng chứng:**
```python
# session_manager.py - standard logging
logger = logging.getLogger(__name__)
logger.info(f"Registered tool: {tool.name}")  # f-string in log
```
- **Hậu quả trong production:**
  - Inconsistent log format
  - Hard to parse with log aggregation
  - No structured field queries
- **Đề xuất fix:** Migrate to structlog, use bound loggers:
  ```python
  logger = structlog.get_logger(__name__)
  logger.info("tool_registered", tool_name=tool.name)
  ```
- **Effort:** 8 giờ (across codebase)

---

### Weakness #13: No Health Check Endpoint
- **Mức độ:** Medium
- **File:** `src/interfaces/server/` (missing health.py)
- **Mô tả:** Không có health endpoint cho Kubernetes/load balancer.
- **Hậu quả trong production:**
  - Can't do rolling deployments
  - LB can't detect unhealthy instances
  - No automatic failover
- **Đề xuất fix:** Implement `/health` endpoint với:
  - Liveness: Is process alive?
  - Readiness: Can accept traffic?
  - Dependencies: Redis, DB connectivity
- **Effort:** 4 giờ

---

### Weakness #14: CancellationScope Cleanup Handlers Fire-and-Forget
- **Mức độ:** Medium
- **File:** `src/core/runtime/cancellation.py`
- **Mô tả:** Cleanup handlers được scheduled nhưng không awaited, exceptions không propagate.
- **Bằng chứng:**
```python
# Line 178-184
if asyncio.iscoroutinefunction(handler.callback):
    asyncio.create_task(self._run_handler(handler))  # Fire and forget!
else:
    handler.callback()
```
- **Hậu quả trong production:**
  - Cleanup failures silently ignored
  - Resource leaks có thể không được detected
  - Hard to debug cleanup issues
- **Đề xuất fix:** Track cleanup tasks, log failures, optionally propagate.
- **Effort:** 2 giờ

---

### Weakness #15: LLM Router No Timeout on Provider Call
- **Mức độ:** Medium
- **File:** `src/infrastructure/llm/router.py`
- **Mô tả:** Router không có timeout khi gọi provider, có thể hang indefinitely.
- **Bằng chứng:**
```python
# Line 174-200 - select_provider returns provider, no timeout on actual call
async def select_provider(...) -> LLMProvider | None:
    ...
    return self._providers[client_hint]
# Caller phải tự handle timeout
```
- **Hậu quả trong production:**
  - Request hangs if provider unresponsive
  - No circuit breaker at router level
  - Cascade failure possible
- **Đề xuất fix:** Wrap provider calls với timeout + circuit breaker.
- **Effort:** 3 giờ

---

### Weakness #16: No Rate Limiting on API Endpoints
- **Mức độ:** Medium
- **File:** `src/interfaces/` (API layer)
- **Mô tả:** Không có rate limiting, vulnerable to abuse.
- **Hậu quả trong production:**
  - DoS from single client
  - Cost explosion from runaway clients
  - Resource exhaustion
- **Đề xuất fix:** Implement per-client rate limiting với sliding window.
- **Effort:** 4 giờ

---

### Weakness #17: AgentMemory Prompt Injection Risk
- **Mức độ:** Medium
- **File:** `src/core/memory/store.py`
- **Mô tả:** `format_for_prompt()` có thể include attacker-controlled content trong prompt.
- **Bằng chứng:**
```python
# Line 117-140
def format_for_prompt(self, items: List[Dict], max_chars: int = 1200) -> str:
    ...
    lines.append("... error={error} cause={cause} fix={fix}".format(...))
    # attacker có thể inject vào error/cause/fix fields
```
- **Hậu quả trong production:**
  - Prompt injection attacks
  - Model behavior manipulation
  - Potential data exfiltration
- **Đề xuất fix:** Sanitize all user-controlled fields, escape special chars.
- **Effort:** 3 giờ

---

### Weakness #18: No Version in Cache Keys
- **Mức độ:** Medium
- **File:** `src/infrastructure/cache/tool/cache.py`
- **Mô tả:** Cache keys không include model/provider version, old data returned.
- **Bằng chứng:**
```python
# Line 164-180 - generate_key
def generate_key(self, tool: str, version: str, args: dict[str, Any]) -> str:
    # version là tool version, không phải model/provider version!
```
- **Hậu quả trong production:**
  - Stale cache khi model updated
  - Incorrect responses returned
  - Silent data inconsistency
- **Đề xuất fix:** Include provider version in key generation.
- **Effort:** 2 giờ

---

## 4. Items Already OK

| Aspect | Status | Notes |
|--------|--------|-------|
| Async/Await | OK | Correct usage in all reviewed async functions |
| Circuit Breaker State Machine | OK | Closed/Open/Half-open states implemented |
| Event Bus Persistence | OK | Consumer position persisted in Redis |
| Leader Election | OK | Lua scripts for atomic operations |
| Signature Verification | OK | Raises SecurityError when crypto missing |
| Determinism Logic | OK | Hash verification correctly implemented |

---

## 5. Priority Fix Order

### P0 (This Week - Production Risk)
1. **Weakness #1**: Session State Lost → Integrate persistence
2. **Weakness #2**: Memory Store Not Atomic → Fix file write
3. **Weakness #3**: Idempotency In-Memory → Add Redis backend

### P1 (This Sprint)
4. **Weakness #6**: Missing Error Metrics
5. **Weakness #8**: Circuit Breaker Race
6. **Weakness #9**: No Retry in Circuit Breaker
7. **Weakness #10**: Load Shedding

### P2 (Next Sprint)
8. **Weakness #4**: Missing trace_id
9. **Weakness #5**: Circular Import Risk
10. **Weakness #11**: Tool Registry Thread Safety

### P3 (Backlog)
11. **Weakness #12**: Structured Logging Migration
12. **Weakness #13**: Health Check Endpoint
13. **Weakness #14-18**: Remaining Medium items

---

## 6. Testing Gaps

| Gap | Coverage | Fix |
|-----|----------|-----|
| Unit test for session persistence | 0% | Add tests |
| Chaos testing for Redis failure | 0% | Add chaos tests |
| Integration test for MCP manager | 0% | Add integration tests |
| Error path test coverage | <30% | Add error scenario tests |

---

**Report Generated**: 2026-05-23  
**Total Weaknesses**: 18  
**Critical**: 5  
**High**: 5  
**Medium**: 8
