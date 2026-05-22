# 2.1 – MCP client (Model Context Protocol)

## Lệnh Agent

```
@prompts/phase_2_21.md Thực hiện task này. Commit [Phase 2.1]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 2.1 |
| **Tên** | MCP client (Model Context Protocol) |
| **Mô tả** | Giao tiếp với tool server |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ MCP stdio subprocess có thể deadlock nếu không flush đúng. Dùng communicate() không readline() trực tiếp.

### Phụ thuộc (depends_on)

- 1b.1, 1b.4

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "MCP client (Model Context Protocol)"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 2.1] MCP client (Model Context Protocol)`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
