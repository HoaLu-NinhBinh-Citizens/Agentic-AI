# Phase 1a – Khởi tạo & Nghiên cứu

## Lệnh Agent

```
@prompts/phase_1a.md Thực hiện tuần tự. Commit [Phase 1a]. Cập nhật build_log.md + ERA_ROADMAP. Không hỏi lại.
```

## Mục tiêu
Tạo cấu trúc dự án, nghiên cứu công cụ, lựa chọn stack, xây dựng mock agent.

## Bảng sub-phase

| ID | Sub‑phase | Mô tả |
|----|-----------|-------|
| 1a.1 | Xác định yêu cầu và phạm vi | Debug firmware nhúng (ARM Cortex‑M, RISC‑V, ESP32, v.v.) |
| 1a.2 | Khảo sát công cụ hiện có | OpenOCD, GDB, pyOCD, JLink, STLink, CMSIS‑DAP, QEMU, Renode |
| 1a.3 | Lựa chọn stack công nghệ | FastAPI, WebSocket, Redis, PostgreSQL, Docker, Kubernetes, Prometheus |
| 1a.4 | Phân tích đối thủ cạnh tranh | Segger SystemView, Lauterbach, Tracealyzer, AI debug khác |
| 1a.5 | Lập kế hoạch kiến trúc tổng thể | Event sourcing, saga, multi‑agent, microservices hay monolithic |
| 1a.6 | Xây dựng mock agent và test harness | Mock LLM, mock tool calling |

## Task list (thực hiện tuần tự)

- [ ] **1a.1** Tạo `docs/requirements.md` — yêu cầu debug firmware nhúng
- [ ] **1a.2** Tạo `docs/tool_survey.md` — OpenOCD, GDB, pyOCD, J-Link, ST-Link, CMSIS-DAP, QEMU, Renode
- [ ] **1a.3** Kiểm tra `pyproject.toml` — fastapi, uvicorn, websockets, pytest, structlog, prometheus, httpx, pyyaml, …
- [ ] **1a.4** Tạo `docs/competitors.md` — Segger, Lauterbach, Tracealyzer
- [ ] **1a.5** Tạo `docs/architecture.md` — event sourcing, saga, multi-agent
- [ ] **1a.6** `src/core/agent/mock_agent.py` + `tests/unit/test_mock_agent.py`
- [ ] **1a.7** `.env.example` — DATABASE_URL, REDIS_URL, LLM_API_KEY, LOG_LEVEL, SNAPSHOT_ENCRYPTION_KEY
- [ ] **1a.8** Cấu trúc thư mục `src/`, `tests/`, `docs/`, `configs/` theo STRUCTURE_TREE

## Kết thúc phase

- [ ] Commit `[Phase 1a]`
- [ ] `build_log.md` cập nhật
- [ ] `docs/ERA_ROADMAP.md` cập nhật TT

## Hướng dẫn
- Mỗi task hoàn thành thì commit ngay
- Nếu lỗi, tự sửa hoặc ghi log và bỏ qua (nếu không critical)
