# 5.7 – Cost Governance

## Lệnh Agent

```
@prompts/phase_5_57.md Thực hiện task này. Commit [Phase 5.7]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 5.7 |
| **Tên** | Cost Governance |
| **Mô tả** | Token budget, adaptive routing, model tiering, embedding budget |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Cost không có observability → không biết token spend. Phải track cost/session real-time, alert khi exceed budget.

### Phụ thuộc (depends_on)

- 4.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Cost Governance"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 5.7] Cost Governance`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
