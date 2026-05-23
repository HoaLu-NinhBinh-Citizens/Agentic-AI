# ADR-001: Architecture Style

**Date:** 2026-05-23
**Status:** Accepted
**Deciders:** AI_SUPPORT Team

---

## Context

We need to choose an architecture style for AI_SUPPORT platform that:
- Supports MVP delivery in Phase 1-2
- Can scale to production in Phase 6+
- Matches solo/small team capacity

## Decision

We will use a **Monolithic Architecture** with in-memory state for Phase 1-2.

## Options Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| Monolithic | Simple, fast MVP, single deploy | Harder to scale later | **Chosen** |
| Microservices | Independent scaling, fault isolation | Complexity, distributed systems challenges | Rejected |
| Serverless | Auto-scale, pay-per-use | Cold starts, vendor lock-in | Rejected |

## Rationale

1. **MVP Speed** — Monolithic is fastest to deliver Phase 1-2
2. **Team Size** — Solo/small team cannot manage microservices complexity
3. **YAGNI** — Don't add complexity until we have evidence of need
4. **Boring Tech** — Use proven, well-understood patterns

## Consequences

### Positive
- Fast initial development
- Simple deployment
- Easy debugging

### Negative
- Will need to refactor if scale demands it
- Technical debt if we don't refactor at right time

## Migration Path

```
Phase 1-2: Monolithic + in-memory
Phase 4:   Add PostgreSQL for persistence
Phase 6:   Extract services if evidence shows need
Phase 11+: Multi-node if required
```

## Review Date

Review at Phase 6 start (estimated Q3 2026).
