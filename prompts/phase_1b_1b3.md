# 1b.3 – Tích hợp LLM local (Ollama)

## Lệnh Agent

```
@prompts/phase_1b_1b3.md Thực hiện task này. Commit [Phase 1b.3]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 1b.3 |
| **Tên** | Tích hợp LLM local (Ollama) |
| **Mô tả** | Gọi model, parse response |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ Ollama có thể chưa có trong env. Mock Ollama response để dev không bị block.

### Phụ thuộc (depends_on)

- Không phụ thuộc phase khác

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Tích hợp LLM local (Ollama)"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 1b.3] Tích hợp LLM local (Ollama)`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
