# 4.3 – Nén context

## Lệnh Agent

```
@prompts/phase_4_43.md Thực hiện task này. Commit [Phase 4.3]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 4.3 |
| **Tên** | Nén context |
| **Mô tả** | Summarization, selective retention |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ Summarization tốn token + latency. Chỉ summarize khi context > threshold, không summarize always.

### Phụ thuộc (depends_on)

- 4.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Nén context"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 4.3] Nén context`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
