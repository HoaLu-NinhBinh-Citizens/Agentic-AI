# 5.3 – Multi‑agent coordination

## Lệnh Agent

```
@prompts/phase_5_53.md Thực hiện task này. Commit [Phase 5.3]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 5.3 |
| **Tên** | Multi‑agent coordination |
| **Mô tả** | Debug agent, test agent, patch agent, reviewer agent |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Multi-agent nếu không deterministic → nondeterministic bug. Agent response phải deterministic given same input. Dùng seed/LLM temperature=0.

### Phụ thuộc (depends_on)

- 5.2

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Multi‑agent coordination"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 5.3] Multi‑agent coordination`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
