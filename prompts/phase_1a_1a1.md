# 1a.1 – Xác định yêu cầu và phạm vi

## Lệnh Agent

```
@prompts/phase_1a_1a1.md Thực hiện task này. Commit [Phase 1a.1]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 1a.1 |
| **Tên** | Xác định yêu cầu và phạm vi |
| **Mô tả** | Debug firmware nhúng (ARM Cortex‑M, RISC‑V, ESP32, v.v.) |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [LOW] LOW |
| **Team size** | Solo |
| **Tech depth** | Low — mostly docs |

### Hidden Trap / Điểm yếu

> ⚠️ Scope creep — thêm quá nhiều chip/feature không cần thiết cho MVP. Lock scope: ARM Cortex-M only, debug view only.

### Phụ thuộc (depends_on)

- Không phụ thuộc phase khác

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Xác định yêu cầu và phạm vi"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 1a.1] Xác định yêu cầu và phạm vi`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
