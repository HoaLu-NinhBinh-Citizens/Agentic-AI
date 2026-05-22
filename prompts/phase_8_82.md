# 8.2 – Static firmware analysis

## Lệnh Agent

```
@prompts/phase_8_82.md Thực hiện task này. Commit [Phase 8.2]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 8.2 |
| **Tên** | Static firmware analysis |
| **Mô tả** | Call graph, ISR graph, stack estimate, unsafe API |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [V.HARD] VeryHard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | VeryHigh |

### Hidden Trap / Điểm yếu

> ⚠️ ISR graph analysis: ISR không có symbol trong ELF stripped. Phải infer ISR từ vector table.

### Phụ thuộc (depends_on)

- 8.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Static firmware analysis"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 8.2] Static firmware analysis`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
