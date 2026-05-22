# 7.3 – Test harness generator

## Lệnh Agent

```
@prompts/phase_7_hil_73.md Thực hiện task này. Commit [Phase 7.3]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 7.3 |
| **Tên** | Test harness generator |
| **Mô tả** | Unity, CppUTest, GoogleTest |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [MED] MEDIUM |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Test harness generator phải handle different test framework syntax. Unity, CppUTest, GTest có format khác nhau.

### Phụ thuộc (depends_on)

- 7.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Test harness generator"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 7.3] Test harness generator`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
