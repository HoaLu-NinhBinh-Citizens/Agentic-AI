# 11.4b – Agent quality metrics

## Lệnh Agent

```
@prompts/phase_11_114b.md Thực hiện task này. Commit [Phase 11.4b]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 11.4b |
| **Tên** | Agent quality metrics |
| **Mô tả** | Acceptance rate, false positive rate, time to patch |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ Agent quality metrics: false positive rate phụ thuộc threshold. Phải report precision/recall curve.

### Phụ thuộc (depends_on)

- 11.4

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Agent quality metrics"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 11.4b] Agent quality metrics`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
