# Current Architectural Problems

> **Document type**: Read-only baseline analysis — no code was modified.
> **Date**: 2026-06-13
> **Rule**: Only evidence-backed observations. No solutions proposed.

---

## P-01: O(N) Lexical Scan in Hybrid Retrieval

**Problem**: `HybridRetriever._search_chunk_store()` calls `self.chunk_store.get_all()` and iterates over every chunk to compute lexical relevance scores. There is no full-text search index.

**Evidence**: `src/infrastructure/retrieval/hybrid.py` line 55: `for chunk in self.chunk_store.get_all():`

**Root cause**: No FTS index (SQLite FTS5, Tantivy, or equivalent) was implemented for the chunk store. Lexical search is a linear scan.

**Confidence**: High — directly observed in source code, confirmed in two separate review sessions (2026-06-11 and 2026-06-13).

---

## P-02: Timeout Mismatch Between LLM Providers and Server Stream

**Problem**: The server's `RuntimeManager` enforces a 30-second stream timeout (`STREAM_TIMEOUT_SEC = 30.0`). However, LLM provider adapters allow significantly longer timeouts — Anthropic's adapter computes `120 + prompt_chars/50`, capped at 300 seconds.

This means a long LLM generation will be killed by the server timeout after 30s, even though the provider hasn't timed out yet. The client sees a `TIMEOUT` error for a response that was still being generated.

**Evidence**:
- `src/core/runtime/runtime_manager.py` line 23: `STREAM_TIMEOUT_SEC = 30.0`
- `src/infrastructure/llm/anthropic_llm.py`: timeout formula `120 + prompt_chars/50`, max 300s
- `src/core/runtime/runtime_manager.py` line 81: `await asyncio.wait_for(..., timeout=STREAM_TIMEOUT_SEC)`

**Root cause**: The server stream timeout was set for the Phase 1B "minimal viable server" and was never updated when real LLM providers (with longer generation times) were integrated.

**Confidence**: High — values read directly from source.

---

## P-03: Dual Orchestration Systems with Unclear Production Path

**Problem**: Three orchestration namespaces exist:
1. `core/orchestration/` — LangGraph-based workflows (AgentState, WorkflowState, RollbackEngine)
2. `core/multi_agent/` — Message bus-based multi-agent system (OrchestratorAgent, CodeGenAgent, etc.)
3. `application/orchestration/` — ToolExecutionService with middleware

The server (`main.py`) uses none of the first two directly. It instantiates `RealAgent` and `ToolExecutionService` only. The LangGraph and multi-agent systems are fully implemented but appear unwired from the serving path.

Additionally, `core/multi_agent/__init__.py` re-exports `LangGraphAgent` and `LangGraphOrchestrator` from `core/orchestration/`, creating a circular alias relationship.

**Evidence**:
- `main.py` lines 43-44: imports `RealAgent` from `core.agent.real_agent`, not from any orchestration module
- `main.py` line 160: `ToolExecutionService(session_manager)` — from `application.orchestration`, not `core.orchestration`
- `core/multi_agent/__init__.py` line 52: `from src.core.orchestration.langgraph_agent import LangGraphAgent, LangGraphOrchestrator`

**Root cause**: Multiple orchestration approaches were built in parallel (phases 1-5) without consolidation. The server was wired to the simplest path (`RealAgent`).

**Confidence**: High for the aliasing. Medium for whether the orchestration systems are *never* used — they could be invoked through code paths not explored in this review (e.g., specific workflow triggers).

---

## P-04: ~40% Dead/Orphaned Code

**Problem**: Large portions of the codebase have no production call sites:
- `src/app/` — shadow API server, orchestrator, embedded agent
- `src/domains/` — shadow of `src/domain/` (note the trailing 's')
- `src/agent/` — thin alias re-exporting from `core.agent`
- `infrastructure/distributed/`, `infrastructure/sharding/`, `infrastructure/fleet/`, `infrastructure/chaos/`, `infrastructure/hsm/` — stub packages
- `infrastructure/performance/rust/` — Cargo.toml with no Python imports
- `core/health/` — four empty sub-packages (liveness, readiness, runtime_health)
- `core/checkpoint/` — four empty sub-packages (checkpoint_manager, replay, rollback, snapshot)
- Parts of `core/execution/` — `worker_pool/`, `executor/`, `task_queue/` are stubs

**Evidence**:
- Glob search for `__init__.py` in these directories shows empty files or minimal pass-through
- Import grep across the serving path (`interfaces/server/main.py` and its transitive imports) finds zero references to these modules
- Confirmed in prior session (2026-06-11)

**Root cause**: Speculative scaffolding created during phased development (Phase 1-5 structure). Packages were created ahead of implementation and never filled or removed.

**Confidence**: High for listed packages. The exact percentage (40%) is estimated from file counts, not verified by automated dead-code analysis.

---

## P-05: Dual Import Convention

**Problem**: Two import styles coexist across the codebase:
1. `from src.domain.knowledge.kb import KnowledgeBase` (~427 files)
2. `from domain.models.execution import ExecutionRequest` (~14 files)

Both work because PYTHONPATH includes both the repo root and `src/`. The server also manually adds `src/` to `sys.path` at startup.

**Evidence**:
- `main.py` lines 31-33: `_SRC_DIR = Path(__file__).parent.parent.parent; sys.path.insert(0, str(_SRC_DIR))`
- `pyproject.toml` line 79-80: `"" = "src"` and `"agentic_ai" = "src/agentic_ai"`
- `pyproject.toml` line 100: `pythonpath = ["src", "."]`
- grep for `from src.` vs bare imports shows the split

**Root cause**: The project was initially structured with `src/` prefix imports, then some modules (particularly those added for the server in Phase 2B) switched to bare imports. No linting rule enforces consistency.

**Confidence**: High

---

## P-06: Dependency Inversion Violations

**Problem**: The domain layer directly depends on infrastructure:
1. `domain/knowledge/embeddings.py` imports `EmbeddingService` from `infrastructure/embeddings/` — an HTTP client to Ollama
2. `core/agent/real_agent.py` imports `LLMManager`, `LLMConfig`, `ModelProvider` from `infrastructure/llm/` inside a method body

Port interfaces exist but are empty:
- `core/ports/llm_provider/__init__.py` — empty
- `core/ports/vector_store/__init__.py` — status unknown
- `domain/ports/knowledge_store.py` — implemented (used by ChromaDB adapter)

**Evidence**:
- `real_agent.py` lines 39-43: lazy `from infrastructure.llm.llm_manager import ...`
- `core/ports/llm_provider/__init__.py`: empty file (5 bytes)

**Root cause**: Port scaffolding was created but implementations were wired directly to infrastructure for speed. The port pattern is partially applied (KnowledgeStore port exists and is used, LLMProvider port does not).

**Confidence**: High

---

## P-07: No Health Probes

**Problem**: The server exposes only a trivial `/health` endpoint that returns `{"status": "ok"}` unconditionally. It does not check:
- SQLite connection health
- LLM provider availability
- MCP server subprocess health
- Indexing service status
- Memory/resource usage

The `core/health/` package exists with four sub-packages (`liveness/`, `readiness/`, `runtime_health/`) but all contain only empty `__init__.py` files.

**Evidence**:
- `main.py` lines 253-256: `/health` returns static dict
- `core/health/liveness/__init__.py`, `core/health/readiness/__init__.py`: empty files

**Root cause**: Health probes were scaffolded but never implemented.

**Confidence**: High

---

## P-08: No FileWatcher or MCP Server Recovery

**Problem**:
1. `FileWatcher` uses watchdog's `Observer` thread. If the thread dies (exception, OOM), there is no heartbeat or restart mechanism. Indexing stops silently.
2. MCP server subprocesses have no heartbeat. If a subprocess dies, it is not detected until the next JSON-RPC call, which then fails. There is no automatic reconnection.

**Evidence**:
- `infrastructure/indexing/file_watcher.py`: `Observer.start()` is called once. No health check loop.
- `infrastructure/mcp/manager.py`: `ConnectedServer` holds subprocess reference but no periodic liveness check.

**Root cause**: Both subsystems were designed for happy-path operation. Fault recovery was deferred.

**Confidence**: High

---

## P-09: Three HTTP Client Libraries

**Problem**: The codebase uses three different HTTP client libraries concurrently:
1. `httpx` — LLM client, completion engine (async)
2. `aiohttp` — embedding service, SSE streaming (async)
3. `requests` — some legacy/sync LLM adapters

Each maintains its own connection pool. There is no shared pool or unified client.

**Evidence**:
- `infrastructure/llm/client.py`: `httpx.AsyncClient` with pool config
- `infrastructure/embeddings/embedding_service.py`: `aiohttp.ClientSession`
- `infrastructure/llm/anthropic_llm.py`: uses HTTP directly (pattern varies by adapter)
- `pyproject.toml` lists both `httpx` and `aiohttp` in dependencies

**Root cause**: Different subsystems were developed at different times, each choosing the HTTP library available/preferred at that point.

**Confidence**: High

---

## P-10: Completion Engine Not Connected to Retrieval

**Problem**: `CompletionEngine` takes only `file_path, cursor_line, cursor_col, source_before, source_after` as input. It does not access the `KnowledgeBase`, `HybridRetriever`, or `ReferenceGraph` for cross-file context.

**Evidence**: `infrastructure/completion/completion_engine.py` constructor and `complete()` method signatures take no retrieval-related dependencies. The FIM prompt is built from local file context only.

**Root cause**: The completion engine was implemented as a standalone Ollama FIM wrapper. Integration with the retrieval pipeline was not part of its design.

**Confidence**: High

---

## P-11: Session TTL May Expire During Long Work

**Problem**: `PersistentSessionManager` uses a default TTL of 1 hour (3600s). Long coding sessions that don't make API calls within the TTL window may have their session expired from the in-memory cache. The session data still exists in SQLite but the in-memory state (tool registry, MCP references) would be lost.

**Evidence**: Prior review session identified this. Exact TTL value configurable but default is 3600s.

**Root cause**: TTL was designed for server memory management, not for long-lived IDE sessions.

**Confidence**: Medium — behavior depends on whether the Electron IDE makes periodic keep-alive calls. NEED MORE EVIDENCE on the Electron side.

---

## P-12: EventEmitter Disconnected from Server Event Loop

**Problem**: The `core/events/` module provides a full `EventEmitter` with `LoggingMiddleware`, `MetricsMiddleware`, and domain event types. However, the server's WebSocket handler sends events directly via `send_event` callbacks. The two event systems appear disconnected.

**Evidence**:
- `main.py` does not import from `core.events`
- `main.py:458`: `async def send_event(event): await client.send_event(event)` — direct WebSocket send
- `core/events/__init__.py`: exports `EventEmitter`, `event_emitter` singleton

**Root cause**: The domain event system and the transport event system were developed independently.

**Confidence**: Medium — the `EventEmitter` could be used within subsystems not explored in this review. Its absence from the main server loop is confirmed.

---

## P-13: VectorIndex Brute-Force Cosine Similarity

**Problem**: `infrastructure/retrieval/vector_index.py` implements vector search using NumPy matrix operations — brute-force cosine similarity over all stored vectors. This is O(N) per query.

ChromaDB (used by `KnowledgeBase`) has HNSW indexing internally. But the separate `VectorIndex` class used by `HybridRetriever` does not use HNSW.

**Evidence**: Prior deep-dive agent reported `VectorIndex` loads/persists as `.npz` and uses `np.dot` for cosine similarity.

**Root cause**: Two vector search implementations exist — ChromaDB (via `KnowledgeStore` port) and `VectorIndex` (NumPy). The `HybridRetriever` uses the latter.

**Confidence**: Medium — the exact query path depends on runtime configuration. NEED MORE EVIDENCE on which `VectorIndex` instance `HybridRetriever` receives.

---

## P-14: In-Memory-Only Idempotency Store

**Problem**: `core/execution/idempotency.py` implements `InMemoryIdempotencyStore` with TTL-based expiry (default 300s). State is lost on server restart. There is no persistent backing store.

**Evidence**: Prior deep-dive agent reported the implementation. Class name includes "InMemory" explicitly.

**Root cause**: Designed as Phase 2C implementation. Persistent store deferred.

**Confidence**: High

---

## P-15: CORS Allows All Origins

**Problem**: The FastAPI server configures CORS with `allow_origins=["*"]`, `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`.

**Evidence**: `main.py` lines 214-220.

**Root cause**: Development convenience setting not tightened for production.

**Confidence**: High

---

## P-16: File Read API Has No Path Restriction

**Problem**: The `/api/fs/read` endpoint accepts any filesystem path and reads it. There is no workspace scoping, no path traversal protection, no allowlist.

**Evidence**: `main.py` lines 284-305: `file_path = Path(path)` then `file_path.read_text()` — no validation beyond `is_file()`.

**Root cause**: Implemented as a minimal utility for the Electron IDE, without security hardening.

**Confidence**: High

---

## Summary Table

| ID | Problem | Severity | Confidence |
|----|---------|----------|------------|
| P-01 | O(N) lexical scan | Critical (scaling) | High |
| P-02 | Timeout mismatch (30s vs 300s) | High (reliability) | High |
| P-03 | Dual orchestration systems | High (complexity) | High |
| P-04 | ~40% dead code | High (maintenance) | High |
| P-05 | Dual import convention | Medium (consistency) | High |
| P-06 | DI violations | Medium (architecture) | High |
| P-07 | No health probes | High (ops) | High |
| P-08 | No watcher/MCP recovery | High (reliability) | High |
| P-09 | Three HTTP clients | Medium (resources) | High |
| P-10 | Completion disconnected from retrieval | High (quality) | High |
| P-11 | Session TTL expiry risk | Medium (reliability) | Medium |
| P-12 | EventEmitter disconnected | Low (design) | Medium |
| P-13 | Brute-force vector search | Medium (scaling) | Medium |
| P-14 | In-memory idempotency | Medium (reliability) | High |
| P-15 | CORS allows all origins | High (security) | High |
| P-16 | Unrestricted file read API | Critical (security) | High |
