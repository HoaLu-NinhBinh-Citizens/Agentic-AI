# Phase 5.7 – Cost Governance

> Sub-phase của Phase 5. Đã bao gồm trong `phase_5.md`. File riêng để Agent tập trung.

## 1. BỐI CẨNH

- **Product:** Embedded CI/HIL Intelligence Platform
- **Tier:** ⭐ Tier 1 — không có cost governance → chi phí bùng nổ khi scale
- **Hidden complexity:** 🟡 trung bình
- **Phụ thuộc:** Phase 4.1 (gateway), Phase 5.6 (sandbox)

> ⚠️ Khi scale: embeddings, reranking, traces, replay, telemetry, fine-tune → chi phí bùng nổ. Cần governance trước Phase 11+.

## 2. TASK LIST

| ID | Sub‑phase | Mô tả | Done khi |
|----|-----------|-------|----------|
| **5.7** | **Token budget** | Per-session, per-user limits. Exceed → graceful reject. |
| 5.7a | Adaptive routing | Route to cheapest model meeting quality threshold. Fallback chain. |
| 5.7b | Inference policy | Cache strategy, model tiering (fast/balanced/accurate). Cache hit visible. |
| 5.7c | Embedding budget | RAG cost control, rerank budget, embedding cache. Cost/embedding bounded. |
| 5.7d | Cost observability | Metric: cost_per_session, model_tier_usage, cache_hit_rate. |

## 3. CẤU TRÚC FILE

```
src/core/cost_governance/
├── token_budget.py      # PerSessionBudget, PerUserBudget
├── adaptive_router.py    # RouteToCheapestModel, fallback chain
├── inference_policy.py   # ModelTiering, cache strategy
├── embedding_budget.py  # EmbeddingBudget, rerank budget
└── metrics.py           # CostMetrics
tests/unit/test_cost_governance/
```

## 4. ACCEPTANCE CRITERIA

- [ ] Token exceed → reject + metric
- [ ] Adaptive routing: primary fails → fallback chain works
- [ ] Cache hit rate visible in metrics
- [ ] Embedding budget: max embeddings/session bounded
- [ ] pytest pass

## 5. KẾT THÚC

- [ ] Commit `[Phase 5.7] cost governance`
- [ ] build_log + ERA_ROADMAP
