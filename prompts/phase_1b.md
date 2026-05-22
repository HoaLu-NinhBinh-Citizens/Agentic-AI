# Phase 1b – Minimal Viable Runtime

## Lệnh Agent

```
@prompts/phase_1b.md Thực hiện tuần tự. Commit [Phase 1b]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Mục tiêu
FastAPI + WebSocket server, JWT auth, streaming token, tích hợp Ollama, tool registry cơ bản.

## Bảng sub-phase

| ID | Sub‑phase | Mô tả |
|----|-----------|-------|
| 1b.1 | FastAPI + WebSocket server | Session management, authentication JWT |
| 1b.2 | Streaming token response | SSE / WebSocket streaming |
| 1b.3 | Tích hợp LLM local (Ollama) | Gọi model, parse response |
| 1b.4 | Tool registry cơ bản | Định nghĩa tool, schema, gọi hàm |
| 1b.5 | Logging và health checks | Structured logging, /health endpoint |

## Task list (thực hiện tuần tự)

- [ ] **1b.1** `src/interfaces/server/main.py` — `/health`, sessions, `WS /ws/{session_id}`
- [ ] **1b.2** `websocket/manager.py`, `websocket/client.py`
- [ ] **1b.3** Streaming token từ mock agent — events `token`, `done`, `error`
- [ ] **1b.4** JWT auth — `python-jose`
- [ ] **1b.5** `src/infrastructure/llm/ollama_provider.py` — `generate_stream`
- [ ] **1b.6** Tool registry — `core/tools/tool_registry.py`, `domain/models/tool_call.py`
- [ ] **1b.7** Structured logging + Prometheus middleware
- [ ] **1b.8** `tests/integration/test_websocket_chat.py`, `test_session_lifecycle.py`

## Kết thúc phase

- [ ] Test: `curl http://localhost:8000/health` → OK
- [ ] Commit `[Phase 1b]`, build_log, ERA_ROADMAP

## Hướng dẫn
- Chạy: `python -m uvicorn src.interfaces.server.main:app --reload`
- Mỗi task commit riêng
