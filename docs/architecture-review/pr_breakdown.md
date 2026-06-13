# PR Breakdown — Execution Plan

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13

---

## Cross-Document Contradictions (Inherited)

**CD-1**: T-05 placement — `refactor_strategy.md` places T-05 in Phase C2 (parallel with T-03); `dependency_order.md` places T-05 sequentially last after T-04. **Not resolved. This PR breakdown follows `refactor_strategy.md` phasing (T-05 parallel with T-03 in Phase C).**

**CD-2**: T-06 presentation — sometimes shown as standalone, sometimes as subset of T-02. **Cosmetic. T-06 is absorbed into PR-001.**

**CD-3**: T-04 sub-PR split — `regression_plan.md` recommends 4 sub-PRs; `refactor_strategy.md` treats T-04 as single phase. **Compatible refinement. This breakdown uses 4 sub-PRs.**

---

## PR Index

| PR | Title | Phase | Task | Root Cause |
|----|-------|-------|------|------------|
| PR-001 | Harden server defaults | A | T-02/T-06 | RC-2 |
| PR-002 | Delete obvious dead code trees | B (B1) | T-01 | RC-1 |
| PR-003 | Consolidate orchestration system | B (B2) | T-01 | RC-1 |
| PR-004 | Resolve EventEmitter disposition | B (B3) | T-01 | RC-1 |
| PR-005 | Add FTS5 retrieval indexing | C1 | T-03 | RC-3 |
| PR-006 | Add FileWatcher fault recovery | C2 | T-05 | RC-5 |
| PR-007 | Add MCP server fault recovery | C2 | T-05 | RC-5 |
| PR-008 | Add persistent idempotency store | C2 | T-05 | RC-5 |
| PR-009 | Unify import convention | D | T-04 | RC-4 |
| PR-010 | Consolidate HTTP clients to httpx | D | T-04 | RC-4 |
| PR-011 | Implement LLM and embedding ports | D | T-04 | RC-4 |
| PR-012 | Wire completion to retrieval context | D | T-04 | RC-4 |

---

## PR Details

### PR-001: Harden Server Defaults

| Field | Value |
|-------|-------|
| **Engineering Goal** | Close security vulnerabilities (P-15, P-16), fix timeout mismatch (P-02), review session TTL (P-11) |
| **Business Value** | Eliminates arbitrary file read and CORS bypass. Stops spurious timeout errors during normal chat. |
| **Root Cause Addressed** | RC-2: Phase 1B defaults never updated for production |
| **Dependencies** | None |
| **Blocked By** | None |
| **Enables** | All subsequent PRs (security baseline) |
| **Confidence Level** | High — config-only changes with well-understood behavior |

### PR-002: Delete Obvious Dead Code Trees

| Field | Value |
|-------|-------|
| **Engineering Goal** | Remove confirmed dead packages: `src/app/`, `src/domains/`, `src/agent/`, `infrastructure/{distributed,sharding,fleet,chaos,hsm,performance/rust}`, `core/{health,checkpoint}` stubs |
| **Business Value** | ~30-40% less code. Faster onboarding, cleaner grep results, reduced maintenance surface. |
| **Root Cause Addressed** | RC-1: Speculative scaffolding never pruned |
| **Dependencies** | None (soft: PR-001 preferred first) |
| **Blocked By** | None |
| **Enables** | PR-003, PR-004, PR-005 through PR-012 (fewer files to touch) |
| **Confidence Level** | High for listed packages. Risk: undiscovered callers. |

### PR-003: Consolidate Orchestration System

| Field | Value |
|-------|-------|
| **Engineering Goal** | Delete unchosen orchestration namespace(s). Keep single system (likely RealAgent-only path). |
| **Business Value** | Single orchestration path eliminates confusion for contributors. |
| **Root Cause Addressed** | RC-1 |
| **Dependencies** | PR-002 |
| **Blocked By** | **DECISION GATE**: Orchestration path must be chosen before starting |
| **Enables** | PR-005 (clearer retrieval path), PR-006-008 (known processes to protect) |
| **Confidence Level** | Medium — depends on correctness of the orchestration decision |

### PR-004: Resolve EventEmitter Disposition

| Field | Value |
|-------|-------|
| **Engineering Goal** | Delete `core/events/` if zero callers found, or wire it into the server event loop if callers exist |
| **Business Value** | Eliminates dead infrastructure or activates a useful eventing layer |
| **Root Cause Addressed** | RC-1 |
| **Dependencies** | PR-002 (fewer files to audit after dead tree deletion) |
| **Blocked By** | **EVIDENCE GATE**: EventEmitter caller audit must be completed |
| **Enables** | None directly |
| **Confidence Level** | Medium — depends on caller audit results |

### PR-005: Add FTS5 Retrieval Indexing

| Field | Value |
|-------|-------|
| **Engineering Goal** | Replace O(N) `get_all()` scan with FTS5 MATCH queries. Add migration for existing chunk data. Determine VectorIndex disposition. |
| **Business Value** | Enables scaling beyond toy repos. Retrieval latency drops from O(N) to O(log N). |
| **Root Cause Addressed** | RC-3: No FTS index for lexical search |
| **Dependencies** | PR-002 (soft — dead retrieval paths removed) |
| **Blocked By** | PR-002 (soft) |
| **Enables** | PR-012 (stable retrieval API for completion wiring) |
| **Confidence Level** | High — FTS5 is mature; change is additive |

### PR-006: Add FileWatcher Fault Recovery

| Field | Value |
|-------|-------|
| **Engineering Goal** | Add `is_alive()` health check, watchdog loop with backoff, max restart limit to FileWatcher |
| **Business Value** | Indexing recovers automatically after thread death instead of failing silently |
| **Root Cause Addressed** | RC-5 |
| **Dependencies** | PR-002 (soft — confirmed which processes to protect) |
| **Blocked By** | None |
| **Enables** | None directly |
| **Confidence Level** | High — additive, well-understood watchdog pattern |

### PR-007: Add MCP Server Fault Recovery

| Field | Value |
|-------|-------|
| **Engineering Goal** | Add periodic heartbeat, auto-reconnect with exponential backoff, tool registry repopulation to MCPClientManager |
| **Business Value** | MCP tools recover automatically after subprocess death |
| **Root Cause Addressed** | RC-5 |
| **Dependencies** | PR-002 (soft) |
| **Blocked By** | None |
| **Enables** | None directly |
| **Confidence Level** | High — additive methods on existing class |

### PR-008: Add Persistent Idempotency Store

| Field | Value |
|-------|-------|
| **Engineering Goal** | Replace `InMemoryIdempotencyStore` with SQLite-backed store. Preserve API. Add TTL pruning. |
| **Business Value** | Idempotency survives server restarts. Tool call deduplication is durable. |
| **Root Cause Addressed** | RC-5 |
| **Dependencies** | PR-002 (soft) |
| **Blocked By** | None |
| **Enables** | None directly |
| **Confidence Level** | High — well-understood SQLite pattern |

### PR-009: Unify Import Convention

| Field | Value |
|-------|-------|
| **Engineering Goal** | Choose single import convention, mechanical rename across all files, add lint rule |
| **Business Value** | Eliminates dual-convention confusion. Lint rule prevents regression. |
| **Root Cause Addressed** | RC-4 |
| **Dependencies** | PR-002 (fewer files), PR-003, PR-004 |
| **Blocked By** | **DECISION GATE**: Import convention must be chosen. All Phase B PRs must be merged. |
| **Enables** | PR-010, PR-011, PR-012 (clean import foundation) |
| **Confidence Level** | Medium — mechanical but high file count; risk of circular imports |

### PR-010: Consolidate HTTP Clients to httpx

| Field | Value |
|-------|-------|
| **Engineering Goal** | Replace aiohttp and requests with httpx across all provider adapters and embedding service. Remove old dependencies. |
| **Business Value** | Single HTTP client, single connection pool, reduced dependency surface |
| **Root Cause Addressed** | RC-4 |
| **Dependencies** | PR-009 (imports must be stable before client swap) |
| **Blocked By** | **DECISION GATE**: HTTP client must be chosen. PR-009 merged. |
| **Enables** | PR-011 (port adapters use unified client) |
| **Confidence Level** | Medium — SSE streaming compatibility needs verification |

### PR-011: Implement LLM and Embedding Ports

| Field | Value |
|-------|-------|
| **Engineering Goal** | Define `LLMProviderPort` and `EmbeddingPort` interfaces. Implement in each adapter. Wire RealAgent and domain layer through ports. |
| **Business Value** | Proper dependency inversion. Domain layer no longer imports infrastructure. |
| **Root Cause Addressed** | RC-4 |
| **Dependencies** | PR-010 (adapters use unified HTTP client) |
| **Blocked By** | PR-010 merged |
| **Enables** | PR-012 |
| **Confidence Level** | Medium — requires careful port design |

### PR-012: Wire Completion to Retrieval Context

| Field | Value |
|-------|-------|
| **Engineering Goal** | Add optional retrieval parameter to CompletionEngine. Inject cross-file context into FIM prompt. Graceful degradation when retrieval unavailable. |
| **Business Value** | Completions gain cross-file awareness — better ghost text suggestions |
| **Root Cause Addressed** | RC-4 |
| **Dependencies** | PR-005 (stable retrieval API), PR-011 (ports in place) |
| **Blocked By** | **DECISION GATE**: Completion context scope decided. PR-005 and PR-011 merged. |
| **Enables** | None (final PR) |
| **Confidence Level** | Medium — completion quality is subjective |

---

## Execution Order

```
PR-001  Harden server defaults
  │
  ▼
PR-002  Delete obvious dead code trees
  │
  ├──────────────┐
  ▼              ▼
PR-003          PR-004
Consolidate     Resolve
orchestration   EventEmitter
  │              │
  └──────┬───────┘
         │
    ┌────┴────────────────────┐
    │                         │
    ▼                         ▼
PR-005                   PR-006, PR-007, PR-008
Add FTS5 indexing         Fault recovery (3 PRs, parallel)
    │                         │
    └────────┬────────────────┘
             │
             ▼
         PR-009  Unify import convention
             │
             ▼
         PR-010  Consolidate HTTP clients
             │
             ▼
         PR-011  Implement LLM/embedding ports
             │
             ▼
         PR-012  Wire completion to retrieval
```

### Why This Order Minimizes Risk

1. **PR-001 first**: Security fixes are urgent, low-risk, and independent. Every subsequent testing cycle runs on a hardened server.
2. **PR-002 before PR-003/004**: Obvious dead trees have zero risk of callers. Deleting them first reduces the audit scope for orchestration and EventEmitter decisions.
3. **PR-003 and PR-004 can be parallel**: They touch different subsystems (orchestration vs events).
4. **PR-005 parallel with PR-006/007/008**: FTS5 and fault recovery touch different files. Only `file_watcher.py` overlaps, and changes are orthogonal.
5. **PR-009 through PR-012 strictly sequential**: Each sub-PR builds on the previous. Import convention must stabilize before HTTP clients change, which must stabilize before ports are implemented, which must exist before completion wiring.

### Critical Path

```
PR-001 → PR-002 → PR-003 → PR-009 → PR-010 → PR-011 → PR-012
```

### Parallelizable PRs

| Set | PRs | Condition |
|-----|-----|-----------|
| 1 | PR-003, PR-004 | Both after PR-002 |
| 2 | PR-005, PR-006, PR-007, PR-008 | All after PR-003/004. Touch different subsystems. |

### Blocked PRs

| PR | Blocked By | Type |
|----|-----------|------|
| PR-003 | Orchestration decision | Decision gate |
| PR-004 | EventEmitter caller audit | Evidence gate |
| PR-009 | Import convention decision | Decision gate |
| PR-010 | HTTP client decision, PR-009 | Decision gate + dependency |
| PR-012 | Completion context scope decision | Decision gate |
