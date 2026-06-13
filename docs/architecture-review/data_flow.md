# Data Flow & Runtime Lifecycle

> **Document type**: Read-only baseline analysis — no code was modified.
> **Date**: 2026-06-13

---

## 1. Request Lifecycle (Chat Message)

### Stage-by-stage flow

```
User types message in Electron IDE
  │
  ▼
[1] ChatPanel.tsx → useAI hook → WebSocket.send({type: "chat", message: "..."})
  │
  ▼
[2] FastAPI WebSocket handler (main.py:474)
    ├── Checks: is session streaming? → reject with BUSY
    ├── Rate limiter: SlidingWindowRateLimiter (5 req / 10s per session)
    └── If allowed → RuntimeManager.execute()
  │
  ▼
[3] RuntimeManager.execute() (runtime_manager.py:56)
    ├── Creates asyncio.Event for cancellation
    ├── Creates StreamInfo tracking object
    ├── Wraps in asyncio.wait_for(timeout=30s)
    └── Calls RealAgent.stream_response()
  │
  ▼
[4] RealAgent.stream_response() (real_agent.py)
    ├── Lazy-initializes LLMManager if first call
    │     └── Detects provider: OPENAI_API_KEY → ANTHROPIC_API_KEY → Ollama
    ├── Sends prompt to LLMManager
    └── Streams tokens back via send_event callback
  │
  ▼
[5] LLMManager → Provider Adapter (e.g., openai_llm.py)
    ├── Builds HTTP request with provider-specific format
    ├── Sends via httpx.AsyncClient (shared pool, 100 connections)
    ├── Dynamic timeout: e.g., Anthropic 120 + prompt_chars/50 (max 300s)
    ├── Retry with exponential backoff (max 2 retries)
    └── Streams SSE response, parses token/tool_call events
  │
  ▼
[6] Token streaming back to client
    ├── Each token → send_event({type: "token", data: {text: "..."}})
    ├── Tool calls accumulated via ToolAccumulator
    ├── On complete → send_event({type: "done"})
    └── WebSocket client receives and renders incrementally
  │
  ▼
[7] Electron renderer displays tokens in ChatPanel
```

### Error/Cancellation Paths

```
Timeout (30s server-side):
  RuntimeManager catches asyncio.TimeoutError
  → Sets cancellation_event
  → Sends {type: "error", code: "TIMEOUT"}
  → Cleans up StreamInfo

User cancels:
  WebSocket receives {type: "cancel"}
  → RuntimeManager.cancel_stream(session_id)
  → Sets cancellation_event on StreamInfo
  → Agent's streaming loop checks event and exits

WebSocket disconnect:
  finally block in websocket_endpoint
  → cancel_stream_for_client(session_id, client)
  → disconnect(session_id, client)
  → client.close()
```

---

## 2. Request Lifecycle (Tool Execution)

```
Client sends {type: "tool_call", data: {tool_name, arguments, call_id, trace_id}}
  │
  ▼
[1] handle_tool_call() (main.py:538)
    ├── Validates tool_name and arguments exist
    └── Calls ToolExecutionService.execute_tool()
  │
  ▼
[2] ToolExecutionService.execute_tool() (service.py:72)
    ├── Looks up ToolRegistry from PersistentSessionManager
    ├── If pipeline exists → runs through middleware chain
    ├── Finds tool in registry (built-in or MCP-discovered)
    └── Executes tool
  │
  ▼
[3] Tool execution (built-in or MCP)
    ├── Built-in: direct Python function call
    └── MCP: MCPClientManager.call_tool()
          ├── JSON-RPC over stdio to MCP server subprocess
          ├── Circuit breaker check
          └── Response parsing
  │
  ▼
[4] Result broadcast
    ├── broadcast_to_session({type: "tool_call_result", data: {...}})
    └── On error: broadcast({type: "tool_call_error", data: {...}})
```

---

## 3. Request Lifecycle (Inline Completion)

```
User types in Editor (Electron)
  │
  ▼
[1] useInlineCompletion hook detects keystroke
    ├── Debounce: 150ms
    └── Builds context: file_path, cursor_line, cursor_col, prefix, suffix
  │
  ▼
[2] Path A: Electron → ollamaClient.ts → Ollama /api/generate directly
    OR
    Path B: Electron → Backend → CompletionEngine → Ollama
  │
  ▼
[3] CompletionEngine (completion_engine.py)
    ├── Cache check: LRU keyed by file_path|line|col|file_hash
    ├── If miss → build FIM prompt: <PRE>{prefix}<SUF>{suffix}<MID>
    ├── Stream from Ollama via httpx
    ├── Yield characters until first \n (single-line)
    └── Store in cache
  │
  ▼
[4] Electron renders ghost text in Editor
```

**Observation**: The Electron IDE has its own `ollamaClient.ts` which may call Ollama directly, bypassing the backend CompletionEngine. NEED MORE EVIDENCE on which path is used in practice.

---

## 4. Runtime Lifecycle

### Startup Sequence

```
[1] uvicorn starts → loads interfaces.server.main:app

[2] FastAPI lifespan handler begins (main.py:122)
    │
    ├─[3] SessionStore() → aiosqlite.connect() → CREATE TABLE IF NOT EXISTS
    │     └── PersistentSessionManager(store) → set_config(tool_config)
    │     └── await session_manager.initialize()
    │         └── Loads existing sessions from SQLite
    │
    ├─[4] ConnectionManager() — empty, awaits WebSocket connections
    │
    ├─[5] RealAgent() — lazy init, no LLM connection yet
    │     └── RuntimeManager(real_agent) → await start()
    │
    ├─[6] MCPClientManager (conditional)
    │     ├── Checks configs/mcp/servers.yaml exists
    │     ├── If yes → await mcp_manager.initialize() with 15s timeout
    │     │     ├── Reads YAML config
    │     │     ├── Spawns MCP server subprocesses (stdio)
    │     │     ├── JSON-RPC initialize handshake per server
    │     │     └── Discovers tools from each server
    │     └── If no config or error → mcp_manager = None (skipped)
    │
    ├─[7] session_manager.set_mcp_manager(mcp_manager)
    │
    ├─[8] ToolExecutionService(session_manager)
    │
    ├─[9] IndexingService (conditional, AI_SUPPORT_ENABLE_INDEXING=1)
    │     ├── ChromaDBKnowledgeStore(DEFAULT_KB_DIR)
    │     ├── KnowledgeBase(store=chromadb_store)
    │     ├── EmbeddingService() — connects to Ollama for bge-m3
    │     ├── IncrementalIndexer(kb, embed_svc, state_db)
    │     │     └── SQLite state DB (.ai_support/index_state.db)
    │     ├── FileWatcher(workspace, callback)
    │     │     └── watchdog Observer on workspace directory
    │     └── await indexing_service.start()
    │           ├── indexer.connect() — opens state DB
    │           ├── watcher.start() — begins filesystem monitoring
    │           └── create_task(indexer.sync()) — initial full sync
    │
    └─[10] ServerState assembled, stored in app.state.server_state
           └── Logger: "Loaded N active sessions from database"

[11] yield — server is now accepting requests

[12] Shutdown sequence (on SIGINT/SIGTERM):
     ├── indexing_service.stop() — stops watcher, waits for pending tasks
     ├── session_manager.close() — closes SQLite connection
     ├── runtime_manager.stop() — cancels all active streams
     ├── connection_manager.close_all_for_session("*") — closes all WebSockets
     └── mcp_manager.shutdown() — kills MCP server subprocesses
```

### Background Workers & Watchers

| Worker | Type | Lifecycle | Restart Behavior |
|--------|------|-----------|-----------------|
| **FileWatcher** | watchdog thread | Starts with IndexingService | No auto-restart. If thread dies, indexing stops silently. |
| **MCP server processes** | stdio subprocess | Spawned during init | No heartbeat. Death detected only on next RPC call. |
| **Rate limiter pruning** | Lazy (on next request) | Triggered every 60s if requests arrive | Self-healing. |
| **Session TTL** | Lazy (on access) | Checked when session is retrieved | Expired sessions remain in SQLite until accessed. |
| **Stream timeout** | asyncio.wait_for | 30s per chat request | Task cancelled on timeout. |
| **Heartbeat** | WebSocket ping/pong | Per connection | Connection closed if pong not received. |

### Caches

| Cache | Location | Size | TTL | Invalidation |
|-------|----------|------|-----|-------------|
| **Session cache** | PersistentSessionManager | In-memory dict | 1hr default | On delete, on access (TTL check) |
| **Embedding cache** | EmbeddingService | LRU 4,096 entries | None (LRU eviction) | Never — stale embeddings persist until evicted |
| **Completion cache** | CompletionEngine | LRU 512 entries | None | Per-file invalidation on save |
| **Fix cache** | FixCache | LRU 500 entries | 7 days | By rule_id:code_hash key |
| **Content hash cache** | IncrementalIndexer | LRU 10,000 entries | None | LRU eviction |
| **Rate limiter** | ServerState | Dict per session | 30min idle TTL | Pruned every 60s on request |
| **Tool cache** | infrastructure/cache/tool/ | Configurable | Adaptive TTL | 15-component system with SWR |

---

## 5. Event Flow

### Application Events (core/events/)

```
[Source Component]
  │
  ▼
EventEmitter.emit(Event)
  │
  ├── LoggingMiddleware → logs event
  ├── MetricsMiddleware → records metrics
  │
  ▼
[Registered Handlers]
  ├── LoggingHandler
  ├── MetricsHandler
  └── AlertHandler
```

**Event types** (from domain event modules):
- `codegen_events.py` — code generation start, complete, error
- `firmware_events.py` — flash start, complete, verify
- `hardware_events.py` — probe connect, disconnect, error
- `runtime_events.py` — agent start, stop, error
- `session_events.py` — session create, delete, expire
- `workflow_events.py` — workflow start, step, complete, rollback

**Observation**: The event system exists and is fully implemented, but its integration with the main server loop (the `websocket_endpoint` handler) is unclear. The server sends WebSocket events directly via `send_event` callbacks, not through the EventEmitter. The two event systems (WebSocket protocol events and domain EventEmitter events) appear to be disconnected.

**NEED MORE EVIDENCE**: Whether `EventEmitter` is instantiated and used in the production serving path.

### WebSocket Protocol Events (transport layer)

```
Server → Client events:
  {type: "token",           data: {text, ...}}
  {type: "done",            data: {}}
  {type: "error",           data: {code, message}}
  {type: "tool_call_start", data: {call_id, tool_name}}
  {type: "tool_call_result",data: {call_id, result}}
  {type: "tool_call_error", data: {call_id, error}}
  {type: "ping",            data: {}}

Client → Server events:
  {type: "chat",      message: "..."}
  {type: "cancel",    data: {}}
  {type: "tool_call", data: {tool_name, arguments, call_id, trace_id}}
  {type: "pong",      data: {}}
```

---

## 6. Indexing Data Flow

```
[Filesystem event] ← watchdog Observer
  │
  ▼
FileWatcher.on_change(FileChange)
  ├── Debounce: 0.5s per path
  ├── Filter: .py, .js, .ts, .c, .cpp, .h, .go, .rs, etc.
  └── call_soon_threadsafe → asyncio loop
  │
  ▼
IndexingService._on_watcher_change()
  └── IncrementalIndexer.reindex_files([changed_paths])
  │
  ▼
IncrementalIndexer
  ├── [1] Compute content hash (ThreadPoolExecutor)
  ├── [2] Compare with SQLite state DB
  │       └── Skip unchanged files (hash match)
  ├── [3] Parse with SafeTreeSitterIndexer
  │       ├── Full parse (<5000 lines)
  │       ├── Partial parse (5000-100000 lines)
  │       ├── Incremental parse (very large)
  │       └── Regex fallback (if tree-sitter unavailable)
  ├── [4] Chunk content (HardwareChunker)
  │       ├── Register specs → split at headers
  │       ├── Code → split at function boundaries
  │       └── Generic → paragraph split with overlap
  ├── [5] Generate embeddings (EmbeddingService)
  │       ├── Ollama bge-m3 via aiohttp
  │       ├── LRU cache check first
  │       ├── Retry with exponential backoff
  │       └── Fallback: hash-based deterministic embedding
  ├── [6] Upsert into KnowledgeBase
  │       └── ChromaDB.add() with metadata
  └── [7] Update SQLite state DB (path, hash, timestamp)
```

---

## 7. Retrieval Data Flow

```
Query arrives (from agent or API)
  │
  ▼
HybridRetriever.search_docs(query)
  │
  ├── [1] Lexical search: _search_chunk_store()
  │       ├── Build query terms from query object
  │       ├── ChunkStore.get_all() ← returns ALL chunks
  │       ├── For each chunk: score by term overlap
  │       └── Returns scored RetrievalHit list
  │
  ├── [2] Semantic search: _search_vector_index()
  │       ├── VectorIndex.search(query_embedding, top_k)
  │       │     ├── NumPy cosine similarity (brute force)
  │       │     └── OR ChromaDB HNSW (if via KnowledgeBase path)
  │       └── Returns similarity scores per chunk
  │
  ├── [3] Merge: _merge_hits(lexical, vector_scores)
  │       └── Combine scores from both sources
  │
  ├── [4] Reference KB: _search_reference_kb()
  │       └── Additional domain knowledge hits
  │
  ├── [5] Rerank: _rerank_hits(query, merged)
  │       └── Deterministic reranking algorithm
  │
  └── [6] Dedupe + top_k: _dedupe_hits_by_path()[:top_k]
          └── Final ranked results
```

---

## 8. AI Pipeline Summary

```
[Input] User message or code context
  │
  ▼
[Retrieval] HybridRetriever (if context needed)
  ├── Lexical: O(N) scan of ChunkStore
  └── Semantic: ChromaDB HNSW or NumPy brute-force
  │
  ▼
[Embedding] Ollama bge-m3 (for query embedding)
  ├── LRU cache check
  └── HTTP to localhost:11434/api/embeddings
  │
  ▼
[Prompt Construction] RealAgent / LLMAgentService
  ├── System prompt + context + user message
  ├── Tool definitions (if tool calling enabled)
  └── Token limit: 8000 (LLMAgentService) or 2048 (RealAgent)
  │
  ▼
[LLM Invocation] LLMManager → Provider Adapter
  ├── Provider selection by env vars or role routing
  ├── HTTP streaming via httpx/aiohttp
  ├── Circuit breaker + retry (max 2, exp backoff)
  └── Dynamic timeout (120-300s depending on provider)
  │
  ▼
[Streaming] SSE parsing → token events
  ├── ToolAccumulator for partial tool calls
  └── Token-by-token callback to WebSocket
  │
  ▼
[Edit Application] (if LLM returns diff/fix)
  ├── DiffEngine: parse unified diff
  ├── EditSession: conflict detection + TOCTOU check
  ├── Auto-backup before apply
  ├── Fuzzy hunk matching (±20 lines)
  └── Rollback on failure
```
