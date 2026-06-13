# Regression Plan — Behavioral Preservation

> **Document type**: Read-only planning — no code was modified.
> **Date**: 2026-06-13
> **Rule**: Defines what must NOT change during refactoring.

---

## 1. Behaviors That Must Remain Unchanged

### 1.1 Server API Contract

| Endpoint / Protocol | Behavior | Verified By |
|---------------------|----------|-------------|
| `GET /health` | Returns `{"status": "ok"}` with 200 | Integration test |
| `GET /sessions` | Returns list of active sessions | Integration test |
| `POST /sessions` | Creates new session, returns session ID | Integration test |
| `DELETE /sessions/{id}` | Deletes session | Integration test |
| `GET /api/fs/read?path=...` | Returns file content for valid workspace paths | Integration test |
| `GET /api/fs/dir?path=...` | Returns directory listing | Integration test |
| `GET /api/ai/config/status` | Returns AI configuration status | Integration test |
| `WS /ws/{session_id}` | Full-duplex chat, tool execution, heartbeat | E2E test |

### 1.2 WebSocket Protocol

| Message Type (Client→Server) | Expected Server Behavior |
|------------------------------|-------------------------|
| `{type: "chat", message: "..."}` | Streams `token` events, ends with `done` |
| `{type: "cancel"}` | Stops current stream, no more `token` events |
| `{type: "tool_call", data: {...}}` | Executes tool, returns `tool_call_result` or `tool_call_error` |
| `{type: "pong"}` | Acknowledged (heartbeat response) |

| Message Type (Server→Client) | Contract |
|------------------------------|----------|
| `{type: "token", data: {text}}` | Incremental text token |
| `{type: "done"}` | Stream complete |
| `{type: "error", data: {code, message}}` | Error with machine-readable code |
| `{type: "tool_call_start", data: {call_id, tool_name}}` | Tool execution beginning |
| `{type: "tool_call_result", data: {call_id, result}}` | Tool execution complete |
| `{type: "tool_call_error", data: {call_id, error}}` | Tool execution failed |
| `{type: "ping"}` | Heartbeat request |

**Rule**: No message type may be renamed, removed, or have its field schema changed without a corresponding Electron IDE update.

### 1.3 Internal Python APIs

| API | Signature / Contract | Used By |
|-----|---------------------|---------|
| `RealAgent.stream_response(prompt, send_event, session_id)` | Async generator yielding tokens | `RuntimeManager` |
| `RuntimeManager.execute(session_id, prompt, send_event)` | Wraps agent execution with timeout and cancellation | `main.py` WebSocket handler |
| `ToolExecutionService.execute_tool(session_id, tool_name, arguments)` | Returns tool result dict | `main.py` tool handler |
| `PersistentSessionManager.create_session()` | Returns session ID string | `main.py` |
| `PersistentSessionManager.get_session(id)` | Returns session object or None | `main.py` |
| `HybridRetriever.search_docs(query)` | Returns `list[RetrievalHit]` | Agent context building |
| `CompletionEngine.complete(file_path, cursor_line, cursor_col, source_before, source_after)` | Returns completion string | Electron completion endpoint |
| `MCPClientManager.call_tool(server_name, tool_name, arguments)` | Returns tool result | `ToolExecutionService` |
| `IncrementalIndexer.reindex_files(paths)` | Re-indexes given file paths | `IndexingService` |

**Rule**: Return types and essential behavior must be preserved. Internal implementation may change. New optional parameters may be added.

---

## 2. User Workflows That Must Not Break

### 2.1 Chat Workflow
1. User opens Electron IDE
2. IDE connects to server via WebSocket
3. User types message in ChatPanel
4. Server streams response tokens
5. Response renders incrementally
6. User can cancel mid-stream

**Regression risk per task**:
- T-02: Timeout change could affect streaming behavior → test with long and short prompts
- T-01: Dead code deletion could break imports in agent path → test full chat round-trip
- T-04: LLM port change could alter response format → test with each provider

### 2.2 Tool Execution Workflow
1. LLM generates a tool call during chat
2. Server dispatches to ToolExecutionService
3. Tool executes (built-in or MCP)
4. Result sent back to client
5. LLM receives result and continues

**Regression risk per task**:
- T-01: If orchestration system changes, tool dispatch path may change
- T-05: MCP recovery could affect tool availability during reconnection

### 2.3 Inline Completion Workflow
1. User types in Editor
2. After 150ms debounce, completion request sent
3. CompletionEngine builds FIM prompt from local context
4. Ollama generates completion
5. Ghost text displayed

**Regression risk per task**:
- T-04: Adding retrieval context changes the FIM prompt → completion quality could change (should improve, but test)

### 2.4 File Operations Workflow
1. User reads file via IDE
2. IDE sends `/api/fs/read` request
3. Server returns file content

**Regression risk per task**:
- T-02: Path validation added → must not reject valid workspace paths

### 2.5 Indexing Workflow
1. Server starts with `AI_SUPPORT_ENABLE_INDEXING=1`
2. FileWatcher monitors workspace
3. File changes trigger re-indexing
4. Chunks stored in ChromaDB + ChunkStore
5. Retrieval uses indexed data

**Regression risk per task**:
- T-01: Dead code deletion near indexing path
- T-03: FTS5 addition changes ChunkStore internals
- T-05: FileWatcher recovery changes lifecycle

---

## 3. APIs That Must Remain Compatible

### 3.1 External APIs (Server ↔ Client)

| API | Compatibility Level | Notes |
|-----|-------------------|-------|
| REST endpoints | Full backward compat | No endpoint removed or renamed |
| WebSocket message types | Full backward compat | No message type removed or renamed |
| WebSocket message fields | Full backward compat | New fields OK, removal forbidden |
| Session ID format | Full backward compat | String format unchanged |

### 3.2 Internal APIs (Python Module Boundaries)

| API Boundary | Compatibility Level | Notes |
|-------------|-------------------|-------|
| `RealAgent` public methods | Signature compat | New optional params OK |
| `HybridRetriever.search_docs()` | Return type compat | `list[RetrievalHit]` unchanged |
| `CompletionEngine.complete()` | Signature compat | New optional params OK for retrieval context |
| `ToolExecutionService.execute_tool()` | Full compat | Called by server handler |
| `PersistentSessionManager` | Full compat | Called by server handler |
| `MCPClientManager.call_tool()` | Full compat | New health methods additive only |

### 3.3 Configuration Compatibility

| Config | Location | Rule |
|--------|----------|------|
| `configs/mcp/servers.yaml` | MCP server definitions | Format unchanged |
| `pyproject.toml` entry points | `agentic-ai` CLI | Entry point unchanged |
| Environment variables | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `AI_SUPPORT_ENABLE_INDEXING` | Names unchanged, behavior unchanged |
| `.ai_support/` directory | State DBs, backups | Directory structure unchanged |

---

## 4. Per-Task Regression Matrix

### T-02: Harden Server Defaults

| What Could Regress | How to Detect | Mitigation |
|--------------------|--------------| -----------|
| Valid file reads rejected | Test all existing file read paths | Allowlist-based validation with workspace root |
| Chat killed by timeout that was previously OK | Compare `STREAM_TIMEOUT_SEC` old vs new | Set new timeout >= max observed generation time |
| Electron can't connect after CORS change | Test WebSocket from Electron origin | Include Electron origin in allowed list |
| Session expires during active use | Test TTL refresh on activity | Ensure activity resets TTL |

### T-01: Dead Code Consolidation

| What Could Regress | How to Detect | Mitigation |
|--------------------|--------------|------------|
| Import error on server startup | `python -c "from interfaces.server.main import app"` | Run before merge |
| Import error in deep dependency | Recursive import of all packages | Run before merge |
| Test fixtures reference deleted module | `python -m pytest tests/` | Update or remove affected tests |
| CLI entry point broken | `agentic-ai --help` | Verify entry point still resolves |
| Third-party plugin imports deleted path | Grep for deleted package names in config/plugin files | Document breaking changes |

### T-03: Retrieval FTS

| What Could Regress | How to Detect | Mitigation |
|--------------------|--------------|------------|
| Retrieval recall drops | Golden query set comparison | Assert recall >= 1.0 vs old scan |
| Retrieval ranking changes | Compare top-5 results for golden queries | Accept ranking changes if recall preserved |
| Indexing breaks | E2E indexing test | FTS5 update integrated into existing chunk insert path |
| Existing ChunkStore callers break | API signature check | Keep `get_all()` method (deprecated) alongside FTS |

### T-04: Unify Infrastructure

| What Could Regress | How to Detect | Mitigation |
|--------------------|--------------|------------|
| Import resolution breaks | Recursive import test + lint rule | Run lint on every file before merge |
| LLM provider stops working | Per-provider integration test | Test each provider individually |
| SSE streaming breaks with httpx | Streaming test per provider | httpx supports SSE; verify with mock |
| Completion quality changes | Completion benchmark comparison | Compare before/after on fixed scenarios |
| Connection pool exhaustion | Load test with 20 concurrent requests | Verify pool settings match or exceed old combined pools |

### T-05: Fault Recovery

| What Could Regress | How to Detect | Mitigation |
|--------------------|--------------|------------|
| FileWatcher happy path changes | Existing FileWatcher tests | Run before and after |
| MCP tool call latency increases | Benchmark tool call latency | Heartbeat must be lightweight |
| CPU usage at idle increases | CPU benchmark at idle | Watchdog interval must be seconds, not milliseconds |
| Idempotency behavior changes | Existing idempotency tests | Preserve `InMemoryIdempotencyStore` API |

---

## 5. Regression Test Execution Protocol

### Before Each Task

1. Record baseline: run full test suite, capture pass/fail counts
2. Record baseline benchmarks for affected metrics
3. Tag the pre-change commit

### After Each Task

1. Run full test suite — compare pass/fail counts to baseline
2. Run affected benchmarks — compare to baseline
3. Run manual validation checklist for the phase
4. Any unexpected test failure blocks merge until investigated

### After All Tasks

1. Run full test suite from clean checkout
2. Run all benchmarks
3. Run complete manual validation checklist
4. Compare server behavior to pre-refactoring baseline (same requests → same responses)

---

## 6. Rollback Plan

Each phase must be independently revertable:

| Phase | Rollback Method | Data Migration |
|-------|----------------|----------------|
| A (T-02) | `git revert` the commit | None (config only) |
| B (T-01) | `git revert` — restores deleted files | None (no data changes) |
| C1 (T-03) | `git revert` + drop FTS5 table | `DROP TABLE IF EXISTS chunks_fts` |
| C2 (T-05) | `git revert` + drop idempotency table | `DROP TABLE IF EXISTS idempotency_store` |
| D (T-04) | `git revert` — restores old imports | None (no data changes), but must also revert lint rule |

**Critical**: Phase D revert is the most complex because it touches hundreds of files. Consider splitting T-04 into sub-PRs:
1. Import convention change (mechanical, easily reverted)
2. HTTP client consolidation
3. LLM port implementation
4. Completion-retrieval wiring

Each sub-PR is independently revertable.
