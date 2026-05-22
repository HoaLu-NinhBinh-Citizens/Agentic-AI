# 6.2a – Firmware versioning

## Lệnh Agent

```
@prompts/phase_6.2_62a.md Thực hiện task này. Commit [Phase 6.2a]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 6.2a |
| **Tên** | Firmware versioning |
| **Mô tả** | Lưu hash, version, compatibility |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ Firmware hash nếu dùng MD5 → không secure. Bắt buộc SHA256.

### Phụ thuộc (depends_on)

- 6.2

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Firmware versioning"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 6.2a] Firmware versioning`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
