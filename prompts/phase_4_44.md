# 4.4 – Working memory

## Lệnh Agent

```
@prompts/phase_4_44.md Thực hiện task này. Commit [Phase 4.4]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 4.4 |
| **Tên** | Working memory |
| **Mô tả** | Lưu tool outputs per session |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ Working memory nếu không TTL sẽ leak. Bắt buộc TTL per session, auto-cleanup.

### Phụ thuộc (depends_on)

- 1b.4

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Working memory"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 4.4] Working memory`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
