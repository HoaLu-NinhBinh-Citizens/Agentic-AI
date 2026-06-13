# Dependency Graph Analysis

> **Document type**: Read-only baseline analysis — no code was modified.
> **Date**: 2026-06-13

---

## 1. Package Dependency Graph

### Top-Level Packages

```
src/
├── interfaces/         → core, infrastructure, application, domain
│   └── server/         → core.agent, core.runtime, core.session,
│                         core.rate_limiter, infrastructure.persistence,
│                         infrastructure.mcp, application.orchestration,
│                         interfaces.server.websocket
│
├── application/        → core, domain, infrastructure
│   ├── orchestration/  → domain.models, core.session
│   ├── planner/        → (self-contained, minimal external deps)
│   ├── workflows/      → domain, infrastructure
│   ├── editing/        → infrastructure.editing
│   ├── suggestion/     → infrastructure.llm
│   └── llm/            → core.tools, infrastructure.llm
│
├── core/               → src.core (internal), src.infrastructure, src.domain
│   ├── agent/          → infrastructure.llm
│   ├── orchestration/  → src.core.orchestration (internal)
│   ├── multi_agent/    → src.core.orchestration (cross-reference)
│   ├── events/         → (self-contained)
│   ├── session/        → infrastructure.persistence
│   ├── runtime/        → core.agent
│   ├── memory/         → (self-contained)
│   ├── tools/          → infrastructure.mcp
│   └── execution/      → (self-contained)
│
├── domain/             → (minimal, mostly self-contained)
│   ├── knowledge/      → infrastructure.embeddings (violation, see below)
│   ├── hardware/       → (self-contained)
│   ├── models/         → (self-contained)
│   └── ports/          → (abstract interfaces only)
│
├── infrastructure/     → src.core, src.domain, external libraries
│   ├── llm/            → httpx, aiohttp
│   ├── mcp/            → mcp SDK, src.infrastructure.resilience
│   ├── indexing/        → src.domain.knowledge, src.infrastructure.embeddings,
│   │                     tree-sitter-languages, watchdog
│   ├── retrieval/      → src.infrastructure.models, src.core.config
│   ├── embeddings/     → aiohttp (Ollama HTTP)
│   ├── vector_db/      → chromadb
│   ├── persistence/    → aiosqlite
│   ├── observability/  → opentelemetry SDK
│   ├── cache/          → (self-contained)
│   ├── resilience/     → (self-contained)
│   └── completion/     → httpx (Ollama HTTP)
│
└── agentic_ai/         → (CLI entry point, minimal)
```

---

## 2. Module Dependency Matrix

### Server Startup Dependencies (Critical Path)

```
interfaces.server.main
  ├── application.orchestration.tool_execution.config
  ├── application.orchestration.tool_execution.service
  │     └── domain.models.execution
  │     └── domain.models.tool_call
  ├── core.agent.real_agent
  │     └── infrastructure.llm.llm_manager
  │           ├── infrastructure.llm.openai_llm
  │           ├── infrastructure.llm.anthropic_llm
  │           └── infrastructure.llm.ollama_provider
  ├── core.rate_limiter
  ├── core.runtime.runtime_manager
  ├── core.session.persistent_manager
  │     └── infrastructure.persistence.sqlite.session_store
  │           └── aiosqlite
  ├── infrastructure.mcp.manager
  │     ├── infrastructure.mcp.config
  │     ├── infrastructure.resilience.circuit_breaker
  │     ├── mcp SDK (optional)
  │     └── shared.exceptions.tool_errors
  └── interfaces.server.websocket.manager
```

### Indexing Pipeline Dependencies

```
infrastructure.indexing.service
  ├── domain.knowledge.kb
  │     └── domain.knowledge.chunking
  │     └── domain.knowledge.embeddings
  │     └── domain.ports.knowledge_store
  ├── infrastructure.vector_db.chromadb.knowledge_store
  │     └── chromadb
  ├── infrastructure.embeddings.embedding_service
  │     └── aiohttp
  ├── infrastructure.indexing.incremental
  │     └── sqlite3
  │     └── asyncio, threading
  └── infrastructure.indexing.file_watcher
        └── watchdog
```

### Retrieval Pipeline Dependencies

```
infrastructure.retrieval.hybrid
  ├── core.config.agent_prompts
  ├── infrastructure.models (ChunkRecord, RetrievalHit, etc.)
  ├── infrastructure.retrieval.chunk_store
  ├── infrastructure.retrieval.knowledge_base
  ├── infrastructure.retrieval.query_analyzer
  └── infrastructure.retrieval.vector_index
        └── numpy (optional)
```

---

## 3. Circular Dependencies

### Confirmed

**1. `core.multi_agent` ↔ `core.orchestration`**

- `core/multi_agent/__init__.py` imports from `src.core.orchestration.langgraph_agent`
- `core/orchestration/__init__.py` imports from `src.core.orchestration.langgraph_workflow`
- Both packages export `LangGraphAgent` and `LangGraphOrchestrator`

**Nature**: `multi_agent` re-exports `orchestration` symbols, creating an alias dependency. Not a true circular import at the module level, but creates conceptual confusion about ownership.

**Evidence**: `core/multi_agent/__init__.py` line 52: `from src.core.orchestration.langgraph_agent import LangGraphAgent, LangGraphOrchestrator, create_langgraph_orchestrator`

**Confidence**: High

### Suspected

**2. `domain.knowledge` → `infrastructure.embeddings`**

- `domain/knowledge/embeddings.py` imports `EmbeddingService` from `infrastructure.embeddings`
- This violates dependency inversion: domain layer should not depend on infrastructure

**Evidence**: `domain/knowledge/embeddings.py` uses `EmbeddingService` (Ollama HTTP client) directly rather than through a port.

**Confidence**: High (structural violation, not a runtime circular import)

**3. `infrastructure.retrieval.hybrid` → `core.config`**

- Infrastructure imports from core config for constants
- Direction: infrastructure → core (acceptable in most architectures, but worth noting)

**Evidence**: `hybrid.py` line 5: `from src.core.config.agent_prompts import GENERIC_QUERY_STOPWORDS, MIN_HIGH_CONFIDENCE_HITS, VECTOR_RERANK_CANDIDATES`

**Confidence**: High

---

## 4. Ownership Boundaries

### Clear Ownership

| Package | Owner | Responsibility |
|---------|-------|---------------|
| `interfaces/server/` | Server team | HTTP/WS transport, request handling |
| `core/agent/` | Agent team | Agent lifecycle, LLM interaction |
| `domain/knowledge/` | Domain team | Knowledge model, chunking, citation |
| `domain/hardware/` | Hardware team | Embedded target abstraction |
| `infrastructure/llm/` | Platform team | LLM provider adapters |
| `infrastructure/indexing/` | Platform team | File watching, incremental index |
| `infrastructure/mcp/` | Platform team | MCP protocol integration |

### Unclear Ownership

| Package | Issue |
|---------|-------|
| `core/orchestration/` vs `core/multi_agent/` | Both own workflow orchestration. `multi_agent` re-exports from `orchestration`. No clear boundary. |
| `application/orchestration/` | Third orchestration namespace. Owns `ToolExecutionService` which belongs in service layer. |
| `core/agent/` vs `application/llm/` | Both wrap LLM calls. `RealAgent` uses `LLMManager` directly; `LLMAgentService` adds tool execution loop. Unclear which is the primary path. |
| `infrastructure/retrieval/` vs `domain/knowledge/` | Retrieval logic split across both. `KnowledgeBase` in domain does search; `HybridRetriever` in infrastructure does different search. |
| `src/app/` | Dead shadow of `interfaces/server/` and `application/`. No clear owner. |

---

## 5. High Coupling Points

### 5.1 ServerState Container

`interfaces/server/main.py:ServerState` holds references to 5 subsystems: `session_manager`, `connection_manager`, `runtime_manager`, `real_agent`, `tool_execution_service`. Every WebSocket handler accesses all of them through `get_state()`.

**Evidence**: `main.py` lines 69-84.

### 5.2 PersistentSessionManager

Owns: session CRUD, tool registry lifecycle, MCP manager reference, config storage. A single class with 4 distinct responsibilities.

**Evidence**: `main.py` lines 130-131 (config), line 158 (MCP manager), line 160 (tool execution).

### 5.3 RealAgent

Directly imports and instantiates `LLMManager`, `LLMConfig`, `ModelProvider` from infrastructure. No dependency injection — hard-coded `from infrastructure.llm.llm_manager import ...` inside method body.

**Evidence**: `real_agent.py` lines 39-43.

---

## 6. Low Cohesion Points

### 6.1 `core/` Package

Contains 20+ sub-packages spanning agent runtime, orchestration, multi-agent, events, session, memory, tools, execution, health, checkpoint, scheduler, background jobs, workspace, versioning, config, cost governance, middleware, parsing, ports, runtime, fix engine.

Many of these are stub packages (empty `__init__.py`): `health/`, `checkpoint/`, parts of `execution/`.

**Evidence**: Glob of `src/core/**/__init__.py` returns 95+ files. Many contain only pass or empty exports.

### 6.2 `infrastructure/` Package

Contains 46+ sub-packages. While individually focused, the sheer breadth suggests insufficient pruning of unused modules.

### 6.3 `application/planner/`

Contains 20+ files (audit trail, branch recorder, condition evaluator, cost forecast, deadlock detector, events, expansion guard, interrupt handler, join policy, metrics, resume idempotency, retry manager, schema validator, semantic retriever, snapshot manager, types). High internal cohesion, but unclear how many of these are exercised in production.

---

## 7. Dependency Inversion Violations

### 7.1 Domain → Infrastructure

`domain/knowledge/embeddings.py` depends on `infrastructure/embeddings/embedding_service.py` (Ollama HTTP client). The domain layer should define a port; infrastructure should implement it.

**A port exists** at `domain/ports/knowledge_store.py` for storage but NOT for embeddings.

**Confidence**: High

### 7.2 Agent → Infrastructure (Direct Import)

`core/agent/real_agent.py` imports `infrastructure.llm.llm_manager` directly inside a method body (lazy import, but still a direct dependency).

A `core/ports/llm_provider/__init__.py` exists but is empty — the port was scaffolded but never implemented.

**Evidence**: `core/ports/llm_provider/__init__.py` is empty. `real_agent.py` line 39: `from infrastructure.llm.llm_manager import LLMManager, LLMConfig, ModelProvider`

**Confidence**: High

---

## 8. External Dependency Map

| Library | Used By | Purpose |
|---------|---------|---------|
| `fastapi` | `interfaces/server/` | HTTP/WS server |
| `uvicorn` | `interfaces/server/` | ASGI server |
| `aiosqlite` | `infrastructure/persistence/` | Async SQLite |
| `httpx` | `infrastructure/llm/client.py`, `infrastructure/completion/` | HTTP client (LLM + completion) |
| `aiohttp` | `infrastructure/embeddings/`, `infrastructure/llm/streaming.py` | Embedding HTTP, SSE streaming |
| `chromadb` | `infrastructure/vector_db/` | Vector store |
| `openai` | `infrastructure/llm/openai_llm.py` | OpenAI SDK (conditional) |
| `anthropic` | `infrastructure/llm/anthropic_llm.py` | Anthropic SDK (conditional) |
| `mcp` | `infrastructure/mcp/` | MCP protocol SDK (conditional) |
| `tree-sitter-languages` | `infrastructure/indexing/tree_sitter/` | AST parsing |
| `watchdog` | `infrastructure/indexing/file_watcher.py` | Filesystem events |
| `opentelemetry-*` | `infrastructure/observability/` | Distributed tracing |
| `structlog` | Throughout | Structured logging |
| `pydantic` | `application/api/`, domain models | Data validation |
| `langgraph` | `core/orchestration/` | Workflow orchestration |
| `numpy` | `infrastructure/retrieval/vector_index.py` | Vector similarity (optional) |
| `rich` | `infrastructure/editing/diff_engine.py` | Terminal rendering (optional) |

**Observation**: Three HTTP client libraries coexist: `httpx` (primary), `aiohttp` (embeddings + streaming), `requests` (some legacy adapters). Each has its own connection pool.

**Evidence**: `pyproject.toml` dependencies, import analysis across source files.
