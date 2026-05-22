# 6.7 – GDB client

## Lệnh Agent

```
@prompts/phase_6.7_67.md Thực hiện task này. Commit [Phase 6.7]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 6.7 |
| **Tên** | GDB client |
| **Mô tả** | Kết nối, backtrace, biến |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Solo |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ GDB RSP packet nếu không handle long response → truncation. Phải chunk reading với acknowledge packet.

### Phụ thuộc (depends_on)

- 6.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "GDB client"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 6.7] GDB client`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
