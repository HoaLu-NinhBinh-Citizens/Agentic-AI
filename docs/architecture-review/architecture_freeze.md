# Architecture Freeze Rules

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13
> **Rule**: Defines what MUST NOT change during refactoring unless explicitly approved.

---

## 1. Must NOT Change (Without Explicit Approval)

### 1.1 Public APIs

| API | Contract | Freeze Rule |
|-----|----------|-------------|
| `GET /health` | Returns `{"status": "ok"}` with 200 | Response body and status code frozen |
| `GET /sessions` | Returns list of active sessions | Response schema frozen |
| `POST /sessions` | Creates session, returns session ID | Response schema frozen |
| `DELETE /sessions/{id}` | Deletes session | Behavior frozen |
| `GET /api/fs/read?path=...` | Returns file content | Response format frozen. New error codes (403) allowed as additive. |
| `GET /api/fs/dir?path=...` | Returns directory listing | Response schema frozen |
| `GET /api/ai/config/status` | Returns AI config status | Response schema frozen |
| `WS /ws/{session_id}` | Full-duplex WebSocket | Protocol frozen (see §1.2) |

**Rule**: No endpoint may be removed, renamed, or have its response schema changed. New endpoints may be added. New error response codes (e.g., 403) may be added to existing endpoints.

### 1.2 Protocols

| Protocol | Element | Freeze Rule |
|----------|---------|-------------|
| WebSocket Client→Server | `{type: "chat", message}` | Message type and field names frozen |
| WebSocket Client→Server | `{type: "cancel"}` | Frozen |
| WebSocket Client→Server | `{type: "tool_call", data: {tool_name, arguments, call_id, trace_id}}` | Frozen |
| WebSocket Client→Server | `{type: "pong"}` | Frozen |
| WebSocket Server→Client | `{type: "token", data: {text}}` | Frozen |
| WebSocket Server→Client | `{type: "done"}` | Frozen |
| WebSocket Server→Client | `{type: "error", data: {code, message}}` | Frozen. New error codes allowed. |
| WebSocket Server→Client | `{type: "tool_call_start", data: {call_id, tool_name}}` | Frozen |
| WebSocket Server→Client | `{type: "tool_call_result", data: {call_id, result}}` | Frozen |
| WebSocket Server→Client | `{type: "tool_call_error", data: {call_id, error}}` | Frozen |
| WebSocket Server→Client | `{type: "ping"}` | Frozen |
| MCP JSON-RPC | `initialize`, `tools/list`, `tools/call` | Frozen (standard MCP protocol) |

**Rule**: No message type may be removed or renamed. No required field may be removed. New optional fields may be added to existing messages. New message types may be added.

### 1.3 Storage Schemas

| Storage | Schema Element | Freeze Rule |
|---------|---------------|-------------|
| SQLite session store | `sessions` table schema | Column names and types frozen. New columns allowed. |
| SQLite index state | `(path, mtime, content_hash, indexed_at)` | Column names frozen. New columns allowed. |
| ChromaDB | Collection name and metadata schema | Frozen |
| `.ai_support/` directory | Directory structure and file naming | Frozen |
| `configs/mcp/servers.yaml` | YAML format for MCP server definitions | Frozen |

**Rule**: No existing table column may be removed or renamed. No existing file format may change. New tables, columns, and files may be added.

### 1.4 Editor Contracts

| Contract | Element | Freeze Rule |
|----------|---------|-------------|
| Electron → Server | WebSocket URL format `/ws/{session_id}` | Frozen |
| Electron → Server | REST endpoint paths | Frozen |
| Server → Electron | WebSocket message format | Frozen (see §1.2) |
| Server → Electron | Token streaming behavior | Frozen: one `token` event per chunk, `done` at end |
| Server → Electron | Tool call lifecycle | Frozen: `tool_call_start` → `tool_call_result`/`tool_call_error` |

**Rule**: The Electron IDE must not require any code changes to work with refactored server code. All changes must be backward-compatible from the IDE's perspective.

### 1.5 Event Contracts

| Contract | Element | Freeze Rule |
|----------|---------|-------------|
| WebSocket event types | `token`, `done`, `error`, `tool_call_start`, `tool_call_result`, `tool_call_error`, `ping` | Type strings frozen |
| WebSocket event data | Field names within `data` objects | Frozen. New fields allowed. |
| Domain event types (if kept) | `EventType` enum values | Frozen if EventEmitter is wired in. Deletable if EventEmitter is deleted (T-01 decision). |

### 1.6 External Integrations

| Integration | Element | Freeze Rule |
|-------------|---------|-------------|
| LLM providers | Provider detection: `OPENAI_API_KEY` → `ANTHROPIC_API_KEY` → Ollama fallback | Priority order frozen |
| Ollama | Base URL `localhost:11434` | Default frozen (configurable override allowed) |
| MCP servers | YAML config format, stdio subprocess protocol | Frozen |
| `pyproject.toml` | `agentic-ai` CLI entry point | Entry point name frozen |
| Environment variables | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `AI_SUPPORT_ENABLE_INDEXING` | Variable names and semantics frozen |

---

## 2. Allowed Internal Changes

### 2.1 Always Allowed (No Approval Required)

| Change Type | Scope | Condition |
|-------------|-------|-----------|
| Delete dead code | Any confirmed-dead module | Zero live importers verified |
| Add new internal methods | Any module | Method is not part of public API |
| Change method implementation | Any module | Public signature and return type preserved |
| Add new optional parameters | Any public method | Default value preserves old behavior |
| Add new classes/modules | Any package | No existing import paths change |
| Add new SQLite tables | Any DB | Existing tables unchanged |
| Add new test files | `tests/` | Existing tests unchanged |
| Change constants/config defaults | Server internals | Documented and tested |
| Add lint rules | CI config | Does not reject previously valid code in surviving modules |
| Update `pyproject.toml` dependencies | Dependencies | No removal without migration (see §2.2) |

### 2.2 Allowed With Documentation

| Change Type | Scope | Required Documentation |
|-------------|-------|-----------------------|
| Remove Python dependency | `pyproject.toml` | Verify zero imports in surviving code. Note in PR description. |
| Change import convention | All `.py` files | Decision documented. Migration script provided. Team notified. |
| Deprecate public method | Any module | Add deprecation warning. Document replacement. Keep for >= 1 release cycle. |
| Add new environment variables | Server config | Document in README or config guide. Provide sensible defaults. |
| Change internal module structure | `src/` layout | All surviving imports still resolve. |

### 2.3 Requires Explicit Approval

| Change Type | Approval From | Reason |
|-------------|--------------|--------|
| Remove or rename REST endpoint | Project lead + IDE team | Breaks Electron IDE |
| Change WebSocket message schema | Project lead + IDE team | Breaks Electron IDE |
| Change SQLite table column names | Project lead | May break existing data |
| Change MCP config format | Project lead | Breaks existing deployments |
| Remove environment variable | Project lead | Breaks existing deployments |
| Change LLM provider priority order | Project lead + product | Affects default user experience |
| Change `pyproject.toml` entry points | Project lead | Breaks CLI users |

---

## 3. Per-Task Freeze Exceptions

| Task | Frozen Element | Exception | Justification |
|------|---------------|-----------|---------------|
| T-02 | CORS config | Allowed to restrict from `*` to explicit list | Security fix — reducing permissions, not changing API |
| T-02 | `/api/fs/read` responses | Allowed to add 403 error code | Additive error case — existing valid paths unchanged |
| T-02 | `STREAM_TIMEOUT_SEC` | Allowed to increase | Config value, not API. Increasing makes existing behavior more permissive |
| T-01 | Internal module layout | Allowed to delete packages | Dead code only. Production paths unaffected |
| T-03 | SQLite schema | Allowed to add `chunks_fts` table | Additive table. Existing tables unchanged |
| T-05 | SQLite schema | Allowed to add `idempotency_store` table | Additive table |
| T-05 | `MCPClientManager` | Allowed to add `health_check()`, `reconnect()` | Additive methods. Existing methods unchanged |
| T-04 | Import paths | Allowed to change all import paths | One-time convention unification. Requires team coordination and migration script |
| T-04 | `pyproject.toml` deps | Allowed to remove `aiohttp`, `requests` | After verifying zero remaining imports |
| T-04 | `RealAgent` constructor | Allowed to add port parameter | With default that preserves old behavior |
| T-04 | `CompletionEngine` constructor | Allowed to add retrieval parameter | Optional with default (no retrieval) |

---

## 4. Freeze Verification

Before merging any task, verify:

- [ ] No REST endpoint removed or renamed
- [ ] No WebSocket message type removed or renamed
- [ ] No WebSocket message field removed
- [ ] No SQLite column removed or renamed
- [ ] No environment variable removed or renamed
- [ ] No MCP config format changed
- [ ] No `pyproject.toml` entry point changed
- [ ] Electron IDE works without code changes (manual test)

This checklist is part of the acceptance criteria for every phase.
