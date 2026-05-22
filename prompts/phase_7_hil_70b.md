# 7.0b – Simulator cho ESP32

## Lệnh Agent

```
@prompts/phase_7_hil_70b.md Thực hiện task này. Commit [Phase 7.0b]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 7.0b |
| **Tên** | Simulator cho ESP32 |
| **Mô tả** | ESP‑IDF emulator |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [V.HARD] VeryHard |
| **Risk** | [CRIT] CRITICAL |
| **Team size** | Team |
| **Tech depth** | VeryHigh |

### Hidden Trap / Điểm yếu

> ⚠️ ESP-IDF emulator không production-ready. Cân nhắc dùng real hardware hoặc skip phase này.

### Phụ thuộc (depends_on)

- 7.0a

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Simulator cho ESP32"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 7.0b] Simulator cho ESP32`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
