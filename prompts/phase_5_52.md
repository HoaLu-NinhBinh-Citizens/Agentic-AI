# 5.2 – Saga orchestration

## Lệnh Agent

```
@prompts/phase_5_52.md Thực hiện task này. Commit [Phase 5.2]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 5.2 |
| **Tên** | Saga orchestration |
| **Mô tả** | Cho debug workflow dài (rollback nếu lỗi) |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [V.HARD] VeryHard |
| **Risk** | [CRIT] CRITICAL |
| **Team size** | Small |
| **Tech depth** | VeryHigh |

### Hidden Trap / Điểm yếu

> ⚠️ Saga rollback nếu thiếu compensation step → inconsistent state. Mỗi step PHẢI có compensation. Test rollback trước khi implement forward.

### Phụ thuộc (depends_on)

- 5.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Saga orchestration"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 5.2] Saga orchestration`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
