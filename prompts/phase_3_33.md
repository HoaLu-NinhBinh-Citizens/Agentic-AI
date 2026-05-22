# 3.3 – Circuit breaker

## Lệnh Agent

```
@prompts/phase_3_33.md Thực hiện task này. Commit [Phase 3.3]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 3.3 |
| **Tên** | Circuit breaker |
| **Mô tả** | Cho LLM và tool endpoints |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Circuit breaker state machine phải thread-safe. Dùng enum State(CLOSED/OPEN/HALF_OPEN), không bool flag.

### Phụ thuộc (depends_on)

- 3.2

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Circuit breaker"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 3.3] Circuit breaker`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
