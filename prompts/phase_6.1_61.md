# 6.1 – EmbeddedTarget model

## Lệnh Agent

```
@prompts/phase_6.1_61.md Thực hiện task này. Commit [Phase 6.1]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 6.1 |
| **Tên** | EmbeddedTarget model |
| **Mô tả** | Chip, board, debug probe, toolchain |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Target state machine (UNKNOWN→CONNECTED→HALTED→RUNNING→FAULT) phải atomic. Race condition khi multiple probes attach/detach.

### Phụ thuộc (depends_on)

- Không phụ thuộc phase khác

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "EmbeddedTarget model"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 6.1] EmbeddedTarget model`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
