# ADR-003: Event Store Strategy

**Date:** 2026-05-23
**Status:** Accepted
**Deciders:** AI_SUPPORT Team

---

## Context

We need event sourcing for:
- Replay debugging sessions
- Audit trail
- Saga orchestration

## Decision

**Phase 1-2:** In-memory event store  
**Phase 4+:** PostgreSQL event store with append-only log

## Options Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| In-memory | Fast, simple | Lost on restart | **Phase 1-2** |
| PostgreSQL | Durable, queryable | Complexity | **Phase 4+** |
| Kafka | High throughput | Overkill for MVP | Rejected |
| NATS | Lightweight | No persistence | Rejected |

## Rationale

1. **In-memory first** — MVP needs speed over durability
2. **PostgreSQL later** — Add when we have real data volume
3. **Don't use Kafka** — Overkill for solo/small team

## Event Schema

```python
@dataclass
class Event:
    id: str           # UUID
    type: str         # "session_created", "tool_called", etc.
    timestamp: float  # Unix timestamp
    data: dict        # Event payload
    metadata: dict    # correlation_id, user_id, etc.
```

## Consequences

### Positive
- Fast MVP development
- Can iterate on event schema
- No infrastructure overhead

### Negative
- Events lost on restart (acceptable for MVP)
- Need migration strategy to PostgreSQL

## Migration Plan

```
Phase 1-2: InMemoryEventStore
Phase 4:   PostgreSQLEventStore with dual-write
Phase 5:   Full migration, drop in-memory
```
