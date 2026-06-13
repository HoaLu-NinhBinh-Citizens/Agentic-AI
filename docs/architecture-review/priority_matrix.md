# Priority Matrix — Ranked Issues

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13

---

## 1. Impact Analysis Per Task

### T-02: Harden Server Defaults (P-02, P-11, P-15, P-16)

| Dimension | Impact | Evidence |
|-----------|--------|----------|
| Developer productivity | Low | Timeout mismatch causes retries but workaround is shorter prompts |
| User experience | **High** | P-02: 30s timeout kills valid LLM generations → user sees spurious errors |
| Reliability | **High** | P-11: sessions can expire mid-work |
| Scalability | None | Config values, not architecture |
| Security | **Critical** | P-15: CORS * with credentials. P-16: arbitrary file read |
| Maintenance | Low | Isolated config changes |

### T-01: Dead Code Audit & Consolidation (P-03, P-04, P-07, P-12)

| Dimension | Impact | Evidence |
|-----------|--------|----------|
| Developer productivity | **High** | 40% dead code doubles navigation, grep noise, onboarding time |
| User experience | None directly | Dead code isn't executed |
| Reliability | Low | Dead code doesn't break production, but confuses maintenance |
| Scalability | None directly |  |
| Security | Low | Dead code may have unpatched vulnerabilities but isn't reachable |
| Maintenance | **Critical** | Every future task is harder with 40% noise. Three orchestration systems confuse any contributor. |

### T-03: Add Retrieval Indexing (P-01, P-13)

| Dimension | Impact | Evidence |
|-----------|--------|----------|
| Developer productivity | **High** | Slow retrieval → slow AI suggestions → developer waits |
| User experience | **High** | Retrieval quality and speed directly affect suggestion relevance |
| Reliability | Low | O(N) is slow, not incorrect |
| Scalability | **Critical** | O(N) scan is the single point that breaks at >100K LOC |
| Security | None |  |
| Maintenance | Low | Localized to retrieval subsystem |

### T-04: Unify Infrastructure Standards (P-05, P-06, P-09, P-10)

| Dimension | Impact | Evidence |
|-----------|--------|----------|
| Developer productivity | Medium | Dual imports cause confusion; 3 HTTP clients cause debugging overhead |
| User experience | **High** | P-10: completion without cross-file context = low-quality suggestions |
| Reliability | Medium | Multiple connection pools → harder timeout management |
| Scalability | Low | Connection pool fragmentation has minor overhead |
| Security | None |  |
| Maintenance | **High** | Import inconsistency and DI violations make refactoring risky |

### T-05: Add Fault Recovery (P-08, P-14)

| Dimension | Impact | Evidence |
|-----------|--------|----------|
| Developer productivity | Medium | Silent indexing failure → stale suggestions until restart |
| User experience | Medium | MCP tool calls fail silently when server dies |
| Reliability | **High** | No watchdog, no recovery, no persistent idempotency |
| Scalability | Low |  |
| Security | None |  |
| Maintenance | Medium | Adding watchdog is localized |

### T-06: Path Restriction on File API (P-16)

| Dimension | Impact | Evidence |
|-----------|--------|----------|
| Security | **Critical** | Arbitrary file read from any WebSocket client |

(Subset of T-02; scored independently for urgency tracking.)

---

## 2. Complexity Analysis

| Task | Complexity | Rationale |
|------|-----------|-----------|
| **T-06** | **Low** | Add `Path.resolve()` check and workspace root validation. <10 lines of logic. |
| **T-02** | **Low** | Change 4-5 constant values / config patterns across `main.py`. Low risk, high confidence. |
| **T-01** | **Medium** | Requires careful verification that "dead" code is truly dead (grep all imports, check test fixtures, check CLI paths). Deletion itself is mechanical. Decision on orchestration path (LangGraph vs multi-agent vs RealAgent-only) requires architectural judgment. |
| **T-03** | **Medium** | FTS5 integration into `ChunkStore` is well-understood. Need to verify which vector search path is active (P-13) before deciding scope. SQLite FTS5 is a mature technology. |
| **T-04** | **High** | Cross-cutting change touching hundreds of files (import convention). HTTP client consolidation requires verifying all provider adapters work with one library. Completion↔retrieval wiring requires design decisions about what context to inject. |
| **T-05** | **Medium** | Watchdog pattern is straightforward. Persistent idempotency via SQLite is well-understood. MCP reconnection requires careful subprocess lifecycle handling. |

---

## 3. Risk Analysis

| Task | Risk of Fixing | Risk of NOT Fixing | Migration Difficulty | Backward Compat Risk |
|------|---------------|-------------------|---------------------|---------------------|
| **T-06** | **Minimal** — path validation only | **Critical** — any client can read `/etc/passwd` or `C:\Windows\System32\config\SAM` | None | None (new restriction only) |
| **T-02** | **Low** — config changes, easily tested | **High** — P-02 causes visible bugs now. P-15/P-16 are security holes. | None | P-02 (longer timeout) may need client-side adjustment for progress indicators |
| **T-01** | **Medium** — risk of deleting something that IS used through an undiscovered path | **High** — every future task costs more; new contributors are confused | Low (deletion, not migration) | Risk of breaking imports if any external tool depends on dead paths |
| **T-03** | **Low** — FTS5 is additive, old path can be kept as fallback | **Critical for scaling** — project cannot target repos >100K LOC | Low (additive index alongside existing store) | None (new index, old path preserved) |
| **T-04** | **Medium-High** — import convention change across 400+ files risks merge conflicts and subtle import-order bugs | **Medium** — tolerable short-term, but accumulates tech debt | High (bulk rename, client consolidation) | High — any plugin, test, or script using `from src.` must be updated |
| **T-05** | **Low** — additive watchdog and persistent store | **Medium** — production outages go undetected | Low (additive) | None (new capability only) |

---

## 4. Priority Scoring

**Formula**: Priority = Impact × Urgency × (1 / Complexity) × Risk_of_not_fixing

| Task | Impact | Urgency | Complexity⁻¹ | Risk_if_unfixed | **Score** | **Priority** |
|------|--------|---------|--------------|----------------|-----------|------------|
| **T-02** (incl T-06) | Critical (security) | Immediate | High (low effort) | Critical | **36** | **P0** |
| **T-01** | High (maintenance) | High (blocks all) | Medium | High | **24** | **P0** |
| **T-03** | Critical (scaling) | High | Medium | Critical | **24** | **P0** |
| **T-04** | High (quality + maintenance) | Medium | Low (high effort) | Medium | **8** | **P1** |
| **T-05** | High (reliability) | Medium | Medium | Medium | **12** | **P1** |

### Final Priority Ranking

```
P0 (Do Now):
  [1] T-02 — Harden server defaults (incl. T-06 security fix)
  [2] T-01 — Dead code audit & consolidation
  [3] T-03 — Add retrieval indexing (FTS)

P1 (Strategic):
  [4] T-05 — Add fault recovery
  [5] T-04 — Unify infrastructure standards

P2: None identified
P3: None identified
```

---

## 5. Rationale for P0 Classification

### T-02 (P0 rank #1)
- **Why P0**: Contains two active security vulnerabilities (P-15 CORS, P-16 file read) and one actively user-visible bug (P-02 timeout mismatch). Lowest effort of all tasks.
- **Why rank #1**: Highest urgency-to-effort ratio. Can be completed in hours, not days. Security issues should never wait.

### T-01 (P0 rank #2)
- **Why P0**: Blocks or increases cost of every subsequent task. 40% dead code is not a cosmetic issue — it's a multiplicative cost on all future engineering.
- **Why rank #2**: Moderate effort (requires careful dead code verification), but the compounding benefit justifies immediate action after security fixes.

### T-03 (P0 rank #3)
- **Why P0**: O(N) lexical scan is the single biggest architectural limit. Without FTS, the project cannot scale beyond toy repos. This is the capability ceiling.
- **Why rank #3**: After T-01 removes dead retrieval paths, T-03's scope is clearer and smaller.

---

## 6. Rationale for P1 Classification

### T-05 (P1 rank #4)
- **Why P1 not P0**: Fault recovery is important but not urgent. FileWatcher and MCP servers work correctly on the happy path. The risk is in rare failure scenarios (OOM, subprocess crash), which are tolerable during active development.
- **Why before T-04**: Lower effort and lower risk than T-04. Improves reliability meaningfully.

### T-04 (P1 rank #5)
- **Why P1 not P0**: Import unification is the highest-risk, highest-effort task. It touches 400+ files and risks merge conflicts. The benefit (consistency, DI, unified HTTP client) is real but not urgent.
- **Why last**: Every other task makes T-04 easier. After T-01 deletes dead code (fewer files to change), T-03 stabilizes retrieval (fewer moving parts during HTTP client consolidation), and T-05 adds process recovery (safety net during refactoring).

---

## 7. "Do NOT Fix Yet" List

| Problem | Why Not Yet |
|---------|------------|
| P-05 (dual import convention) | Part of T-04. Changing imports before T-01 (dead code removal) means changing imports in files that will be deleted. Do T-01 first. |
| P-06 (DI violations) | Part of T-04. Implementing the LLM port before deciding which orchestration path survives (T-01 decision) may produce a port that wraps the wrong abstraction. |
| P-09 (three HTTP clients) | Part of T-04. Consolidating before T-01 means consolidating clients that serve dead code paths. Consolidating before T-03 means the retrieval HTTP client hasn't settled yet. |
| P-10 (completion ↔ retrieval) | Part of T-04. Wiring completion to retrieval before T-03 (FTS) means wiring to a retrieval system that's about to change. After T-03, the retrieval API is stable. |
| P-12 (disconnected EventEmitter) | Part of T-01. If the EventEmitter has zero callers after dead code audit, it should be deleted, not wired in. Decision requires T-01 evidence. |
| P-13 (brute-force VectorIndex) | Part of T-03. Need to verify during T-03 whether this path is exercised. May be dead code (deleted in T-01) or may be the primary path (fixed in T-03). |
| P-14 (in-memory idempotency) | Part of T-05. Adding SQLite persistence to the idempotency store before the codebase is consolidated means targeting an architecture that's about to change. |
