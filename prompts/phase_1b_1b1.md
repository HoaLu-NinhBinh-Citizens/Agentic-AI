# 1b.1 – FastAPI + WebSocket server

## Lệnh Agent

```
@prompts/phase_1b_1b1.md Thực hiện task này. Commit [Phase 1b.1]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 1b.1 |
| **Tên** | FastAPI + WebSocket server |
| **Mô tả** | Session management, authentication JWT |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ JWT nếu implement sớm sẽ tốn thời gian. Có thể skip JWT ở Phase 1b, chỉ session ID.

### Phụ thuộc (depends_on)

- Không phụ thuộc phase khác

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "FastAPI + WebSocket server"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 1b.1] FastAPI + WebSocket server`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
