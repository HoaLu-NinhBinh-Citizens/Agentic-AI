# 12.3b – Auto‑rollback triggers

## Lệnh Agent

```
@prompts/phase_12_123b.md Thực hiện task này. Commit [Phase 12.3b]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 12.3b |
| **Tên** | Auto‑rollback triggers |
| **Mô tả** | Dựa trên metrics (error rate, latency, acceptance) |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ Auto-rollback trigger: alert noise → alert fatigue. Phải tune threshold cẩn thận.

### Phụ thuộc (depends_on)

- 12.3a

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Auto‑rollback triggers"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 12.3b] Auto‑rollback triggers`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
