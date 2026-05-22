# 9.3a – Approval workflow

## Lệnh Agent

```
@prompts/phase_9_93a.md Thực hiện task này. Commit [Phase 9.3a]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 9.3a |
| **Tên** | Approval workflow |
| **Mô tả** | WebSocket, CLI, REST, timeout, rollback |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ Approval timeout: nếu approver offline → workflow stuck. Bắt buộc timeout với auto-reject + notification.

### Phụ thuộc (depends_on)

- 9.3

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Approval workflow"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 9.3a] Approval workflow`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
