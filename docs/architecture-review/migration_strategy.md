# Migration Strategy

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13
> **Scope**: Migration plan for all 6 engineering tasks (T-01 through T-06).

---

## Cross-Document Contradictions Detected

**CD-1**: `refactor_strategy.md` places T-05 in Phase C2 (parallel with T-03), but `dependency_order.md` §3 places T-05 as the final sequential task after T-04. `priority_matrix.md` ranks T-05 before T-04. These documents disagree on whether T-05 runs in parallel with T-03 or sequentially after T-04. **Not resolved here — requires decision before Phase C begins.**

**CD-2**: `root_cause_summary.md` and `dependency_order.md` state T-06 is absorbed into T-02. `test_strategy.md` uses "T-02 / T-06" headers as if they coexist. Cosmetic inconsistency — functionally T-06 is part of T-02.

**CD-3**: `regression_plan.md` recommends splitting T-04 into 4 sub-PRs. `refactor_strategy.md` treats T-04 as a single phase. Not a contradiction — the sub-PR split is a refinement compatible with the higher-level plan.

---

## 1. Migration Phases Overview

```
Phase A ──→ Phase B ──→ Phase C ──→ Phase D
T-02/T-06    T-01        T-03         T-04
                         T-05*
                         (* see CD-1)
```

Each phase is a self-contained migration unit with its own commit(s), tests, and rollback path.

---

## 2. T-02 / T-06: Harden Server Defaults

### Current State
- `STREAM_TIMEOUT_SEC = 30.0` in `runtime_manager.py`
- CORS: `allow_origins=["*"]`, `allow_credentials=True`
- `/api/fs/read`: accepts any filesystem path, no workspace scoping
- Session TTL: 3600s default, no refresh-on-activity confirmation

### Target State
- `STREAM_TIMEOUT_SEC >= 120` (configurable via env var)
- CORS: explicit origin allowlist (localhost + Electron app origin)
- `/api/fs/read`: paths resolved and validated against workspace root; symlink escape blocked
- Session TTL: confirmed refresh-on-activity behavior

### Migration Boundary
- Changes confined to `src/interfaces/server/main.py` and `src/core/runtime/runtime_manager.py`
- No schema changes, no data migration, no new dependencies

### Affected Subsystems
| Subsystem | Impact |
|-----------|--------|
| FastAPI server (`main.py`) | CORS config, file API handler, session TTL |
| RuntimeManager | Timeout constant |
| Electron IDE | Must be in CORS allowlist to connect |
| All LLM providers | Benefit from longer timeout |

### Affected Interfaces
- `/api/fs/read` — adds 403 responses for out-of-workspace paths
- WebSocket — streaming behavior changes (longer timeout before kill)
- CORS headers — restricts `Access-Control-Allow-Origin`

### Affected Storage
- None

### Affected Caches
- Session cache TTL behavior may change if refresh-on-activity is added

### Affected Protocols
- HTTP CORS headers (restricted)
- No WebSocket protocol changes

### Migration Sequence

```
Preconditions
  ✓ Identify Electron app origin (localhost:port or file:// scheme)
  ✓ Measure current max LLM generation time across providers
  ✓ Baseline: run full test suite, record pass count
     ↓
Migration
  1. Change STREAM_TIMEOUT_SEC to >= 120
  2. Replace CORS allow_origins=["*"] with explicit allowlist
  3. Add workspace root validation to /api/fs/read
  4. Add symlink escape detection
  5. Verify session TTL refresh-on-activity
     ↓
Verification
  1. Run T-02 unit tests (path traversal, CORS, timeout)
  2. Run T-02 integration tests (file API, streaming, CORS enforcement)
  3. Run T-02 security tests (symlink, null byte, directory listing)
  4. Run full existing test suite — compare pass count to baseline
     ↓
Acceptance
  ✓ All T-02 tests pass
  ✓ Zero test regressions vs baseline
  ✓ Manual: Electron IDE connects and chats successfully
  ✓ Manual: file reads outside workspace return 403
  ✓ Security review sign-off
     ↓
Monitoring
  - Watch for false-positive 403s on valid file reads (first 24h)
  - Watch for TIMEOUT errors during normal chat (should be zero)
     ↓
Completion
  ✓ PR merged
  ✓ No incidents reported within monitoring window
```

### Why This Order Minimizes Risk
- Preconditions ensure the Electron origin is known before restricting CORS (avoids locking out the IDE).
- Migration steps are independent config changes — any one can be reverted without affecting the others.
- Verification runs security tests before acceptance to catch path validation edge cases early.

---

## 3. T-01: Dead Code Audit & Consolidation

### Current State
- ~1,393 Python files (~363K lines)
- ~40% estimated dead/orphaned code
- 3 orchestration namespaces: `core/orchestration/`, `core/multi_agent/`, `application/orchestration/`
- Dead trees: `src/app/`, `src/domains/`, `src/agent/`, `infrastructure/{distributed,sharding,fleet,chaos,hsm,performance/rust}`, `core/{health,checkpoint}` stubs
- `core/events/` EventEmitter: fully implemented, disconnected from server

### Target State
- Dead trees deleted
- Single orchestration namespace
- EventEmitter either deleted or wired in (based on evidence)
- File count reduced by >= 30%

### Migration Boundary
- Deletion only — no new code, no refactoring of surviving code
- `__init__.py` files that re-exported deleted symbols must be updated
- Tests that imported deleted modules must be updated or removed

### Affected Subsystems
| Subsystem | Impact |
|-----------|--------|
| `src/app/` | Entire tree deleted |
| `src/domains/` | Entire tree deleted |
| `src/agent/` | Entire tree deleted |
| `infrastructure/{distributed,sharding,fleet,chaos,hsm,performance/rust}` | Deleted |
| `core/{health,checkpoint}` | Stub packages deleted |
| `core/multi_agent/` OR `core/orchestration/` | One deleted (decision required) |
| `core/events/` | Delete or wire in (evidence required) |
| Test suite | Tests for deleted modules removed |

### Affected Interfaces
- None (dead code has no production callers by definition)
- Risk: undiscovered callers in tests, scripts, or plugins

### Affected Storage
- None

### Affected Caches
- None

### Affected Protocols
- None

### Prerequisites (DECISION REQUIRED)
1. **Which orchestration system to keep?** Options: RealAgent-only (current production path), LangGraph, multi-agent. This decision determines what gets deleted.
2. **Is EventEmitter used outside `main.py`?** Must verify via import graph before deciding delete vs wire-in.

### Migration Sequence

```
Preconditions
  ✓ Decision: orchestration path chosen
  ✓ Evidence: EventEmitter caller audit complete
  ✓ Baseline: run full test suite, record pass count
  ✓ Baseline: record file count (find src -name "*.py" | wc -l)
     ↓
Migration (ordered by risk)
  Phase B1: Delete obviously dead trees (zero risk of callers)
    1. Delete src/app/
    2. Delete src/domains/
    3. Delete src/agent/
    4. Delete infrastructure/{distributed,sharding,fleet,chaos,hsm,performance/rust}
    5. Delete core/{health,checkpoint} stubs
    6. Verify: server starts, tests pass
  Phase B2: Consolidate orchestration (requires decision)
    7. Delete the unchosen orchestration namespace
    8. Update __init__.py re-exports if any
    9. Verify: server starts, tests pass
  Phase B3: Handle EventEmitter (requires evidence)
    10. Delete or wire in core/events/
    11. Update tests
    12. Verify: full test suite
     ↓
Verification
  1. Run import graph analysis — zero imports from deleted packages
  2. Recursive import of all remaining packages — zero ImportError
  3. Server startup — no errors
  4. Full test suite — compare pass count to baseline (expect decrease only for intentionally removed tests)
  5. E2E: chat + tool execution + indexing
     ↓
Acceptance
  ✓ File count reduced by >= 30%
  ✓ Single orchestration namespace
  ✓ Zero import errors
  ✓ All production workflows functional
  ✓ Deleted packages documented in commit message
     ↓
Monitoring
  - Watch for import errors in CI across all branches
  - Watch for user-reported broken scripts/plugins
     ↓
Completion
  ✓ PR merged
  ✓ No import errors reported within monitoring window
```

### Why This Order Minimizes Risk
- B1 (obvious dead trees) is zero-risk and can be verified immediately.
- B2 (orchestration consolidation) depends on a decision gate — cannot start until decision is made.
- B3 (EventEmitter) depends on evidence from B1 (fewer files to audit after deletion).
- Each sub-phase can be merged independently, allowing partial rollback.

---

## 4. T-03: Add Retrieval Indexing (FTS)

### Current State
- `HybridRetriever._search_chunk_store()` calls `ChunkStore.get_all()` and iterates over every chunk — O(N)
- `VectorIndex` uses NumPy brute-force cosine similarity — O(N) per query
- No FTS5 virtual table exists
- SQLite used for index state (`IncrementalIndexer`)

### Target State
- FTS5 virtual table created alongside chunk data table
- `_search_chunk_store()` uses FTS5 MATCH queries — O(log N)
- Existing chunk data migrated into FTS5 index
- `VectorIndex` path: verified as dead (delete) or live (fix in scope)

### Migration Boundary
- Changes confined to `src/infrastructure/retrieval/` (`hybrid.py`, `chunk_store.py`, `vector_index.py`)
- New SQLite virtual table (FTS5) — requires schema migration
- No API changes to `HybridRetriever.search_docs()` return type

### Affected Subsystems
| Subsystem | Impact |
|-----------|--------|
| `infrastructure/retrieval/chunk_store.py` | FTS5 table creation, insert/update/delete sync |
| `infrastructure/retrieval/hybrid.py` | `_search_chunk_store()` rewritten to use FTS5 |
| `infrastructure/retrieval/vector_index.py` | Verify live/dead, delete or fix |
| `infrastructure/indexing/incremental.py` | Chunk insert must also populate FTS5 |

### Affected Storage
- SQLite: new `chunks_fts` FTS5 virtual table
- One-time migration: populate FTS5 from existing chunk data

### Affected Caches
- No direct cache changes
- Retrieval results feed LLM prompts — indirectly affects response quality

### Affected Protocols
- None

### Migration Sequence

```
Preconditions
  ✓ T-01 complete (dead retrieval paths removed)
  ✓ VectorIndex path determined: dead or live
  ✓ Baseline: retrieval latency benchmarks on small/medium/large datasets
  ✓ Baseline: golden query set results captured
     ↓
Migration
  1. Add FTS5 virtual table creation to ChunkStore initialization
  2. Add auto-migration: detect missing FTS5 table, populate from existing chunks
  3. Modify chunk insert/update/delete to sync FTS5 table
  4. Rewrite _search_chunk_store() to use FTS5 MATCH
  5. Keep get_all() as deprecated fallback (remove in future)
  6. If VectorIndex is dead: delete. If live: fix or replace.
     ↓
Verification
  1. Unit tests: FTS5 CRUD, query syntax, equivalence with old scan
  2. Integration: index files → search → verify results
  3. Migration test: pre-existing ChunkStore → FTS5 populated → search works
  4. Benchmark: latency on all dataset sizes
  5. Golden query set: all expected results in top-10
  6. Full test suite: zero regressions
     ↓
Acceptance
  ✓ FTS5 table exists and populated
  ✓ Lexical search uses FTS5 (no get_all() in hot path)
  ✓ Golden query set passes
  ✓ Latency benchmarks show improvement
  ✓ No data loss during migration
     ↓
Monitoring
  - Watch retrieval quality in real usage (first week)
  - Monitor FTS5 DB size growth
  - Monitor lexical search latency p99
     ↓
Completion
  ✓ PR merged
  ✓ Benchmarks documented
  ✓ Migration path tested
```

### Why This Order Minimizes Risk
- Precondition on T-01 ensures dead retrieval paths are gone — fewer moving parts.
- Step 5 keeps `get_all()` as deprecated fallback — allows instant rollback to O(N) scan if FTS5 has issues.
- Migration is auto-detected and idempotent — safe to run on existing or fresh databases.

---

## 5. T-05: Add Fault Recovery

### Current State
- FileWatcher: watchdog `Observer` thread, no health check, no restart
- MCP servers: stdio subprocesses, no heartbeat, no auto-reconnect
- Idempotency: `InMemoryIdempotencyStore` with TTL, lost on restart

### Target State
- FileWatcher: health check loop, auto-restart with backoff on thread death
- MCP servers: periodic heartbeat, auto-reconnect with backoff on subprocess death
- Idempotency: SQLite-backed persistent store, TTL still enforced

### Migration Boundary
- Changes to `infrastructure/indexing/file_watcher.py`, `infrastructure/mcp/manager.py`, `core/execution/idempotency.py`
- New SQLite table for idempotency (or column in existing DB)
- New methods added to existing classes (additive, no signature breaks)

### Affected Subsystems
| Subsystem | Impact |
|-----------|--------|
| FileWatcher | New watchdog loop, `is_alive()` method |
| MCPClientManager | New `health_check()`, `reconnect()` methods |
| IdempotencyStore | New SQLite backend, preserves existing API |
| IndexingService | Uses FileWatcher — indirectly affected |
| ToolExecutionService | Uses MCP tools — indirectly affected |

### Affected Storage
- New SQLite table: `idempotency_store` (key, value, created_at, expires_at)

### Affected Caches
- Idempotency transitions from in-memory to persistent — semantically equivalent

### Affected Protocols
- MCP JSON-RPC: heartbeat uses existing `ping` or `list_tools` — no protocol extension

### Migration Sequence

```
Preconditions
  ✓ T-01 complete (confirmed which processes to protect)
  ✓ Baseline: CPU at idle, FileWatcher tests pass, MCP tests pass
     ↓
Migration (three independent sub-tasks)
  Sub-task 1: FileWatcher recovery
    1. Add is_alive() health check to FileWatcher
    2. Add watchdog loop with configurable interval and backoff
    3. Add max restart limit and alert on exhaustion
  Sub-task 2: MCP server recovery
    4. Add periodic heartbeat to MCPClientManager
    5. Add auto-reconnect with exponential backoff
    6. Repopulate tool registry after reconnect
  Sub-task 3: Persistent idempotency
    7. Create SQLite table for idempotency entries
    8. Implement SQLite-backed IdempotencyStore with same API
    9. Add TTL-based pruning (scheduled or on-access)
     ↓
Verification
  1. Unit tests for each sub-task
  2. Integration: kill FileWatcher → verify recovery
  3. Integration: kill MCP subprocess → verify reconnect
  4. Integration: restart server → verify idempotency persistence
  5. Negative: rapid kills → verify backoff, no CPU spin
  6. Benchmark: CPU at idle unchanged
  7. Full test suite: zero regressions
     ↓
Acceptance
  ✓ FileWatcher restarts within 10s of thread death
  ✓ MCP server reconnects within 10s of subprocess death
  ✓ Idempotency survives server restart
  ✓ CPU idle unchanged
  ✓ No infinite restart loops
     ↓
Monitoring
  - Watch CPU usage at idle (first 48h)
  - Watch recovery event logs for unexpected restarts
  - Watch idempotency DB size (should be bounded)
     ↓
Completion
  ✓ PR(s) merged
  ✓ Recovery behavior documented
```

### Why This Order Minimizes Risk
- Three sub-tasks are independent — can be merged in any order or parallel.
- Each sub-task is additive (new methods/tables, no signature changes) — rollback is removing the addition.
- CPU monitoring during verification catches watchdog spin before merge.

---

## 6. T-04: Unify Infrastructure Standards

### Current State
- Two import conventions: `from src.X` (~427 files), bare `from X` (~14 files)
- Three HTTP clients: httpx, aiohttp, requests
- LLM port scaffolded but empty (`core/ports/llm_provider/__init__.py`)
- `RealAgent` imports `LLMManager` directly from infrastructure
- `domain/knowledge/embeddings.py` imports `EmbeddingService` from infrastructure
- `CompletionEngine` has no retrieval context

### Target State
- Single import convention enforced by lint rule
- Single HTTP client (httpx recommended)
- LLM port interface implemented and used by `RealAgent`
- Embedding port interface implemented, domain layer uses port
- `CompletionEngine` accepts optional retrieval context

### Migration Boundary
- Cross-cutting: touches ~400+ files for import convention
- HTTP client swap: all provider adapters + embedding service
- Port implementation: new interfaces + adapter updates
- Completion wiring: `CompletionEngine` constructor change

### Affected Subsystems
| Subsystem | Impact |
|-----------|--------|
| Every Python file | Import path change |
| `infrastructure/llm/` | HTTP client swap, port adapter |
| `infrastructure/embeddings/` | HTTP client swap, port adapter |
| `infrastructure/completion/` | Retrieval dependency added |
| `core/agent/real_agent.py` | Uses LLM port instead of direct import |
| `core/ports/llm_provider/` | Port interface populated |
| `domain/knowledge/embeddings.py` | Uses embedding port |

### Affected Storage
- None

### Affected Caches
- Completion cache key may change if retrieval context is included in key

### Affected Protocols
- None (HTTP client swap is internal)

### Prerequisites (DECISIONS REQUIRED)
1. **Which import convention?** `from src.X` (majority) or bare `from X` (minority)
2. **Which HTTP client?** httpx (recommended, HTTP/2, async+sync) or aiohttp (SSE advantage)
3. **What context to inject into completion?** Cross-file symbols, recent edits, project structure — product decision

### Migration Sequence (Sub-PR strategy from regression_plan.md)

```
Preconditions
  ✓ T-01 complete (fewer files to change)
  ✓ T-03 complete (retrieval API stable)
  ✓ Decisions: import convention, HTTP client, completion context scope
  ✓ Baseline: full test suite, per-provider integration tests, completion benchmarks
     ↓
Migration (4 sub-PRs, sequential)
  Sub-PR 1: Import convention unification
    1. Choose convention (e.g., bare imports)
    2. Mechanical rename across all files
    3. Add ruff/lint rule to enforce
    4. Verify: all imports resolve, lint passes, tests pass
  Sub-PR 2: HTTP client consolidation
    5. Replace aiohttp usage in EmbeddingService with httpx
    6. Replace requests usage in legacy adapters with httpx
    7. Configure shared httpx.AsyncClient pool
    8. Remove aiohttp and requests from dependencies
    9. Verify: all providers work, embedding works, tests pass
  Sub-PR 3: LLM and embedding port implementation
    10. Define LLMProviderPort interface
    11. Implement port in each provider adapter
    12. Wire RealAgent to use port
    13. Define EmbeddingPort interface
    14. Wire domain/knowledge/embeddings.py to use port
    15. Verify: identical behavior through ports, tests pass
  Sub-PR 4: Completion-retrieval wiring
    16. Add optional retrieval parameter to CompletionEngine
    17. Inject cross-file context into FIM prompt
    18. Graceful degradation when retrieval unavailable
    19. Verify: completion works with and without retrieval
     ↓
Verification (per sub-PR)
  1. Full test suite after each sub-PR
  2. Per-provider integration test after sub-PR 2 and 3
  3. Import lint after sub-PR 1
  4. Completion benchmark after sub-PR 4
     ↓
Acceptance
  ✓ Zero lint violations
  ✓ Zero import errors
  ✓ Single HTTP client library in use
  ✓ All providers work through port
  ✓ Completion accepts retrieval context
  ✓ No benchmark regressions > 10%
     ↓
Monitoring
  - Watch for import errors across branches (post-merge conflicts)
  - Watch connection pool health under load
  - Watch completion latency with retrieval context
     ↓
Completion
  ✓ All sub-PRs merged
  ✓ Lint rule in CI
  ✓ aiohttp/requests removed from pyproject.toml
```

### Why This Order Minimizes Risk
- Sub-PR ordering follows dependency: imports first (foundation), then HTTP client (transport), then ports (abstraction), then completion (feature). Each builds on the previous.
- Sub-PR 1 is the highest-risk (most files) but lowest-complexity (mechanical rename). Doing it first means subsequent sub-PRs don't need to deal with import inconsistency.
- Sub-PR 4 is last because it depends on stable retrieval API (from T-03) and stable HTTP client (from sub-PR 2).
- Each sub-PR is independently revertable.

---

## 7. Global Migration Sequence Summary

```
[1] Phase A: T-02/T-06 — Harden server defaults
    Files: 2 (main.py, runtime_manager.py)
    Risk: Minimal
    Rollback: git revert
    Data migration: None

[2] Phase B: T-01 — Dead code consolidation
    Files: ~500 deleted
    Risk: Medium (undiscovered callers)
    Rollback: git revert (restores files)
    Data migration: None
    DECISION GATE: orchestration path

[3] Phase C: T-03 + T-05 — FTS indexing + Fault recovery
    T-03 files: 3-4 in infrastructure/retrieval/
    T-05 files: 3 (file_watcher, mcp/manager, idempotency)
    Risk: Low (additive changes)
    Rollback: git revert + drop new tables
    Data migration: FTS5 population (idempotent), idempotency table creation
    NOTE: T-03 and T-05 can run in parallel (different files)
    DECISION GATE: resolve CD-1 (parallel vs sequential)

[4] Phase D: T-04 — Unify infrastructure
    Files: ~400+ (import change) + adapters + ports
    Risk: Medium-High (cross-cutting)
    Rollback: git revert per sub-PR
    Data migration: None
    DECISION GATES: import convention, HTTP client, completion context
```

---

## 8. Prerequisites Summary

| Task | Hard Prerequisites | Soft Prerequisites | Decisions Required |
|------|-------------------|-------------------|-------------------|
| T-02/T-06 | None | None | None |
| T-01 | None | None | Orchestration path, EventEmitter disposition |
| T-03 | T-01 (soft) | VectorIndex determination | None |
| T-05 | T-01 (soft) | None | None |
| T-04 | T-01 (soft), T-03 (soft) | T-05 (soft) | Import convention, HTTP client, completion context |
