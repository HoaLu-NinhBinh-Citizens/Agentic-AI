# PROMPTS REVIEW — AI_SUPPORT
**Ngày:** 2026-05-22 | **Tổng:** 134 sub-phases

---

## Đọc file riêng lẻ

Mỗi sub-phase có file riêng: `prompts/phase_X_Y.md`

---

## Tổng hợp Weakness Analysis

### Legend

| Icon | Độ khó | Icon | Risk |
|------|---------|------|------|
| [EZ] | Easy | [LOW] | LOW |
| [MED] | Medium | [MED] | MEDIUM |
| [HARD] | Hard | [HIGH] | HIGH |
| [V.HARD] | VeryHard | [CRIT] | CRITICAL |
| [RESEARCH] | ResearchGrade | | |

---

## CRITICAL Risk Sub-phases (làm cuối cùng, cần Team)

| ID | Tên | Độ khó | Điểm yếu |
|----|------|--------|-----------|
| **5.1** | Event sourcing | VeryHard | Replay không deterministic → bug rất khó debug |
| **5.2** | Saga orchestration | VeryHard | Rollback thiếu compensation → inconsistent state |
| **5.6** | Agent Runtime Kernel | VeryHard | Orphan agent leak, crash isolation failure |
| **6.2c** | Flash infrastructure | VeryHard | A/B switch không atomic → brick device |
| **7.0a** | Simulator STM32 | VeryHard | QEMU không accurate 100% → false confidence |
| **7.0b** | Simulator ESP32 | VeryHard | ESP-IDF emulator không production-ready |
| **7.6a** | Board auto-replacement | VeryHard | Distinguish hardware vs software vs cable failure |
| **9.1** | Patch sandbox | VeryHard | Container escape → SECURITY RISK |
| **11.1** | Data collection PII | VeryHard | PII removal sai → legal risk |
| **12.4** | Fine-tune LLM | VeryHard | Data quality quyết định model quality |
| **14.1** | OTA orchestrator | VeryHard | Partial update → brick device (customer loss) |
| **14.4** | Predictive failure | VeryHard | Không có labeled failure data ban đầu |
| **15.4** | ISO 27001/SOC2 | Hard | External audit required (process, không phải code) |
| **15.4a** | E2E encryption | Hard | Key management là hardest part |
| **15.4b** | Code signing | Hard | Private key protection, HSM cost |
| **15.4e** | Audit trail immutable | Hard | Cryptographic integrity (hash chain / WORM) |

---

## HIGH Risk Sub-phases (cần Small team)

| ID | Điểm yếu chính |
|----|-----------------|
| **1a.5** | Thiết kế quá complex sớm |
| **2.1** | MCP stdio subprocess deadlock |
| **3.3** | Circuit breaker state machine race |
| **3.6** | OpenTelemetry span propagation qua WS |
| **4.1** | LLM provider response format khác nhau |
| **4.2** | Vector store down → block user |
| **4.6** | Hallucinated facts poison RAG |
| **5.1** | Event replay nondeterministic |
| **5.2** | Compensation step thiếu |
| **5.3** | Multi-agent nondeterministic |
| **5.4** | Snapshot không atomic với event log |
| **5.7** | Cost không observability |
| **6.1** | Target state machine race |
| **6.2b** | Compatibility matrix version-aware |
| **6.3** | RTT buffer overflow |
| **6.7** | GDB RSP packet truncation |
| **7.1** | OpenOCD version differences |
| **7.1a** | Multi-probe unified interface |
| **7.4** | Board state không persistent |
| **7.5** | USB overload khi concurrent flash |
| **7.6** | Reset không clean → FS corruption |
| **7.7** | Flaky detection khó |
| **8.1** | Tree-sitter crash on large codebase |
| **8.2** | ISR inference từ stripped ELF |
| **8.4b** | Bug dependency graph circular |
| **9.2** | Risk score không calibrated |
| **9.3** | Trust threshold không balanced |
| **10.1** | Semantic cache hash |
| **10.2** | Semantic router wrong decision |
| **11.3** | Encryption key management |
| **11.4** | Benchmark không realistic |
| **12.1** | Evaluation baseline reproducibility |
| **13.2** | LLM call nondeterministic in replay |
| **13.4** | Chaos cascade failure |
| **13b.1-4** | Symbolic execution research-grade |
| **14.2** | Crash cluster không đúng root cause |
| **14.3** | Anomaly detection false positive |
| **15.1** | Air-gapped constraints |
| **15.3** | Offline = không có LLM API |
| **15.3a** | Offline sync conflict resolution |
| **16.4b** | AI đề xuất breaking change |

---

## Research-Grade Sub-phases (chỉ startup 10+ engineers)

| ID | Tên | Điểm yếu |
|----|------|-----------|
| **13.5** | Execution semantics | CFG/ISR/DMA modeling — nhiều debugger TM còn struggle |
| **13.6** | Compiler intelligence | DWARF/LTO/inline asm — vùng cực khó |
| **13b.1** | Symbolic execution | Path explosion → không terminate |
| **13b.2** | CFG from stripped binary | Indirect jump targets khó resolve |
| **13b.3** | DMA modeling | Runtime config không capture được by static analysis |
| **13b.4** | Causal reasoning | Possible causes số lượng lớn |

---

## Solo- feasible Sub-phases (Easy/Medium, LOW/MEDIUM risk)

| ID | Tên | Risk |
|----|------|------|
| **1a.1** | Requirements scope | LOW |
| **1a.2** | Tool survey | LOW |
| **1a.3** | Stack selection | LOW |
| **1a.6** | Mock agent | LOW |
| **1b.2** | WS streaming | LOW |
| **1b.5** | Logging | LOW |
| **2.4** | Tool caching | LOW |
| **2.5** | Tool versioning | MEDIUM |
| **3.4** | Structured logging | MEDIUM |
| **3.5** | Prometheus metrics | LOW |
| **4.4** | Working memory | MEDIUM |
| **4.5** | Long-term memory | MEDIUM |
| **5.5** | Human-in-the-loop | MEDIUM |
| **6.1c** | Auto-detect | MEDIUM |
| **6.4** | Serial monitor | MEDIUM |
| **6.7b** | Core dump (stripped ELF) | MEDIUM |
| **8.3b** | Pattern versioning | MEDIUM |
| **8.4a** | Concurrent bug handling | MEDIUM |
| **9.3a** | Approval timeout | MEDIUM |
| **9.4** | Skill learning | MEDIUM |
| **10.3** | CLI UX | LOW |
| **10.4** | Approval UI | MEDIUM |
| **10.6** | GitHub Actions | MEDIUM |
| **10.6a** | Jenkins plugin | MEDIUM |
| **10.6b** | GitLab CI | MEDIUM |
| **11.2** | Labeling tool | MEDIUM |
| **11.4b** | Agent quality metrics | MEDIUM |
| **11.5** | Regression testing | MEDIUM |
| **11.6** | Human feedback loop | MEDIUM |
| **12.3** | Model rollback | MEDIUM |
| **12.3a** | Canary deployment | MEDIUM |
| **12.3b** | Auto-rollback triggers | MEDIUM |
| **13.1** | Grafana dashboard | LOW |
| **13.3** | SLO | MEDIUM |
| **14.5** | Jira/Slack integration | MEDIUM |
| **14.6** | QA dashboard | LOW |
| **15.2** | Licensing | LOW |
| **15.4c** | TLS 1.3 + mTLS | MEDIUM |
| **15.4d** | On-prem data | MEDIUM |
| **16.1** | OSS governance | LOW |
| **16.3** | Documentation | MEDIUM |
| **16.5** | ROI metrics | MEDIUM |

---

## Thứ tự ưu tiên thực tế

### Round 1 — Solo feasible (1a → 7_cli)

```
1a.1 → 1a.2 → 1a.3 → 1a.6
→ 1b.2 → 1b.5
→ 2.4 → 3.5
→ 4.4 → 4.5
→ 5.5
→ 6.1c → 6.4
→ CLI
```

### Round 2 — Solo/Small (1b → 5)

```
1b.1 → 1b.3 → 1b.4
→ 2.1 → 2.2 → 2.3 → 2.5
→ 3.1 → 3.2 → 3.4
→ 4.1 → 4.3
→ 5.4
```

### Round 3 — Small team (5 → 8)

```
5.1 → 5.2 (CRITICAL) → 5.3 → 5.6 (CRITICAL)
→ 4.6 (CRITICAL)
→ 6.1 → 6.1a → 6.1b
→ 6.2 → 6.2a → 6.2b → 6.2c (CRITICAL)
→ 6.3 → 6.5 → 6.6 → 6.7 → 6.7b
→ 8.1 → 8.3 → 8.3a → 8.3b → 8.4 → 8.4a → 8.4b
```

### Round 4 — Team (7 → 12)

```
7.0a (CRITICAL) → 7.1 → 7.1a → 7.2 → 7.3 → 7.4 → 7.5 → 7.6 → 7.6a (CRITICAL) → 7.7
→ 9.1 (CRITICAL) → 9.2 → 9.3 → 9.3a → 9.4 → 9.5
→ 10.1 → 10.2 → 10.3 → 10.4 → 10.5 → 10.6 → 10.6a → 10.6b
→ 11.1 (CRITICAL) → 11.2 → 11.3 → 11.4 → 11.4a → 11.4b → 11.5 → 11.6
→ 12.1 → 12.2 → 12.3 → 12.3a → 12.3b → 12.4 (CRITICAL) → 12.5
```

### Round 5 — Startup (13 → 16)

```
13.1 → 13.2 → 13.3 → 13.4 → 13.7
→ 13b.1-4 (RESEARCH — only if dedicated team)
→ 13.5-6 (RESEARCH)
→ 14.1 (CRITICAL) → 14.2 → 14.3 → 14.4 (CRITICAL) → 14.5 → 14.6
→ 15.1 → 15.2 → 15.3 → 15.3a → 15.4 → 15.4a → 15.4b → 15.4c → 15.4d → 15.4e
→ 16.1 → 16.2 → 16.3 → 16.4a → 16.4b → 16.4c → 16.4d → 16.5
```

---

## File count per difficulty

| Độ khó | Count |
|--------|-------|
| Trivial | 0 |
| Easy | ~15 |
| Medium | ~50 |
| Hard | ~50 |
| VeryHard | ~14 |
| ResearchGrade | ~7 |

---

## Hướng dẫn sử dụng

1. **Mở** `prompts/phase_X_Y.md` để review từng sub-phase riêng
2. **Đọc** Weakness Analysis trước khi implement
3. **Kiểm tra** depends_on — đảm bảo prerequisite đã done
4. **Cập nhật** `docs/ERA_ROADMAP.md` sau mỗi phase

---

## Script

Regenerate prompts:

```bash
python scripts/generate_prompts.py
```
