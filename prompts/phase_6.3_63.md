# 6.3 – RTT / real-time trace

## Lệnh Agent

```
@prompts/phase_6.3_63.md Thực hiện task này. Commit [Phase 6.3]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 6.3 |
| **Tên** | RTT / real-time trace |
| **Mô tả** | RTT up-channel, register updates, watchpoints, buffer |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Solo |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ RTT buffer size nếu nhỏ → overflow. Phải dynamic buffer hoặc throttle reader.

### Phụ thuộc (depends_on)

- 6.1c

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "RTT / real-time trace"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 6.3] RTT / real-time trace`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
