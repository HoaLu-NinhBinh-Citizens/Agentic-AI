# ADR-002: Database Choice

**Date:** 2026-05-23
**Status:** Accepted
**Deciders:** AI_SUPPORT Team

---

## Context

We need a database for:
- Session state
- Event store (future)
- Long-term memory
- Configuration

## Decision

**Primary:** PostgreSQL  
**Cache:** Redis  
**File:** Local filesystem for artifacts

## Options Considered

### PostgreSQL vs Alternatives

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| PostgreSQL | ACID, JSON, mature, rich features | Slightly more weight than MySQL | **Chosen** |
| MySQL | Simple, widely used | Less JSON support, older | Rejected |
| MongoDB | Flexible schema | Eventual consistency issues | Rejected |
| SQLite | No setup, file-based | Not good for concurrent writes | Rejected for production |

### Redis vs Alternatives

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| Redis | Data structures, persistence, pub/sub | Memory footprint | **Chosen** |
| Memcached | Simple, low memory | No persistence | Rejected |

## Rationale

1. **PostgreSQL**
   - ACID compliance critical for session state
   - JSON support for flexible metadata
   - Mature, well-understood

2. **Redis**
   - Pub/sub for WebSocket
   - TTL for session cleanup
   - Persistence option

## Consequences

### Positive
- Robust data integrity
- Mature tooling
- Easy backup/restore

### Negative
- Requires running PostgreSQL + Redis
- Slightly more complex deployment

## Implementation

```python
# Phase 1-2: SQLite for dev, PostgreSQL for production
# Phase 4+: Full PostgreSQL migration
```
