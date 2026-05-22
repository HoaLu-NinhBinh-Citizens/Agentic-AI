# Phase 8 – Static Analysis & Intelligence

## Lệnh Agent

```
@prompts/phase_8.md Thực hiện tuần tự. Commit [Phase 8]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Bảng sub-phase

| ID | Sub‑phase | Mô tả |
|----|-----------|-------|
| 8.1 | Project indexer | compile_commands.json, tree‑sitter, symbols |
| 8.2 | Static firmware analysis | Call graph, ISR graph, stack estimate, unsafe API |
| 8.3 | Error pattern library | Lưu pattern lỗi (HardFault, timeout, deadlock) |
| 8.3a | Auto‑learn error patterns | Từ log mới, phát hiện pattern tương tự |
| 8.3b | Pattern versioning | Cập nhật pattern mà không break |
| 8.4 | Bug report parser | Log → structured bug (type, location, suspect) |
| 8.4a | Concurrent bug handling | Phân lập, ưu tiên, merge |
| 8.4b | Bug dependency graph | Bug A phụ thuộc bug B |
| 8.5 | Symbolic execution | ~~Cho các lỗi path‑sensitive~~ → **MOVED Phase 13b** |

## Task list (thực hiện tuần tự)

- [ ] **8.1** Project indexer — compile_commands, tree-sitter, symbols
- [ ] **8.2** Static analysis — call graph, ISR, stack estimate
- [ ] **8.3** Pattern library — HardFault, timeout, deadlock patterns
- [ ] **8.3a** Auto-learn — từ log mới
- [ ] **8.3b** Pattern versioning — deprecation path
- [ ] **8.4** Bug parser — log → structured bug
- [ ] **8.4a** Concurrent handling — deduplicate
- [ ] **8.4b** Bug dependency graph — DAG
- [ ] **8.5** ~~Symbolic execution~~ — **LOẠI**, move Phase 13b

## Kết thúc phase

- [ ] Indexer parse ELF symbols
- [ ] ≥10 error patterns in library
- [ ] Commit `[Phase 8]`, build_log, ERA_ROADMAP
