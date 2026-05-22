# 1b.5 – Logging và health checks

## Lệnh Agent

```
@prompts/phase_1b_1b5.md Thực hiện task này. Commit [Phase 1b.5]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 1b.5 |
| **Tên** | Logging và health checks |
| **Mô tả** | Structured logging, /health endpoint |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [EZ] Easy |
| **Risk** | [LOW] LOW |
| **Team size** | Solo |
| **Tech depth** | Low-Medium |

### Hidden Trap / Điểm yếu

> ⚠️ Structured logging nên dùng structlog từ đầu. Đổi sau rất tốn effort.

### Phụ thuộc (depends_on)

- Không phụ thuộc phase khác

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Logging và health checks"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 1b.5] Logging và health checks`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
