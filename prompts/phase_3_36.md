# 3.6 – Distributed tracing

## Lệnh Agent

```
@prompts/phase_3_36.md Thực hiện task này. Commit [Phase 3.6]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 3.6 |
| **Tên** | Distributed tracing |
| **Mô tả** | OpenTelemetry + Jaeger |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ OpenTelemetry setup dễ nhưng span context propagation qua WS khó. Đảm bảo correlation_id được propagate trong WS messages.

### Phụ thuộc (depends_on)

- 3.4, 3.5

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Distributed tracing"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 3.6] Distributed tracing`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
