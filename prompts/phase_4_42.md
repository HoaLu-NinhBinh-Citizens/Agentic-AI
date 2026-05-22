# 4.2 – RAG cơ bản

## Lệnh Agent

```
@prompts/phase_4_42.md Thực hiện task này. Commit [Phase 4.2]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 4.2 |
| **Tên** | RAG cơ bản |
| **Mô tả** | Vector store (Chroma / Qdrant / PGVector) |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Vector store có thể down. Phải có in-memory fallback. Không block user vì vector store chậm.

### Phụ thuộc (depends_on)

- 4.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "RAG cơ bản"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 4.2] RAG cơ bản`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
