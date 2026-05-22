# 1a.2 – Khảo sát công cụ hiện có

## Lệnh Agent

```
@prompts/phase_1a_1a2.md Thực hiện task này. Commit [Phase 1a.2]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 1a.2 |
| **Tên** | Khảo sát công cụ hiện có |
| **Mô tả** | OpenOCD, GDB, pyOCD, JLink, STLink, CMSIS‑DAP, QEMU, Renode |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [EZ] Easy |
| **Risk** | [LOW] LOW |
| **Team size** | Solo |
| **Tech depth** | Low — research only |

### Hidden Trap / Điểm yếu

> ⚠️ Survey quá sâu vào tool details mà không cần cho Phase 1. Chỉ cần high-level comparison table.

### Phụ thuộc (depends_on)

- Không phụ thuộc phase khác

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Khảo sát công cụ hiện có"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 1a.2] Khảo sát công cụ hiện có`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
