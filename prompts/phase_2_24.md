# 2.4 – Tool caching

## Lệnh Agent

```
@prompts/phase_2_24.md Thực hiện task này. Commit [Phase 2.4]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 2.4 |
| **Tên** | Tool caching |
| **Mô tả** | TTL‑based cache, LRU |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [EZ] Easy |
| **Risk** | [LOW] LOW |
| **Team size** | Solo |
| **Tech depth** | Low-Medium |

### Hidden Trap / Điểm yếu

> ⚠️ Cache key phải hash stable (sort keys, canonical JSON). Sai key → cache miss liên tục.

### Phụ thuộc (depends_on)

- 2.2

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Tool caching"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 2.4] Tool caching`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
