# Dependency Map — Current State

> **Date**: 2026-06-14
> **As of commit**: `a2042cb` (post PR-003)

---

## 1. Python Dependencies (pyproject.toml)

### Core

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | >=0.135.0 | HTTP/WebSocket server |
| uvicorn | >=0.35.0 | ASGI server |
| pydantic | >=2.11.0 | Data validation |
| pydantic-settings | >=2.10.0 | Settings management |
| aiosqlite | >=0.19.0 | Async SQLite (session persistence) |
| aiohttp | >=3.12.0 | Async HTTP client |
| asyncpg | >=0.31.0 | PostgreSQL (unused in production path) |
| httpx | >=0.28.0 | HTTP client |

### AI/LLM

| Package | Version | Purpose |
|---------|---------|---------|
| openai | >=2.31.0 | OpenAI provider |
| anthropic | >=0.40.0 | Anthropic provider |
| ollama | >=0.5.0 | Local Ollama provider |
| langchain | >=0.3.0 | LLM framework utilities |
| chromadb | >=1.0.0 | Vector database |

### Observability

| Package | Version | Purpose |
|---------|---------|---------|
| structlog | >=25.0.0 | Structured logging |
| opentelemetry-api | >=1.35.0 | Tracing API |
| opentelemetry-sdk | >=1.35.0 | Tracing SDK |
| opentelemetry-exporter-otlp | >=1.35.0 | OTLP export |
| opentelemetry-instrumentation-asgi | >=0.46b0 | ASGI instrumentation |
| opentelemetry-instrumentation-fastapi | >=0.46b0 | FastAPI instrumentation |

### Infrastructure

| Package | Version | Purpose |
|---------|---------|---------|
| mcp | >=1.0.0,<2.0.0 | Model Context Protocol |
| pyyaml | >=6.0 | YAML config |
| cachetools | >=5.5.0 | In-memory caching |
| tree-sitter-languages | >=1.10.0 | Code parsing |
| watchdog | >=3.0.0 | File watching |
| pygls | >=1.0.0 | LSP server |
| python-dotenv | >=1.1.0 | Env files |
| websockets | >=15.0.0 | WebSocket client |

### CLI/UI

| Package | Version | Purpose |
|---------|---------|---------|
| rich | >=14.0.0 | Terminal output |
| typer | >=0.16.0 | CLI framework |
| prompt-toolkit | >=3.0.0 | Interactive prompts |
| pygments | >=2.17.0 | Syntax highlighting |

### Removed in PR-003

| Package | Version | Reason |
|---------|---------|--------|
| ~~langgraph~~ | ~~>=0.2.0~~ | All LangGraph orchestration code deleted |

---

## 2. Production Import Graph (main.py)

```
interfaces.server.main
├── application.orchestration.tool_execution.config
├── application.orchestration.tool_execution.service
├── core.agent.real_agent
├── core.rate_limiter
├── core.runtime.runtime_manager
├── core.session.persistent_manager
├── infrastructure.persistence.sqlite.session_store
├── infrastructure.mcp.manager
├── interfaces.server.websocket.manager
└── (optional) infrastructure.indexing.service
```

All imports resolve successfully. No broken chains in the production path.

---

## 3. Entry Points

| Command | Module | Status |
|---------|--------|--------|
| `ai-support` | `agentic_ai.cli:main` | Live |
| `ai-server` | `interfaces.server.main:app` | Live |
| `agentic-ai` | `agentic_ai.cli:main` | Live |

---

## 4. Optional Dependencies

| Group | Packages | Purpose |
|-------|----------|---------|
| `dev` | pytest, pytest-asyncio, ruff, mypy, pre-commit | Development |
| `server` | uvicorn[standard], websockets | Production server |
| `dashboard` | streamlit | Dashboard UI |

---

## 5. Orphan Internal Dependencies (not reachable from main.py)

These source files import from deleted or non-existent modules:

| File | Broken Import | Impact |
|------|--------------|--------|
| `application/api/app/chat_endpoints.py` | `core.multi_agent.agent` (deleted) | File is orphan — not imported by production path |
| `application/api/app/component_factory.py` | `src.benchmarking` (never existed) | Transitively breaks `embedded_agent.py` test imports |
| `application/api/app/aikicad_orchestrator.py` | `domains.safety.WriteBoundaryGuard` (symbol missing) | File works at module level but symbol doesn't exist in target |

---

## 6. Stale Artifacts

| Artifact | Issue | Resolution |
|----------|-------|------------|
| `src/AI_support.egg-info/SOURCES.txt` | Lists deleted orchestration files | Auto-fixed on `pip install -e .` |
| `src/AI_support.egg-info/requires.txt` | Lists `langgraph>=0.2.0` | Auto-fixed on `pip install -e .` |
| `src/core/multi_agent/coordination/__pycache__/` | 26 stale .pyc files | Delete manually or `find . -name __pycache__ -exec rm -rf {} +` |
| `src/core/orchestration/__pycache__/` | 5 stale .pyc files | Same |
| `src/multi_agent/__pycache__/` | 2 stale .pyc files | Same |
