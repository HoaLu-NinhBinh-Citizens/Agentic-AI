# Files Classification

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13

---

## PR-001: Harden Server Defaults

### Likely Modified Files
- `src/interfaces/server/main.py` — CORS config, file API handler, session TTL
- `src/core/runtime/runtime_manager.py` — `STREAM_TIMEOUT_SEC` constant

### Likely Created Files
- `tests/unit/test_path_validation.py` (or similar)
- `tests/unit/test_cors_config.py` (or similar)
- `tests/integration/test_file_api_security.py` (or similar)

### Likely Deleted Files
- None

### Files That MUST NOT Be Touched
- All files outside `src/interfaces/server/` and `src/core/runtime/`
- `pyproject.toml` (no dependency changes)
- WebSocket handler logic (protocol frozen)
- Any frontend/Electron files

---

## PR-002: Delete Obvious Dead Code Trees

### Likely Modified Files
- `__init__.py` files that re-export symbols from deleted packages
- `pyproject.toml` if entry points reference deleted modules

### Likely Created Files
- None

### Likely Deleted Files
- `src/app/` — entire tree
- `src/domains/` — entire tree
- `src/agent/` — entire tree
- `src/infrastructure/distributed/` — entire tree
- `src/infrastructure/sharding/` — entire tree
- `src/infrastructure/fleet/` — entire tree
- `src/infrastructure/chaos/` — entire tree
- `src/infrastructure/hsm/` — entire tree
- `src/infrastructure/performance/rust/` — entire tree
- `src/core/health/` — entire tree (empty stubs)
- `src/core/checkpoint/` — entire tree (empty stubs)
- Parts of `src/core/execution/` — `worker_pool/`, `executor/`, `task_queue/` if confirmed dead
- Tests for deleted modules

### Files That MUST NOT Be Touched
- `src/interfaces/server/main.py` (production server)
- `src/core/agent/real_agent.py` (production agent)
- `src/infrastructure/retrieval/` (live retrieval code)
- `src/infrastructure/mcp/` (live MCP code)
- `src/infrastructure/indexing/` (live indexing code)
- `src/infrastructure/completion/` (live completion code)
- `src/infrastructure/llm/` (live LLM code)
- `src/infrastructure/embeddings/` (live embedding code)
- `src/core/orchestration/` and `src/core/multi_agent/` — handled in PR-003
- `src/core/events/` — handled in PR-004

---

## PR-003: Consolidate Orchestration System

### Likely Modified Files
- `__init__.py` files with re-exports from deleted orchestration namespace
- `src/core/multi_agent/__init__.py` (re-exports `LangGraphAgent` — may need cleanup)

### Likely Created Files
- None

### Likely Deleted Files
- **If RealAgent-only**: `src/core/orchestration/` (LangGraph) AND `src/core/multi_agent/` (multi-agent bus)
- **If LangGraph kept**: `src/core/multi_agent/` (partial — keep LangGraph re-exports)
- Tests for deleted orchestration system

### Files That MUST NOT Be Touched
- `src/core/agent/real_agent.py` (production agent — keep regardless of decision)
- `src/application/orchestration/` (ToolExecutionService — production)
- `src/interfaces/server/main.py` — unless removing dead imports

---

## PR-004: Resolve EventEmitter Disposition

### Likely Modified Files
- **If wired in**: `src/interfaces/server/main.py` (import and use EventEmitter)
- **If wired in**: Modules that should emit events

### Likely Created Files
- None

### Likely Deleted Files
- **If deleted**: `src/core/events/` — entire tree
- Tests for EventEmitter (if deleted)

### Files That MUST NOT Be Touched
- WebSocket handler event delivery logic (protocol frozen)
- Any file outside `core/events/` and `main.py`

---

## PR-005: Add FTS5 Retrieval Indexing

### Likely Modified Files
- `src/infrastructure/retrieval/chunk_store.py` — FTS5 table creation, insert/update/delete sync
- `src/infrastructure/retrieval/hybrid.py` — `_search_chunk_store()` rewritten to use FTS5
- `src/infrastructure/indexing/incremental.py` — chunk insert must also populate FTS5 (if not handled by ChunkStore)

### Likely Created Files
- `tests/unit/test_fts5_indexing.py` (or similar)
- `tests/integration/test_retrieval_fts5.py` (or similar)
- `tests/benchmark/test_retrieval_benchmark.py` (or similar)

### Likely Deleted Files
- `src/infrastructure/retrieval/vector_index.py` — **if confirmed dead** (NEED MORE EVIDENCE)

### Files That MUST NOT Be Touched
- `src/infrastructure/retrieval/reference_graph.py`
- `src/domain/knowledge/` — domain layer
- `src/infrastructure/embeddings/` — embedding service
- ChromaDB adapter files

---

## PR-006: Add FileWatcher Fault Recovery

### Likely Modified Files
- `src/infrastructure/indexing/file_watcher.py` — add `is_alive()`, watchdog loop, backoff

### Likely Created Files
- `tests/unit/test_file_watcher_recovery.py` (or similar)

### Likely Deleted Files
- None

### Files That MUST NOT Be Touched
- `src/infrastructure/indexing/incremental.py` (indexer logic)
- `src/infrastructure/indexing/service.py` (indexing service)
- All other files

---

## PR-007: Add MCP Server Fault Recovery

### Likely Modified Files
- `src/infrastructure/mcp/manager.py` — add `health_check()`, `reconnect()`, heartbeat loop

### Likely Created Files
- `tests/unit/test_mcp_recovery.py` (or similar)

### Likely Deleted Files
- None

### Files That MUST NOT Be Touched
- MCP config files (`configs/mcp/servers.yaml`)
- MCP protocol handling (JSON-RPC format frozen)
- All other files

---

## PR-008: Add Persistent Idempotency Store

### Likely Modified Files
- `src/core/execution/idempotency.py` — add SQLite-backed implementation

### Likely Created Files
- `tests/unit/test_persistent_idempotency.py` (or similar)

### Likely Deleted Files
- None (`InMemoryIdempotencyStore` may be kept as fallback or test utility)

### Files That MUST NOT Be Touched
- `src/core/execution/tool_executor.py` (if exists — execution logic)
- `src/application/orchestration/` (ToolExecutionService)
- All other files

---

## PR-009: Unify Import Convention

### Likely Modified Files
- **All Python files in `src/`** — import statement changes (~400+ files after dead code deletion)
- **All Python files in `tests/`** — import statement changes
- CI/linter config — add import convention lint rule
- `pyproject.toml` — PYTHONPATH / package config if needed

### Likely Created Files
- `scripts/migrate_imports.py` (or similar migration script for other branches)
- Lint rule configuration

### Likely Deleted Files
- None

### Files That MUST NOT Be Touched
- File content beyond import statements (no logic changes)
- `configs/` directory
- Documentation files
- Frontend/Electron files
- Vendor/generated files

---

## PR-010: Consolidate HTTP Clients to httpx

### Likely Modified Files
- `src/infrastructure/llm/client.py` — may already use httpx
- `src/infrastructure/llm/anthropic_llm.py` — HTTP client swap
- `src/infrastructure/llm/openai_llm.py` — if uses aiohttp/requests
- `src/infrastructure/llm/ollama_provider.py` — if uses aiohttp/requests
- `src/infrastructure/llm/gemini_llm.py` — if uses aiohttp/requests
- `src/infrastructure/llm/groq_provider.py` — if uses aiohttp/requests
- `src/infrastructure/embeddings/embedding_service.py` — aiohttp → httpx
- `pyproject.toml` — remove aiohttp, requests dependencies

### Likely Created Files
- `tests/integration/test_provider_streaming.py` (per-provider SSE test)

### Likely Deleted Files
- None (files modified, not deleted)

### Files That MUST NOT Be Touched
- `src/core/agent/real_agent.py` — agent logic (uses LLM via manager, not directly)
- `src/domain/` — domain layer
- `src/interfaces/server/main.py` — server wiring
- Provider API contracts (response format, error types)

---

## PR-011: Implement LLM and Embedding Ports

### Likely Modified Files
- `src/core/ports/llm_provider/__init__.py` — populate with port interface
- `src/core/agent/real_agent.py` — use port instead of direct infrastructure import
- `src/domain/knowledge/embeddings.py` — use embedding port instead of `EmbeddingService`
- Each LLM provider adapter — implement port interface
- `src/interfaces/server/main.py` — wire port into RealAgent constructor (if needed)

### Likely Created Files
- `src/core/ports/llm_provider/port.py` (or similar — port interface definition)
- `src/core/ports/embedding/port.py` (or similar)
- `tests/unit/test_llm_port.py`
- `tests/unit/test_embedding_port.py`

### Likely Deleted Files
- None

### Files That MUST NOT Be Touched
- WebSocket handler (protocol frozen)
- REST endpoint handlers
- Storage/DB files
- MCP files

---

## PR-012: Wire Completion to Retrieval Context

### Likely Modified Files
- `src/infrastructure/completion/completion_engine.py` — add optional retrieval parameter, modify FIM prompt
- `src/interfaces/server/main.py` — wire retrieval into CompletionEngine (if server-side completion)

### Likely Created Files
- `tests/unit/test_completion_with_retrieval.py`
- `tests/integration/test_completion_retrieval_e2e.py`

### Likely Deleted Files
- None

### Files That MUST NOT Be Touched
- `src/infrastructure/retrieval/` — retrieval logic (stable from PR-005)
- LLM provider files
- WebSocket protocol
- Frontend completion files (Electron `ollamaClient.ts`) — **NEED MORE EVIDENCE** on whether this is used

---

## Summary: NEED MORE EVIDENCE Items

| Item | Affects | Resolution Method |
|------|---------|-------------------|
| Electron app `Origin` header value | PR-001 (CORS allowlist) | Inspect Electron main process or capture in network log |
| External plugins importing dead packages | PR-002 (undiscovered callers) | Grep all non-Python files for deleted package names |
| VectorIndex live/dead status | PR-005 (delete or fix) | Trace `HybridRetriever` initialization |
| aiohttp SSE behavior vs httpx | PR-010 (streaming compatibility) | Build prototype, test with each provider |
| Concurrent SQLite access for idempotency | PR-008 (DB locking) | Profile `InMemoryIdempotencyStore` usage patterns |
| Electron completion path (`ollamaClient.ts` vs backend) | PR-012 (scope) | Inspect `useInlineCompletion.ts` |
| Plugins using `aiohttp`/`requests` directly | PR-010 (breaking change) | Grep for imports outside `src/infrastructure/` |
