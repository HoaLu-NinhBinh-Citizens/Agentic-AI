# Refactor Strategy — Implementation Sequence

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13
> **Rule**: High-level roadmap only. No implementation details.

---

## Recommended Implementation Sequence

```
┌─────────────────────────────────────────────────┐
│ PHASE A: Secure & Stabilize                     │
│                                                 │
│  T-02: Harden server defaults                   │
│  ├── Fix stream timeout mismatch (P-02)         │
│  ├── Restrict CORS origins (P-15)               │
│  ├── Add workspace scoping to file API (P-16)   │
│  └── Review session TTL for IDE use case (P-11) │
│                                                 │
│  Effort: Low                                    │
│  Risk: Minimal                                  │
│  Outcome: Security vulnerabilities closed,      │
│           user-visible timeout bugs fixed        │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│ PHASE B: Simplify                               │
│                                                 │
│  T-01: Dead code audit & consolidation          │
│  ├── Verify dead trees via import graph          │
│  ├── Delete confirmed dead packages             │
│  │   (src/app, src/domains, src/agent,          │
│  │    infrastructure/{distributed,sharding,      │
│  │    fleet,chaos,hsm,performance/rust},         │
│  │    core/{health,checkpoint} stubs)            │
│  ├── Decide orchestration path:                 │
│  │   RealAgent-only? LangGraph? Multi-agent?    │
│  │   Delete the others.                         │
│  └── Verify and delete or integrate EventEmitter│
│                                                 │
│  Effort: Medium                                 │
│  Risk: Medium (must verify before deleting)     │
│  Outcome: ~40% less code, clear ownership,      │
│           single orchestration path              │
│                                                 │
│  DECISION REQUIRED before starting:             │
│  → Which orchestration system to keep?          │
│  → Is EventEmitter used outside main.py?        │
└─────────────────────┬───────────────────────────┘
                      │
          ┌───────────┴───────────┐
          │                       │
          ▼                       ▼
┌──────────────────────┐ ┌──────────────────────────┐
│ PHASE C1: Scale      │ │ PHASE C2: Harden         │
│                      │ │                          │
│ T-03: Retrieval FTS  │ │ T-05: Fault recovery     │
│ ├── Add FTS5 to      │ │ ├── FileWatcher watchdog  │
│ │   ChunkStore       │ │ ├── MCP server heartbeat  │
│ ├── Replace O(N)     │ │ │   + auto-reconnect     │
│ │   lexical scan     │ │ └── Persistent            │
│ ├── Verify VectorIdx │ │     idempotency store    │
│ │   usage (P-13)     │ │                          │
│ └── Eliminate or fix  │ │ Effort: Medium           │
│     brute-force path │ │ Risk: Low (additive)     │
│                      │ │                          │
│ Effort: Medium       │ │                          │
│ Risk: Low (additive) │ │                          │
└──────────┬───────────┘ └────────────┬─────────────┘
           │                          │
           └────────────┬─────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│ PHASE D: Unify                                  │
│                                                 │
│  T-04: Unify infrastructure standards           │
│  ├── Standardize import convention              │
│  │   (choose one: bare or prefixed)             │
│  │   Add ruff/lint rule to enforce              │
│  ├── Consolidate HTTP clients                   │
│  │   (target: httpx only)                       │
│  ├── Implement LLM port (core/ports/llm)        │
│  │   Wire RealAgent through port                │
│  ├── Implement Embedding port                   │
│  │   Fix domain→infrastructure violation        │
│  └── Wire completion to retrieval               │
│     (cross-file context for FIM)                │
│                                                 │
│  Effort: High                                   │
│  Risk: Medium-High (cross-cutting, merge risk)  │
│  Outcome: Clean architecture, proper DI,        │
│           single HTTP stack, smarter completions │
│                                                 │
│  PREREQUISITES:                                 │
│  → T-01 complete (fewer files to change)        │
│  → T-03 complete (retrieval API stable)         │
│  → T-05 complete (safety net during refactor)   │
└─────────────────────────────────────────────────┘
```

---

## Why This Order Is Correct

### Phase A before Phase B
Security and correctness fixes have zero dependency on architecture cleanup. They are the smallest tasks with the highest urgency. Fixing them first means every subsequent testing cycle runs on a secure, correctly-timeoutted server.

### Phase B before Phases C/D
Dead code removal is a **cost multiplier** for every subsequent phase:
- T-03 (retrieval FTS): After T-01, the retrieval subsystem has one clear path, not two or three. The FTS addition targets a known, live code path.
- T-04 (import unification): After T-01, there are ~800 files to update instead of ~1,400. The 40% reduction directly translates to 40% less mechanical work and 40% fewer merge conflict opportunities.
- T-05 (fault recovery): After T-01, the processes to protect are known. No point adding a watchdog for a FileWatcher that might serve a dead indexing path.

### C1 and C2 in parallel
T-03 (retrieval FTS) and T-05 (fault recovery) touch completely different subsystems:
- T-03: `infrastructure/retrieval/`, `infrastructure/indexing/`
- T-05: `infrastructure/indexing/file_watcher.py`, `infrastructure/mcp/manager.py`, `core/execution/idempotency.py`

Only `file_watcher.py` overlaps, and the changes are orthogonal (T-03 doesn't change the watcher; T-05 adds a restart loop around it).

### Phase D last
T-04 is the highest-risk task. It touches the most files and crosses the most module boundaries. Every prior phase reduces its scope and risk:
- T-01 removes ~40% of files that would need import changes
- T-03 stabilizes the retrieval API (so the HTTP client consolidation and completion wiring target a stable interface)
- T-05 provides a safety net (if fault recovery is in place, a botched import migration that crashes a subsystem is detected and recovered)

---

## Decision Points

| Decision | When Needed | Who Decides | Impact |
|----------|-------------|-------------|--------|
| **Which orchestration to keep** (RealAgent-only vs LangGraph vs multi-agent) | Before T-01 (Phase B) | Project lead | Determines what gets deleted. Wrong choice loses useful code. |
| **Which import convention** (bare vs `from src.`) | Before T-04 (Phase D) | Team consensus | Determines mechanical scope of T-04. |
| **Which HTTP client** (httpx vs aiohttp) | Before T-04 (Phase D) | Platform team | httpx is recommended (HTTP/2, async+sync), but aiohttp has SSE streaming advantages. |
| **What context to inject into completion** | Before T-04 sub-task (completion wiring) | Product + engineering | Determines completion quality ceiling. |

---

## What This Roadmap Does NOT Cover

This roadmap addresses the 16 architectural problems identified in the baseline review. It does NOT cover:

- New feature development
- Electron IDE improvements
- Test coverage expansion
- CI/CD pipeline changes
- Performance profiling (actual benchmarks vs estimates)
- Database migration (no schema changes needed for these tasks)

These are deferred intentionally. The roadmap's purpose is to bring the architecture to a state where new features can be added safely and at scale. Feature work should resume after Phase B at the earliest, and ideally after Phase C.

---

## Success Criteria Per Phase

| Phase | Success Criteria |
|-------|-----------------|
| **A** | No CORS * in production. File API rejects paths outside workspace. Stream timeout ≥120s. Zero spurious TIMEOUT errors in normal chat. |
| **B** | `find src -name "*.py" \| wc -l` drops by ≥30%. Single orchestration namespace. Zero empty `__init__.py` stub packages. |
| **C1** | `HybridRetriever._search_chunk_store()` uses FTS5 index, not `get_all()`. Retrieval latency on 100K LOC repo is <100ms. |
| **C2** | FileWatcher auto-restarts after simulated crash. MCP server reconnects within 10s of subprocess death. Idempotency store survives server restart. |
| **D** | All imports use one convention with lint rule enforced. Single `httpx.AsyncClient` across all HTTP calls. CompletionEngine accepts retrieval context. `core/ports/llm_provider/` is populated and used. |
