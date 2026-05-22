# 8.3a – Auto‑learn error patterns

## Lệnh Agent

```
@prompts/phase_8_83a.md Thực hiện task này. Commit [Phase 8.3a]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 8.3a |
| **Tên** | Auto‑learn error patterns |
| **Mô tả** | Từ log mới, phát hiện pattern tương tự |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Auto-learn pattern: new pattern có thể poison pattern library. Phải có human review gate trước khi auto-add.

### Phụ thuộc (depends_on)

- 8.3

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Auto‑learn error patterns"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 8.3a] Auto‑learn error patterns`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
