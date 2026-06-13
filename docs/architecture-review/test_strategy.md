# Test Strategy — Refactoring Validation

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13
> **Scope**: Covers all 6 engineering tasks (T-01 through T-06) from the refactor strategy.

---

## 1. T-02 / T-06: Harden Server Defaults

### Affected Components
- `src/interfaces/server/main.py` — CORS config, file API, stream timeout, session TTL
- `src/core/runtime/runtime_manager.py` — `STREAM_TIMEOUT_SEC` constant

### Affected Interfaces
- `/api/fs/read` — path validation added
- `/health` — unchanged
- WebSocket `/ws/{session_id}` — stream timeout behavior changes
- CORS headers — origins restricted

### Affected Storage
- None

### Affected Caches
- Session cache TTL may change (P-11)

### Critical Paths
1. File API path traversal: `Path(user_input).resolve()` must stay within workspace root
2. Stream timeout: must not kill valid LLM generations; must still kill hung streams
3. CORS: Electron IDE must still connect after origin restriction

---

### Unit Tests

**T-02-U01: Path traversal rejection**
- Input: `../../etc/passwd`, `C:\Windows\System32\config\SAM`, `..\..\..`, absolute paths outside workspace
- Expected: 403 Forbidden for each
- Input: valid relative path within workspace
- Expected: 200 OK with file content

**T-02-U02: Path normalization edge cases**
- Input: symlink pointing outside workspace
- Expected: 403 Forbidden
- Input: path with `..` segments that resolve inside workspace (e.g., `src/../src/main.py`)
- Expected: 200 OK

**T-02-U03: Stream timeout configuration**
- Assert `STREAM_TIMEOUT_SEC` >= 120
- Assert timeout is configurable via environment variable or config

**T-02-U04: CORS origin validation**
- Assert `allow_origins` does not contain `"*"`
- Assert configured origins include the Electron app origin

**T-02-U05: Session TTL appropriateness**
- Assert default TTL >= 3600s (1hr) for IDE use case
- Verify TTL refresh on activity (session access resets TTL)

### Integration Tests

**T-02-I01: File API end-to-end security**
- Start server with a defined workspace root
- HTTP request to `/api/fs/read` with path outside workspace → 403
- HTTP request to `/api/fs/read` with valid path → 200 + correct content
- HTTP request to `/api/fs/read` with nonexistent path → 404

**T-02-I02: Stream timeout with real LLM mock**
- Start server with mock LLM that streams tokens for 60s
- Send chat message via WebSocket
- Assert: stream is NOT killed at 30s
- Assert: stream completes or hits the new (longer) timeout

**T-02-I03: CORS enforcement**
- Send HTTP request with `Origin: http://evil.example.com`
- Assert: no `Access-Control-Allow-Origin` header in response
- Send HTTP request with allowed origin
- Assert: correct CORS headers present

**T-02-I04: Session TTL with activity**
- Create session
- Wait 50% of TTL
- Access session (simulating activity)
- Wait another 50% of original TTL
- Assert: session is still alive (TTL was refreshed)

### Regression Tests

**T-02-R01: Existing file reads still work**
- All previously valid file read paths (relative to workspace) must return identical content

**T-02-R02: Chat still works end-to-end**
- Send chat message → receive token stream → receive done event
- Verify no timeout for normal-length responses

**T-02-R03: Electron IDE connectivity**
- WebSocket connection from Electron origin succeeds
- Full chat round-trip works

### Negative Tests

**T-02-N01: Null byte injection in file path**
- Input: `src/main.py%00.txt`
- Expected: 400 or 403

**T-02-N02: Unicode path traversal**
- Input: paths with Unicode directory separators or homoglyphs
- Expected: 403 for traversal attempts

**T-02-N03: Very long file path**
- Input: path exceeding OS max path length
- Expected: 400

### Security Tests

**T-02-S01: Directory listing prevention**
- `/api/fs/read` with a directory path → 400 (not a file listing)

**T-02-S02: Sensitive file protection**
- Paths matching `.env`, `*.key`, `*.pem`, credentials patterns → 403 or configurable deny list

**T-02-S03: Symlink escape**
- Create symlink inside workspace pointing to `/etc/passwd` (or equivalent)
- `/api/fs/read` on symlink path → 403

---

## 2. T-01: Dead Code Audit & Consolidation

### Affected Components
- `src/app/` — entire tree (deletion candidate)
- `src/domains/` — entire tree (deletion candidate)
- `src/agent/` — entire tree (deletion candidate)
- `src/infrastructure/{distributed,sharding,fleet,chaos,hsm,performance/rust}/` — deletion candidates
- `src/core/{health,checkpoint}/` — deletion candidates (empty stubs)
- `src/core/multi_agent/` OR `src/core/orchestration/` — one deleted based on decision
- `src/core/events/` — delete or wire in based on evidence

### Affected Interfaces
- None directly (dead code has no callers)
- Risk: undiscovered callers break

### Affected Storage
- None

### Affected Caches
- None

### Critical Paths
1. Import graph verification: every deleted module must have zero live importers
2. Orchestration decision: the kept system must handle all existing workflows
3. Test fixtures: some tests may import from dead modules

---

### Unit Tests

**T-01-U01: Import graph integrity**
- For every deleted package, assert zero imports from any remaining `.py` file
- Implementation: static analysis script using AST or grep

**T-01-U02: `__init__.py` export completeness**
- After deletion, every `__init__.py` that previously re-exported deleted symbols must be updated
- Assert: no `ImportError` when importing any remaining package's public API

**T-01-U03: Orchestration path correctness**
- The surviving orchestration system's public API must cover all methods used by `main.py`
- Assert: `RealAgent`, `RuntimeManager`, `ToolExecutionService` import successfully

### Integration Tests

**T-01-I01: Server startup after deletion**
- `python -c "from interfaces.server.main import app"` succeeds
- `uvicorn interfaces.server.main:app --host 0.0.0.0 --port 0` starts without import errors

**T-01-I02: Full import tree**
- Recursively import every remaining package under `src/`
- Assert: zero `ImportError`, zero `ModuleNotFoundError`

**T-01-I03: Existing test suite passes**
- `python -m pytest tests/` — all previously passing tests still pass
- Tests that imported deleted modules are expected to fail and must be updated or removed

### Regression Tests

**T-01-R01: Server startup dependencies**
- The 10-step startup sequence from `data_flow.md` §4 must complete without error

**T-01-R02: Chat round-trip**
- WebSocket chat message → token stream → done — identical behavior

**T-01-R03: Tool execution**
- Tool call via WebSocket → tool result — identical behavior

**T-01-R04: Indexing pipeline (if enabled)**
- `AI_SUPPORT_ENABLE_INDEXING=1` → indexing starts, processes files, no import errors

### Negative Tests

**T-01-N01: Importing deleted modules fails cleanly**
- `import src.app` → `ModuleNotFoundError`
- `import src.domains` → `ModuleNotFoundError`
- No partial imports or zombie `__init__.py` files

### End-to-End Tests

**T-01-E01: Full workflow after consolidation**
- Start server → connect WebSocket → send chat → receive response → send tool call → receive result → disconnect
- Assert: identical behavior to pre-deletion baseline

---

## 3. T-03: Add Retrieval Indexing (FTS)

### Affected Components
- `src/infrastructure/retrieval/hybrid.py` — `_search_chunk_store()` method
- `src/infrastructure/retrieval/chunk_store.py` — FTS5 table addition
- `src/infrastructure/retrieval/vector_index.py` — verify if exercised or dead

### Affected Interfaces
- `HybridRetriever.search_docs()` — return type and ranking may change
- `ChunkStore` — new FTS5 methods

### Affected Storage
- SQLite: new FTS5 virtual table alongside chunk data
- Migration: existing chunk data must be indexed into FTS5

### Affected Caches
- None directly, but retrieval results feed into LLM prompt construction

### Critical Paths
1. FTS5 index must return results that are a superset of the old linear scan for the same query
2. Ranking order may change — must verify relevance quality does not degrade
3. Migration: existing indexed chunks must populate the FTS5 table

---

### Unit Tests

**T-03-U01: FTS5 index CRUD**
- Insert chunk → FTS5 search by terms → found
- Delete chunk → FTS5 search → not found
- Update chunk content → FTS5 search reflects new content

**T-03-U02: FTS5 query syntax**
- Single term search
- Multi-term AND search
- Phrase search
- Prefix search (`test*`)
- Special characters in query (parentheses, quotes) — handled without SQL injection

**T-03-U03: Lexical search equivalence**
- For a fixed set of 100 chunks and 20 queries, assert: every result from old `get_all()` scan appears in FTS5 results (recall >= 1.0)
- Precision may differ (FTS5 may return additional relevant results)

**T-03-U04: VectorIndex path determination**
- If `VectorIndex` is dead code: assert it is deleted (covered by T-01)
- If `VectorIndex` is live: unit test its search correctness with known embeddings

**T-03-U05: Empty index behavior**
- FTS5 search on empty index → empty results, no error

**T-03-U06: Large document handling**
- Insert chunk with 100K characters → FTS5 indexes and searches correctly

### Integration Tests

**T-03-I01: Retrieval pipeline end-to-end**
- Index 100 files via `IncrementalIndexer`
- Query via `HybridRetriever.search_docs()`
- Assert: results returned in < target latency (see benchmark_plan.md)
- Assert: results are relevant (top-5 contain expected files for known queries)

**T-03-I02: Incremental index update**
- Index files → modify one file → re-index → search
- Assert: updated content appears in results; old content does not

**T-03-I03: Migration from existing data**
- Start with pre-existing ChunkStore data (no FTS5 table)
- Run migration
- Assert: FTS5 table populated, search works on migrated data

### Regression Tests

**T-03-R01: Retrieval result quality**
- Define a golden set: 10 queries with expected top-5 results (manually curated)
- After FTS5 migration, all golden queries return expected results in top-10

**T-03-R02: HybridRetriever API compatibility**
- `search_docs()` return type is unchanged (`list[RetrievalHit]`)
- All existing callers of `search_docs()` work without modification

**T-03-R03: Indexing pipeline unaffected**
- `IncrementalIndexer` still hashes, parses, chunks, embeds, and stores identically
- Only the ChunkStore's internal search changes

### Benchmark Tests

**T-03-B01: Lexical search latency**
- Measure: time for `_search_chunk_store()` with 1K, 10K, 100K chunks
- Compare: old O(N) scan vs FTS5
- Assert: FTS5 is sublinear

**T-03-B02: Index build time**
- Measure: time to build FTS5 index from 100K chunks
- This is a one-time migration cost

**T-03-B03: Incremental update cost**
- Measure: time to update FTS5 index for a single chunk insert/update/delete

### Negative Tests

**T-03-N01: SQL injection via search query**
- Input: `"; DROP TABLE chunks; --`
- Expected: parameterized query prevents injection; returns empty or safe results

**T-03-N02: Corrupt FTS5 index**
- Simulate FTS5 table corruption (e.g., delete the shadow tables)
- Expected: graceful error, fallback or rebuild, not crash

---

## 4. T-04: Unify Infrastructure Standards

### Affected Components
- All `.py` files with `from src.` imports (~427 files) OR bare imports (~14 files) — depending on convention chosen
- `src/infrastructure/llm/client.py` — HTTP client consolidation
- `src/infrastructure/embeddings/embedding_service.py` — HTTP client swap
- `src/core/agent/real_agent.py` — DI via LLM port
- `src/core/ports/llm_provider/` — implement port interface
- `src/infrastructure/completion/completion_engine.py` — retrieval context injection
- `src/domain/knowledge/embeddings.py` — decouple from infrastructure

### Affected Interfaces
- Import paths change across the codebase
- `CompletionEngine` constructor gains retrieval dependency
- `RealAgent` constructor gains LLM port dependency
- `EmbeddingService` interface extracted to port

### Affected Storage
- None

### Affected Caches
- Completion cache key may change if context is added to FIM prompt

### Critical Paths
1. Import convention change: every existing import must resolve after the switch
2. HTTP client swap: every LLM provider adapter must work with the unified client
3. LLM port: `RealAgent` must produce identical responses through the port
4. Completion context: FIM quality must not degrade

---

### Unit Tests

**T-04-U01: Import convention lint rule**
- Run linter (ruff/custom rule) on entire codebase
- Assert: zero violations of the chosen convention
- Assert: no file uses the rejected convention

**T-04-U02: LLM port interface completeness**
- Assert: `LLMProviderPort` defines all methods used by `RealAgent`
- Assert: each provider adapter (`openai_llm`, `anthropic_llm`, `ollama_provider`, `gemini_llm`, `groq_provider`) implements the port

**T-04-U03: LLM port behavior equivalence**
- For each provider adapter: mock HTTP, call via port → same response as direct call

**T-04-U04: Embedding port interface**
- Assert: `EmbeddingPort` defines `embed()` method
- Assert: `domain/knowledge/embeddings.py` uses port, not concrete `EmbeddingService`

**T-04-U05: HTTP client unification**
- Assert: `aiohttp` is not imported anywhere in the codebase (if httpx chosen)
- Assert: `requests` is not imported anywhere in the codebase
- Assert: single `httpx.AsyncClient` instance is shared or pool-managed

**T-04-U06: CompletionEngine with retrieval context**
- Mock retrieval returning cross-file symbols
- Assert: FIM prompt includes cross-file context
- Assert: completion still works when retrieval returns empty

### Integration Tests

**T-04-I01: All imports resolve**
- `python -c "import importlib; importlib.import_module('src')"` style recursive import of every package
- Assert: zero import errors

**T-04-I02: LLM generation through port**
- Start server → send chat → receive response
- Assert: response quality indistinguishable from pre-port implementation

**T-04-I03: Embedding via port**
- Index a file → verify embedding is stored
- Assert: embedding dimensions and values match pre-port behavior

**T-04-I04: HTTP client pool behavior**
- Concurrent LLM + embedding + completion requests
- Assert: all succeed, single connection pool is used
- Assert: no connection pool exhaustion under 20 concurrent requests

**T-04-I05: Completion with retrieval context**
- Index a multi-file project
- Request completion in file A that references symbols from file B
- Assert: completion includes cross-file awareness (qualitative check)

### Regression Tests

**T-04-R01: Provider-specific behavior preserved**
- For each LLM provider: send same prompt → assert response format is identical
- Tool call accumulation still works
- Streaming still works
- Error handling (rate limit, auth failure) still produces correct error types

**T-04-R02: Embedding determinism**
- Same input text → same embedding vector (within floating point tolerance)

**T-04-R03: Completion quality baseline**
- Define 10 completion scenarios with expected outputs
- Assert: post-refactor completions are at least as good (manual review or automated metric)

**T-04-R04: Connection pool resource usage**
- After consolidation, max open connections should be <= sum of previous pools
- No file descriptor leaks under sustained load

### Negative Tests

**T-04-N01: Missing provider API key**
- Remove all API keys → assert graceful fallback to Ollama
- Assert: no unhandled exception, clear error message

**T-04-N02: Retrieval service down during completion**
- CompletionEngine with retrieval dependency that throws
- Assert: completion still works with local-only context (graceful degradation)

---

## 5. T-05: Add Fault Recovery

### Affected Components
- `src/infrastructure/indexing/file_watcher.py` — watchdog restart loop
- `src/infrastructure/mcp/manager.py` — heartbeat + auto-reconnect
- `src/core/execution/idempotency.py` — SQLite persistence

### Affected Interfaces
- `MCPClientManager` — new `health_check()` and `reconnect()` methods
- `FileWatcher` — new `is_alive()` method
- `IdempotencyStore` — persists across restarts

### Affected Storage
- New SQLite table for idempotency store (or column in existing DB)
- Idempotency entries survive server restart

### Affected Caches
- Idempotency store transitions from in-memory to persistent

### Critical Paths
1. FileWatcher must restart within configurable interval after thread death
2. MCP servers must reconnect without losing tool registry
3. Idempotency store must not grow unbounded (TTL still applies)

---

### Unit Tests

**T-05-U01: FileWatcher restart on thread death**
- Start FileWatcher → kill Observer thread → assert: new Observer thread starts within timeout
- Verify: file change events resume after restart

**T-05-U02: FileWatcher health check**
- `is_alive()` returns True when Observer is running
- `is_alive()` returns False when Observer thread is dead

**T-05-U03: MCP server heartbeat**
- Mock MCP server that responds to heartbeat → assert: server marked healthy
- Mock MCP server that does not respond → assert: server marked unhealthy after timeout

**T-05-U04: MCP server auto-reconnect**
- Kill MCP subprocess → assert: reconnection attempted
- Assert: tool registry repopulated after reconnect
- Assert: reconnection uses exponential backoff

**T-05-U05: Persistent idempotency store CRUD**
- Store entry → retrieve → matches
- Store entry → restart (new instance, same DB) → retrieve → matches
- Store entry → wait past TTL → retrieve → not found (expired)

**T-05-U06: Idempotency store bounded growth**
- Insert 10,000 entries → assert: DB size is bounded
- Expired entries are pruned on schedule or access

### Integration Tests

**T-05-I01: FileWatcher recovery end-to-end**
- Start IndexingService → kill Observer thread → modify a file → assert: file is re-indexed after watcher restarts

**T-05-I02: MCP server crash and recovery**
- Start server with MCP config → kill MCP subprocess → call tool → assert: tool call fails with clear error → wait for reconnect → call tool again → succeeds

**T-05-I03: Idempotency across server restart**
- Execute tool with idempotency key → record result → restart server → execute same tool with same key → assert: same result returned (deduplicated)

**T-05-I04: Multiple MCP server recovery**
- Start 3 MCP servers → kill 1 → assert: other 2 unaffected
- Killed server reconnects independently

### Regression Tests

**T-05-R01: FileWatcher happy path unchanged**
- File modification → indexing triggered — same behavior as before

**T-05-R02: MCP tool execution happy path unchanged**
- Tool call → result — same latency and behavior as before

**T-05-R03: Idempotency deduplication still works**
- Duplicate tool call within TTL → deduplicated — same behavior as before

### Negative Tests

**T-05-N01: FileWatcher restart limit**
- Kill Observer thread 10 times rapidly → assert: backoff increases, no infinite restart loop, alert emitted

**T-05-N02: MCP server permanently unavailable**
- MCP server binary deleted → reconnection fails → assert: server marked permanently failed after max retries, clear error surfaced

**T-05-N03: Idempotency DB corruption**
- Corrupt SQLite file → assert: graceful fallback (in-memory or rebuild), not crash

**T-05-N04: Idempotency DB locked**
- Hold exclusive lock on DB file → assert: timeout and clear error, not hang

---

## 6. Cross-Task Testing

### End-to-End Tests (All Tasks)

**E2E-01: Full server lifecycle after all refactoring**
- Start server → all subsystems initialize → connect client → chat → tool call → completion → disconnect → shutdown
- Assert: identical user-facing behavior to pre-refactoring baseline

**E2E-02: Indexing + Retrieval + Completion pipeline**
- Enable indexing → index files → modify file → re-index → chat with retrieval context → inline completion
- Assert: all subsystems interact correctly

**E2E-03: Fault injection during operation**
- During active chat: kill MCP server, kill FileWatcher, corrupt a cache
- Assert: errors are surfaced, recovery happens, no data corruption

### Test Execution Order

```
Phase A (T-02/T-06):
  1. Run T-02 unit tests
  2. Run T-02 integration tests
  3. Run T-02 security tests
  4. Run full existing test suite (regression)

Phase B (T-01):
  1. Run import graph analysis (T-01-U01)
  2. Delete dead code
  3. Run T-01 integration tests (server startup, import tree)
  4. Run full existing test suite — update/remove tests for deleted modules
  5. Run E2E-01

Phase C1 (T-03):
  1. Run T-03 unit tests
  2. Run T-03 integration tests
  3. Run T-03 benchmark tests
  4. Run retrieval regression tests (T-03-R01)
  5. Run E2E-02

Phase C2 (T-05) — parallel with C1:
  1. Run T-05 unit tests
  2. Run T-05 integration tests
  3. Run T-05 negative tests
  4. Run E2E-03

Phase D (T-04):
  1. Run T-04-U01 (lint rule) after import convention change
  2. Run T-04 unit tests
  3. Run T-04 integration tests
  4. Run full existing test suite (regression)
  5. Run E2E-01 + E2E-02

Final:
  Run all tests together
  Run all benchmarks
  Manual validation checklist (see validation_checklist.md)
```
