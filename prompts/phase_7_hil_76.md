# 7.6 – Board watchdog & health

## Lệnh Agent

```
@prompts/phase_7_hil_76.md Thực hiện task này. Commit [Phase 7.6]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 7.6 |
| **Tên** | Board watchdog & health |
| **Mô tả** | Reset khi treo |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Solo |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Board watchdog: nếu reset không clean → file system corruption. Phải graceful shutdown trước reset.

### Phụ thuộc (depends_on)

- 7.5

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Board watchdog & health"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 7.6] Board watchdog & health`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
