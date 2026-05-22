# 9.1 – Patch sandbox

## Lệnh Agent

```
@prompts/phase_9_91.md Thực hiện task này. Commit [Phase 9.1]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 9.1 |
| **Tên** | Patch sandbox |
| **Mô tả** | Container/worktree, compile + test |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [V.HARD] VeryHard |
| **Risk** | [CRIT] CRITICAL |
| **Team size** | Team |
| **Tech depth** | VeryHigh |

### Hidden Trap / Điểm yếu

> ⚠️ Patch sandbox: malicious code có thể escape container. Phải seccomp + AppArmor + no network. ĐÂY LÀ SECURITY CRITICAL.

### Phụ thuộc (depends_on)

- 5.6, 8.1

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Patch sandbox"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 9.1] Patch sandbox`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
