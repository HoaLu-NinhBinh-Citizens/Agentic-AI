# Architecture — Current State

> **Date**: 2026-06-14
> **As of commit**: `a2042cb` (post PR-003)

---

## 1. Production Path

The production server is `src/interfaces/server/main.py` (FastAPI, v1.3.0).

```
Client (WebSocket/REST)
  └─► interfaces/server/main.py
        ├─► core/agent/real_agent.py          — RealAgent (LLM orchestration)
        ├─► application/orchestration/tool_execution/
        │     ├─ config.py                     — get_tool_execution_config()
        │     └─ service.py                    — ToolExecutionService
        ├─► core/rate_limiter.py               — SlidingWindowRateLimiter
        ├─► core/runtime/runtime_manager.py    — RuntimeManager
        ├─► core/session/persistent_manager.py — PersistentSessionManager
        ├─► infrastructure/persistence/sqlite/ — SessionStore
        ├─► infrastructure/mcp/manager.py      — MCPClientManager
        └─► interfaces/server/websocket/       — ConnectionManager
```

**Single orchestration path**: `RealAgent` is the sole agent orchestrator. All alternative orchestration systems (LangGraph, multi-agent coordination, application-layer supervisor) were deleted in PR-003.

---

## 2. Layer Structure

```
src/
├── interfaces/          — Server (FastAPI), CLI, TUI, IDE bridge, VS Code, desktop
├── application/         — Use-case orchestration, API app, workflows, evaluation, planner
│   └── orchestration/
│       └── tool_execution/   — LIVE: config + service + middleware
├── core/                — Agent, runtime, session, memory, tools, parsing, events, config
│   ├── agent/           — RealAgent + memory, metrics, middleware, prompts
│   ├── runtime/         — Dispatcher, scheduler, admission, retry, DLQ, workflow
│   ├── session/         — Lifecycle, state, store
│   ├── memory/          — ChromaDB, compression, decision traces, governance
│   ├── tools/           — Built-in tool definitions
│   ├── events/          — EventEmitter (dead — zero importers, PR-004 scope)
│   ├── execution/       — Code executor, execution graph, worker (stubs remaining)
│   └── workspace/       — File watcher, multi-root, ownership
├── domain/              — Firmware, hardware (flash/GDB/HAL/serial/SVD), knowledge, events
├── domains/             — EDA/KiCad, firmware, hardware engine, safety, validation, autonomy
├── infrastructure/      — LLM, MCP, retrieval, indexing, persistence, observability, sandbox,
│                          analysis, hardware, HIL, tools, cache, security, router, gateway
├── shared/              — Config, constants, enums, exceptions, protocols, utils, validators
├── schemas/             — API, DTO, IDL (gRPC/protobuf), WebSocket, validation
├── agentic_ai/          — CLI entry point (ai-support, agentic-ai commands)
└── AgenticAI/           — Electron desktop app (JS/TS, separate build)
```

---

## 3. Key Subsystems

| Subsystem | Location | Status |
|-----------|----------|--------|
| RealAgent | `core/agent/real_agent.py` | **Live** — production orchestrator |
| ToolExecutionService | `application/orchestration/tool_execution/` | **Live** — WebSocket tool_call handling |
| MCP Client | `infrastructure/mcp/` | **Live** — tool discovery via servers.yaml |
| Indexing Service | `infrastructure/indexing/` | **Live** — optional, env-gated (`AI_SUPPORT_ENABLE_INDEXING`) |
| LLM Gateway | `infrastructure/llm/` | **Live** — providers, routing, tokenizer |
| Session Management | `core/session/` + `infrastructure/persistence/sqlite/` | **Live** — SQLite-backed |
| Runtime Manager | `core/runtime/runtime_manager.py` | **Live** — stream execution |
| EventEmitter | `core/events/` | **Dead** — zero production importers (PR-004 scope) |
| Analysis/Rules | `infrastructure/analysis/` | **Live** — ML detectors, language parsers |
| Router | `infrastructure/router/` | **Live** — fairness, policy, observation |
| Hardware/HIL | `infrastructure/hardware/` + `infrastructure/hil/` | **Live** — flash, JLink, GDB, OpenOCD |

---

## 4. File Counts (Python only, excluding Electron app)

| Directory | .py files |
|-----------|-----------|
| `src/` (Python) | ~1,296 |
| `tests/` | ~351 |
| **Total** | ~1,647 |

---

## 5. Deleted in PR-003

| Package | Files Removed |
|---------|---------------|
| `core/orchestration/` (LangGraph) | 6 |
| `core/multi_agent/` (coordination) | 42 |
| `multi_agent/` (redirect layer) | 3 |
| `application/orchestration/` dead subtrees (agents, supervisor, coordination, recovery, routing) | 14 |
| `infrastructure/distributed/` | 8 |
| `infrastructure/chaos/` | 1 |
| `infrastructure/fleet/predictive_failure.py` | 1 |
| `infrastructure/sharding/` | 1 |
| `infrastructure/testing/production_scenarios.py` | 1 |
| `core/checkpoint/` | 5 |
| `core/execution/` (executor, task_queue, worker_pool stubs) | 3 |
| `core/health/` | 4 |
| `agent/` (top-level stubs) | 5 |
| `app/` (top-level stubs) | 4 |
| Test files | 24 |
| `langgraph` dependency from pyproject.toml | — |
| **Total** | ~132 files, ~33,524 lines |

---

## 6. Known Issues

1. **Stale `__pycache__`** in `core/multi_agent/`, `core/orchestration/`, `multi_agent/` — .pyc files from deleted modules remain on disk.
2. **Stale `egg-info`** — `src/AI_support.egg-info/` references deleted files and `langgraph`. Regenerated on next `pip install -e .`.
3. **16 test collection errors** — all pre-existing (missing `src.events`, `src.hardware`, `src.learning`, `src.observability`, `src.benchmarking`, broken symbol imports in `domains.safety`, `domains.hardware_engine`, `core.tools.flash_tools`, `models`). Not caused by PR-003.
4. **`core/events/`** — zero production importers, scheduled for PR-004.
5. **`application/api/app/chat_endpoints.py`** — imports from deleted `core.multi_agent.agent` but file itself is orphan (only imported by orphan `api_server.py`). Should be deleted in a follow-up.
