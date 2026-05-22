# 7.2 – Serial monitor nâng cao

## Lệnh Agent

```
@prompts/phase_7_hil_72.md Thực hiện task này. Commit [Phase 7.2]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 7.2 |
| **Tên** | Serial monitor nâng cao |
| **Mô tả** | Ghi log, trích xuất test result |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ Serial extraction từ test output phải handle multi-line log. Regex phải greedy để không miss log lines.

### Phụ thuộc (depends_on)

- 6.4

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Serial monitor nâng cao"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 7.2] Serial monitor nâng cao`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
