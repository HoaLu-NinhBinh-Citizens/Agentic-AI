# 4.1 – Hỗ trợ nhiều LLM

## Lệnh Agent

```
@prompts/phase_4_41.md Thực hiện task này. Commit [Phase 4.1]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 4.1 |
| **Tên** | Hỗ trợ nhiều LLM |
| **Mô tả** | Ollama, Groq, OpenAI, Claude, Gemini, Local models |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Mỗi LLM provider có response format khác nhau. Abstract LLM interface từ đầu, không if/else provider trong code.

### Phụ thuộc (depends_on)

- 3.3

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Hỗ trợ nhiều LLM"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 4.1] Hỗ trợ nhiều LLM`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
