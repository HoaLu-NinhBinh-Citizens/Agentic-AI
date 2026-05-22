# 6.1a – Abstraction layer cho nhiều chip

## Lệnh Agent

```
@prompts/phase_6.1_61a.md Thực hiện task này. Commit [Phase 6.1a]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 6.1a |
| **Tên** | Abstraction layer cho nhiều chip |
| **Mô tả** | STM32, NXP, TI, ESP32, RISC‑V |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [V.HARD] VeryHard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Team |
| **Tech depth** | VeryHigh |

### Hidden Trap / Điểm yếu

> ⚠️ Abstraction layer không nên over-abstract. Chỉ implement 1 chip thực tế (STM32), các chip khác là interface.

### Phụ thuộc (depends_on)

- 6.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Abstraction layer cho nhiều chip"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 6.1a] Abstraction layer cho nhiều chip`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
