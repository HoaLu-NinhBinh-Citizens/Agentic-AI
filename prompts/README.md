# AI_SUPPORT — Phase Prompts (Sequential Agent Build)

Bộ prompt cho **Embedded CI/HIL Intelligence Platform** (Option B — đã lock).

## Cách dùng

1. **Open Folder** → `Agentic-AI`
2. **`Ctrl + I`** → **Agent**
3. Gửi:

```
@prompts/phase_1a.md Thực hiện tuần tự. Commit [Phase 1a]. Cập nhật build_log.md + ERA_ROADMAP.
```

4. Dừng → `continue`

---

## Thứ tự phase

### Era 1 — Core Debug Loop

| # | File | Tên |
|---|------|-----|
| 1 | `phase_1a.md` | Khởi tạo & Nghiên cứu |
| 2 | `phase_1b.md` | Minimal Viable Runtime |
| 3 | `phase_2.md` | MCP & Tool Execution |
| 4 | `phase_3.md` | Reliability & Observability |
| 5 | `phase_4.md` | LLM Gateway + Memory Governance |
| 6 | `phase_5.md` | Durable Workflow + Agent Runtime + Cost Governance |
| 7 | `phase_6.1.md` | Embedded Target & Abstraction |
| 8 | `phase_6.2.md` | Target Loader, Registry, Firmware |
| 9 | `phase_6.3.md` | Real-Time Tracing (RTT) |
| 10 | `phase_6.4.md` | Serial Monitor |
| 11 | `phase_6.5.md` | HAL Query |
| 12 | `phase_6.6.md` | SVD Parser |
| 13 | `phase_6.7.md` | GDB & Core Dump |
| 14 | `phase_7_cli.md` | CLI + TUI |

### Era 2 — Reliability & Scale

| # | File | Tên |
|---|------|-----|
| 15 | `phase_7.md` | HIL & Simulation |
| 16 | `phase_8.md` | Static Analysis (INDEXING + PATTERNS) |
| 17 | `phase_9.md` | Patch Suggestion & Trust Model |
| 18 | `phase_10.md` | Tooling, UX & CI/CD |
| 19 | `phase_11.md` | Data Pipeline & Benchmark |

### Era 3 — Intelligence & Autonomy

| # | File | Tên |
|---|------|-----|
| 20 | `phase_12.md` | Model Evaluation |
| 21 | `phase_13.md` | Production Hardening |
| 22 | `phase_13b.md` | Symbolic Execution (MOVED) |
| 23 | `phase_14.md` | Fleet & Telemetry |
| 24 | `phase_15.md` | Security & Offline |
| 25 | `phase_16.md` | Business & Ecosystem |

---

## Quy tắc chung

- **Cấu trúc:** `docs/STRUCTURE_TREE.md` là nguồn đúng
- **Log:** `build_log.md`
- **Commit:** `[Phase X.Y] mô tả`
- **Test:** `python -m pytest tests/unit/ -q` trước khi chuyển phase
- **Đã có code:** đọc `build_log.md` — task ✅ verify + test

---

## Product Identity (LOCKED)

> **Embedded CI/HIL Intelligence Platform** (Option B)

---

## Phần quan trọng nhất

| Phase | Tại sao |
|-------|---------|
| **Phase 5** | "Linh hồn" — replay, saga, snapshots, deterministic orchestration |
| **Phase 4.6** | Memory Governance — ngăn hallucinated facts |
| **Phase 5.6** | Agent Runtime Kernel — formalizes execution layer |
| **Phase 5.7** | Cost Governance — ngăn chi phí bùng nổ |
| **Phase 8** | Symbolic execution LOẠI → Phase 13b |

---

## Thứ tự ưu tiên (nếu chọn sub-set)

1. Era 1 hoàn tất (1a → 7_cli)
2. Phase 4.6 Memory Governance trước Phase 11+
3. Phase 5.6 + 5.7 trước Phase 8
4. Phase 7 HIL scaffold trước Phase 8
5. Phase 8 → 11 (Era 2)
6. Phase 13b symbolic — chỉ khi có prerequisites

---

## Master roadmap

- **`docs/ERA_ROADMAP.md`** — bảng TT ✅/🔄/⬜, Tier Value, Execution Reality

## Template

Xem `prompts/_TEMPLATE.md`
