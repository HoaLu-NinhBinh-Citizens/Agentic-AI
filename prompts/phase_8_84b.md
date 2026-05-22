# 8.4b – Bug dependency graph

## Lệnh Agent

```
@prompts/phase_8_84b.md Thực hiện task này. Commit [Phase 8.4b]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 8.4b |
| **Tên** | Bug dependency graph |
| **Mô tả** | Bug A phụ thuộc bug B |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Bug dependency graph có thể circular. Phải detect và break cycle.

### Phụ thuộc (depends_on)

- 8.4a

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Bug dependency graph"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 8.4b] Bug dependency graph`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
