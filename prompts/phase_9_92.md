# 9.2 – Patch suggestion

## Lệnh Agent

```
@prompts/phase_9_92.md Thực hiện task này. Commit [Phase 9.2]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 9.2 |
| **Tên** | Patch suggestion |
| **Mô tả** | Git diff, giải thích, risk score |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Risk score nếu không calibrated → false positive cao. Phải tune với real patches.

### Phụ thuộc (depends_on)

- 9.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Patch suggestion"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 9.2] Patch suggestion`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
