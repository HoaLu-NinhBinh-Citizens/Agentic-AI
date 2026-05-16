# Phase 1A: Minimal Viable Runtime

## Overview

Phase 1A implements the minimal viable runtime foundation for AI_support. It allows clients (VS Code extension, CLI, TUI) to create sessions, send chat messages over WebSocket, and receive streaming tokens from a mock agent.

## Technology Stack

| Component | Technology |
|-----------|------------|
| Web framework | FastAPI + Uvicorn |
| WebSocket | FastAPI native WebSocket support |
| Data validation | Pydantic (minimal, only for API) |
| Concurrency | asyncio (no threading) |
| Testing | pytest + pytest-asyncio + httpx + websockets |

## Event Protocol (WebSocket)

### Server → Client Events

Only THREE event types:

| Type | Payload | When |
|------|---------|------|
| `token` | `{"content": "H", "is_last": false}` | Each chunk of response |
| `done` | `{"success": true}` | After all tokens sent |
| `error` | `{"code": "BUSY", "message": "..."}` | On failure |

### Event Format

```json
{
  "type": "token",
  "data": {
    "content": "Hello",
    "is_last": false
  }
}
```

### Error Codes

| Code | When | Description |
|------|------|-------------|
| `BUSY` | Session has ongoing streaming | Only one chat can run per session at a time. Returned when client sends a second chat while the first is still streaming. |
| `SESSION_NOT_FOUND` | Invalid session ID | Session does not exist or has been deleted. |

## Session States

| State | Description |
|-------|-------------|
| `active` | Session exists and can accept chat messages |
| `ended` | Session has been deleted |

**Note:** `busy` is a runtime state (not persisted), indicating an ongoing streaming operation within an active session. It is not a session state.

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

## Logging Conventions

| Level | Usage |
|-------|-------|
| `INFO` | Session lifecycle: create, delete, WebSocket connect/disconnect |
| `DEBUG` | WebSocket messages: incoming chat, outgoing tokens |
| `ERROR` | Exceptions, send failures, unexpected conditions |

## API Endpoints

### Create Session

```bash
curl -X POST http://localhost:8000/sessions
# Response: {"session_id": "abc-123", "ws_url": "ws://localhost:8000/ws/abc-123"}
```

With workspace:

```bash
curl -X POST http://localhost:8000/sessions -H "Content-Type: application/json" -d '{"workspace": "/path/to/workspace"}'
```

### Get Session Info

```bash
curl http://localhost:8000/sessions/{session_id}
# Response: {"id": "...", "created_at": "...", "workspace": null, "status": "active"}
```

### Delete Session

```bash
curl -X DELETE http://localhost:8000/sessions/{session_id}
# Response: {"status": "deleted"}
```

### Health Check

```bash
curl http://localhost:8000/health
# Response: {"status": "ok"}
```

## WebSocket Chat

### Connect to WebSocket

```bash
websocat ws://localhost:8000/ws/{session_id}
```

### Send Chat Message

```json
{"type": "chat", "message": "Hello, world!"}
```

### Receive Token Events

```json
{"type": "token", "data": {"content": "H", "is_last": false}}
{"type": "token", "data": {"content": "e", "is_last": false}}
{"type": "token", "data": {"content": "l", "is_last": false}}
{"type": "token", "data": {"content": "l", "is_last": false}}
{"type": "token", "data": {"content": "o", "is_last": true}}
{"type": "done", "data": {"success": true}}
```

### Multiple WebSocket Clients Per Session

A session can have multiple WebSocket connections. When a chat message is sent:

1. Events (tokens, done, error) are broadcast to **all** WebSocket connections of that session
2. Any connected client receives the same streaming response
3. This enables multi-client collaboration (e.g., IDE + CLI connected to same session)

### Error Handling

If `send_json` raises an exception (e.g., WebSocket disconnected):

1. Log the error at `ERROR` level
2. Stop streaming for that connection
3. Continue streaming to other connected clients (if any)
4. Cleanup resources when the WebSocket is disconnected

## Architecture

```
src/
├── core/
│   ├── agent/
│   │   └── mock_agent.py       # Mock agent for streaming responses
│   └── session/
│       └── session_manager.py    # In-memory session management
└── interfaces/
    └── server/
        ├── main.py              # FastAPI server
        └── websocket/
            └── manager.py       # WebSocket connection manager
```

## Non-Goals (Explicitly Excluded)

| Category | What NOT to implement |
|----------|----------------------|
| Persistence | SQLite, files, any database |
| Heartbeat | ping-pong, keepalive |
| Cancellation | abort ongoing agent task |
| Timeout | request timeout, idle timeout |
| Backpressure | bounded queues, flow control |
| Rate limiting | per-session or global limits |
| Task management | registry, supervision, orchestration |
| Real AI | LLM, tool calling, MCP |
| Security | authentication, authorization |

These will be added in later phases (1B, 2, 3...).

## Testing

### Run All Tests

```bash
python -m pytest tests/ -v
```

### Run Unit Tests Only

```bash
python -m pytest tests/unit/ -v
```

### Run Integration Tests Only

```bash
python -m pytest tests/integration/ -v
```

### With Coverage

```bash
python -m pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=70
```

## Definition of Done

- [x] Server starts without errors
- [x] POST /sessions returns session ID and WebSocket URL
- [x] GET /sessions/{id} returns session info
- [x] DELETE /sessions/{id} deletes session
- [x] GET /health returns {"status": "ok"}
- [x] WebSocket connects with valid session ID
- [x] Sending {"type": "chat", "message": "hello"} returns token events followed by done
- [x] Sending second chat while first is streaming returns BUSY error
- [x] WebSocket closes with code 4001 for invalid session
- [x] All unit tests pass
- [x] All integration tests pass
- [x] Coverage ≥ 70%
- [x] No print() statements (use logging)
- [x] Documentation complete

## Next Phase (1B - Explicitly NOT in Phase 1A)

- SQLite persistence for sessions
- Heartbeat / ping-pong to detect dead clients
- Graceful cancellation of streaming
- Request timeout
- Token-level backpressure (bounded queue)
- Rate limiting
