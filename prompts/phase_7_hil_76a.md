# 7.6a – Board pool & auto‑replacement

## Lệnh Agent

```
@prompts/phase_7_hil_76a.md Thực hiện task này. Commit [Phase 7.6a]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 7.6a |
| **Tên** | Board pool & auto‑replacement |
| **Mô tả** | Dự phòng board |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [V.HARD] VeryHard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Team |
| **Tech depth** | VeryHigh |

### Hidden Trap / Điểm yếu

> ⚠️ Board pool auto-replacement: detect bad board khó. Phải distinguish hardware failure vs software failure vs cable issue.

### Phụ thuộc (depends_on)

- 7.6

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Board pool & auto‑replacement"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 7.6a] Board pool & auto‑replacement`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
