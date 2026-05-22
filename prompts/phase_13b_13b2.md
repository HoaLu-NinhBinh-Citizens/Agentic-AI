# 13b.2 – CFG + ISR modeling

## Lệnh Agent

```
@prompts/phase_13b_13b2.md Thực hiện task này. Commit [Phase 13b.2]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 13b.2 |
| **Tên** | CFG + ISR modeling |
| **Mô tả** | Control flow graph + interrupt interaction |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [RESEARCH] ResearchGrade |
| **Risk** | [CRIT] CRITICAL |
| **Team size** | Startup |
| **Tech depth** | ResearchGrade |

### Hidden Trap / Điểm yếu

> ⚠️ CFG reconstruction từ stripped binary: indirect jump targets khó resolve. Không 100% accurate.

### Phụ thuộc (depends_on)

- 13b.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "CFG + ISR modeling"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 13b.2] CFG + ISR modeling`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
