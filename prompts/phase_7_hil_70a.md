# 7.0a – Simulator cho STM32

## Lệnh Agent

```
@prompts/phase_7_hil_70a.md Thực hiện task này. Commit [Phase 7.0a]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 7.0a |
| **Tên** | Simulator cho STM32 |
| **Mô tả** | QEMU, Renode (filter obvious failures) |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [V.HARD] VeryHard |
| **Risk** | [CRIT] CRITICAL |
| **Team size** | Team |
| **Tech depth** | VeryHigh |

### Hidden Trap / Điểm yếu

> ⚠️ QEMU emulation không chính xác 100% → test pass trên QEMU nhưng fail trên hardware thật. Phải có hardware CI.

### Phụ thuộc (depends_on)

- 6.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Simulator cho STM32"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 7.0a] Simulator cho STM32`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
