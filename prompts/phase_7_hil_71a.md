# 7.1a – Multi‑probe adapter

## Lệnh Agent

```
@prompts/phase_7_hil_71a.md Thực hiện task này. Commit [Phase 7.1a]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 7.1a |
| **Tên** | Multi‑probe adapter |
| **Mô tả** | JLink, STLink, CMSIS‑DAP, pyOCD |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Multi-probe: J-Link và ST-Link có command set khác nhau. Unified interface phải abstract thấp, không phạm vi quá rộng.

### Phụ thuộc (depends_on)

- 7.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Multi‑probe adapter"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 7.1a] Multi‑probe adapter`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
