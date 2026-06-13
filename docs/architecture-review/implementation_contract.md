# Implementation Contract

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13

---

## PR-001: Harden Server Defaults

### Goal
Close P-15 (CORS *), P-16 (unrestricted file read), P-02 (30s timeout mismatch), P-11 (session TTL review). Config-only changes to 2 files.

### Non-goals
- Implementing health probes (P-07 — addressed by T-01 deletion)
- Redesigning session management
- Adding rate limiting or authentication

### Constraints
- Changes confined to `main.py` and `runtime_manager.py`
- Electron IDE origin must be in CORS allowlist — **NEED MORE EVIDENCE** on exact origin header value
- New timeout must exceed maximum observed LLM generation time across all providers

### Assumptions
- Electron IDE sends a consistent `Origin` header (not `null` or dynamic)
- `STREAM_TIMEOUT_SEC` is the only server-side timeout that kills LLM streams
- Session TTL refresh-on-activity is either already implemented or trivially addable

### Architecture Invariants
- REST endpoint paths unchanged
- WebSocket protocol unchanged
- `/api/fs/read` return format unchanged for valid paths (adds 403 for invalid paths)

### Preconditions
- [ ] Electron app origin identified
- [ ] Max LLM generation time measured across providers
- [ ] Baseline test suite pass count recorded

### Postconditions
- [ ] `allow_origins` does not contain `"*"`
- [ ] `/api/fs/read` rejects paths outside workspace
- [ ] `STREAM_TIMEOUT_SEC` >= 120
- [ ] All existing tests pass

### Success Criteria
- Zero CORS bypass possible from unauthorized origins
- Zero path traversal possible via file API
- Zero spurious TIMEOUT errors during normal chat
- Electron IDE connects and completes chat round-trip

### Failure Criteria
- Any existing test regresses
- Electron IDE cannot connect
- Valid workspace file reads rejected (false positive)
- Normal-length LLM generation killed by timeout

### Rollback Trigger
Any failure criterion met.

### Rollback Completion Criteria
- Server behavior identical to pre-PR-001 state
- Zero test regressions

---

## PR-002: Delete Obvious Dead Code Trees

### Goal
Delete confirmed dead packages: `src/app/`, `src/domains/`, `src/agent/`, `infrastructure/{distributed,sharding,fleet,chaos,hsm,performance/rust}`, `core/{health,checkpoint}` stubs. Update affected `__init__.py` files. Remove/update tests for deleted modules.

### Non-goals
- Deciding orchestration path (PR-003)
- Resolving EventEmitter (PR-004)
- Deleting any module with uncertain live/dead status

### Constraints
- Deletion only — no new code, no refactoring of surviving code
- Every deleted package must have zero verified live importers
- Tests for deleted modules must be explicitly documented before removal

### Assumptions
- Import graph analysis accurately identifies all callers (no dynamic imports to deleted packages in production paths)
- No external plugins import from deleted packages — **NEED MORE EVIDENCE** (grep non-Python files)

### Architecture Invariants
- Server startup sequence unchanged
- All REST/WebSocket endpoints unchanged
- All production workflows functional (chat, tools, indexing, completion)

### Preconditions
- [ ] Baseline test suite pass count recorded
- [ ] Baseline file count recorded
- [ ] Import graph analysis confirms zero live importers for each target

### Postconditions
- [ ] File count reduced by >= 30%
- [ ] Server starts without import errors
- [ ] Recursive import of all remaining packages: zero `ImportError`
- [ ] `import src.app` raises `ModuleNotFoundError`

### Success Criteria
- All listed dead trees deleted
- Server starts and serves requests identically
- Test suite passes (minus intentionally removed tests)

### Failure Criteria
- Server fails to start (import error)
- Previously passing test fails unexpectedly
- Production workflow breaks (chat, tools, indexing)

### Rollback Trigger
Any failure criterion met, or undiscovered live caller found.

### Rollback Completion Criteria
- All deleted files restored
- File count returns to pre-PR-002 level
- Full test suite passes at pre-PR-002 pass count

---

## PR-003: Consolidate Orchestration System

### Goal
Delete unchosen orchestration namespace(s). Ensure the surviving system handles all existing workflows. Update `__init__.py` re-exports.

### Non-goals
- Enhancing or refactoring the surviving orchestration system
- Adding new orchestration capabilities
- Changing `main.py` wiring beyond removing dead imports

### Constraints
- **DECISION GATE**: Orchestration path must be chosen and documented before this PR begins
- Only deletion and `__init__.py` cleanup — no new abstractions

### Assumptions
- `RealAgent` is the production path (highest likelihood based on evidence)
- LangGraph and multi-agent systems have zero production callers (medium confidence — P-03)

### Architecture Invariants
- `main.py` imports `RealAgent`, `RuntimeManager`, `ToolExecutionService` — these must resolve
- Chat + tool execution work end-to-end

### Preconditions
- [ ] PR-002 merged
- [ ] Orchestration decision documented with rationale
- [ ] All code paths using the surviving system identified

### Postconditions
- [ ] Single orchestration namespace exists
- [ ] `main.py` imports resolve
- [ ] Server starts, chat + tools work

### Success Criteria
- Single orchestration path, documented
- Zero import errors

### Failure Criteria
- Server fails to start
- Chat or tool execution breaks
- Deleted orchestration system had undiscovered callers

### Rollback Trigger
Any failure criterion met.

### Rollback Completion Criteria
- Deleted namespace restored
- Server behavior identical to pre-PR-003

---

## PR-004: Resolve EventEmitter Disposition

### Goal
If zero callers: delete `core/events/`. If callers exist: wire EventEmitter into the server event loop or document why it should remain disconnected.

### Non-goals
- Building a new event system
- Adding event-driven features
- Changing WebSocket event handling

### Constraints
- **EVIDENCE GATE**: Caller audit must complete before starting
- If wired in: must not change WebSocket protocol
- If deleted: must not cause import errors

### Assumptions
- EventEmitter caller audit can be completed via static analysis after PR-002 reduces file count

### Architecture Invariants
- WebSocket event delivery unchanged
- No new message types added to protocol

### Preconditions
- [ ] PR-002 merged (fewer files to audit)
- [ ] EventEmitter caller audit complete

### Postconditions
- [ ] `core/events/` either deleted or actively used by at least one production path
- [ ] Zero import errors
- [ ] Decision documented

### Success Criteria
- EventEmitter status resolved with evidence
- No lingering dead infrastructure

### Failure Criteria
- Unexpected callers found that break when EventEmitter is deleted
- Wiring EventEmitter changes WebSocket behavior

### Rollback Trigger
Any failure criterion met.

### Rollback Completion Criteria
- `core/events/` restored if deleted
- Server behavior identical to pre-PR-004

---

## PR-005: Add FTS5 Retrieval Indexing

### Goal
Add FTS5 virtual table to ChunkStore. Replace `get_all()` scan with FTS5 MATCH queries. Auto-migrate existing chunk data. Determine VectorIndex disposition.

### Non-goals
- Changing `HybridRetriever.search_docs()` return type
- Removing `get_all()` method (keep as deprecated fallback)
- Optimizing vector search (VectorIndex fix/delete is in scope; HNSW is not)

### Constraints
- FTS5 must be available on target SQLite build — if not, **STOP** (platform constraint)
- Migration must be idempotent and transactional
- Ranking order may change — recall must not regress

### Assumptions
- SQLite FTS5 is available on all target platforms
- Existing chunk data is valid and can be indexed without transformation
- `get_all()` callers (if any outside HybridRetriever) still work

### Architecture Invariants
- `search_docs()` returns `list[RetrievalHit]`
- ChunkStore public API preserved (new methods additive)
- No REST/WebSocket changes

### Preconditions
- [ ] PR-002 merged (soft — dead retrieval paths removed)
- [ ] VectorIndex path determined: dead or live
- [ ] Baseline retrieval benchmarks recorded
- [ ] Golden query set captured

### Postconditions
- [ ] FTS5 table exists and populated
- [ ] `_search_chunk_store()` uses FTS5 MATCH, not `get_all()`
- [ ] Golden query set: all expected results in top-10
- [ ] Retrieval latency improved vs baseline

### Success Criteria
- Lexical search is O(log N) via FTS5
- Recall >= 1.0 vs old scan on golden query set
- Latency improvement on all dataset sizes

### Failure Criteria
- FTS5 recall regression (golden set results missing)
- Migration loses chunk data
- Retrieval latency increases

### Rollback Trigger
Any failure criterion met, or FTS5 unavailable on target platform.

### Rollback Completion Criteria
- `_search_chunk_store()` reverted to `get_all()` scan
- FTS5 table dropped: `DROP TABLE IF EXISTS chunks_fts`
- Retrieval behavior identical to pre-PR-005

---

## PR-006: Add FileWatcher Fault Recovery

### Goal
Add `is_alive()` health check, watchdog loop with configurable interval and exponential backoff, max restart limit to FileWatcher.

### Non-goals
- Changing FileWatcher's file-change detection behavior
- Adding metrics or alerting infrastructure
- Modifying IndexingService

### Constraints
- Watchdog must NOT spin (CPU idle unchanged)
- Backoff must prevent infinite restart loops
- Must not change FileWatcher's public API

### Assumptions
- `Observer` thread death is detectable via `is_alive()` on the thread object
- FileWatcher can be restarted by creating a new `Observer` instance

### Architecture Invariants
- File change events still trigger indexing identically
- No protocol changes

### Preconditions
- [ ] PR-002 merged (soft — confirmed FileWatcher is live code)
- [ ] Baseline CPU at idle recorded

### Postconditions
- [ ] FileWatcher restarts within 10s of thread death
- [ ] CPU at idle unchanged vs baseline
- [ ] Max restart limit prevents infinite loops

### Success Criteria
- Auto-recovery works on simulated thread death
- No CPU spin

### Failure Criteria
- CPU idle increases
- Infinite restart loop
- Happy-path file watching changes

### Rollback Trigger
CPU spin or infinite restart loop.

### Rollback Completion Criteria
- Watchdog loop removed
- FileWatcher behavior identical to pre-PR-006

---

## PR-007: Add MCP Server Fault Recovery

### Goal
Add periodic heartbeat, auto-reconnect with exponential backoff, tool registry repopulation after reconnect to MCPClientManager.

### Non-goals
- Extending MCP protocol
- Adding new tool discovery mechanisms
- Changing tool execution semantics

### Constraints
- Heartbeat must use existing JSON-RPC methods (e.g., `tools/list` as ping) — no protocol extension
- Reconnect must repopulate tool registry atomically
- Must not affect happy-path tool call latency

### Assumptions
- MCP server subprocess can be reconnected by re-running the stdio initialization handshake
- Tool registry can be fully rebuilt from `tools/list` response

### Architecture Invariants
- `call_tool()` API unchanged
- MCP JSON-RPC protocol unchanged

### Preconditions
- [ ] PR-002 merged (soft)
- [ ] Baseline tool call latency recorded

### Postconditions
- [ ] MCP server reconnects within 10s of subprocess death
- [ ] Tool registry repopulated after reconnect
- [ ] Reconnection uses exponential backoff

### Success Criteria
- Auto-recovery works on simulated subprocess kill
- Tools re-discovered after reconnect

### Failure Criteria
- Tools lost after reconnect
- Heartbeat causes excessive subprocess load
- Happy-path latency increases

### Rollback Trigger
Tool registry loss or performance regression.

### Rollback Completion Criteria
- Heartbeat and reconnect removed
- MCPClientManager behavior identical to pre-PR-007

---

## PR-008: Add Persistent Idempotency Store

### Goal
Replace `InMemoryIdempotencyStore` with SQLite-backed store. Preserve existing API. Add TTL-based pruning.

### Non-goals
- Changing idempotency semantics (TTL, key format)
- Adding distributed idempotency
- Changing tool execution flow

### Constraints
- Must handle concurrent access without `database is locked` errors — **NEED MORE EVIDENCE** on concurrent access patterns
- DB size must be bounded (TTL pruning)
- Must not affect tool execution latency

### Assumptions
- `InMemoryIdempotencyStore` API is the contract (same methods, same semantics)
- SQLite WAL mode is sufficient for concurrent read/write

### Architecture Invariants
- `IdempotencyStore` API unchanged
- Tool execution semantics unchanged

### Preconditions
- [ ] PR-002 merged (soft)

### Postconditions
- [ ] Idempotency entries survive server restart
- [ ] Expired entries are pruned
- [ ] DB size is bounded

### Success Criteria
- Persistence across restart verified
- No DB locking under concurrent access
- DB size bounded

### Failure Criteria
- `OperationalError: database is locked`
- DB grows unbounded
- Tool execution latency increases

### Rollback Trigger
DB locking or unbounded growth.

### Rollback Completion Criteria
- Reverted to `InMemoryIdempotencyStore`
- `DROP TABLE IF EXISTS idempotency_store`

---

## PR-009: Unify Import Convention

### Goal
Choose single import convention, mechanically rename all imports, add ruff/lint rule to enforce.

### Non-goals
- Changing module structure or package layout
- Moving files between directories
- Any functional code change

### Constraints
- **DECISION GATE**: Convention must be chosen before starting
- All feature branches must be notified (merge conflict risk)
- Migration script must be provided for other branches

### Assumptions
- Mechanical rename does not introduce circular imports (if it does: **STOP**, requires architectural resolution)
- `from src.X` convention is the likely choice (used by ~427 files vs ~14 bare)

### Architecture Invariants
- All existing imports resolve after rename
- No functional behavior change
- Lint rule added to CI

### Preconditions
- [ ] All Phase B PRs merged (PR-002, PR-003, PR-004)
- [ ] Import convention decision documented
- [ ] Team notified of upcoming change
- [ ] Migration script prepared and tested

### Postconditions
- [ ] Zero lint violations for import convention
- [ ] All imports resolve
- [ ] Full test suite passes

### Success Criteria
- Single convention enforced by lint
- Zero import errors

### Failure Criteria
- Circular imports discovered
- Import resolution failure
- Any existing test fails

### Rollback Trigger
Circular imports or import resolution failure.

### Rollback Completion Criteria
- All imports reverted to dual convention
- Lint rule removed

---

## PR-010: Consolidate HTTP Clients to httpx

### Goal
Replace aiohttp and requests with httpx in all provider adapters and embedding service. Configure shared connection pool. Remove old dependencies from `pyproject.toml`.

### Non-goals
- Changing LLM provider API contracts
- Adding HTTP/2 features
- Optimizing connection pool beyond matching old capacity

### Constraints
- **DECISION GATE**: HTTP client must be chosen
- SSE streaming must work identically — **NEED MORE EVIDENCE** on aiohttp SSE behavior differences vs httpx
- Connection pool capacity >= sum of old pools

### Assumptions
- httpx supports all SSE patterns used by current providers
- `httpx-sse` extension or equivalent available if needed

### Architecture Invariants
- `LLMManager` API unchanged
- `EmbeddingService` API unchanged
- Response format from each provider unchanged

### Preconditions
- [ ] PR-009 merged
- [ ] HTTP client decision documented
- [ ] Per-provider SSE streaming verified with httpx

### Postconditions
- [ ] Zero imports of `aiohttp` or `requests` in `src/`
- [ ] `aiohttp` and `requests` removed from `pyproject.toml`
- [ ] All providers work with httpx
- [ ] Connection pool stable under 20 concurrent requests

### Success Criteria
- Single HTTP client library
- All providers functional
- SSE streaming works

### Failure Criteria
- Any provider stops working
- SSE streaming breaks (garbled/missing tokens)
- Connection pool exhaustion under load

### Rollback Trigger
Provider failure or SSE streaming breakage.

### Rollback Completion Criteria
- Old HTTP clients restored
- `aiohttp`/`requests` re-added to `pyproject.toml`

---

## PR-011: Implement LLM and Embedding Ports

### Goal
Define `LLMProviderPort` and `EmbeddingPort` interfaces in `core/ports/`. Implement in each provider adapter. Wire `RealAgent` and `domain/knowledge/embeddings.py` through ports.

### Non-goals
- Changing LLM provider behavior
- Adding new providers
- Changing embedding dimensions or model

### Constraints
- Port interface must cover all methods used by `RealAgent` (nothing more)
- `RealAgent` constructor may gain port parameter — must have default preserving old behavior
- `domain/knowledge/embeddings.py` must import from port, not infrastructure

### Assumptions
- Port abstraction does not require changes to `main.py` server wiring that affect WebSocket protocol (if it does: **STOP** — protocol freeze violation)

### Architecture Invariants
- Same prompt → same response through port
- No WebSocket protocol changes
- No REST API changes

### Preconditions
- [ ] PR-010 merged (adapters use unified HTTP client)

### Postconditions
- [ ] `LLMProviderPort` defined with all RealAgent-used methods
- [ ] All 5 provider adapters implement port
- [ ] `RealAgent` uses port, not direct infrastructure import
- [ ] `EmbeddingPort` defined
- [ ] `domain/knowledge/embeddings.py` uses port

### Success Criteria
- Behavior equivalence: same prompt → same response
- No DI violations from domain → infrastructure for LLM/embedding

### Failure Criteria
- Behavior change through port
- Import error
- Port interface too narrow (missing method used at runtime)

### Rollback Trigger
Behavior change or runtime missing-method error.

### Rollback Completion Criteria
- `RealAgent` reverted to direct `LLMManager` import
- Port files can remain (unused) or be deleted

---

## PR-012: Wire Completion to Retrieval Context

### Goal
Add optional retrieval parameter to `CompletionEngine`. Inject cross-file context into FIM prompt. Graceful degradation when retrieval unavailable.

### Non-goals
- Changing the FIM model or provider
- Adding caching for retrieval results
- Changing completion debounce timing

### Constraints
- **DECISION GATE**: Completion context scope must be decided (symbols, recent edits, project structure)
- Retrieval parameter must be optional with default (no retrieval) — existing callers unchanged
- Completion must work when retrieval returns empty

### Assumptions
- Cross-file context improves FIM quality (if it degrades: consider reverting or making it configurable)
- `CompletionEngine` is called from backend, not directly from Electron — **NEED MORE EVIDENCE** on whether Electron uses `ollamaClient.ts` directly

### Architecture Invariants
- `CompletionEngine.complete()` existing signature preserved (new optional param only)
- No WebSocket protocol changes

### Preconditions
- [ ] PR-005 merged (stable retrieval API)
- [ ] PR-011 merged (ports in place)
- [ ] Completion context scope decided
- [ ] Baseline completion quality recorded

### Postconditions
- [ ] `CompletionEngine` accepts optional retrieval parameter
- [ ] Completion works with retrieval context
- [ ] Completion works without retrieval context (graceful degradation)
- [ ] Completion latency within acceptable range

### Success Criteria
- Cross-file awareness in completions
- Graceful degradation
- No latency regression beyond acceptable threshold

### Failure Criteria
- Completion quality degrades with retrieval context
- Completion breaks when retrieval is unavailable
- Latency regression > 50%

### Rollback Trigger
Quality degradation or unacceptable latency.

### Rollback Completion Criteria
- Retrieval parameter removed or defaulted to None
- Completion behavior identical to pre-PR-012
