# 🚀 PROMPT CHO PHASE {X.Y}: {TÊN}

## 0. LỆNH AGENT

```
@prompts/phase_{X.Y}.md Thực hiện tuần tự. Commit [Phase {X.Y}] sau mỗi task. Cập nhật build_log.md + docs/ERA_ROADMAP.md. Không hỏi lại.
```

## 1. BỐI CẢNH

- **Product Identity:** Embedded CI/HIL Intelligence Platform (Option B — đã lock)
- **Tham chiếu:** `docs/ERA_ROADMAP.md` — bảng TT, Tier Value, Execution Reality
- **Tier:** ⭐ Tier 1 / Tier 2 / Tier 3 (xem ERA_ROADMAP §Tier Value)

## 2. PRODUCT CONTEXT

| Câu hỏi | Trả lời |
|---------|---------|
| Embedded AI != chatbot | = target abstraction + hardware semantics + debug transport + firmware metadata |
| Phase 5 là linh hồn | replay, saga, snapshots, deterministic orchestration → Phase 8–16 dễ hơn |
| Symbolic execution | KHÔNG làm ở Phase 8 — move Phase 13b (cần deterministic replay + pattern library) |
| Flaky hardware | Phase 7 khó hơn AI nhiều — ưu tiên robustness over features |

## 3. YÊU CẦU KỸ THUẬT

- Python 3.11+, type hints, async/await
- Logging: structlog + correlation_id
- Metrics: Prometheus
- Tests: unit ≥80%, integration khi có
- **Memory Governance:** nếu phase liên quan memory → TTL, provenance, confidence decay, PII policy
- **Cost Governance:** nếu phase liên quan LLM → token budget, model tiering, adaptive routing
- **Agent Runtime:** nếu phase liên quan orchestration → lifecycle, sandbox, idempotency

## 4. PHASE CONTEXT (điền trước khi chạy)

- Đã hoàn thành: …
- Phụ thuộc Phase: …
- Gây risk cho: …
- Hidden complexity: 🟡 trung bình / 🔴 cao / 🔴 research-grade

## 5. TASK LIST

| ID | Sub‑phase | Mô tả | Done khi | Ưu tiên |
|----|-----------|-------|----------|---------|

## 6. KẾT THÚC PHASE

- [ ] Tất cả task done hoặc ⬜ có justification trong ERA_ROADMAP
- [ ] `build_log.md` cập nhật
- [ ] `docs/ERA_ROADMAP.md` cập nhật TT
- [ ] Commit với tag `[Phase {X.Y}]`

## 7. SEQUENCING RULES

1. Memory Governance (4.6) trước Phase 11+
2. Cost Governance (5.7) trước Phase 11+
3. Agent Runtime Kernel (5.6) trước Phase 8+
4. Symbolic execution chỉ ở Phase 13b
5. Phase 7 HIL scaffold trước Phase 8
