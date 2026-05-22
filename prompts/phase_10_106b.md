# 10.6b – GitLab CI & Azure DevOps

## Lệnh Agent

```
@prompts/phase_10_106b.md Thực hiện task này. Commit [Phase 10.6b]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 10.6b |
| **Tên** | GitLab CI & Azure DevOps |
| **Mô tả** | Hỗ trợ thêm CI/CD |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ GitLab CI template phải handle both gitlab.com và self-hosted. Self-hosted có config khác.

### Phụ thuộc (depends_on)

- 10.6

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "GitLab CI & Azure DevOps"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 10.6b] GitLab CI & Azure DevOps`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
