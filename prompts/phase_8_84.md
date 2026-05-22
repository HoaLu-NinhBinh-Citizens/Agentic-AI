# 8.4 – Bug report parser

## Lệnh Agent

```
@prompts/phase_8_84.md Thực hiện task này. Commit [Phase 8.4]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 8.4 |
| **Tên** | Bug report parser |
| **Mô tả** | Log → structured bug (type, location, suspect) |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [MED] MEDIUM |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Bug parser phải handle multiple log formats. Test trên ≥5 format khác nhau.

### Phụ thuộc (depends_on)

- 8.3

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Bug report parser"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 8.4] Bug report parser`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
