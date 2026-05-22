# MASTER BUILD PROMPT - Part 1 (Phases 1a-5b)

**Hướng dẫn thực hiện tự động toàn bộ dự án AI_SUPPORT**

## QUY TẮC THỰC HIỆN

1. **Đọc prompt phase hiện tại** từ file này
2. **Tạo/sửa code** đúng cấu trúc thư mục đã định
3. **Viết unit test** (pytest) cho từng task
4. **Commit** sau mỗi task (Conventional Commits)
5. **Ghi log** vào `build_log.md`
6. **Tự động sửa lỗi** nếu có thể
7. **Tiếp tục** không cần hỏi lại

---

## PHASE 1a: Minimal Viable Runtime

### Mục tiêu
Server WebSocket cơ bản, mock agent streaming, session management

### Cấu trúc thư mục
```
src/
├── core/
│   ├── agent/mock_agent.py      # Mock streaming response
│   └── session/session_manager.py # In-memory session
└── interfaces/server/
    ├── main.py                  # FastAPI + WebSocket
    └── websocket/
        ├── client.py           # WS client wrapper
        └── manager.py          # Connection manager
```

### Tasks
- [ ] Tạo `src/core/agent/mock_agent.py` - Mock agent với `stream_response(message, send_event, cancellation_event)`
- [ ] Tạo `src/core/session/session_manager.py` - In-memory session management
- [ ] Tạo `src/interfaces/server/websocket/client.py` - WebSocket client wrapper
- [ ] Tạo `src/interfaces/server/websocket/manager.py` - Connection manager (multi-client per session)
- [ ] Tạo `src/interfaces/server/main.py` - FastAPI server với:
  - `POST /sessions` - Create session
  - `GET /sessions/{id}` - Get session
  - `DELETE /sessions/{id}` - Delete session
  - `WS /ws/{session_id}` - WebSocket endpoint
  - `GET /health` - Health check
- [ ] Events: `token`, `done`, `error` (BUSY, SESSION_NOT_FOUND)
- [ ] Unit tests cho tất cả components
- [ ] Integration test với httpx + websockets

### Non-Goals
- Không có persistence, heartbeat, cancellation, timeout, backpressure, rate limiting
- Không có LLM, tool calling, MCP, security

---

## PHASE 1b: Runtime Hardening

### Mục tiêu
Thêm reliability features: persistence, heartbeat, cancellation, timeout, backpressure, rate limiting

### Cấu trúc thư mục
```
src/
├── core/
│   ├── runtime/runtime_manager.py  # Stream cancellation/timeout
│   └── rate_limiter.py             # Sliding window rate limiter
├── infrastructure/
│   └── persistence/sqlite/
│       ├── schema.sql
│       └── session_store.py
└── runtime/__init__.py  # Stub compatibility
```

### Tasks
- [ ] Tạo `src/infrastructure/persistence/sqlite/schema.sql` - Sessions table
- [ ] Tạo `src/infrastructure/persistence/sqlite/session_store.py` - SQLite persistence
- [ ] Tạo `src/core/runtime/runtime_manager.py` - Stream cancellation + timeout
- [ ] Tạo `src/core/rate_limiter.py` - Sliding window rate limiter (5 req/10s)
- [ ] Cập nhật `websocket/client.py` - Heartbeat (ping/pong 30s) + backpressure (Queue maxsize=100)
- [ ] Cập nhật `main.py` - Load sessions on startup, event types: `ping`, `pong`, `cancelled`
- [ ] Error codes: `RATE_LIMITED`, `TIMEOUT`, `MAX_CONNECTIONS`
- [ ] Unit tests: session_store, rate_limiter, runtime_manager
- [ ] Integration tests

### Non-Goals
- Không có tool execution, LLM, MCP

---

## PHASE 2a: MCP Integration

### Mục tiêu
Kết nối MCP servers qua stdio transport, discover tools

### Cấu trúc thư mục
```
src/
├── infrastructure/mcp/
│   ├── manager.py      # MCPClientManager
│   └── config.py       # MCPConfigLoader, MCPServerConfig
└── configs/mcp/servers.yaml
```

### Tasks
- [ ] Tạo `configs/mcp/servers.yaml` - Default filesystem server
- [ ] Tạo `src/infrastructure/mcp/config.py` - MCPServerConfig (Pydantic), MCPConfigLoader
- [ ] Tạo `src/infrastructure/mcp/manager.py` - MCPClientManager:
  - Load config from YAML
  - Spawn stdio subprocess
  - Initialize handshake (60s timeout)
  - List tools (30s timeout)
  - Namespaced tool registry (server_name/tool_name)
  - Graceful shutdown
- [ ] Cập nhật `main.py` - Initialize MCP on startup
- [ ] Unit tests: config, manager
- [ ] Integration tests

### Non-Goals
- Không có tool execution (call_tool)

---

## PHASE 2b: Tool Execution Runtime

### Mục tiêu
Thực thi MCP tools, orchestration layer

### Cấu trúc thư mục
```
src/
├── domain/models/tool_call.py      # ToolCallState, ToolCallRecord
├── core/execution/
│   ├── tool_tracker.py            # Pending queue, history
│   └── tool_registry.py           # Dispatch, semaphore, timeout
├── infrastructure/tool_execution/
│   └── executor.py               # ToolExecutor, MCPToolExecutor
└── application/orchestration/
    └── tool_execution/service.py  # ToolExecutionService
```

### Tasks
- [ ] Tạo `src/domain/models/tool_call.py` - ToolCallState enum, ToolCallRecord dataclass
- [ ] Tạo `src/core/execution/tool_tracker.py` - Pending/history management, async lock
- [ ] Tạo `src/core/execution/tool_registry.py` - Semaphore concurrency, asyncio.wait_for timeout
- [ ] Tạo `src/infrastructure/tool_execution/executor.py` - ToolExecutor (abstract), MCPToolExecutor
- [ ] Tạo `src/application/orchestration/tool_execution/service.py` - ToolExecutionService
- [ ] WebSocket events: `tool_call`, `tool_call_start`, `tool_call_result`, `tool_call_error`
- [ ] Error codes: TOOL_NOT_FOUND, TIMEOUT, MCP_ERROR, INVALID_ARGUMENTS, etc.
- [ ] Session lifecycle: create ToolTracker/ToolRegistry on session create
- [ ] Unit tests: tool_tracker, tool_executor, tool_registry
- [ ] Integration tests

### Non-Goals
- Không có cancel_tool, retry, streaming results, security

---

## PHASE 2c: True Cancellation + Retry

### Mục tiêu
Abort in-flight tool calls, automatic retry with backoff

### Tasks
- [ ] Tạo `src/core/execution/cancellation.py` - CancellationToken, CancellationScope
- [ ] Cập nhật `MCPToolExecutor` - Propagate cancellation to MCP subprocess
- [ ] Tạo `src/infrastructure/tool_execution/retry.py` - RetryPolicy, ExponentialBackoff
- [ ] Thêm `tool_cancel` message type
- [ ] Unit tests: cancellation, retry
- [ ] Integration tests

---

## PHASE 2d: Multi-Server Routing + Load Balancing

### Mục tiêu
Route tool calls to appropriate MCP servers, load balancing

### Tasks
- [ ] Tạo `src/infrastructure/router/router.py` - ToolRouter, RoundRobin, LeastLoaded strategies
- [ ] Cập nhật `MCPToolExecutor` - Multi-server support
- [ ] Health checking, connection pooling
- [ ] Unit tests: router strategies
- [ ] Integration tests

---

## PHASE 3: LLM Integration

### Mục tiêu
Thay mock agent bằng real LLM (OpenAI/Anthropic), tool calling

### Cấu trúc thư mục
```
src/
├── infrastructure/llm/
│   ├── provider.py       # LLMProvider interface
│   ├── openai_llm.py     # OpenAI implementation
│   ├── anthropic_llm.py  # Anthropic implementation
│   └── ollama_llm.py     # Ollama (local) implementation
└── configs/llm/
    └── providers.yaml
```

### Tasks
- [ ] Tạo `src/infrastructure/llm/provider.py` - LLMProvider abstract class
- [ ] Tạo `src/infrastructure/llm/openai_llm.py` - OpenAI GPT-4
- [ ] Tạo `src/infrastructure/llm/anthropic_llm.py` - Anthropic Claude
- [ ] Tạo `src/infrastructure/llm/ollama_llm.py` - Ollama local
- [ ] Tạo `configs/llm/providers.yaml` - LLM configuration
- [ ] Cập nhật `mock_agent.py` → `agent.py` - Real LLM + tool calling
- [ ] Tool use from LLM → ToolExecutionService
- [ ] Streaming responses with tool results interleaved
- [ ] Unit tests: LLM providers (mock)
- [ ] Integration tests

---

## PHASE 4a: Tool Caching

### Mục tiêu
Cache tool results, reduce redundant calls

### Tasks
- [ ] Tạo `src/infrastructure/cache/tool/cache.py` - ToolResultCache, TTL-based eviction
- [ ] Cập nhật `ToolRegistry` - Integrate cache
- [ ] Cache key: tool_name + arguments hash
- [ ] Invalidate on cache clear
- [ ] Unit tests: cache TTL, eviction

---

## PHASE 4b: Semantic Router

### Mục tiêu
Route requests based on semantic similarity

### Tasks
- [ ] Tạo `src/infrastructure/router/semantic_router.py` - SemanticRouter
- [ ] Embed requests using LLM
- [ ] Route to appropriate handler/agent
- [ ] Unit tests

---

## PHASE 4c: Semantic Memory

### Mục tiêu
Persistent semantic memory using embeddings

### Tasks
- [ ] Tạo `src/core/memory/semantic_memory.py` - SemanticMemory
- [ ] Embedding storage and retrieval
- [ ] ChromaDB integration (optional)
- [ ] Fallback to in-memory
- [ ] Unit tests

---

## PHASE 4d: Memory Compression

### Mục tiêu
Compress old memories, prune irrelevant ones

### Tasks
- [ ] Tạo `src/core/memory/compression/pruner.py` - MemoryPruner
- [ ] Importance scoring
- [ ] LLM-based summarization
- [ ] Tiered storage
- [ ] Unit tests

---

## PHASE 5a: Workflow Runtime

### Mục tiêu
Workflow execution engine with DAG

### Tasks
- [ ] Tạo `src/core/runtime/workflow/engine.py` - WorkflowEngine
- [ ] DAG definition, topological sort
- [ ] Parallel execution
- [ ] Error handling and retry
- [ ] Unit tests

---

## PHASE 5b: Enterprise Planner

### Mục tiêu
Task decomposition and planning

### Tasks
- [ ] Tạo `src/application/planner/planner.py` - TaskPlanner
- [ ] LLM-based task decomposition
- [ ] Dependency graph generation
- [ ] Plan validation
- [ ] Unit tests

---

## PHASE 5d: Multi-Agent Coordination

### Mục tiêu
Multiple agents working together

### Tasks
- [ ] Tạo `src/core/multi_agent/coordination/` - Coordination layer
- [ ] Agent roles and responsibilities
- [ ] Message passing
- [ ] Conflict resolution
- [ ] Unit tests

---

## BẮT ĐẦU THỰC HIỆN

**Thực hiện tuần tự từ Phase 1a.**

Mỗi phase cần:
1. Đọc chi tiết prompt trong `docs/phase*.md`
2. Tạo code + unit tests
3. Chạy tests
4. Commit với message theo format: `feat(phase-N): description`
5. Cập nhật `build_log.md`
6. Tiếp tục phase tiếp theo

**Nếu gặp lỗi**: Tự sửa nếu có thể, hoặc báo cáo rõ ràng.
