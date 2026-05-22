# Phase 3 – Reliability & Observability

## Lệnh Agent

```
@prompts/phase_3.md Thực hiện tuần tự. Commit [Phase 3]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Bảng sub-phase

| ID | Sub‑phase | Mô tả |
|----|-----------|-------|
| 3.1 | Retry và backoff | Exponential backoff, jitter |
| 3.2 | Rate limiting | Per user, per tool, sliding window |
| 3.3 | Circuit breaker | Cho LLM và tool endpoints |
| 3.4 | Structured logging | JSON logs, ELK stack integration |
| 3.5 | Prometheus metrics | Latency, error rate, tool usage, queue size |
| 3.6 | Distributed tracing | OpenTelemetry + Jaeger |

## Task list (thực hiện tuần tự)

- [ ] **3.1** Retry — `gateway/retry.py`, `retry_policy.py`, jitter
- [ ] **3.2** `core/rate_limiter.py` — sliding window
- [ ] **3.3** Circuit breaker — MCP + LLM paths
- [ ] **3.4** JSON logging + correlation_id middleware
- [ ] **3.5** Metrics — tool_usage, circuit_breaker_state, `/metrics`
- [ ] **3.6** OpenTelemetry — `infrastructure/observability/otel.py`
- [ ] **3.7** Unit tests circuit breaker, rate limiter

## Kết thúc phase

- [ ] Endpoint `/metrics` scrape được
- [ ] Commit `[Phase 3]`, build_log, ERA_ROADMAP
