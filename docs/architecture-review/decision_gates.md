# Decision Gates

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13

---

## Phase A: Harden Server Defaults (T-02 / T-06)

### GO Criteria
- [ ] Electron app origin identified and documented
- [ ] Max LLM generation time measured across all configured providers
- [ ] Baseline test suite run recorded (pass count)
- [ ] All T-02 unit tests pass
- [ ] All T-02 integration tests pass
- [ ] All T-02 security tests pass
- [ ] Full test suite: zero regressions vs baseline
- [ ] Manual: Electron IDE connects and completes a chat round-trip
- [ ] Manual: file read outside workspace returns 403
- [ ] Architecture freeze checklist passes (no protocol/API changes)

### NO-GO Criteria
- Any existing test fails that was passing before the change
- Electron IDE cannot connect via WebSocket
- Valid workspace file reads return 403 (false positive)
- LLM generation for normal-length prompts times out
- CORS headers are missing for the Electron origin
- Compile/import failure in any module

### STOP Criteria
- Electron app origin cannot be determined (NEED MORE EVIDENCE — resolve before proceeding)
- Security review finds additional vulnerabilities in the file API beyond P-16 (scope change — re-plan)
- Session TTL behavior requires changes to `PersistentSessionManager` API (scope creep — separate task)

---

## Phase B: Dead Code Consolidation (T-01)

### Pre-Phase Decision Gate
Before starting Phase B, the following decisions must be made:

| Decision | Options | Required By |
|----------|---------|-------------|
| Orchestration path | RealAgent-only / LangGraph / Multi-agent | Project lead |
| EventEmitter disposition | Delete / Wire in | Evidence from caller audit |

**STOP if either decision is not made.** Do not begin Phase B without both decisions documented.

### GO Criteria (Sub-phase B1: Obvious Dead Trees)
- [ ] Import graph analysis confirms zero live importers for: `src/app/`, `src/domains/`, `src/agent/`, `infrastructure/{distributed,sharding,fleet,chaos,hsm,performance/rust}`, `core/{health,checkpoint}`
- [ ] Server starts after deletion
- [ ] Recursive import of all remaining packages: zero `ImportError`
- [ ] Full test suite: only tests for deleted modules fail (document which)
- [ ] File count reduced

### GO Criteria (Sub-phase B2: Orchestration Consolidation)
- [ ] Orchestration decision is documented with rationale
- [ ] All code paths currently using `RealAgent` still work after deleting the unchosen namespace
- [ ] `main.py` imports resolve
- [ ] Server starts
- [ ] Chat + tool execution work end-to-end
- [ ] Updated/removed tests documented

### GO Criteria (Sub-phase B3: EventEmitter)
- [ ] EventEmitter caller audit complete (zero callers → delete; callers found → wire in or document)
- [ ] If deleted: no `ImportError` in surviving code
- [ ] If wired in: events flow through the emitter in at least one verified path

### NO-GO Criteria
- Server fails to start after any sub-phase
- More tests fail than expected (unexpected failures beyond deleted-module tests)
- `agentic-ai --help` CLI entry point fails
- Production workflow (chat, tools, indexing) breaks

### STOP Criteria
- Orchestration decision not made (cannot proceed with B2)
- EventEmitter evidence insufficient — callers found in code paths not fully analyzed (defer B3)
- Discovered that a "dead" tree has external consumers (plugins, notebooks, scripts) — re-scope before deleting
- Unexpected architectural dependency between dead code and live code (requires deeper analysis)

---

## Phase C1: Retrieval FTS (T-03)

### GO Criteria
- [ ] T-01 complete and stable (monitoring window passed)
- [ ] VectorIndex path determined: dead (deleted in T-01) or live (scope clarified)
- [ ] Baseline retrieval benchmarks recorded (all dataset sizes)
- [ ] Baseline golden query set results captured
- [ ] FTS5 available on target platform (verified via `SELECT fts5()`)
- [ ] All T-03 unit tests pass
- [ ] All T-03 integration tests pass
- [ ] FTS5 migration test passes (pre-existing data → FTS5 populated)
- [ ] Golden query set: all expected results in top-10
- [ ] Benchmark: lexical search latency improved vs baseline
- [ ] Full test suite: zero regressions
- [ ] Architecture freeze checklist passes

### NO-GO Criteria
- FTS5 recall regression: golden query set results missing from top-10
- FTS5 migration loses data (chunk count before != after)
- Retrieval latency increases vs baseline
- Any existing test fails (beyond ranking-order changes in retrieval tests)
- SQLite `OperationalError` during FTS5 table creation

### STOP Criteria
- FTS5 not available on target SQLite build (platform constraint — requires alternative approach)
- VectorIndex determination reveals a complex dependency chain not covered by T-01 (re-scope)
- Retrieval pipeline has more callers than documented — need full dependency audit before changing internals

---

## Phase C2: Fault Recovery (T-05)

### GO Criteria
- [ ] T-01 complete and stable (confirmed which processes to protect)
- [ ] Baseline CPU at idle recorded
- [ ] All T-05 unit tests pass
- [ ] All T-05 integration tests pass (FileWatcher recovery, MCP reconnect, idempotency persistence)
- [ ] All T-05 negative tests pass (restart limit, permanent failure, DB corruption, DB locked)
- [ ] CPU at idle: unchanged vs baseline (watchdog does not spin)
- [ ] Full test suite: zero regressions
- [ ] Architecture freeze checklist passes

### NO-GO Criteria
- CPU at idle increases (watchdog spinning)
- MCP reconnection loses tool registry (tools not re-discovered)
- Idempotency DB locked under concurrent access
- Infinite restart loop observed
- Any existing test fails

### STOP Criteria
- FileWatcher recovery requires changes to watchdog library API (dependency risk)
- MCP heartbeat requires MCP protocol extension (protocol freeze violation — re-scope to use existing methods)
- Idempotency DB conflicts with existing SQLite usage patterns (concurrent access design required)

---

## Phase D: Unify Infrastructure (T-04)

### Pre-Phase Decision Gate
Before starting Phase D, the following decisions must be made:

| Decision | Options | Required By |
|----------|---------|-------------|
| Import convention | `from src.X` / bare `from X` | Team consensus |
| HTTP client | httpx / aiohttp | Platform team |
| Completion context scope | Symbols / recent edits / project structure | Product + engineering |

**STOP if any decision is not made.** Do not begin Phase D without all three decisions documented.

### GO Criteria (Sub-PR 1: Import Convention)
- [ ] Import convention decision documented
- [ ] Migration script provided and tested
- [ ] All feature branches merged or notified
- [ ] Lint rule configured and tested
- [ ] All imports resolve after mechanical rename
- [ ] Lint: zero violations
- [ ] Full test suite passes
- [ ] Architecture freeze checklist passes

### GO Criteria (Sub-PR 2: HTTP Client)
- [ ] HTTP client decision documented
- [ ] All LLM provider adapters work with chosen client (per-provider test)
- [ ] Embedding service works with chosen client
- [ ] SSE streaming works with chosen client (streaming test)
- [ ] Connection pool configured with capacity >= old combined pools
- [ ] Load test: 20 concurrent requests, zero pool timeouts
- [ ] `aiohttp` and `requests` removed from `pyproject.toml`
- [ ] Zero imports of `aiohttp` or `requests` in `src/`
- [ ] Full test suite passes

### GO Criteria (Sub-PR 3: Ports)
- [ ] `LLMProviderPort` interface defined with all methods used by `RealAgent`
- [ ] All 5 provider adapters implement the port
- [ ] `RealAgent` uses port, not direct infrastructure import
- [ ] `EmbeddingPort` interface defined
- [ ] `domain/knowledge/embeddings.py` uses port, not concrete `EmbeddingService`
- [ ] Behavior equivalence: same prompt → same response through port
- [ ] Full test suite passes

### GO Criteria (Sub-PR 4: Completion-Retrieval Wiring)
- [ ] Completion context scope decision documented
- [ ] `CompletionEngine` accepts optional retrieval parameter
- [ ] Completion works with retrieval context (cross-file awareness)
- [ ] Completion works without retrieval context (graceful degradation)
- [ ] Completion latency benchmark: within acceptable range
- [ ] Full test suite passes

### NO-GO Criteria (Any Sub-PR)
- Compile/import failure
- Any LLM provider stops working
- SSE streaming breaks (garbled or missing tokens)
- Connection pool exhaustion under load test
- Completion quality regression (manual review)
- Any existing test fails

### STOP Criteria
- Import convention change reveals circular imports that cannot be resolved without architectural changes
- httpx does not support a required SSE streaming pattern used by a provider (need alternative approach)
- Port abstraction requires changes to `main.py` server wiring that affect the WebSocket protocol (protocol freeze violation)
- Feature branches with old imports cannot be migrated (team coordination failure — delay until resolved)
- Completion with retrieval context is consistently worse than without (product decision: may not wire completion to retrieval)
- Security issue discovered during refactoring (immediate STOP, security fix takes priority)

---

## Global Decision Gates

### Before Starting Any Phase

- [ ] Previous phase is complete and stable (monitoring window passed, no rollback needed)
- [ ] Baseline measurements recorded for the new phase's metrics
- [ ] All required decisions for the phase are made and documented
- [ ] Team notified of upcoming changes (especially for T-01 deletions and T-04 import changes)

### After Completing All Phases

| Gate | Criteria |
|------|----------|
| **Final GO** | Full test suite passes from clean checkout. All benchmarks within thresholds. All manual validation checklist items pass. Electron IDE works end-to-end. |
| **Final NO-GO** | Any test failure. Any benchmark regression > 50%. Any manual validation failure. Any security issue. |
| **Final STOP** | Architectural issue discovered that was not covered by the planning documents. Requires re-planning before proceeding. |

---

## Risk Matrix

| Task | Compile Risk | Runtime Risk | Regression Risk | Migration Risk | Operational Risk | Security Risk |
|------|-------------|-------------|----------------|---------------|-----------------|--------------|
| **T-02** | Low | Low | Low | Low | Low | Low (fixes security) |
| **T-01** | **Medium** | **Medium** | **Medium** | Low | Low | Low |
| **T-03** | Low | Low | **Medium** | **Medium** | Low | Low |
| **T-05** | Low | **Medium** | Low | Low | **Medium** | Low |
| **T-04 SP1** | **High** | **Medium** | **High** | **High** | **Medium** | Low |
| **T-04 SP2** | Low | **High** | **Medium** | Low | Low | Low |
| **T-04 SP3** | **Medium** | Low | Low | Low | Low | Low |
| **T-04 SP4** | Low | Low | **Medium** | Low | Low | Low |

### Justifications

| Risk | Task | Level | Why |
|------|------|-------|-----|
| Compile | T-01 | Medium | Deleted packages may have undiscovered importers |
| Compile | T-04 SP1 | High | Import convention change across 400+ files — any typo causes ImportError |
| Runtime | T-01 | Medium | Lazy imports from deleted modules surface only at runtime |
| Runtime | T-04 SP2 | High | HTTP client swap may break SSE streaming, connection pooling, or timeout behavior |
| Runtime | T-05 | Medium | Watchdog/heartbeat loops run continuously — bugs cause resource exhaustion |
| Regression | T-01 | Medium | Tests for deleted modules must be removed; risk of removing tests that cover live behavior |
| Regression | T-03 | Medium | Retrieval ranking may change — golden set prevents recall regression but ranking changes are expected |
| Regression | T-04 SP1 | High | Every test file's imports change — risk of subtle import-order dependencies |
| Regression | T-04 SP4 | Medium | Completion quality is subjective — hard to define automated pass/fail |
| Migration | T-03 | Medium | FTS5 migration from existing data must be idempotent and lossless |
| Migration | T-04 SP1 | High | All feature branches need migration script. Team coordination required |
| Operational | T-05 | Medium | New background loops (watchdog, heartbeat) increase operational surface area |
| Operational | T-04 SP1 | Medium | Import convention change affects all developer tooling (IDE, linters, debuggers) |

---

## Checkpoint Strategy

### Phase A Checkpoints

| Checkpoint | What to Verify | Success Criteria | Rollback Trigger |
|------------|---------------|------------------|------------------|
| CP-A1 | CORS restriction applied | `Origin: evil.example.com` rejected; Electron origin allowed | Electron IDE cannot connect |
| CP-A2 | File API hardened | Path traversal returns 403; valid paths return 200 | Valid file reads rejected |
| CP-A3 | Stream timeout updated | 60s mock LLM stream completes without timeout | Normal chat times out |
| CP-A4 | Full regression | All existing tests pass | Any test regression |

### Phase B Checkpoints

| Checkpoint | What to Verify | Success Criteria | Rollback Trigger |
|------------|---------------|------------------|------------------|
| CP-B1 | B1 deletions safe | Server starts; recursive import clean; file count down | Import error on startup |
| CP-B2 | Orchestration consolidated | Single namespace; chat + tools work | Chat or tool execution breaks |
| CP-B3 | EventEmitter resolved | Deleted or wired in; no import errors | Unexpected callers found |
| CP-B4 | Full regression | All production workflows work; test suite stable | Any production workflow breaks |

### Phase C1 Checkpoints

| Checkpoint | What to Verify | Success Criteria | Rollback Trigger |
|------------|---------------|------------------|------------------|
| CP-C1-1 | FTS5 table created | Table exists; populated from existing chunks | Migration failure |
| CP-C1-2 | Lexical search uses FTS5 | `_search_chunk_store()` does not call `get_all()` | Retrieval still uses O(N) scan |
| CP-C1-3 | Quality preserved | Golden query set passes | Recall regression |
| CP-C1-4 | Performance improved | Benchmark shows latency decrease | Latency increases |

### Phase C2 Checkpoints

| Checkpoint | What to Verify | Success Criteria | Rollback Trigger |
|------------|---------------|------------------|------------------|
| CP-C2-1 | FileWatcher recovery | Thread kill → auto-restart within 10s | No restart; or CPU spin |
| CP-C2-2 | MCP recovery | Subprocess kill → reconnect; tools re-discovered | Tools lost after reconnect |
| CP-C2-3 | Idempotency persistence | Store entry → restart → entry survives | Data lost on restart |
| CP-C2-4 | No resource regression | CPU idle unchanged; DB size bounded | CPU increase or unbounded growth |

### Phase D Checkpoints (per sub-PR)

| Checkpoint | What to Verify | Success Criteria | Rollback Trigger |
|------------|---------------|------------------|------------------|
| CP-D1-1 | Import convention | All imports resolve; lint zero violations | Import error |
| CP-D2-1 | HTTP client unified | All providers work; streaming works; pool stable | Provider failure or pool exhaustion |
| CP-D3-1 | Ports implemented | RealAgent uses port; embedding uses port; behavior identical | Behavior change through port |
| CP-D4-1 | Completion wired | Cross-file context in FIM; graceful degradation | Completion quality degrades |
| CP-D-FINAL | Full regression | All tests pass; all benchmarks within thresholds | Any regression |
