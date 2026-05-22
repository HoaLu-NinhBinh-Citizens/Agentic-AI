# Phase 13 – Production Hardening & Advanced Features

## Lệnh Agent

```
@prompts/phase_13.md Thực hiện tuần tự. Commit [Phase 13]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Bảng sub-phase

| ID | Sub‑phase | Mô tả |
|----|-----------|-------|
| 13.1 | Monitoring & alerting | Prometheus, Grafana, PagerDuty |
| 13.2 | Deterministic replay | Snapshot workspace, replay tool IO, agent state |
| 13.3 | Error budget & SLO | 99.9% availability, tự động cảnh báo |
| 13.4 | Chaos engineering | Test farm failure, network partition |
| 13.5 | Execution semantics | CFG, ISR interaction, DMA modeling |
| 13.6 | Compiler intelligence | ELF symbol, ABI, inline asm, stack usage |
| 13.7 | Hardware ontology | Từ SVD, causal graph cho lỗi |

## Task list (thực hiện tuần tự)

- [ ] **13.1** Monitoring — Grafana dashboard, PagerDuty integration
- [ ] **13.2** Deterministic replay — workspace snapshot, tool IO replay
- [ ] **13.3** SLO — error budget, 99.9% availability
- [ ] **13.4** Chaos — farm failure, network partition
- [ ] **13.5** Execution semantics — **⚠️ research-grade**, chỉ nếu Phase 13b done
- [ ] **13.6** Compiler intel — **⚠️ rất khó**, DWARF, ABI, LTO
- [ ] **13.7** Hardware ontology — SVD → causal graph

## Kết thúc phase

- [ ] Grafana dashboard works
- [ ] Commit `[Phase 13]`, build_log, ERA_ROADMAP

## Ghi chú
> ⚠️ Phase 13.5 + 13.6: research-grade, nhiều debugger thương mại còn struggle. Không làm sớm.
