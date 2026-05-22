# 7.4 – Hardware farm manager

## Lệnh Agent

```
@prompts/phase_7_hil_74.md Thực hiện task này. Commit [Phase 7.4]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 7.4 |
| **Tên** | Hardware farm manager |
| **Mô tả** | Quản lý board, trạng thái |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Hardware farm manager: board state không persistent → sau restart không biết board nào đang used. Phải persist board state vào DB.

### Phụ thuộc (depends_on)

- 7.3

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Hardware farm manager"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 7.4] Hardware farm manager`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
