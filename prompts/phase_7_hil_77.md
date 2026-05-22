# 7.7 – Flaky test detector

## Lệnh Agent

```
@prompts/phase_7_hil_77.md Thực hiện task này. Commit [Phase 7.7]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 7.7 |
| **Tên** | Flaky test detector |
| **Mô tả** | Retry, phân tích |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [MED] MEDIUM |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Flaky test detector: flaky không deterministic → retry có thể pass nhưng vẫn flaky. Phải track flaky pattern, không chỉ pass/fail.

### Phụ thuộc (depends_on)

- 7.5

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Flaky test detector"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 7.7] Flaky test detector`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
