# Technical Constraints - AI_SUPPORT

**Date:** 2026-05-23
**Phase:** 1a.1

---

## Technical Stack

| Component | Constraint |
|-----------|------------|
| **Python** | 3.11+ |
| **Type Hints** | Required (strict mode) |
| **Async** | async/await for I/O |
| **Logging** | structlog + correlation_id |
| **Metrics** | Prometheus (future) |
| **Tests** | Unit ≥80%, integration when available |

## Code Standards

### File Limits
- Single source file: **≤500 lines**
- Single function: **≤50 lines**
- Comments: Explain non-obvious WHY only

### No Hard-Coding
```python
# ❌ WRONG
if speed > 1500:
    delay = 200

# ✅ CORRECT
MAX_SPEED_RPM = config.get("motor_max_rpm", 1500)
DEBOUNCE_DELAY_MS = config.get("debounce_ms", 200)
```

### Import Rules
- Use absolute imports from project root
- No circular dependencies
- Group: stdlib → third-party → local

## Hardware Constraints

| Constraint | Value |
|------------|-------|
| **Max probe count** | 1 active connection |
| **Memory read** | ≤1MB per request |
| **Stack trace depth** | ≤256 frames |
| **Timeout (default)** | 30 seconds |

## API Constraints

| Endpoint | Method | Constraint |
|----------|--------|------------|
| `/health` | GET | No auth required |
| `/ws/debug` | WS | JWT optional |
| `/api/*` | * | JWT required |

## Security Constraints

- No secrets in code (use env vars)
- PII must be redacted from logs
- Board state data encrypted at rest

## Performance Constraints

| Metric | Target |
|--------|--------|
| Debug query latency | <1 second |
| Memory per session | ≤100MB |
| Concurrent sessions | ≤10 |
| Log volume | ≤1MB/hour |

---

## Enforcement

These constraints are enforced by:
- Pre-commit hooks (format, lint)
- Code review
- Integration tests
