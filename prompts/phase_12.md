# Phase 12 – Model Evaluation & Fine‑tuning

## Lệnh Agent

```
@prompts/phase_12.md Thực hiện tuần tự. Commit [Phase 12]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Bảng sub-phase

| ID | Sub‑phase | Mô tả |
|----|-----------|-------|
| 12.1 | Evaluation framework | So sánh RAG vs fine‑tune vs baseline |
| 12.2 | A/B testing | Triển khai song song, phân tích thống kê |
| 12.3 | Model rollback | Tự động quay lại nếu performance giảm |
| 12.3a | Canary deployment | Phát hành model mới cho 1% user |
| 12.3b | Auto‑rollback triggers | Dựa trên metrics (error rate, latency, acceptance) |
| 12.4 | Fine‑tune LLM | Trên dữ liệu debug (≥1000 mẫu) |
| 12.5 | Quantization & optimization | GPU/CPU inference, ONNX, TensorRT |

## Task list (thực hiện tuần tự)

- [ ] **12.1** Evaluation framework — RAG vs fine-tune vs baseline
- [ ] **12.2** A/B testing — song song, thống kê
- [ ] **12.3** Model rollback — auto rollback khi perf giảm
- [ ] **12.3a** Canary — 1% user
- [ ] **12.3b** Auto-rollback triggers
- [ ] **12.4** Fine-tune LLM — ≥1000 mẫu
- [ ] **12.5** Quantization — ONNX, TensorRT

## Kết thúc phase

- [ ] Evaluation framework measurable
- [ ] Rollback works
- [ ] Commit `[Phase 12]`, build_log, ERA_ROADMAP
