# 1a.6 – Xây dựng mock agent và test harness

## Lệnh Agent

```
@prompts/phase_1a_1a6.md Thực hiện task này. Commit [Phase 1a.6]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 1a.6 |
| **Tên** | Xây dựng mock agent và test harness |
| **Mô tả** | Mock LLM, mock tool calling |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [LOW] LOW |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ Mock agent quá phức tạp. Giữ đơn giản: generate() → string.

### Phụ thuộc (depends_on)

- Không phụ thuộc phase khác

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Xây dựng mock agent và test harness"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 1a.6] Xây dựng mock agent và test harness`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
