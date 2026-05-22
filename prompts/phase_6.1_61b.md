# 6.1b – Plugin system cho chip vendor

## Lệnh Agent

```
@prompts/phase_6.1_61b.md Thực hiện task này. Commit [Phase 6.1b]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 6.1b |
| **Tên** | Plugin system cho chip vendor |
| **Mô tả** | Dễ dàng thêm chip mới |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [MED] MEDIUM |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Plugin sandbox nếu không isolate → malicious plugin có thể đọc file. Dùng subprocess với resource limits.

### Phụ thuộc (depends_on)

- 6.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Plugin system cho chip vendor"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 6.1b] Plugin system cho chip vendor`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
