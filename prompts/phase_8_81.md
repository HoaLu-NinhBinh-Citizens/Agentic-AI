# 8.1 – Project indexer

## Lệnh Agent

```
@prompts/phase_8_81.md Thực hiện task này. Commit [Phase 8.1]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 8.1 |
| **Tên** | Project indexer |
| **Mô tả** | compile_commands.json, tree‑sitter, symbols |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Tree-sitter parse có thể crash trên large codebase. Phải chunk parsing + incremental update.

### Phụ thuộc (depends_on)

- 6.7

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Project indexer"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 8.1] Project indexer`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
