# Architecture — Current State

> **Date**: 2026-06-14
> **As of commit**: `01f3d35` (post PR-004)

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

**Single orchestration path**: `RealAgent` is the sole agent orchestrator. All alternative orchestration systems were deleted in PR-003. All legacy redirect packages were deleted in PR-004.

---

## 2. Layer Structure

```
src/
├── interfaces/          — Server (FastAPI), CLI, TUI, IDE bridge, VS Code, desktop
├── application/         — Use-case orchestration, API app, workflows, evaluation, planner
│   └── orchestration/
│       └── tool_execution/   — LIVE: config + service + middleware
├── core/                — Agent, runtime, session, memory, tools, parsing, config
│   ├── agent/           — RealAgent + memory, metrics, middleware, prompts
│   ├── runtime/         — Dispatcher, scheduler, admission, retry, DLQ, workflow
│   ├── session/         — Lifecycle, state, store
│   ├── memory/          — ChromaDB, compression, decision traces, governance
│   ├── tools/           — Built-in tool definitions
│   ├── config/          — Output policy, AI support config, agent prompts
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
| Analysis/Rules | `infrastructure/analysis/` | **Live** — ML detectors, language parsers |
| Router | `infrastructure/router/` | **Live** — fairness, policy, observation |
| Hardware/HIL | `infrastructure/hardware/` + `infrastructure/hil/` | **Live** — flash, JLink, GDB, OpenOCD |

---

## 4. File Counts (Python only, excluding Electron app)

| Directory | .py files |
|-----------|-----------|
| `src/` (Python) | ~1,241 |
| `tests/` | ~344 |
| **Total** | ~1,585 |

---

## 5. Cleanup History

| PR | Files Removed | Lines Removed | Scope |
|----|---------------|---------------|-------|
| PR-002 | ~32 | ~4,000 | Dead code Tier 1+2 (zero-importer stubs, test-only packages) |
| PR-003 | ~132 | ~33,524 | Orchestration consolidation (LangGraph, multi-agent, supervisor) |
| PR-004 | ~64 | ~7,076 | Redirect packages, core/events, orphan files, dead tests |
| Docs cleanup | 53 | ~11,064 | Stale planning artifacts |
| **Cumulative** | **~281** | **~55,664** | |

---

## 6. Known Issues

1. **2 test collection errors** — both pre-existing production code bugs:
   - `test_aikicad_agent.py`: `WriteBoundaryGuard` missing from `domains.safety`
   - `test_embedded_agent_regression.py`: `component_factory.py` → `src.benchmarking` (never existed)
2. **5 pre-existing test failures** — logic bugs in `test_p3_observability`, `test_tools`, `test_flash_tools` (×3)
3. **Orphan dependency**: `langchain>=0.3.0` in `pyproject.toml` — zero importers in `src/`
4. **Dual import convention**: `src.` prefix vs bare imports coexist (PR-009 scope)
5. **Stale `egg-info`** — `src/AI_support.egg-info/` references deleted files. Regenerated on `pip install -e .`
