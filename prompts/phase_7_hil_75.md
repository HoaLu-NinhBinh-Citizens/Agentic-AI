# 7.5 – Test orchestrator

## Lệnh Agent

```
@prompts/phase_7_hil_75.md Thực hiện task này. Commit [Phase 7.5]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 7.5 |
| **Tên** | Test orchestrator |
| **Mô tả** | Song song trên nhiều board |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Test orchestrator: concurrent flashing nhiều board cùng lúc có thể gây USB overload → all boards fail. Phải có throttle (max 2-3 boards đồng thời).

### Phụ thuộc (depends_on)

- 7.4

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Test orchestrator"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 7.5] Test orchestrator`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
