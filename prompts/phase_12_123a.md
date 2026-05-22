# 12.3a – Canary deployment

## Lệnh Agent

```
@prompts/phase_12_123a.md Thực hiện task này. Commit [Phase 12.3a]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 12.3a |
| **Tên** | Canary deployment |
| **Mô tả** | Phát hành model mới cho 1% user |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [MED] Medium |
| **Risk** | [MED] MEDIUM |
| **Team size** | Solo |
| **Tech depth** | Medium |

### Hidden Trap / Điểm yếu

> ⚠️ Canary: traffic splitting có latency spike. Phải gradual increase (1%→5%→10%→50%→100%).

### Phụ thuộc (depends_on)

- 12.3

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Canary deployment"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 12.3a] Canary deployment`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
