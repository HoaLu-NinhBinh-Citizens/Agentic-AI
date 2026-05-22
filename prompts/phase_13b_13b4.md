# 13b.4 – Causal reasoning

## Lệnh Agent

```
@prompts/phase_13b_13b4.md Thực hiện task này. Commit [Phase 13b.4]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 13b.4 |
| **Tên** | Causal reasoning |
| **Mô tả** | Root cause graph từ error → hardware fault |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [RESEARCH] ResearchGrade |
| **Risk** | [CRIT] CRITICAL |
| **Team size** | Startup |
| **Tech depth** | ResearchGrade |

### Hidden Trap / Điểm yếu

> ⚠️ Causal reasoning: số lượng possible causes lớn. Phải prune với confidence threshold.

### Phụ thuộc (depends_on)

- 13b.3, 13.7

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Causal reasoning"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 13b.4] Causal reasoning`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
