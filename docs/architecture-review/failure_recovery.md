# Failure Recovery Plan

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13

---

## 1. T-02 / T-06: Harden Server Defaults

### F-02-1: Path validation rejects valid workspace paths (false positive)

| Aspect | Detail |
|--------|--------|
| **Possible failure** | `Path.resolve()` normalization or workspace root comparison rejects a valid path due to symlinks, case sensitivity (Windows), or UNC paths |
| **Detection** | Integration test T-02-I01 catches known cases. Production: user reports file read failure, server logs 403 for workspace-internal path |
| **Immediate mitigation** | Revert path validation commit. Alternatively, add the specific path pattern to an allowlist |
| **Recovery strategy** | Fix the path normalization logic to handle the edge case. Re-run security test suite |
| **Long-term prevention** | Maintain a comprehensive test corpus of path formats (symlinks, UNC, case variants, Unicode). Run on Windows and Linux in CI |

### F-02-2: CORS blocks Electron IDE

| Aspect | Detail |
|--------|--------|
| **Possible failure** | Electron app sends requests from an origin not in the allowlist (e.g., `file://` protocol, `app://` custom scheme, or dynamic port) |
| **Detection** | Manual test T-02-I03 / Electron connectivity test. Production: IDE shows connection error |
| **Immediate mitigation** | Add the correct origin to the allowlist and redeploy. Alternatively, temporarily revert to `allow_origins=["*"]` |
| **Recovery strategy** | Determine the exact `Origin` header Electron sends (inspect via browser DevTools or log server-side). Add to allowlist |
| **Long-term prevention** | Document the Electron app's `Origin` header in project documentation. Add automated test that starts Electron and verifies WebSocket connection |

### F-02-3: New timeout too short for specific LLM provider/model

| Aspect | Detail |
|--------|--------|
| **Possible failure** | A specific model (e.g., large Anthropic model with long context) exceeds the new timeout |
| **Detection** | User reports TIMEOUT error during chat with specific provider. Benchmark T-02 `stream_timeout_headroom_s` shows negative headroom |
| **Immediate mitigation** | Increase `STREAM_TIMEOUT_SEC` via env var override |
| **Recovery strategy** | Make timeout dynamic based on provider (Anthropic already computes `120 + prompt_chars/50`). Set server timeout to max of all provider timeouts |
| **Long-term prevention** | Implement dynamic timeout: server queries the active provider's timeout before wrapping with `wait_for` |

---

## 2. T-01: Dead Code Audit & Consolidation

### F-01-1: Deleted module has undiscovered live caller

| Aspect | Detail |
|--------|--------|
| **Possible failure** | A file not explored during the dead-code audit imports from a deleted package. Server crashes with `ModuleNotFoundError` at startup or at runtime (lazy import) |
| **Detection** | T-01-I01 (server startup), T-01-I02 (recursive import). Production: crash with `ModuleNotFoundError` |
| **Immediate mitigation** | `git revert` the deletion commit to restore the package |
| **Recovery strategy** | Investigate the caller: is it a legitimate production path (restore the module) or another dead-code path (delete the caller too)? |
| **Long-term prevention** | Run static import analysis tool (e.g., `importlab`, `pydeps`, or AST-based script) before any deletion. Require zero-import-count proof per deleted package |

### F-01-2: Orchestration decision is wrong

| Aspect | Detail |
|--------|--------|
| **Possible failure** | The deleted orchestration system (e.g., LangGraph) was actually used by an undiscovered code path or was planned for imminent use |
| **Detection** | User/team reports missing functionality. Runtime error when a workflow type triggers the deleted orchestration path |
| **Immediate mitigation** | `git revert` the orchestration consolidation commit (B2 sub-phase) |
| **Recovery strategy** | Re-evaluate the orchestration decision with full team input. Either restore the deleted system or port needed functionality to the kept system |
| **Long-term prevention** | Require team sign-off on orchestration decision before T-01 B2 begins. Document the decision rationale |

### F-01-3: Test suite has too many failures after deletion

| Aspect | Detail |
|--------|--------|
| **Possible failure** | More tests fail than expected — tests that appeared to be for dead code actually tested shared utilities or fixtures used by live tests |
| **Detection** | T-01-I03 test run shows unexpected failure count (more than tests in deleted directories) |
| **Immediate mitigation** | Do not merge. Investigate each unexpected failure |
| **Recovery strategy** | For each unexpected failure: trace the import chain, determine if the dependency is on the deleted module or a shared fixture. Update the test to use surviving code paths |
| **Long-term prevention** | Before deletion, run `python -m pytest --collect-only` to list which tests import from each package. Cross-reference with deletion list |

---

## 3. T-03: Add Retrieval Indexing (FTS)

### F-03-1: FTS5 recall regression

| Aspect | Detail |
|--------|--------|
| **Possible failure** | FTS5 tokenizer handles terms differently than the old Python-based scoring. Some queries return fewer relevant results |
| **Detection** | T-03-U03 lexical search equivalence test, T-03-R01 golden query set |
| **Immediate mitigation** | Keep `get_all()` as fallback — revert `_search_chunk_store()` to use old scan |
| **Recovery strategy** | Analyze which queries regressed. Adjust FTS5 tokenizer configuration (e.g., `unicode61`, `porter` stemmer). Add missing terms to FTS5 content |
| **Long-term prevention** | Maintain golden query set as a regression gate in CI. Run equivalence test on every retrieval change |

### F-03-2: FTS5 migration corrupts data

| Aspect | Detail |
|--------|--------|
| **Possible failure** | Migration script errors mid-way, leaving FTS5 table partially populated or chunk table corrupted |
| **Detection** | Migration test T-03-I03. Production: search returns partial/wrong results |
| **Immediate mitigation** | Drop FTS5 table, fall back to `get_all()` scan |
| **Recovery strategy** | Fix migration script. Re-run migration from scratch (FTS5 is derived data, can be rebuilt) |
| **Long-term prevention** | Wrap migration in a transaction. Make migration idempotent (check if already populated before inserting). Add checksum verification after migration |

### F-03-3: FTS5 not available on target platform

| Aspect | Detail |
|--------|--------|
| **Possible failure** | Target deployment uses a SQLite build without FTS5 extension compiled in |
| **Detection** | Server startup error: `OperationalError: no such module: fts5` |
| **Immediate mitigation** | Fall back to `get_all()` scan with logged warning |
| **Recovery strategy** | Either install SQLite with FTS5 support or implement runtime feature detection with graceful fallback |
| **Long-term prevention** | Add FTS5 availability check at startup. Document SQLite build requirements |

---

## 4. T-05: Add Fault Recovery

### F-05-1: Watchdog causes CPU spin

| Aspect | Detail |
|--------|--------|
| **Possible failure** | FileWatcher or MCP heartbeat loop runs too frequently, consuming excessive CPU at idle |
| **Detection** | Benchmark `cpu_idle_pct`. Production: high CPU usage with no active requests |
| **Immediate mitigation** | Revert the watchdog commit |
| **Recovery strategy** | Increase watchdog interval (e.g., 5s → 30s). Use `threading.Event.wait(timeout)` instead of `time.sleep()` for interruptible waits |
| **Long-term prevention** | CI benchmark gate: `cpu_idle_pct` must not increase after T-05 |

### F-05-2: MCP reconnection loses tool registry

| Aspect | Detail |
|--------|--------|
| **Possible failure** | After reconnection, the MCP server's tool list differs (e.g., server updated during downtime). Tool registry becomes inconsistent |
| **Detection** | T-05-U04 tool registry repopulation test. Production: tool call fails with "unknown tool" |
| **Immediate mitigation** | Full server restart to re-initialize all MCP connections from scratch |
| **Recovery strategy** | After reconnect, diff the new tool list against the old. Log added/removed tools. Update the tool registry atomically |
| **Long-term prevention** | Make tool registry refresh idempotent. Version-check MCP server capabilities on reconnect |

### F-05-3: Idempotency DB locking

| Aspect | Detail |
|--------|--------|
| **Possible failure** | Multiple async coroutines access the idempotency SQLite DB simultaneously, causing `OperationalError: database is locked` |
| **Detection** | T-05-N04 locked DB test. Production: tool execution errors |
| **Immediate mitigation** | Revert to in-memory idempotency store |
| **Recovery strategy** | Use `aiosqlite` with WAL mode for concurrent read/write. Or use a connection pool with serialized writes |
| **Long-term prevention** | Stress test: 100 concurrent idempotency lookups. Verify zero lock errors |

### F-05-4: Infinite restart loop

| Aspect | Detail |
|--------|--------|
| **Possible failure** | Underlying cause of FileWatcher/MCP death persists, causing immediate re-death after restart. Watchdog enters tight restart loop |
| **Detection** | T-05-N01 restart limit test. Production: rapid log entries for restart events |
| **Immediate mitigation** | Max restart limit reached → stop retrying, log alert |
| **Recovery strategy** | Investigate root cause of persistent death. Fix root cause before re-enabling recovery |
| **Long-term prevention** | Exponential backoff with max restart count (e.g., 5 restarts, then give up). Circuit breaker pattern on recovery itself |

---

## 5. T-04: Unify Infrastructure Standards

### F-04-1: Import convention change causes circular imports

| Aspect | Detail |
|--------|--------|
| **Possible failure** | Changing import paths reveals or creates circular import dependencies that were masked by the old convention |
| **Detection** | T-04-I01 recursive import test. Production: `ImportError: cannot import name X from partially initialized module` |
| **Immediate mitigation** | Revert import convention sub-PR |
| **Recovery strategy** | Identify the circular import chain. Break the cycle by moving shared types to a separate module or using lazy imports |
| **Long-term prevention** | Run `importlab` or equivalent tool to detect circular imports before merging. Add to CI |

### F-04-2: SSE streaming breaks with httpx

| Aspect | Detail |
|--------|--------|
| **Possible failure** | `aiohttp` was used for SSE streaming in `EmbeddingService` and some LLM adapters. `httpx` handles SSE differently (e.g., chunked transfer encoding, newline parsing) |
| **Detection** | T-04-R01 per-provider streaming test. Production: chat produces garbled or missing tokens |
| **Immediate mitigation** | Revert HTTP client sub-PR. Restore aiohttp for the affected adapter |
| **Recovery strategy** | Use `httpx-sse` extension or implement SSE parsing on top of `httpx` raw streaming. Test with each provider |
| **Long-term prevention** | Maintain per-provider streaming integration test in CI with real (or mock) SSE endpoints |

### F-04-3: Connection pool exhaustion

| Aspect | Detail |
|--------|--------|
| **Possible failure** | Unified httpx pool has lower limits than the combined pools. Under load, connections are exhausted |
| **Detection** | T-04-I04 concurrent request test. Production: `httpx.PoolTimeout` errors |
| **Immediate mitigation** | Increase pool limits (`max_connections`, `max_keepalive_connections`) |
| **Recovery strategy** | Calculate: old combined pool capacity (httpx 100 + aiohttp default + requests default). Set new pool to at least that sum |
| **Long-term prevention** | Monitor pool utilization metrics. Set pool limits based on measured peak concurrency |

### F-04-4: Completion quality degrades with retrieval context

| Aspect | Detail |
|--------|--------|
| **Possible failure** | Cross-file retrieval context confuses the FIM model, producing worse completions than local-only context |
| **Detection** | T-04-R03 completion quality baseline comparison. Production: user reports unhelpful completions |
| **Immediate mitigation** | Disable retrieval context injection (set to empty/None). Completion falls back to local-only |
| **Recovery strategy** | Tune the retrieval context: reduce amount, improve relevance filtering, adjust FIM prompt template |
| **Long-term prevention** | A/B test completion quality with and without retrieval context. Make retrieval context a configurable feature flag |

### F-04-5: Import convention change causes merge conflicts in feature branches

| Aspect | Detail |
|--------|--------|
| **Possible failure** | Other engineers have feature branches with the old import convention. After T-04 SP1 merges, every feature branch has massive merge conflicts |
| **Detection** | Team reports merge conflicts after SP1 merge |
| **Immediate mitigation** | Provide a script to automatically update imports in any branch |
| **Recovery strategy** | Run the import rename script on each feature branch. Alternatively, coordinate: all feature branches must merge or rebase before SP1 |
| **Long-term prevention** | Announce import convention change in advance. Merge SP1 during a quiet period (no active feature branches). Provide migration script in the PR description |

---

## 6. Cross-Task Failure Scenarios

### F-X-1: Two phases merged, second one breaks, first cannot be reverted independently

| Aspect | Detail |
|--------|--------|
| **Possible failure** | T-03 merged, then T-04 SP2 merged. T-04 SP2 breaks SSE streaming. Reverting T-04 SP2 is not clean because T-03 changed files in the same area |
| **Detection** | `git revert` produces merge conflicts |
| **Immediate mitigation** | Manual revert: cherry-pick the specific changes to undo from T-04 SP2, resolving conflicts by hand |
| **Recovery strategy** | Keep phases in separate branches until each is stable. Only merge the next phase after the current one passes its monitoring window |
| **Long-term prevention** | Enforce stabilization windows between phases. Do not merge Phase D until Phase C is proven stable |

### F-X-2: Database schema from T-03 and T-05 cannot both be rolled back

| Aspect | Detail |
|--------|--------|
| **Possible failure** | Both `chunks_fts` and `idempotency_store` tables exist. Need to roll back to pre-T-03 state. But T-05 table is in the same DB and should be kept |
| **Detection** | Manual rollback planning |
| **Immediate mitigation** | Run SQL scripts selectively: drop only the table for the reverted task |
| **Recovery strategy** | Table-level rollback, not DB-level. Each migration has its own down-migration script |
| **Long-term prevention** | Use separate DB files for unrelated tables, or maintain explicit migration scripts with up/down for each table |

---

## 7. NEED MORE EVIDENCE Items

| Item | Impact | Resolution |
|------|--------|------------|
| Electron app's `Origin` header value | F-02-2: may block IDE | Inspect Electron main process or capture in network log |
| Whether any external plugin imports dead packages | F-01-1: undiscovered callers | Full-repo grep including non-Python files |
| Whether `VectorIndex` brute-force path is exercised | F-03-1 scope: fix or delete | Trace `HybridRetriever` initialization to see which index is injected |
| `aiohttp` SSE behavior differences vs `httpx` | F-04-2: streaming breakage | Build prototype of httpx-based SSE streaming, test with each provider |
| Concurrent SQLite access pattern for idempotency | F-05-3: DB locking | Profile current `InMemoryIdempotencyStore` usage: how many concurrent accesses? |
