# Phase 5 – Durable Workflow & Multi‑Agent

## Lệnh Agent

```
@prompts/phase_5.md Thực hiện tuần tự. Commit [Phase 5]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Bảng sub-phase

| ID | Sub‑phase | Mô tả |
|----|-----------|-------|
| 5.1 | Event sourcing engine | Lưu mọi action, replay |
| 5.2 | Saga orchestration | Cho debug workflow dài (rollback nếu lỗi) |
| 5.3 | Multi‑agent coordination | Debug agent, test agent, patch agent, reviewer agent |
| 5.4 | Distributed snapshots | Có thể resume sau lỗi |
| 5.5 | Human‑in‑the‑loop | Checkpoint, chờ approve |
| **5.6** | **Agent Runtime Kernel** | Lifecycle, sandbox, deterministic FSM, scheduling, failure isolation |
| **5.7** | **Cost Governance** | Token budget, adaptive routing, model tiering, embedding budget |

## Task list (thực hiện tuần tự)

### Part A — Durable Workflow

- [ ] **5.1** Event store — `planner/event_sourced_state.py`, JSONL replay
- [ ] **5.2** Saga — `compensation_saga.py`, workflow compensation
- [ ] **5.3** Agents — DebugAgent, TestAgent, PatchAgent, ReviewerAgent (kế thừa base)
- [ ] **5.4** Snapshots — `snapshot_manager.py`, workflow archival
- [ ] **5.5** Approval — `rbac_approval.py`, checkpoint timeout rollback

### Part B — Agent Runtime Kernel 🆕

- [ ] **5.6** Agent lifecycle — spawn, suspend, resume, cancel, checkpoint
- [ ] **5.6a** Capability sandbox — tool permissions, resource quota, token budget, filesystem scope
- [ ] **5.6b** Deterministic FSM — replayable execution, action log, idempotency
- [ ] **5.6c** Scheduling — priority, fairness, backpressure
- [ ] **5.6d** Failure isolation — agent crash → isolated, retry boundary

### Part C — Cost Governance 🆕

- [ ] **5.7** Token budget — per-session, per-user limits
- [ ] **5.7a** Adaptive routing — route to cheapest model meeting quality threshold
- [ ] **5.7b** Inference policy — cache strategy, model tiering (fast/balanced/accurate)
- [ ] **5.7c** Embedding budget — RAG cost control, rerank budget
- [ ] **5.7d** Cost observability — metric: cost_per_session, model_tier_usage, cache_hit_rate

## Kết thúc phase

- [ ] Saga: fail mid-step → rollback all previous steps
- [ ] Snapshot: crash after step 3 → resume from step 3
- [ ] Agent cancel → no orphan tasks
- [ ] Sandbox: tool call outside scope → deny
- [ ] Token exceed → graceful reject
- [ ] pytest pass
- [ ] Commit `[Phase 5]`, build_log, ERA_ROADMAP

## Ghi chú
> ⭐ Phase 5 là "linh hồn" của platform. Nếu làm đúng → Phase 8–16 dễ hơn nhiều.
