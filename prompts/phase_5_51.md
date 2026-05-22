# 5.1 – Event sourcing engine

## Lệnh Agent

```
@prompts/phase_5_51.md Thực hiện task này. Commit [Phase 5.1]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 5.1 |
| **Tên** | Event sourcing engine |
| **Mô tả** | Lưu mọi action, replay |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [CRIT] CRITICAL |
| **Team size** | Small |
| **Tech depth** | VeryHigh |

### Hidden Trap / Điểm yếu

> ⚠️ Event sourcing nếu replay không deterministic → bug rất khó debug. Event phải immutable + idempotent. Không emit event có side-effect.

### Phụ thuộc (depends_on)

- 3.6, 4.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Event sourcing engine"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 5.1] Event sourcing engine`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
