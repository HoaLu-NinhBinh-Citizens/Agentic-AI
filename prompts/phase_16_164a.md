# 16.4a – AI tự sinh test case mới

## Lệnh Agent

```
@prompts/phase_16_164a.md Thực hiện task này. Commit [Phase 16.4a]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 16.4a |
| **Tên** | AI tự sinh test case mới |
| **Mô tả** | Dựa trên lỗi chưa gặp, coverage gaps |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [MED] MEDIUM |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ AI sinh test case: generated test có thể test wrong thing. Phải have human review + coverage analysis.

### Phụ thuộc (depends_on)

- 9.5, 11.5

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "AI tự sinh test case mới"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 16.4a] AI tự sinh test case mới`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
