# 6.2b – Compatibility matrix

## Lệnh Agent

```
@prompts/phase_6.2_62b.md Thực hiện task này. Commit [Phase 6.2b]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 6.2b |
| **Tên** | Compatibility matrix |
| **Mô tả** | Target ↔ firmware version |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Compatibility matrix nếu không version-aware → sai check khi firmware version format không đồng nhất.

### Phụ thuộc (depends_on)

- 6.2, 6.2a

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Compatibility matrix"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 6.2b] Compatibility matrix`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
