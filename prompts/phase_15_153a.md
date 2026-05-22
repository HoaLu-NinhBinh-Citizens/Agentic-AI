# 15.3a – Offline sync engine

## Lệnh Agent

```
@prompts/phase_15_153a.md Thực hiện task này. Commit [Phase 15.3a]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 15.3a |
| **Tên** | Offline sync engine |
| **Mô tả** | Đồng bộ khi có mạng (log, telemetry, patches) |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Offline sync: conflict resolution khi online trở lại. CRDT hoặc last-write-wins. Không data loss.

### Phụ thuộc (depends_on)

- 15.3

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Offline sync engine"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 15.3a] Offline sync engine`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
