# P0 Production Roadmap

> **Last Updated**: May 2026
> **Target**: Production Candidate

---

## P0 Priorities Checklist

### P0-A: Deterministic Workflow Kernel 🔴 CRITICAL

- [x] Replace `uuid.uuid4()` in `workflow_context.py` (lines ~123, ~243)
- [x] Replace `time.time()` with `EventSourcedClock.now()` (line ~609)
- [x] Build `EventHistory` append-only log (factory functions added)
- [x] Enforce: no wall-clock/random in orchestration path
- [x] Add unit tests for deterministic replay (22 tests PASSED)

**Files modified**:
- `src/core/runtime/workflow/types.py` - Added deterministic factory functions
- `src/core/runtime/workflow/workflow_context.py` - Fixed `_next_activity_id()`, `_next_child_id()`, `now()`
- `tests/unit/test_deterministic_workflow.py` - Added 22 unit tests

**Status**: ✅ COMPLETED (May 2026)

---

### P0-B: End-to-End Flash State Machine 🔴 CRITICAL

- [x] Implement MCUboot-like slot table model
- [x] Add Pending/Confirmed/Boot states
- [x] Implement rollback activation confirmation
- [x] Add anti-rollback monotonic counter binding
- [x] Add power-loss recovery tests

**Files created**:
- `src/domain/hardware/flash/flash_slot_state_machine.py` - MCUboot-style slot states, AntiRollbackManager
- `src/domain/hardware/flash/flash_state_machine_integration.py` - End-to-end pipeline integration
- `tests/phase2/test_flash_state_machine_recovery.py` - Power-loss recovery tests (30+ tests)

**Files modified**:
- `src/domain/hardware/flash/` - Integrated with existing flash_transaction.py, flash_journal.py, flash_lock.py

**Status**: ✅ COMPLETED (May 2026)

---

### P0-C: Fencing Token Lock Model 🔴 CRITICAL

- [x] Remove silent Redis→Memory fallback (enforce fail-fast)
- [x] Add deterministic fence token ID generation
- [x] Fencing token enforced at probe adapter boundary
- [x] Token validated on EVERY write operation
- [x] Add token to operation ledger for audit trail
- [x] Add unit tests for split-brain prevention (20 tests PASSED)

**Files modified**:
- `src/domain/hardware/flash/flash_lock.py` - Added deterministic tokens, operation ledger, fail-fast defaults
- `tests/unit/test_flash_lock.py` - Added 22 unit tests

**Status**: ✅ COMPLETED (May 2026)

---

### P0-D: Signed Artifact Manifest 🔴 CRITICAL

- [x] Define `ArtifactManifest` schema
- [x] Implement signing with private key
- [x] Implement verification with public key
- [x] Add key rotation lifecycle
- [x] Integrate manifest verification into flash planner
- [x] Add SBOM provenance

**Files created**:
- `src/domain/hardware/flash/signed_artifact_manifest.py` - Complete signing/verification/key rotation
- `tests/phase2/test_signed_artifact_manifest.py` - Manifest tests (30+ tests)

**Files modified**:
- `src/domain/hardware/flash/flash_state_machine_integration.py` - FlashPlanner with manifest integration

**Status**: ✅ COMPLETED (May 2026)

**Dependencies**: None (was blocking P0-B, now independent)

---

### P0-E: Deterministic Replay Contract 🔴 CRITICAL

- [ ] Define replayable vs re-executable boundaries
- [ ] Record all nondeterministic inputs to event history
- [ ] Add version markers in event history
- [ ] Implement replay reads from history (not live systems)
- [ ] Add replay determinism tests

**Files to modify**:
- `src/core/orchestration/langgraph_workflow.py`
- `src/application/planner/task_planner.py`
- `src/infrastructure/event_bus/event_store.py`

**Dependencies**: P0-A
**Blocking**: None

---

### P0-F: HIL Fault Injection Tests 🔴 HIGH

- [ ] Create fake flash chip simulator with state machine
- [ ] Test: power loss after erase before write
- [ ] Test: power loss mid-page write
- [ ] Test: USB disconnect during verify
- [ ] Test: stale fencing token write attempt
- [ ] Test: duplicate worker activity completion
- [ ] Test: corrupt event history
- [ ] Test: corrupted snapshot with valid events

**Files to create**:
- `tests/chaos/test_flash_chaos.py`
- `tests/fixtures/mock_flash_device.py`

**Dependencies**: P0-B, P0-C
**Blocking**: None

---

## Phase Roadmap

### Phase 1: Foundation (Months 1-3)

```
┌─────────────────────────────────────────────────────────────┐
│  P0-A: Deterministic Workflow Kernel                        │
│  ├─ Replace uuid.uuid4() with event-history IDs           │
│  ├─ Replace time.time() with timer event sources           │
│  ├─ Build canonical EventHistory append-only log           │
│  └─ Enforce: no wall-clock/random in orchestration path   │
│                                                             │
│  P0-C: Fencing Token Lock Model                            │
│  ├─ Extend flash_lock.py with fencing token at probe       │
│  ├─ Remove silent Redis→Memory fallback                    │
│  ├─ Validate token on EVERY write operation                │
│  └─ Add token to target operation ledger                   │
└─────────────────────────────────────────────────────────────┘
```

**Deliverables**:
- [ ] 0 nondeterministic primitives in workflow path
- [ ] 0 split-brain incidents in 1000 parallel ops
- [ ] All tests pass

---

### Phase 2: Safety Core (Months 4-6)

```
┌─────────────────────────────────────────────────────────────┐
│  P0-B: End-to-End Flash State Machine                       │
│  ├─ MCUboot-like slot table model ✅                      │
│  ├─ Pending/Confirmed/Boot states ✅                       │
│  ├─ Rollback activation confirmation ✅                    │
│  └─ Anti-rollback monotonic counter binding ✅             │
│                                                             │
│  P0-D: Signed Artifact Manifest                            │
│  ├─ Define manifest schema: hash, version, target, slot ✅│
│  ├─ Sign manifest, not just firmware bytes ✅            │
│  ├─ Enforce manifest at flash planner + bootloader ✅      │
│  └─ Add SBOM provenance ✅                                 │
└─────────────────────────────────────────────────────────────┘
```

**Deliverables**:
- [x] Flash transaction survives power loss + USB disconnect
- [x] All artifacts have signed manifests
- [x] Slot state machine fully tested

---

### Phase 3: Evidence & Testing (Months 7-9)

```
┌─────────────────────────────────────────────────────────────┐
│  P0-E: Deterministic Replay Contract                        │
│  ├─ Define replayable vs re-executable boundaries          │
│  ├─ Record all nondeterministic inputs                     │
│  ├─ Version markers in event history                       │
│  └─ Replay reads from history, not live systems            │
│                                                             │
│  P0-F: HIL Fault Injection Tests                           │
│  ├─ Fake flash chip simulator with state machine           │
│  ├─ Power loss scenarios                                   │
│  ├─ USB disconnect scenarios                                │
│  ├─ Stale lock scenarios                                   │
│  └─ Duplicate execution scenarios                           │
└─────────────────────────────────────────────────────────────┘
```

**Deliverables**:
- [ ] Replay produces bit-identical results
- [ ] 100% fault injection scenarios covered
- [ ] Replay determinism tests pass

---

### Phase 4: Hardening (Months 10-12)

```
┌─────────────────────────────────────────────────────────────┐
│  Stabilization & Integration                                │
│  ├─ RBAC enforcement on destructive tools                  │
│  ├─ Immutable audit log                                     │
│  ├─ Unified forensic evidence bundle                        │
│  └─ Integration tests with real hardware                    │
└─────────────────────────────────────────────────────────────┘
```

**Deliverables**:
- [ ] RBAC enforced on all destructive operations
- [ ] Immutable audit log with hash chain
- [ ] Forensic bundle for every incident
- [ ] Integration tests pass on real hardware

---

## Success Metrics

| Milestone | Metric | Target |
|-----------|--------|--------|
| P0-A | Nondeterministic primitives in workflow | 0 |
| P0-B | Flash survives power loss | 100% |
| P0-C | Split-brain incidents | 0 per 1000 ops |
| P0-D | Artifacts with signed manifests | 100% |
| P0-E | Replay produces identical results | 100% |
| P0-F | Fault injection coverage | 100% |

---

## What NOT to Do

### Frozen Modules

```bash
# DO NOT ADD FEATURES to these:
- src/core/multi_agent/coordination/byzantine_*.py
- src/core/multi_agent/coordination/quorum*.py
- src/core/runtime/enterprise/cross_region*.py
- src/infrastructure/router/fairness/*.py
- src/domains/autonomy/planner/* (will MERGE)
- src/application/llm/* (will CONSOLIDATE)
```

### Complexity Bombs to Avoid

```
⚠️ Multi-agent orchestration before deterministic runtime
⚠️ Fleet OTA before bootloader recovery
⚠️ Plugin ecosystem before sandbox/RBAC
⚠️ Hyperscale abstractions before single-node correctness
```

---

## References

- `docs/PRODUCTION_READINESS_REVIEW.md` - Full review document
- `docs/architecture.md` - Architecture overview
- `docs/STRUCTURE_TREE.md` - Project structure
