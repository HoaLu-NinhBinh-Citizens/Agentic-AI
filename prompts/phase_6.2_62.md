# 6.2 – Target loader & registry

## Lệnh Agent

```
@prompts/phase_6.2_62.md Thực hiện task này. Commit [Phase 6.2]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 6.2 |
| **Tên** | Target loader & registry |
| **Mô tả** | YAML config, registry |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ YAML schema evolution (v1→v2) nếu không có migration → config cũ không load được. Validate schema_version trước khi parse.

### Phụ thuộc (depends_on)

- 6.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Target loader & registry"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 6.2] Target loader & registry`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
