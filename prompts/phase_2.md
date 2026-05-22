# Phase 2 – MCP & Tool Execution

## Lệnh Agent

```
@prompts/phase_2.md Thực hiện tuần tự. Commit [Phase 2]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Bảng sub-phase

| ID | Sub‑phase | Mô tả |
|----|-----------|-------|
| 2.1 | MCP client (Model Context Protocol) | Giao tiếp với tool server |
| 2.2 | Tool calling song song | asyncio.gather, timeout |
| 2.3 | Error handling và retry | Exponential backoff, fallback |
| 2.4 | Tool caching | TTL‑based cache, LRU |
| 2.5 | Tool versioning | Semantic versioning cho tool API |

## Task list (thực hiện tuần tự)

- [ ] **2.1** `configs/mcp/servers.yaml`, `infrastructure/mcp/config.py`, `manager.py`
- [ ] **2.2** `tool_execution/service.py`, `executor.py`, parallel gather
- [ ] **2.3** `core/execution/cancellation.py`, `infrastructure/tool_execution/retry.py`
- [ ] **2.4** `infrastructure/cache/tool/cache.py` — TTL
- [ ] **2.5** Tool version semver — schema trong tool registry
- [ ] **2.6** Unit + integration tests — `test_mcp_*`, `test_phase2b`, `test_phase2c`
- [ ] **2.7** Multi-server routing — `infrastructure/router/router.py` (Phase 2d)

## Kết thúc phase

- [ ] `pytest tests/unit/test_tool_executor.py` (và liên quan) pass
- [ ] Commit `[Phase 2]`, build_log, ERA_ROADMAP

## Hướng dẫn
- Không `shell=True` trong subprocess
- Mỗi task commit riêng
