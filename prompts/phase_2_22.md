# 2.2 – Tool calling song song

## Lệnh Agent

```
@prompts/phase_2_22.md Thực hiện task này. Commit [Phase 2.2]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 2.2 |
| **Tên** | Tool calling song song |
| **Mô tả** | asyncio.gather, timeout |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ asyncio.gather không handle exception tốt. Dùng asyncio.gather(*, return_exceptions=True).

### Phụ thuộc (depends_on)

- 2.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Tool calling song song"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 2.2] Tool calling song song`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
