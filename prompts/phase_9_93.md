# 9.3 – Trust & approval gates

## Lệnh Agent

```
@prompts/phase_9_93.md Thực hiện task này. Commit [Phase 9.3]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 9.3 |
| **Tên** | Trust & approval gates |
| **Mô tả** | Confidence, risk (0‑10), require human |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Trust gate: nếu confidence threshold quá cao → almost no patch approved. Quá thấp → bad patches approved. Phải A/B test threshold.

### Phụ thuộc (depends_on)

- 9.2

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Trust & approval gates"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 9.3] Trust & approval gates`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
