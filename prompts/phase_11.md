# Phase 11 – Data Pipeline, Benchmark & Labeling

## Lệnh Agent

```
@prompts/phase_11.md Thực hiện tuần tự. Commit [Phase 11]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Bảng sub-phase

| ID | Sub‑phase | Mô tả |
|----|-----------|-------|
| 11.1 | Data collection (opt‑in) | Log, coredump, patch (ẩn danh, xoá PII) |
| 11.2 | Data labeling tool | CLI/Web gán nhãn (loại lỗi, patch đúng/sai) |
| 11.3 | Storage & anonymization | PII removal, encryption at rest |
| 11.4 | Benchmark suite | Đánh giá debug (phát hiện lỗi, đề xuất patch) |
| 11.4a | Debug automation benchmark | MTTD, MTTF |
| 11.4b | Agent quality metrics | Acceptance rate, false positive rate, time to patch |
| 11.5 | Regression testing | Chạy benchmark trên mỗi PR |
| 11.6 | Human feedback loop | Thu thập đúng/sai từ user |

## Task list (thực hiện tuần tự)

- [ ] **11.1** Data collection — log, coredump, patch (opt-in)
- [ ] **11.2** Labeling tool — CLI/Web gán nhãn
- [ ] **11.3** Storage — PII removal, encryption at rest
- [ ] **11.4** Benchmark suite — MTTD, MTTF
- [ ] **11.4a** Debug automation benchmark
- [ ] **11.4b** Agent quality metrics
- [ ] **11.5** Regression — benchmark on PR
- [ ] **11.6** Human feedback loop

## Kết thúc phase

- [ ] Data anonymization works
- [ ] Benchmark runs measurable
- [ ] Commit `[Phase 11]`, build_log, ERA_ROADMAP
