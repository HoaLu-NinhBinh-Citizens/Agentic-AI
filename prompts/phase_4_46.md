# 4.6 – Memory Governance

## Lệnh Agent

```
@prompts/phase_4_46.md Thực hiện task này. Commit [Phase 4.6]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | 4.6 |
| **Tên** | Memory Governance |
| **Mô tả** | TTL, provenance, confidence decay, PII policy, dedup |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | [HARD] Hard |
| **Risk** | [HIGH] HIGH |
| **Team size** | Small |
| **Tech depth** | High |

### Hidden Trap / Điểm yếu

> ⚠️ Hallucinated facts trong memory không có provenance → poison toàn bộ RAG. FACT KHÔNG CÓ provenance → không được dùng làm basis cho answer. Đây là lỗi phổ biến nhất của AI memory systems.

### Phụ thuộc (depends_on)

- 4.2, 4.5

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "Memory Governance"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase 4.6] Memory Governance`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
