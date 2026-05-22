# 8.4a – Concurrent bug handling

## Lệnh Agent

```
@prompts/phase_8_84a.md Thực hiện task này. Commit [Phase 8.4a]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 8.4a |
| **Tên** | Concurrent bug handling |
| **Mô tả** | Phân lập, ưu tiên, merge |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ Concurrent bug handling: deduplicate không deterministic → inconsistent bug list. Dùng content hash.

### Phụ thuộc (depends_on)

- 8.4

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Concurrent bug handling"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 8.4a] Concurrent bug handling`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
