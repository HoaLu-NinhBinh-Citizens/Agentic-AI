# 6.1c – Auto‑detect target

## Lệnh Agent

```
@prompts/phase_6.1_61c.md Thực hiện task này. Commit [Phase 6.1c]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 6.1c |
| **Tên** | Auto‑detect target |
| **Mô tả** | Từ debug probe, đọc IDCODE |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ IDCODE read có thể fail nếu target không stop. Phải halt trước khi read IDCODE.

### Phụ thuộc (depends_on)

- 6.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Auto‑detect target"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 6.1c] Auto‑detect target`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
