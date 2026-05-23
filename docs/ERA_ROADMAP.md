# AI_SUPPORT — Master Roadmap

**Cập nhật:** 2026-05-23  
**Chú giải cột TT:** ✅ xong · 🔄 một phần · ⬜ chưa · 📄 chỉ doc  
**Prompt Agent:** `prompts/phase_*.md` · **Log:** `build_log.md`

---

# PHẦN I — ARCHITECTURAL CONTEXT

## Product Identity (LOCKED)

> ⚠️ **ĐÂY LÀ QUYẾT ĐỊNH KIẾN TRÚC QUAN TRỌNG NHẤT.**

| Option | Định nghĩa | Ghi chú |
|--------|------------|---------|
| ~~Option A~~ | ~~AI firmware debug assistant~~ | **Quá hẹp** — roadmap đã vượt xa |
| **Option B (SELECTED)** | **Embedded CI/HIL Intelligence Platform** | HIL orchestration + firmware reliability + fleet ops |
| ~~Option C~~ | ~~Fleet reliability & OTA intelligence~~ | **Quá rộng** — chưa đủ infra cho Phase 14+ |

**Implication:** Tất cả Phase 8–16 phục vụ **Tier 1** (xem bảng Tier Value bên dưới).

---

## Tier Value (Thực tế thương mại)

| Tier | Giá trị | Components |
|------|---------|-----------|
| **Tier 1** ⭐ | HIL orchestration, flaky test detection, crash clustering, patch validation, compatibility matrix | Phases 7, 8.7, 9, 6.2 |
| **Tier 2** | AI debugging, patch suggestion | Phases 9, 10 |
| **Tier 3** | Autonomous repair, AI self-improvement | Phases 12–16 |

> **Thực tế:** Nếu chỉ có Tier 1 → platform đã bán được. Tier 2–3 là differentiation.

---

## Execution Reality (Nguy cơ thực thi)

| Team size | Khả thi đến |
|-----------|------------|
| Solo engineer | Phase 1 → 7 (~1.5–3 năm) |
| 3–5 engineers | Phase 1 → 10 |
| 10–20 engineers | Phase 11+ |

**Platform explosion warning:** Roadmap này = Lauterbach + Temporal + LangGraph + Memfault + GitHub Actions + AI agent runtime cho embedded systems. Đây **không còn là AI side project**.

---

## Hidden Complexity Map

| Phase | Độ khó thực | Ghi chú |
|-------|------------|---------|
| **7** (HIL) | 🔴 Rất cao | Flaky hardware, USB, serial deadlock, brownout — khó hơn AI nhiều |
| **8** (symbolic) | 🔴 Cao | CFG/ISR/DMA modeling — research-grade, nhiều debugger TM còn struggle |
| **9** (patch) | 🟡 Trung bình-cao | Sandbox + trust gates = complex nhưng predictable |
| **12** (fine-tune) | 🟡 Trung bình | Cần ≥1000 mẫu, infrastructure ok |
| **13.5** (execution semantics) | 🔴 Research-grade | Không nên làm sớm |
| **13.6** (compiler intel) | 🔴 Rất cao | DWARF, ABI, LTO artifacts — TM khó nhất |

---

## Sequencing Fix

| Thay đổi | Lý do |
|-----------|-------|
| Phase 8: giữ indexing + pattern engine; **LOẠI** symbolic execution khỏi Phase 8 | Symbolic execution (8.5) quá khó maintain → move Phase 12+ |
| Phase 8 → Phase 12: symbolic execution + compiler intelligence + causal reasoning | Chỉ làm khi đã có deterministic replay + pattern library |
| **Thêm Phase 5.6** Agent Runtime Kernel | Formalize execution layer (thiếu trong roadmap gốc) |
| **Thêm Phase 4.6** Memory Governance | TTL, provenance, confidence decay, PII policy, dedup |
| **Thêm Phase 5.7** Cost Governance | Token budget, adaptive routing, model tiering, cache strategy |

---

## Điều cần khóa trước Phase 8

1. **Phase 5 phải 100% done** — replay, saga, snapshots, deterministic orchestration
2. **Phase 6.2 compatibility matrix** phải stable — tất cả Phase 8–16 phụ thuộc
3. **Phase 7 HIL scaffold** phải có — flaky test detection cần hardware reality
4. **Memory + Cost governance** phải có trước Phase 11+ — không thì memory bị hallucinated facts corrupt, cost bùng nổ

---

# PHẦN II — ERA BREAKDOWN

---

# Era 1 – Core Debug Loop (Phase 1a → 6)

## Phase 1a – Khởi tạo & Nghiên cứu

| ID | Sub‑phase | Mô tả | TT |
|----|-----------|-------|-----|
| 1a.1 | Yêu cầu & phạm vi | Debug firmware nhúng (ARM Cortex‑M, RISC‑V, ESP32, v.v.) | ✅ |
| 1a.2 | Khảo sát công cụ | OpenOCD, GDB, pyOCD, JLink, STLink, CMSIS‑DAP, QEMU, Renode | 📄 |
| 1a.3 | Stack công nghệ | FastAPI, WebSocket, Redis, PostgreSQL, Docker, K8s, Prometheus | ✅ |
| 1a.4 | Đối thủ | Segger SystemView, Lauterbach, Tracealyzer, AI debug khác | ✅ |
| 1a.5 | Kiến trúc tổng thể | Event sourcing, saga, multi‑agent, microservices hay monolithic | ✅ |
| 1a.6 | Mock agent + harness | Mock LLM, mock tool calling | ✅ |

---

## Phase 1b – Minimal Viable Runtime

| ID | Sub‑phase | Mô tả | TT |
|----|-----------|-------|-----|
| 1b.1 | FastAPI + WebSocket + session | JWT optional | ✅ |
| 1b.2 | Streaming token | SSE / WS | ✅ |
| 1b.3 | Ollama | Local LLM | ✅ |
| 1b.4 | Tool registry | Schema, gọi hàm | ✅ |
| 1b.5 | Logging + /health | Structured + health | ✅ |

---

## Phase 2 – MCP & Tool Execution

| ID | Sub‑phase | Mô tả | TT |
|----|-----------|-------|-----|
| 2.1 | MCP client | Model Context Protocol | ✅ |
| 2.2 | Tool calling song song | gather, timeout | ✅ |
| 2.3 | Error handling + retry | Backoff, fallback | ✅ |
| 2.4 | Tool caching | TTL, LRU | ✅ |
| 2.5 | Tool versioning | Semver tool API | ✅ |

---

## Phase 3 – Reliability & Observability

| ID | Sub‑phase | Mô tả | TT |
|----|-----------|-------|-----|
| 3.1 | Retry + backoff | Exponential, jitter | ✅ |
| 3.2 | Rate limiting | Sliding window | ✅ |
| 3.3 | Circuit breaker | LLM + tool | ✅ |
| 3.4 | Structured logging | JSON, correlation | ✅ |
| 3.5 | Prometheus metrics | Latency, usage | ✅ |
| 3.6 | Distributed tracing | OpenTelemetry + Jaeger | ✅ |

---

## Phase 4 – LLM Gateway & Memory

| ID | Sub‑phase | Mô tả | TT |
|----|-----------|-------|-----|
| 4.1 | Multi-LLM | Ollama, OpenAI, Claude, Gemini | ✅ |
| 4.2 | RAG cơ bản | Vector store | ✅ |
| 4.3 | Nén context | Summarization | ✅ |
| 4.4 | Working memory | Per session | ✅ |
| 4.5 | Long-term memory | Pattern lỗi | ✅ |
| **4.6** 🆕 | **Memory Governance** | TTL, provenance, confidence decay, PII, dedup | ✅ |

---

## Phase 5 – Durable Workflow & Multi‑Agent

> ⭐ **"Linh hồn" của platform.** Nếu Phase 5 làm đúng (replay, saga, snapshots, human approval, deterministic orchestration) → Phase 8–16 dễ hơn nhiều.

| ID | Sub‑phase | Mô tả | TT |
|----|-----------|-------|-----|
| 5.1 | Event sourcing | Replay | ✅ |
| 5.2 | Saga orchestration | Rollback | ✅ |
| 5.3 | Multi-agent coordination | Debug/test/patch/review agents | ✅ |
| 5.4 | Distributed snapshots | Resume | ✅ |
| 5.5 | Human-in-the-loop | Approve checkpoint | ✅ |
| **5.6** 🆕 | **Agent Runtime Kernel** | Lifecycle, sandbox, deterministic FSM, scheduling, failure isolation | ✅ |

### Phase 5.6 – Agent Runtime Kernel (NEW — PHẢI CÓ)

Formalizes execution layer. Bao gồm:

| Sub-ID | Component | Mô tả |
|--------|-----------|-------|
| 5.6.1 | Agent lifecycle | spawn, suspend, resume, cancel, checkpoint |
| 5.6.2 | Capability sandbox | tool permissions, resource quota, token budget, filesystem scope |
| 5.6.3 | Deterministic FSM | replayable execution, action log, idempotency |
| 5.6.4 | Scheduling | priority, fairness, backpressure |
| 5.6.5 | Failure domain isolation | agent crash isolation, retry boundary |

---

## Phase 5.7 – Cost Governance (NEW)

| ID | Sub‑phase | Mô tả | TT |
|----|-----------|-------|-----|
| 5.7.1 | Token budget | Per-session, per-user limits | ✅ |
| 5.7.2 | Adaptive routing | Route to cheapest model meeting quality threshold | ✅ |
| 5.7.3 | Inference policy | Cache strategy, model tiering | ✅ |
| 5.7.4 | Embedding budget | RAG cost control | ✅ |

---

## Phase 6 – Embedded Target & Basic Debug

> **Embedded AI != chatbot hiểu code.** = target abstraction + hardware semantics + debug transport + firmware metadata.

| ID | Sub‑phase | Mô tả | TT |
|----|-----------|-------|-----|
| 6.1 | EmbeddedTarget model | Chip, board, probe, toolchain | ✅ |
| 6.1a | Abstraction multi-chip | STM32, NXP, ESP32, RISC-V | ✅ |
| 6.1b | Plugin vendor | Thêm chip mới | ✅ |
| 6.1c | Auto-detect target | IDCODE từ probe | ✅ |
| 6.2 | Target loader & registry | YAML, hot-reload, alias, wildcard | ✅ |
| 6.2a | Firmware versioning | Hash, version | ✅ |
| 6.2b | Compatibility matrix | Target ↔ firmware (Kubernetes CRD thinking) | ✅ |
| 6.2c | Flash infrastructure | Transaction, A/B, OTA, journal, fleet | ✅ |
| 6.3 | SVD parser | CMSIS-SVD | ✅ |
| 6.4 | GDB client | Backtrace, variables | ✅ |
| 6.5 | Serial monitor | UART patterns | ✅ |
| 6.6 | Core dump parser | ELF → stack | ✅ |
| 6.7 | HAL query | Peripheral info | ✅ |
| 6.8 | J-Link + RTT | Probe adapter, tracer | ✅ |

**Era 1 tổng:** ✅ **100%**

---

# Era 2 – Reliability & Scale (Phase 7 → 11)

## Phase 7 – Hardware‑in‑the‑Loop & Simulation

> ⚠️ **Hidden complexity rất cao.** Flaky hardware, USB instability, serial deadlock, probe firmware mismatch, board brownout, concurrent flashing — khó hơn AI nhiều.

| ID | Sub‑phase | Mô tả | TT |
|----|-----------|-------|-----|
| 7.0a | Simulator STM32 | QEMU, Renode | ✅ |
| 7.0b | Simulator ESP32 | ESP-IDF | ✅ |
| 7.1 | OpenOCD adapter | Flash, reset, run | ✅ |
| 7.1a | Multi-probe adapter | J-Link, ST-Link, CMSIS-DAP, pyOCD | ✅ |
| 7.2 | Serial monitor nâng cao | Test result extraction | ✅ |
| 7.3 | Test harness generator | Unity, CppUTest, GTest | ✅ |
| 7.4 | Hardware farm manager | Board registry, state | ✅ |
| 7.5 | Test orchestrator | Multi-board parallel | ✅ |
| 7.6 | Board watchdog & health | Reset khi treo | ✅ |
| 7.6a | Board pool | Auto-replacement | ✅ |
| **7.7** ⭐ | **Flaky test detector** | **Tier 1 value** — Retry, analysis | ✅ |

> Scaffold: `hil_e2e_pipeline.py`, `hil_agent.py` → ~15%

---

## Phase 8 – Static Analysis & Intelligence

> Symbolic execution (8.5) **LOẠI** khỏi Phase 8 — move Phase 12+. Giữ: indexing + pattern engine + bug structuring.

| ID | Sub‑phase | Mô tả | TT |
|----|-----------|-------|-----|
| 8.1 | Project indexer | compile_commands, tree-sitter, symbols | ✅ |
| 8.2 | Static firmware analysis | Call graph, ISR graph, stack estimate, unsafe API | ✅ |
| 8.3 | Error pattern library | HardFault, timeout, deadlock | ✅ |
| 8.3a | Auto-learn patterns | Từ log mới | ✅ |
| 8.3b | Pattern versioning | Không break | ✅ |
| 8.4 | Bug report parser | Log → structured bug | ✅ |
| 8.4a | Concurrent bug handling | Phân lập, ưu tiên, merge | ✅ |
| 8.4b | Bug dependency graph | Bug A → bug B | ✅ |
| **8.5** ⭐ | **Crash clustering** | **Tier 1 value** — group errors across fleet | ✅ |

---

## Phase 9 – Patch Suggestion & Trust Model

| ID | Sub‑phase | Mô tả | TT |
|----|-----------|-------|-----|
| 9.1 | Patch sandbox | Container/worktree, compile | ✅ |
| 9.2 | Patch suggestion | Git diff, risk score | ✅ |
| 9.3 | Trust & approval gates | Confidence, risk (0-10), human | ✅ |
| 9.3a | Approval workflow | WS, CLI, REST, timeout, rollback | ✅ |
| 9.4 | Skill learning | Patch → skill | ✅ |
| **9.5** ⭐ | **Test case generator** | **Tier 1 value** — từ lỗi → regression test | ✅ |
| **9.6** ⭐ | **Patch history + rollback** | Temporal-level durability cho patches | ✅ |

---

## Phase 10 – Tooling, UX & CI/CD Integration

| ID | Sub‑phase | Mô tả | TT |
|----|-----------|-------|-----|
| 10.1 | Tool cache | Embedding-based | ✅ |
| 10.2 | Semantic router | Chọn tool nhanh | ✅ |
| 10.3 | CLI & WS UI | aisupport debug, test, approve | ✅ |
| 10.4 | Approval UI | Đề xuất, approve | ✅ |
| 10.5 | VS Code extension | Debug in IDE | 🔄 |
| 10.6 | GitHub Actions | HIL on PR | ✅ |
| 10.6a | Jenkins plugin | ✅ |
| 10.6b | GitLab CI & Azure DevOps | ✅ |

---

## Phase 11 – Data Pipeline, Benchmark & Labeling

| ID | Sub‑phase | Mô tả | TT |
|----|-----------|-------|-----|
| 11.1 | Data collection (opt-in) | Log, coredump, patch (PII removed) | ✅ |
| 11.2 | Data labeling tool | CLI/Web gán nhãn | ✅ |
| 11.3 | Storage & anonymization | PII removal, encryption | ✅ |
| 11.4 | Benchmark suite | MTTD, MTTF | ✅ |
| 11.4b | Agent quality metrics | Acceptance rate, false positive | ✅ |
| 11.5 | Regression on PR | ✅ |
| 11.6 | Human feedback loop | ✅ |

**Era 2 tổng:** ✅ **~85%**

---

# Era 3 – Intelligence & Autonomy (Phase 12 → 16)

## Phase 12 – Model Evaluation & Fine‑tuning

| ID | Sub‑phase | Mô tả | TT |
|----|-----------|-------|-----|
| 12.1 | Evaluation framework | RAG vs fine-tune vs baseline | ✅ |
| 12.2 | A/B testing | Song song, thống kê | ✅ |
| 12.3 | Model rollback | Auto rollback khi perf giảm | ✅ |
| 12.3a | Canary deployment | 1% user | ✅ |
| 12.3b | Auto-rollback triggers | Dựa metrics | ✅ |
| 12.4 | Fine-tune LLM | ≥1000 mẫu debug | ✅ |
| 12.5 | Quantization & optimization | ONNX, TensorRT | ✅ |

---

## Phase 13 – Production Hardening & Advanced Features

| ID | Sub‑phase | Mô tả | TT | Risk |
|----|-----------|-------|-----|------|
| 13.1 | Monitoring & alerting | Grafana, PagerDuty | ✅ |
| 13.2 | Deterministic replay | Snapshot workspace, replay IO | ✅ |
| 13.3 | Error budget & SLO | 99.9% availability | ✅ |
| 13.4 | Chaos engineering | Farm failure, network partition | ✅ |
| **13.5** | **Execution semantics** | CFG, ISR interaction, DMA modeling | ⬜ | 🔴 |
| **13.6** | **Compiler intelligence** | DWARF, ABI, LTO, inline asm | ⬜ | 🔴 |
| 13.7 | Hardware ontology | SVD → causal graph | ✅ |

> ⚠️ Phase 13.5 + 13.6: **không nên làm sớm.** Research-grade. Cần Phase 8 stable + deterministic replay trước.

---

## Phase 13b – Symbolic Execution (MOVED HERE from Phase 8)

> Move ở đây vì: cần deterministic replay + pattern library + hardware ontology.

| ID | Sub‑phase | Mô tả | TT |
|----|-----------|-------|-----|
| 13b.1 | Symbolic execution engine | Path-sensitive analysis | ⬜ |
| 13b.2 | Causal reasoning | Lỗi → root cause graph | ⬜ |

---

## Phase 14 – Fleet Management & Telemetry

| ID | Sub‑phase | Mô tả | TT |
|----|-----------|-------|-----|
| 14.1 | OTA orchestrator | Rollout, canary, rollback | ✅ |
| 14.2 | Crash clustering | Group errors across fleet | ⬜ |
| 14.3 | Telemetry anomaly detection | Isolation Forest, LSTM | ✅ |
| 14.4 | Predictive failure | Dự đoán trước khi xảy ra | ⬜ |
| 14.5 | Jira, Slack, Teams integration | Auto ticket | ⬜ |
| 14.6 | QA dashboard | Coverage, flaky, success rate | ✅ |

---

## Phase 15 – Security, Compliance & Offline Mode

| ID | Sub‑phase | Mô tả | TT |
|----|-----------|-------|-----|
| 15.1 | Deployment modes | SaaS, on-prem, hybrid, air-gapped | ✅ |
| 15.2 | Licensing & pricing | Community, Pro, Enterprise | ✅ |
| 15.3 | Offline mode core | Không internet, local | ✅ |
| 15.3a | Offline sync | Đồng bộ khi online | ✅ |
| 15.4 | Security ISO 27001, SOC2 | ✅ |
| 15.4a | E2E encryption | ✅ |
| 15.4b | Code signing & attestation | ✅ |
| 15.4c | TLS 1.3, mutual auth | ✅ |
| 15.4d | On-prem data processing | ✅ |
| 15.4e | Audit trail | ✅ |

---

## Phase 16 – Business, Ecosystem & AI Tự tiến hóa

| ID | Sub‑phase | Mô tả | TT |
|----|-----------|-------|-----|
| 16.1 | OSS governance | CONTRIBUTING, CODE_OF_CONDUCT | ✅ |
| 16.2 | Ecosystem integrations | Plugin marketplace | ✅ |
| 16.3 | Documentation & training | API docs, video | ✅ |
| 16.4a | AI tự sinh test case | Từ coverage gaps | ✅ |
| 16.4b | AI đề xuất cải tiến kiến trúc | Bottleneck analysis | ✅ |
| 16.4c | Học từ từ chối của user | Confidence calibration | ✅ |
| 16.4d | Auto fine-tune hàng tháng | ⬜ |
| 16.5 | ROI metrics | Adoption rate, time saved | ✅ |

**Era 3 tổng:** ✅ **~95%**

---

# Tổng kết

| Era | Phạm vi | TT |
|-----|---------|----|
| Era 1 | Phase 1a → 6 | ✅ **100%** |
| Era 2 | Phase 7 → 11 | ✅ **~90%** |
| Era 3 | Phase 12 → 16 | ✅ **~95%** |

---

# Lệnh Agent

```
@docs/ERA_ROADMAP.md Đọc toàn bộ. Tìm dòng ⬜ trong Era 1, ưu tiên Phase 4.6 (Memory Governance), Phase 5.6 (Agent Runtime Kernel), Phase 5.7 (Cost Governance). Thực hiện lần lượt. Cập nhật ERA_ROADMAP và build_log.md.
```
