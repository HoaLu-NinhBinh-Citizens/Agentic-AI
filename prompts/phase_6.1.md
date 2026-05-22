# Phase 6.1 – Embedded Target Model & Abstraction Layer

## Lệnh Agent

```
@prompts/phase_6.1.md Thực hiện tuần tự. Commit [Phase 6.1]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Bảng sub-phase

| ID | Sub‑phase | Mô tả |
|----|-----------|-------|
| 6.1 | EmbeddedTarget model | Chip, board, debug probe, toolchain |
| 6.1a | Abstraction layer cho nhiều chip | STM32, NXP, TI, ESP32, RISC‑V (interface, chỉ 1 chip thực tế) |
| 6.1b | Plugin system cho chip vendor | Dễ dàng thêm chip mới |
| 6.1c | Auto‑detect target | Từ debug probe, đọc IDCODE |

## Task list (thực hiện tuần tự)

- [ ] **6.1.1** `domain/hardware/embedded_target.py` — EmbeddedTarget, states, ChipFamily
- [ ] **6.1.2** `debug_probe.py` — JLink, STLink, CMSIS-DAP probes
- [ ] **6.1.3** `domain/hardware/probe.py` — memory/register port
- [ ] **6.1.4** `infrastructure/hardware/jlink/probe.py`, `rtt.py`
- [ ] **6.1.5** `probe_manager.py`, `configs/hardware/targets.yaml`
- [ ] **6.1.6** `chip_plugin.py`, `auto_detector.py`, `snapshot_manager.py`
- [ ] **6.1.7** `event_bus.py`, `provenance.py`, `capability.py`
- [ ] **6.1.8** `tests/unit/test_embedded_target.py`, `test_jlink_phase61.py`

## Kết thúc phase

- [ ] pytest pass
- [ ] Commit `[Phase 6.1]`, build_log, ERA_ROADMAP

## Ghi chú
> Embedded AI != chatbot hiểu code = target abstraction + hardware semantics + debug transport + firmware metadata.
