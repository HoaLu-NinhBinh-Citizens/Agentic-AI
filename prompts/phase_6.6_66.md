# 6.6 – SVD parser

## Lệnh Agent

```
@prompts/phase_6.6_66.md Thực hiện task này. Commit [Phase 6.6]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 6.6 |
| **Tên** | SVD parser |
| **Mô tả** | Đọc file ARM CMSIS‑SVD |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Solo |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ SVD parsing phải handle incomplete SVD. Nhiều vendor SVD có missing fields.

### Phụ thuộc (depends_on)

- 6.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "SVD parser"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 6.6] SVD parser`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
