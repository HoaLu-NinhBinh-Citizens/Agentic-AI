# Phase 7 – Hardware‑in‑the‑Loop (HIL) & Simulation

## Lệnh Agent

```
@prompts/phase_7.md Thực hiện tuần tự. Commit [Phase 7]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Bảng sub-phase

| ID | Sub‑phase | Mô tả |
|----|-----------|-------|
| 7.0a | Simulator cho STM32 | QEMU, Renode (filter obvious failures) |
| 7.0b | Simulator cho ESP32 | ESP‑IDF emulator |
| 7.1 | OpenOCD adapter | Flash, reset, run |
| 7.1a | Multi‑probe adapter | JLink, STLink, CMSIS‑DAP, pyOCD |
| 7.2 | Serial monitor nâng cao | Ghi log, trích xuất test result |
| 7.3 | Test harness generator | Unity, CppUTest, GoogleTest |
| 7.4 | Hardware farm manager | Quản lý board, trạng thái |
| 7.5 | Test orchestrator | Song song trên nhiều board |
| 7.6 | Board watchdog & health | Reset khi treo |
| 7.6a | Board pool & auto‑replacement | Dự phòng board |
| 7.7 | Flaky test detector | Retry, phân tích |

## Task list (thực hiện tuần tự)

- [ ] **7.0a** QEMU adapter stub
- [ ] **7.0b** ESP-IDF emulator stub
- [ ] **7.1** OpenOCD subprocess adapter
- [ ] **7.1a** Multi-probe — extend domain probes
- [ ] **7.2** Serial extraction — parse test result từ log
- [ ] **7.3** Harness generator — Unity/CppUTest/GTest templates
- [ ] **7.4** Farm manager — board registry, state machine
- [ ] **7.5** Orchestrator — asyncio pool
- [ ] **7.6** Watchdog — reset when no heartbeat
- [ ] **7.6a** Board pool — auto-replacement on failure
- [ ] **7.7** Flaky detector — retry + flaky score

## Kết thúc phase

- [ ] QEMU flash mock works
- [ ] Board state transitions correct
- [ ] Commit `[Phase 7]`, build_log, ERA_ROADMAP

## Ghi chú
> ⚠️ Hidden complexity cao: flaky hardware, USB, serial deadlock, probe firmware mismatch, board brownout — khó hơn AI nhiều.
