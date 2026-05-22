# 3.1 – Retry và backoff

## Lệnh Agent

```
@prompts/phase_3_31.md Thực hiện task này. Commit [Phase 3.1]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 3.1 |
| **Tên** | Retry và backoff |
| **Mô tả** | Exponential backoff, jitter |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ Retry không idempotent tool sẽ gây side-effect. Chỉ retry GET/read operations, không retry write.

### Phụ thuộc (depends_on)

- 2.3

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Retry và backoff"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 3.1] Retry và backoff`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
