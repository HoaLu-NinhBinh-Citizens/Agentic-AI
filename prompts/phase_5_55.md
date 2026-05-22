# 5.5 – Human‑in‑the‑loop

## Lệnh Agent

```
@prompts/phase_5_55.md Thực hiện task này. Commit [Phase 5.5]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 5.5 |
| **Tên** | Human‑in‑the‑loop |
| **Mô tả** | Checkpoint, chờ approve |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium-High |

### Hidden Trap / Điểm yếu

> ⚠️ Human approval nếu không timeout → workflow treo vĩnh viễn. Bắt buộc timeout với auto-rollback.

### Phụ thuộc (depends_on)

- 5.2

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Human‑in‑the‑loop"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 5.5] Human‑in‑the‑loop`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
