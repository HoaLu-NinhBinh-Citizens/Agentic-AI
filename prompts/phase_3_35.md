# 3.5 – Prometheus metrics

## Lệnh Agent

```
@prompts/phase_3_35.md Thực hiện task này. Commit [Phase 3.5]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 3.5 |
| **Tên** | Prometheus metrics |
| **Mô tả** | Latency, error rate, tool usage, queue size |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [EZ] Easy |
| **Risk** | [LOW] LOW |
| **Team size** | Solo |
| **Tech depth** | Low |

### Hidden Trap / Điểm yếu

> ⚠️ Metric cardinality explosion (label với user_id, request_id). Chỉ count/count with low-cardinality labels.

### Phụ thuộc (depends_on)

- 3.4

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Prometheus metrics"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 3.5] Prometheus metrics`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
