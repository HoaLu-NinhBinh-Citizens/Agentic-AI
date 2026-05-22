# 8.3 – Error pattern library

## Lệnh Agent

```
@prompts/phase_8_83.md Thực hiện task này. Commit [Phase 8.3]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 8.3 |
| **Tên** | Error pattern library |
| **Mô tả** | Lưu pattern lỗi (HardFault, timeout, deadlock) |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [MED] MEDIUM |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Error pattern nếu quá generic (.*HardFault.*) → false positive. Phải có context window (nearby lines).

### Phụ thuộc (depends_on)

- 8.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Error pattern library"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 8.3] Error pattern library`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
