# 15.4b – Code signing & attestation

## Lệnh Agent

```
@prompts/phase_15_154b.md Thực hiện task này. Commit [Phase 15.4b]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 15.4b |
| **Tên** | Code signing & attestation |
| **Mô tả** | Xác thực nguồn gốc patch |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [CRIT] CRITICAL |
| **Team size** | Team |
| **Tech depth** | VeryHigh |

### Hidden Trap / Điểm yếu

> ⚠️ Code signing: private key protection. HSM không affordable cho startup. Phải balance security vs cost.

### Phụ thuộc (depends_on)

- 15.4

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Code signing & attestation"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 15.4b] Code signing & attestation`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
