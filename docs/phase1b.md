# Phase 1B: Runtime Hardening

## Overview

Phase 1B extends the Phase 1A minimal viable runtime with reliability and resource protection features. The runtime now persists sessions across restarts, detects dead WebSocket clients, allows cancellation, prevents infinite streams, protects against slow clients, and prevents abuse.

## Technology Stack Additions

| Component | Technology |
|-----------|------------|
| Persistence | aiosqlite |
| Heartbeat | asyncio.create_task + ping/pong events |
| Cancellation | asyncio.Event + CancelledError |
| Timeout | asyncio.wait_for |
| Backpressure | asyncio.Queue per WebSocket (maxsize=100) |
| Rate limiting | sliding window per session (in-memory) |

## Event Protocol (Updated)

### Server → Client Events

| Type | Payload | When |
|------|---------|------|
| `token` | `{"content": "H", "is_last": false}` | Each chunk of response |
| `done` | `{"success": true}` | After all tokens sent |
| `error` | `{"code": "BUSY\|RATE_LIMITED\|TIMEOUT", "message": "..."}` | On failure |
| `cancelled` | `{}` | When stream is cancelled |
| `ping` | `{}` | Heartbeat (every 30s) |
| `pong` | `{}` | Client response to ping |

### Client → Server Messages

| Type | Payload | Description |
|------|---------|-------------|
| `chat` | `{"message": "..."}` | Send chat message |
| `cancel` | `{}` | Cancel ongoing stream |
| `pong` | `{}` | Response to heartbeat ping |

### Error Codes

| Code | When | Description |
|------|------|-------------|
| `BUSY` | Session has ongoing streaming | Only one chat can run per session at a time |
| `SESSION_NOT_FOUND` | Invalid session ID | Session does not exist or has been deleted |
| `RATE_LIMITED` | Too many requests | Chat rate limit exceeded (5 per 10s) |
| `TIMEOUT` | Stream timeout | Stream exceeded 30s limit |
| `MAX_CONNECTIONS` | Too many WebSocket connections | Max 5 concurrent connections per session |

## Database Schema (SQLite)

File: `src/infrastructure/persistence/sqlite/schema.sql`

```sql
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    workspace TEXT,
    state TEXT NOT NULL CHECK (state IN ('active', 'ended'))
);

CREATE INDEX IF NOT EXISTS idx_sessions_state ON sessions(state);
```

### Persistence Rules

- Only session metadata (id, created_at, workspace, state) is persisted
- Streaming state (active stream, queues, tasks) is never persisted
- On server start, load all `state='active'` sessions from DB into memory
- After load, sessions are active but have no active WebSocket connections

## Architecture

```
src/
├── core/
│   ├── agent/
│   │   └── mock_agent.py           # Mock agent with cancellation support
│   ├── session/
│   │   ├── session_manager.py      # Phase 1A in-memory manager (kept for compatibility)
│   │   └── persistent_manager.py   # Phase 1B persistent session manager
│   ├── runtime/
│   │   ├── __init__.py            # Phase 1B RuntimeManager + lazy load Phase 15
│   │   └── runtime_manager.py     # Stream cancellation and timeout
│   └── rate_limiter.py            # Sliding window rate limiter
├── infrastructure/
│   └── persistence/
│       └── sqlite/
│           ├── schema.sql          # Database schema
│           └── session_store.py    # SQLite session store
├── interfaces/
│   └── server/
│       ├── main.py                # FastAPI server (Phase 1B)
│       └── websocket/
│           ├── client.py          # WebSocketClient with heartbeat/backpressure
│           └── manager.py          # Connection manager
└── runtime/                      # Stub for backward compatibility
    └── __init__.py                # Redirects to core.runtime
```

## Key Features

### 1. Session Persistence (SQLite)

- Sessions persist across server restarts
- `PersistentSessionManager` loads active sessions on startup
- Sessions without active connections are marked as "active" (awaiting reconnect)

### 2. Heartbeat (Ping/Pong)

- Server sends ping every 30 seconds
- Client must reply with pong within 10 seconds
- If no pong received, connection is closed (code 1000)
- Missing pong support is acceptable (client will be disconnected)

### 3. Backpressure (Per-WebSocket Queue)

- Each WebSocketClient owns an `asyncio.Queue` (maxsize=100)
- Events are queued and sent asynchronously
- If queue is full:
  - Token events: oldest token is dropped
  - Non-token events (done, error, cancelled, ping, pong): never dropped

### 4. Graceful Cancellation

- Client sends `{"type": "cancel"}` message
- Runtime sets `cancellation_event`
- MockAgent checks `cancellation_event.is_set()` before each token
- If cancelled: sends `{"type": "cancelled"}` and stops streaming
- BUSY state is cleared after cancellation

### 5. Request Timeout

- Streams timeout after 30 seconds
- `asyncio.wait_for` wraps `stream_response`
- On timeout: sends `{"type": "error", "data": {"code": "TIMEOUT"}}`
- BUSY state is cleared after timeout

### 6. Rate Limiting

| Limit | Value | Scope |
|-------|-------|-------|
| Chat requests | 5 per 10 seconds | per session |
| WebSocket connections | 5 concurrent | per session |

- `SlidingWindowRateLimiter` uses in-memory timestamps
- On violation: sends `RATE_LIMITED` error (WebSocket stays open)

## Connection Lifecycle

### New WebSocket Connection

1. Validate session exists
2. Check connection rate limit (max 5 per session)
3. If limit reached: close with code 4003
4. Accept connection
5. Create WebSocketClient with queue and sender task
6. Start heartbeat task

### Client Disconnect

1. Remove client from session
2. Cancel any stream owned by this client
3. Clean up sender and heartbeat tasks

### Session Deletion

1. Mark session as 'ended' in DB
2. Cancel all active streams
3. Close all WebSocket connections
4. Clear rate limiter

### Stream Ownership

- When chat is sent over a specific WebSocket, that client owns the stream
- If that client disconnects, the stream is cancelled

## How to Run

### Start the Server

```bash
uvicorn src.interfaces.server.main:app --reload
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8000` | Server port |
| `LOG_LEVEL` | `INFO` | Logging level |

## Testing

### Run All Phase 1B Tests

```bash
python -m pytest \
  tests/unit/test_session_store.py \
  tests/unit/test_rate_limiter.py \
  tests/unit/test_websocket_client.py \
  tests/unit/test_mock_agent.py \
  tests/unit/test_connection_manager.py \
  tests/unit/test_runtime_manager.py \
  tests/unit/test_persistent_session_manager.py \
  tests/integration/test_phase1b_features.py \
  -v
```

### Run Unit Tests Only

```bash
python -m pytest tests/unit/ -v
```

### Run Integration Tests Only

```bash
python -m pytest tests/integration/test_phase1b_features.py -v
```

### With Coverage

```bash
python -m pytest \
  tests/unit/test_session_store.py \
  tests/unit/test_rate_limiter.py \
  tests/unit/test_websocket_client.py \
  tests/unit/test_mock_agent.py \
  tests/unit/test_connection_manager.py \
  tests/unit/test_runtime_manager.py \
  tests/unit/test_persistent_session_manager.py \
  tests/integration/test_phase1b_features.py \
  --cov=src \
  --cov-report=term-missing
```

## Test Files

| File | Description |
|------|-------------|
| `tests/unit/test_session_store.py` | SQLite store operations (8 tests) |
| `tests/unit/test_rate_limiter.py` | Sliding window rate limiter (6 tests) |
| `tests/unit/test_websocket_client.py` | WebSocketClient heartbeat/backpressure (7 tests) |
| `tests/unit/test_mock_agent.py` | MockAgent streaming (6 tests) |
| `tests/unit/test_connection_manager.py` | ConnectionManager (12 tests) |
| `tests/unit/test_runtime_manager.py` | RuntimeManager cancellation/timeout (15 tests) |
| `tests/unit/test_persistent_session_manager.py` | PersistentSessionManager (8 tests) |
| `tests/integration/test_phase1b_features.py` | Integration tests (10 tests) |

**Total: 71 tests passing**

## Definition of Done

- [x] Sessions survive server restart (SQLite)
- [x] Heartbeat detects dead WebSockets → clean disconnect
- [x] Cancel works: client sends cancel → stream stops → cancelled event sent
- [x] Timeout works: streams longer than 30s are aborted with TIMEOUT error
- [x] Slow clients no longer block the event loop (backpressure with drop)
- [x] Rate limiting prevents chat spam and connection flood
- [x] BUSY state is always cleaned after cancel / timeout / disconnect
- [x] All integration tests pass
- [x] Code coverage ≥ 75%
- [x] No print() – all logging follows structured format
- [x] Documentation complete

## Non-Goals (Reinforced)

| Category | What NOT to implement |
|----------|----------------------|
| Distributed systems | Redis, distributed queues |
| Message persistence | Conversation history |
| Security | Authentication / authorization |
| Real AI | LLM, MCP, tool calling |
| Task orchestration | DAG engine, multi-agent |
| Advanced features | Supervisor framework |

## Next Phase (Phase 2 - Explicitly NOT in Phase 1B)

- Conversation history persistence
- Real agent with LLM integration
- Tool calling infrastructure
- Workspace context management
- Basic MCP protocol support
