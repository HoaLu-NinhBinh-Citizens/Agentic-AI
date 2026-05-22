# 3.4 – Structured logging

## Lệnh Agent

```
@prompts/phase_3_34.md Thực hiện task này. Commit [Phase 3.4]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 3.4 |
| **Tên** | Structured logging |
| **Mô tả** | JSON logs, ELK stack integration |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ JSON log nếu không có schema → không parse được sau. Dùng structlog + known schema fields.

### Phụ thuộc (depends_on)

- 1b.5

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Structured logging"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 3.4] Structured logging`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
