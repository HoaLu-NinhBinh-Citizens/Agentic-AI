# 3.2 – Rate limiting

## Lệnh Agent

```
@prompts/phase_3_32.md Thực hiện task này. Commit [Phase 3.2]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 3.2 |
| **Tên** | Rate limiting |
| **Mô tả** | Per user, per tool, sliding window |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium-High |

### Hidden Trap / Điểm yếu

> ⚠️ Rate limit per-user dùng sliding window nhưng không atomic → race condition. Dùng Redis sorted set hoặc Lua script.

### Phụ thuộc (depends_on)

- 3.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Rate limiting"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 3.2] Rate limiting`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
