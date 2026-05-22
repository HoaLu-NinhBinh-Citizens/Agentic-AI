# 5.4 – Distributed snapshots

## Lệnh Agent

```
@prompts/phase_5_54.md Thực hiện task này. Commit [Phase 5.4]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 5.4 |
| **Tên** | Distributed snapshots |
| **Mô tả** | Có thể resume sau lỗi |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Snapshot nếu capture không đúng thời điểm → resume sai state. Snapshot PHẢI atomic với event log.

### Phụ thuộc (depends_on)

- 5.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Distributed snapshots"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 5.4] Distributed snapshots`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
