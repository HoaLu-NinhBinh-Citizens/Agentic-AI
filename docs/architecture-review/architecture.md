# Architecture Overview

> **Document type**: Read-only baseline analysis — no code was modified.
> **Date**: 2026-06-13
> **Codebase snapshot**: 1,393 Python files (~363K lines) + Electron frontend (~40 TS/TSX files)
> **Branch**: main @ commit 1fce018

---

## 1. System Overview

Agentic-AI is a local-first AI code assistant targeting embedded/firmware engineering. It consists of two runtime surfaces:

| Surface | Technology | Entry Point | Status |
|---------|-----------|-------------|--------|
| **Backend server** | FastAPI + Uvicorn | `src/interfaces/server/main.py` | Production (Phase 2B) |
| **Desktop IDE** | Electron + React + Vite | `src/AgenticAI/electron/main.js` | Active development |
| **CLI** | Typer | `src/agentic_ai/cli.py` | Mostly stub |
| **TUI** | prompt-toolkit | `src/infrastructure/tui/` | Stub |

The backend server exposes REST + WebSocket endpoints. The Electron IDE connects via WebSocket for chat and tool execution. The CLI entry point (`agentic-ai`) is registered in `pyproject.toml` but delegates to a minimal stub.

**Evidence**: `pyproject.toml` lines 67-72 define entry points. `src/interfaces/server/main.py` is a 654-line fully implemented FastAPI app. `src/agentic_ai/cli.py` exists but is not wired to the full agent pipeline.

---

## 2. Layered Architecture

### Layer Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ PRESENTATION LAYER                                              │
│  Electron IDE (src/AgenticAI/)                                  │
│  - React renderer (App.tsx, ChatPanel, Editor, Terminal, etc.)  │
│  - Main process (aiService, ollamaClient, fixEngine, etc.)      │
│  - Hooks (useAI, useAIAgent, useInlineCompletion)               │
└──────────────────────────────┬──────────────────────────────────┘
                               │ WebSocket / REST
┌──────────────────────────────▼──────────────────────────────────┐
│ API LAYER                                                       │
│  FastAPI Server (src/interfaces/server/main.py)                 │
│  - /health, /sessions, /ws/{session_id}                         │
│  - /api/fs/read, /api/fs/dir, /api/ai/config/status             │
│  - WebSocket message types: chat, cancel, tool_call, pong       │
│  - ServerState container, rate limiting, CORS                   │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│ SERVICE LAYER                                                   │
│  RuntimeManager (src/core/runtime/runtime_manager.py)           │
│  - Stream lifecycle (execute, cancel, timeout)                  │
│  ToolExecutionService (src/application/orchestration/           │
│    tool_execution/service.py)                                   │
│  - Tool dispatch, middleware pipeline, broadcasting             │
│  ConnectionManager (src/interfaces/server/websocket/manager.py) │
│  - WebSocket client tracking, heartbeat                        │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│ AGENT LAYER                                                     │
│  RealAgent (src/core/agent/real_agent.py)                       │
│  - LLM provider auto-detection (OpenAI > Anthropic > Ollama)   │
│  - Streaming response generation                               │
│  Multi-Agent System (src/core/multi_agent/)                     │
│  - OrchestratorAgent, CodeGenAgent, ReviewAgent, SecurityAgent  │
│  - MessageBus for inter-agent communication                    │
│  LangGraph Orchestration (src/core/orchestration/)              │
│  - StateGraph workflows, checkpointing, rollback               │
│  Planner (src/application/planner/)                             │
│  - TaskPlanner, DeadlockDetector, DependencyGraph              │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│ AI/LLM LAYER                                                    │
│  LLMManager (src/infrastructure/llm/llm_manager.py)             │
│  - Multi-provider: OpenAI, Anthropic, Ollama, Groq, Gemini     │
│  - Streaming with tool-call accumulation                       │
│  LLMClient (src/infrastructure/llm/client.py)                   │
│  - Role-based routing (DEFAULT, SMOL, SLOW, PLAN, COMMIT)      │
│  - Shared httpx.AsyncClient pool                               │
│  CompletionEngine (src/infrastructure/completion/)              │
│  - FIM prompting via local Ollama                              │
│  CircuitBreaker + RetryPolicy (src/infrastructure/resilience/) │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│ DOMAIN LAYER                                                    │
│  Knowledge (src/domain/knowledge/)                              │
│  - KnowledgeBase, KBEntry, HardwareChunker, Citations          │
│  Hardware (src/domain/hardware/)                                │
│  - EmbeddedTarget, ChipDescription, TargetRegistry             │
│  Models (src/domain/models/)                                    │
│  - ExecutionRequest, ToolCallState, etc.                       │
│  Ports (src/domain/ports/)                                      │
│  - KnowledgeStore (abstract), HardwareSecurityModule (abstract)│
│  Events (src/core/events/)                                      │
│  - EventType, Event, EventEmitter, middleware                  │
│  Diff/Edit (src/infrastructure/editing/diff_engine.py)         │
│  - Unified diff generation/parsing, fuzzy hunk application     │
│  EditSession (src/application/editing/edit_session.py)         │
│  - Multi-file atomic transactions, conflict detection          │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│ INFRASTRUCTURE LAYER                                            │
│  Indexing (src/infrastructure/indexing/)                         │
│  - IncrementalIndexer (SQLite state), SafeTreeSitterIndexer    │
│  - FileWatcher (watchdog), ReferenceGraph (call graph)         │
│  Retrieval (src/infrastructure/retrieval/)                      │
│  - HybridRetriever (lexical + vector), VectorIndex (NumPy)     │
│  Embeddings (src/infrastructure/embeddings/)                    │
│  - EmbeddingService (Ollama bge-m3), LRU cache                │
│  MCP (src/infrastructure/mcp/)                                  │
│  - MCPClientManager (stdio subprocess), tool discovery         │
│  Cache (src/infrastructure/cache/tool/)                         │
│  - 15-component cache system (LRU, SWR, rate limit, etc.)     │
│  Observability (src/infrastructure/observability/)              │
│  - OTEL tracing, structlog, Prometheus metrics                 │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│ STORAGE LAYER                                                   │
│  SQLite (session persistence, index state)                      │
│  ChromaDB (vector store, persistent directory-based)            │
│  Filesystem (.ai_support/ directory for backups, state DBs)     │
│  In-memory (caches, rate limiters, idempotency store)           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Subsystem Descriptions

### 3.1 Server (Interfaces Layer)

**Location**: `src/interfaces/server/main.py`

The FastAPI application is the primary production entry point. It uses `asynccontextmanager` lifespan to initialize and wire all subsystems:

1. `SessionStore` (SQLite) → `PersistentSessionManager`
2. `RealAgent` → `RuntimeManager`
3. `MCPClientManager` (optional, from YAML config)
4. `ToolExecutionService`
5. `IndexingService` (optional, behind `AI_SUPPORT_ENABLE_INDEXING=1`)

All components are held in a `ServerState` container accessible via `app.state.server_state`.

**WebSocket protocol**: Messages are JSON with `type` field: `chat`, `cancel`, `tool_call`, `pong`. Server responds with `token`, `done`, `error`, `tool_call_start`, `tool_call_result`, `tool_call_error` events.

**Evidence**: `main.py` lines 122-204 (lifespan), lines 417-534 (WebSocket handler).

### 3.2 Electron IDE (Presentation Layer)

**Location**: `src/AgenticAI/`

React + Vite + Tailwind desktop app packaged with Electron.

**Renderer components** (~20 TSX files):
- `App.tsx` — root layout
- `ChatPanel.tsx` — AI conversation
- `Editor.tsx` — code editing with Monaco (inferred from project deps)
- `Terminal.tsx` / `TerminalPanel.tsx` — embedded terminal
- `InlineDiffView.tsx` — diff rendering
- `SearchPanel.tsx`, `GitPanel.tsx`, `HardwarePanel.tsx`, etc.

**Main process modules** (~12 TS files):
- `aiService.ts` — backend communication
- `ollamaClient.ts` — direct Ollama calls from Electron
- `fixEngine.ts` — fix application
- `gitIntegration.ts`, `terminal.ts`, `search.ts`, `storage.ts`

**Hooks**: `useAI.ts`, `useAIAgent.ts`, `useInlineCompletion.ts`, `useCodeReview.ts`, `useCommandPalette.ts`

**Evidence**: File listing from `src/AgenticAI/src/`.

### 3.3 Agent Runtime

**RealAgent** (`src/core/agent/real_agent.py`):
- Lazy-initializes `LLMManager` on first use
- Provider detection: checks `OPENAI_API_KEY` → `ANTHROPIC_API_KEY` → falls back to Ollama
- Exposes `generate_response()` and `stream_response()`

**RuntimeManager** (`src/core/runtime/runtime_manager.py`):
- Wraps agent execution with 30s timeout (`STREAM_TIMEOUT_SEC`)
- Tracks active streams per session via `StreamInfo`
- Cooperative cancellation via `asyncio.Event`

**Multi-Agent System** (`src/core/multi_agent/`):
- `BaseAgent`, `MessageBus`, `OrchestratorAgent`
- Specialized agents: `CodeGenAgent`, `ReviewAgent`, `SecurityAgent`, `BuildAgent`, `FlashAgent`, `FirmwareAgent`
- `SharedMemory` for cross-agent state

**LangGraph Orchestration** (`src/core/orchestration/`):
- `LangGraphAgent`, `LangGraphOrchestrator`
- `AgentState`, `WorkflowState` typed state graphs
- `TaskQueue` with priority support
- `RollbackEngine` with compensation actions

**Observation**: Both `multi_agent` and `orchestration` modules export `LangGraphAgent` and `LangGraphOrchestrator`. The `multi_agent/__init__.py` re-exports from `core.orchestration.langgraph_agent`, creating an alias relationship. It is unclear from the server wiring which path is exercised in production — the server uses `RealAgent` directly, not either orchestration system.

### 3.4 LLM Integration

**LLMManager** (`src/infrastructure/llm/llm_manager.py`):
- Orchestrates provider selection, streaming, cost tracking
- Per-provider circuit breakers

**LLMClient** (`src/infrastructure/llm/client.py`):
- 5 providers: Ollama, OpenAI, Anthropic, Groq, Gemini
- Role-based model routing (DEFAULT/SMOL/SLOW/PLAN/COMMIT)
- Shared `httpx.AsyncClient` (max 100 connections, 20 keepalive)

**Provider adapters**: `anthropic_llm.py`, `openai_llm.py`, `ollama_provider.py`, `gemini_llm.py`, `groq_provider.py`
- Each uses HTTP directly (not official SDKs)
- Dynamic timeout: e.g., Anthropic `120 + prompt_chars/50`, capped at 300s

**CompletionEngine** (`src/infrastructure/completion/completion_engine.py`):
- FIM (Fill-in-Middle) via local Ollama `/api/generate`
- 150ms debounce, LRU cache (512 entries), single-line output

### 3.5 Retrieval & Indexing

**IndexingService** (`src/infrastructure/indexing/service.py`):
- Wires `KnowledgeBase` + `EmbeddingService` + `IncrementalIndexer` + `FileWatcher`
- Optional, behind `AI_SUPPORT_ENABLE_INDEXING=1`

**IncrementalIndexer** (`src/infrastructure/indexing/incremental.py`):
- SQLite WAL state DB tracking `(path, mtime, content_hash, indexed_at)`
- Parallel file hashing via ThreadPoolExecutor
- Dependency tracking for cascade re-index
- Batch processing (default 10 files)

**SafeTreeSitterIndexer** (`src/infrastructure/indexing/tree_sitter/`):
- 14+ languages, memory limits (512MB), timeout (30s)
- Parse strategies: FULL, PARTIAL, INCREMENTAL
- Regex fallback when tree-sitter unavailable

**HybridRetriever** (`src/infrastructure/retrieval/hybrid.py`):
- Lexical scoring via `ChunkStore.get_all()` — iterates all chunks
- Semantic search via `VectorIndex`
- Deterministic reranking + dedup

**EmbeddingService** (`src/infrastructure/embeddings/embedding_service.py`):
- Ollama bge-m3, async via aiohttp
- LRU cache (4,096 entries), retry with backoff
- Fallback to hash-based deterministic embeddings

**ChromaDB store** (`src/infrastructure/vector_db/chromadb/knowledge_store.py`):
- PersistentClient, HNSW cosine metric
- In-memory fallback if ChromaDB unavailable

### 3.6 Tool Execution

**ToolExecutionService** (`src/application/orchestration/tool_execution/service.py`):
- Single entry point for tool dispatch
- Middleware pipeline support (Phase 2C)
- Broadcasts tool lifecycle events to WebSocket clients

**MCP Integration** (`src/infrastructure/mcp/manager.py`):
- Spawns MCP servers as stdio subprocesses
- JSON-RPC protocol, tool discovery
- Circuit breaker per server, graceful fallback without MCP SDK

**ToolRegistry**: Per-session namespaced tool registry, supports both built-in tools and MCP-discovered tools.

### 3.7 Edit & Fix Engine

**DiffEngine** (`src/infrastructure/editing/diff_engine.py`):
- Unified diff generation via `difflib.unified_diff`
- Hunk parsing with regex
- Fuzzy hunk matching (±20 lines)

**EditSession** (`src/application/editing/edit_session.py`):
- Multi-file atomic transactions
- Conflict detection modes: ABORT_ALL, SKIP_CONFLICTED, FORCE
- TOCTOU protection (re-reads disk before write)

**FixEngine** (`src/core/fix_engine/`):
- `LLMSuggester`: LLM-based fix generation with cache + retry
- `apply_fix.py`: Auto-backup with SHA256 naming, rollback store
- Iterative fix cycle with regression detection

### 3.8 Session Management

**PersistentSessionManager** (`src/core/session/persistent_manager.py`):
- SQLite-backed via `SessionStore`
- In-memory TTL cache (default 1hr)
- Max sessions tracking (default 1000)
- Owns per-session `ToolRegistry` and `MCPManager` references

### 3.9 Memory System

**Location**: `src/core/memory/`

5-tier memory architecture:
1. **Working Memory** — current task context
2. **Episodic Memory** — specific experiences
3. **Long-Term Memory** — durable knowledge
4. **Session Memory** — per-session state
5. **Semantic Memory** — general knowledge

Includes compression engine (`extractive`, `truncation`, `keyvalue`, `adaptive` strategies), governance (`PII policy`, `retention policy`, `provenance`, `confidence decay`).

### 3.10 Observability

**OpenTelemetry** (`src/infrastructure/observability/telemetry.py`):
- OTEL SDK with OTLP gRPC export
- Batch span processing
- NoOp fallback when OTEL not installed

**structlog**: Used throughout for structured logging.

**Events** (`src/core/events/`):
- `EventEmitter` with middleware chain (`LoggingMiddleware`, `MetricsMiddleware`)
- Domain event types: codegen, firmware, hardware, runtime, session, workflow

---

## 4. Dead/Orphaned Subsystems

The following directories exist but have no production call sites as verified in the June 2026 review:

| Path | Description | Evidence |
|------|-------------|----------|
| `src/app/` | Shadow API server, orchestrator, agent | Duplicates `src/interfaces/server/` and `src/application/` |
| `src/domains/` | Shadow of `src/domain/` | Parallel structure with `s` suffix |
| `src/agent/` | Thin alias | Re-exports `AgentCore`, `AgentExecutor`, `AgentPlanner` from `core.agent` |
| `infrastructure/distributed/` | Distributed systems stubs | No callers |
| `infrastructure/sharding/` | Sharding stubs | No callers |
| `infrastructure/fleet/` | Fleet management stubs | No callers |
| `infrastructure/chaos/` | Chaos engineering stubs | No callers |
| `infrastructure/hsm/` | HSM stubs | No callers |
| `infrastructure/performance/rust/` | Rust performance module | Cargo.toml present, never imported from Python |

**Evidence**: Glob search for imports of these modules finds zero hits in the serving path. Confirmed in prior session (2026-06-11).

---

## 5. Import Convention

Two import styles coexist:

1. **Prefixed**: `from src.domain.knowledge.kb import KnowledgeBase` — used by ~427 files
2. **Bare**: `from domain.models.execution import ExecutionRequest` — used by ~14 files (primarily in `interfaces/server/` and `application/orchestration/`)

This works because `PYTHONPATH` includes both the repo root and `src/` (configured in `pyproject.toml` line 79: `"" = "src"` and line 100: `pythonpath = ["src", "."]`).

The server's `main.py` also manually adds `src/` to `sys.path` (line 31-33).

**Evidence**: `main.py` lines 31-33, `pyproject.toml` lines 79-80, grep counts of import patterns.
