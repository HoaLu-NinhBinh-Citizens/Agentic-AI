# Engineering Dependency Graph & Execution Order

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13

---

## 1. Task Dependency Graph

```
T-06 (Path restriction on file API)
  │
  │  no dependencies — can start immediately
  │
  ▼
  DONE (standalone)


T-02 (Harden server defaults)
  │
  │  no dependencies — can start immediately
  │  (includes T-06 as a subset)
  │
  ▼
  DONE


T-01 (Dead code audit & consolidation)
  │
  │  no dependencies — can start immediately
  │  but creates the CLEANEST base for T-03, T-04, T-05
  │
  ├──────────────────┐
  │                  │
  ▼                  ▼
T-03               T-04
(Retrieval         (Unify infra
 indexing)          standards)
  │                  │
  │  T-03 does NOT   │  T-04 does NOT
  │  depend on T-04  │  depend on T-03
  │                  │
  └────────┬─────────┘
           │
           │  Both should complete before T-05
           │  (fault recovery benefits from clean codebase)
           ▼
         T-05
     (Fault recovery)
```

### Formal Dependency Table

| Task | Blocks | Blocked By | Rationale |
|------|--------|------------|-----------|
| **T-06** | Nothing | Nothing | Standalone security fix. Smallest scope. |
| **T-02** | Nothing | Nothing | Config changes only. Includes T-06 scope. |
| **T-01** | T-03, T-04, T-05 (soft) | Nothing | Removing dead code first makes every subsequent task cheaper. |
| **T-03** | T-05 (soft) | T-01 (soft) | FTS indexing is easier after dead retrieval paths are removed. |
| **T-04** | T-05 (soft) | T-01 (soft) | Import unification is easier after dead packages are deleted. |
| **T-05** | Nothing | T-01 (soft), T-03 (soft), T-04 (soft) | Fault recovery should target the consolidated architecture, not the current one with 40% dead code. |

**"Soft" dependency** means: technically possible to do out of order, but doing T-01 first reduces the scope and risk of every subsequent task.

---

## 2. Parallel Execution Opportunities

```
Phase A (parallel):
  ├── T-06 / T-02 (server hardening — same person, same files)
  └── T-01 (dead code audit — different files entirely)

Phase B (parallel, after T-01):
  ├── T-03 (retrieval indexing — infrastructure/retrieval/)
  └── T-04 (infra unification — cross-cutting but different files from T-03)

Phase C (sequential, after Phase B):
  └── T-05 (fault recovery — touches FileWatcher, MCP, idempotency)
```

**Maximum parallelism**: 2 engineers working in parallel throughout.

---

## 3. Execution Order

### Recommended Sequence

```
[1] T-02 + T-06: Harden server defaults (includes file API restriction)
      │
      │  WHY FIRST: Security fixes have the highest urgency-to-effort ratio.
      │  P-16 (unrestricted file API) and P-15 (CORS *) are active security
      │  vulnerabilities. P-02 (timeout mismatch) causes visible user-facing
      │  errors. All are configuration-level changes with minimal risk.
      │
      ▼
[2] T-01: Dead code audit & consolidation
      │
      │  WHY SECOND: Removing ~40% dead code reduces the cognitive and
      │  mechanical cost of every subsequent task. Tasks T-03, T-04, T-05
      │  all touch files that neighbor dead code. Deleting dead code first
      │  means fewer files to reason about, fewer false grep hits, fewer
      │  import path conflicts.
      │
      │  Also resolves P-03 (dual orchestration) by forcing a decision:
      │  keep one orchestration path, delete the others.
      │
      ▼
[3] T-03: Add retrieval indexing (FTS)
      │
      │  WHY THIRD: P-01 (O(N) lexical scan) is the single biggest
      │  scalability bottleneck. It blocks any repo >100K LOC from being
      │  usable. After T-01 removes dead retrieval paths, the remaining
      │  retrieval architecture is clear enough to add FTS correctly.
      │
      ▼
[4] T-04: Unify infrastructure standards
      │
      │  WHY FOURTH: Import convention, HTTP client consolidation, and
      │  completion↔retrieval wiring are cross-cutting refactors. They
      │  are lower urgency than scaling (T-03) but higher long-term
      │  value than fault recovery (T-05). Doing this after T-03 means
      │  the retrieval infrastructure is already clean when we unify
      │  the HTTP clients that serve it.
      │
      ▼
[5] T-05: Add fault recovery
      │
      │  WHY LAST: Fault recovery should protect the final architecture,
      │  not the current messy one. Adding watchdog/heartbeat for processes
      │  that might be deleted (during T-01) or restructured (during T-04)
      │  would be wasted work. This task naturally comes after the system
      │  is consolidated.
      │
      ▼
  DONE
```

### Alternative Order Considered and Rejected

**"T-03 first because it's the biggest bottleneck"**

Rejected because: T-03 touches `infrastructure/retrieval/hybrid.py` which imports from `core.config.agent_prompts` and depends on `ChunkStore`, `VectorIndex`, `ReferenceKnowledgeBase`. Without T-01 (dead code removal), it's unclear which of these have dead alternate implementations. Starting T-03 before T-01 risks building on paths that should be deleted.

**"T-04 before T-03 because unified imports make everything easier"**

Rejected because: T-04 (import unification) is a large cross-cutting change that touches hundreds of files. It carries more risk of merge conflicts and regressions. T-03 (FTS) is localized to the retrieval subsystem. The scalability benefit of T-03 outweighs the tidiness benefit of T-04.

---

## 4. Critical Path

The critical path (longest sequential chain) is:

```
T-02 → T-01 → T-03 → T-04 → T-05
```

**T-06 is absorbed into T-02.**

With parallelism:
```
T-02 ─────┐
           ├──→ T-03 ──┐
T-01 ─────┘             ├──→ T-05
           ├──→ T-04 ──┘
           │
```

Critical path with parallelism: **T-02 → T-01 → max(T-03, T-04) → T-05**
