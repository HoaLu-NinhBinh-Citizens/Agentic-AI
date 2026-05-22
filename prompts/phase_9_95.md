# 9.5 – Test case generator

## Lệnh Agent

```
@prompts/phase_9_95.md Thực hiện task này. Commit [Phase 9.5]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 9.5 |
| **Tên** | Test case generator |
| **Mô tả** | Từ lỗi → regression test |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Test generator từ crash: generated test có thể flaky. Phải run generated test ≥3 times trước khi commit.

### Phụ thuộc (depends_on)

- 9.4, 7.3

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Test case generator"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 9.5] Test case generator`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
