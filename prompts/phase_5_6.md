# Phase 5.6 – Agent Runtime Kernel

> Sub-phase của Phase 5. Đã bao gồm trong `phase_5.md`. File riêng để Agent tập trung.

## 1. BỐI CẨNH

- **Product:** Embedded CI/HIL Intelligence Platform
- **Tier:** ⭐ Tier 1 — execution layer cho toàn bộ platform
- **Hidden complexity:** 🔴 cao
- **Phụ thuộc:** Phase 5.1–5.5 (workflow)

## 2. TASK LIST

| ID | Sub‑phase | Mô tả | Done khi |
|----|-----------|-------|----------|
| **5.6** | **Agent lifecycle** | spawn, suspend, resume, cancel, checkpoint. No orphan agents. |
| 5.6a | Capability sandbox | tool permissions, resource quota, token budget, filesystem scope. Agent không escape. |
| 5.6b | Deterministic FSM | replayable execution, action log, idempotency. Replay = same output. |
| 5.6c | Scheduling | Priority, fairness, backpressure. No starvation. |
| 5.6d | Failure isolation | Agent crash → isolated, retry boundary. System ≠ agent. |

## 3. CẤU TRÚC FILE

```
src/core/agent_runtime/
├── kernel.py              # AgentLifecycle, spawn/suspend/resume/cancel
├── sandbox.py            # CapabilitySandbox, permissions, quota
├── fsm.py                # DeterministicFSM, action log, replay
├── scheduler.py          # PriorityScheduler, backpressure
└── isolation.py          # FailureDomainIsolation
tests/unit/test_agent_runtime/
```

## 4. ACCEPTANCE CRITERIA

- [ ] Agent spawn → track PID → cancel → no orphan
- [ ] Sandbox: tool call outside scope → deny
- [ ] FSM: same action log → same result on replay
- [ ] Crash one agent → others continue
- [ ] pytest pass

## 5. KẾT THÚC

- [ ] Commit `[Phase 5.6] agent runtime kernel`
- [ ] build_log + ERA_ROADMAP
