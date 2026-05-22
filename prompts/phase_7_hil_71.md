# 7.1 – OpenOCD adapter

## Lệnh Agent

```
@prompts/phase_7_hil_71.md Thực hiện task này. Commit [Phase 7.1]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 7.1 |
| **Tên** | OpenOCD adapter |
| **Mô tả** | Flash, reset, run |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ OpenOCD có nhiều version với command khác nhau. Abstract OpenOCD version detection.

### Phụ thuộc (depends_on)

- 6.1, 6.7

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "OpenOCD adapter"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 7.1] OpenOCD adapter`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
