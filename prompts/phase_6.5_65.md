# 6.5 – HAL query tool

## Lệnh Agent

```
@prompts/phase_6.5_65.md Thực hiện task này. Commit [Phase 6.5]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 6.5 |
| **Tên** | HAL query tool |
| **Mô tả** | Lấy thông tin peripheral |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ HAL query phải handle peripheral not initialized. Đọc register của peripheral chưa clock → 0xFFFFFFFF.

### Phụ thuộc (depends_on)

- 6.1, 6.3

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "HAL query tool"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 6.5] HAL query tool`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
