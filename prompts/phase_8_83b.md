# 8.3b – Pattern versioning

## Lệnh Agent

```
@prompts/phase_8_83b.md Thực hiện task này. Commit [Phase 8.3b]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 8.3b |
| **Tên** | Pattern versioning |
| **Mô tả** | Cập nhật pattern mà không break |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ Pattern versioning: old pattern phải still match khi deprecated. Deprecated pattern vẫn match nhưng log warning.

### Phụ thuộc (depends_on)

- 8.3a

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Pattern versioning"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 8.3b] Pattern versioning`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
