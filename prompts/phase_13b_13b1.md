# 13b.1 – Symbolic execution engine

## Lệnh Agent

```
@prompts/phase_13b_13b1.md Thực hiện task này. Commit [Phase 13b.1]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 13b.1 |
| **Tên** | Symbolic execution engine |
| **Mô tả** | Path‑sensitive analysis cho embedded C |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [RESEARCH] ResearchGrade |
| **Risk** | [CRIT] CRITICAL |
| **Team size** | Startup |
| **Tech depth** | ResearchGrade |

### Hidden Trap / Điểm yếu

> ⚠️ Symbolic execution: path explosion problem → không terminate. Phải có path bound + heuristic pruning. Research-grade, rất ít team làm được.

### Phụ thuộc (depends_on)

- 13.2, 13.7

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Symbolic execution engine"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 13b.1] Symbolic execution engine`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
