# 5.6 – Agent Runtime Kernel

## Lệnh Agent

```
@prompts/phase_5_56.md Thực hiện task này. Commit [Phase 5.6]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 5.6 |
| **Tên** | Agent Runtime Kernel |
| **Mô tả** | Lifecycle, sandbox, deterministic FSM, scheduling, failure isolation |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [V.HARD] VeryHard |
| **Risk** | [CRIT] CRITICAL |
| **Team size** | Team |
| **Tech depth** | VeryHigh |

### Hidden Trap / Điểm yếu

> ⚠️ Agent lifecycle leak (orphan agent) là bug nghiêm trọng. PHẢI có watchdog monitor agent heartbeat. Crash isolation: 1 agent crash không được crash toàn hệ thống.

### Phụ thuộc (depends_on)

- 5.1, 5.3

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Agent Runtime Kernel"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 5.6] Agent Runtime Kernel`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
