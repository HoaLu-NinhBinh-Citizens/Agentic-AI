# 1b.2 – Streaming token response

## Lệnh Agent

```
@prompts/phase_1b_1b2.md Thực hiện task này. Commit [Phase 1b.2]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 1b.2 |
| **Tên** | Streaming token response |
| **Mô tả** | SSE / WebSocket streaming |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [EZ] Easy |
| **Risk** | [LOW] LOW |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ WS streaming cần đúng event format: token/done/error. Sai format → client không parse được.

### Phụ thuộc (depends_on)

- 1b.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Streaming token response"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 1b.2] Streaming token response`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
