# 6.7b – Core dump parser

## Lệnh Agent

```
@prompts/phase_6.7_67b.md Thực hiện task này. Commit [Phase 6.7b]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 6.7b |
| **Tên** | Core dump parser |
| **Mô tả** | ELF → stack, registers |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Core dump parsing phải handle stripped ELF (no symbols). Phải fallback sang stack-only analysis.

### Phụ thuộc (depends_on)

- 6.7

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Core dump parser"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 6.7b] Core dump parser`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
