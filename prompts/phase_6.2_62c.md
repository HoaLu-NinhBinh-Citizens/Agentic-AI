# 6.2c – Flash infrastructure

## Lệnh Agent

```
@prompts/phase_6.2_62c.md Thực hiện task này. Commit [Phase 6.2c]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 6.2c |
| **Tên** | Flash infrastructure |
| **Mô tả** | Transaction, A/B, OTA, journal, fleet |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [V.HARD] VeryHard |
| **Risk** | [CRIT] CRITICAL |
| **Team size** | Team |
| **Tech depth** | VeryHigh |

### Hidden Trap / Điểm yếu

> ⚠️ Flash A/B nếu switch không atomic → brick device. Phải có dual-bank validation + rollback mechanism. ĐÂY LÀ CRITICAL — test kỹ trước khi deploy.

### Phụ thuộc (depends_on)

- 6.2b

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Flash infrastructure"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 6.2c] Flash infrastructure`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
