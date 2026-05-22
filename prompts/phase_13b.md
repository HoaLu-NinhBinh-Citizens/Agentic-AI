# Phase 13b – Symbolic Execution (MOVED from Phase 8)

## Lệnh Agent

```
@prompts/phase_13b.md Thực hiện tuần tự. Commit [Phase 13b]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Bảng sub-phase

| ID | Sub‑phase | Mô tả |
|----|-----------|-------|
| 13b.1 | Symbolic execution engine | Path‑sensitive analysis cho embedded C |
| 13b.2 | CFG + ISR modeling | Control flow graph + interrupt interaction |
| 13b.3 | DMA modeling | Bus access patterns, peripheral conflicts |
| 13b.4 | Causal reasoning | Root cause graph từ error → hardware fault |

## Task list (thực hiện tuần tự)

- [ ] **13b.1** Symbolic execution — paths explored measurable
- [ ] **13b.2** CFG + ISR — deadlock detection
- [ ] **13b.3** DMA modeling — race detection
- [ ] **13b.4** Causal reasoning — explainable root cause

## Prerequisites

- ✅ Phase 5.2 (deterministic replay)
- ✅ Phase 8.3 (pattern library)
- ✅ Phase 13.7 (hardware ontology)

## Kết thúc phase

- [ ] Symbolic exec explore ≥10 paths
- [ ] ISR deadlock detected
- [ ] Commit `[Phase 13b]`, build_log, ERA_ROADMAP

## Ghi chú
> ⚠️ Research-grade. Nhiều debugger thương mại còn struggle. Chỉ làm khi có tất cả prerequisites.
