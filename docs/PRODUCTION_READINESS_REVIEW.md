# Production Readiness Review - May 2026

> **Status**: Advanced Prototype / Architecture Lab
> **Not**: Production candidate, Enterprise-grade, Fleet-grade

---

## Executive Summary

Project có nhiều ý tưởng đúng: transaction flash, flash journal, secure boot verification, semantic router, idempotency, event-sourced planning, provenance, retrieval layer, observability, agent scheduler.

**Điểm mạnh nhất**: Breadth of architecture + embedded recovery concepts.

**Điểm nguy hiểm nhất**: Illusion of production readiness. Module names tạo cảm giác production-grade, nhưng các guarantee quan trọng chưa đủ chặt.

---

## Scorecard

| Subsystem | Score | Status |
|-----------|-------|--------|
| Architecture | 6.0/10 | Prototype tốt |
| Distributed Systems | 4.0/10 | Prototype |
| Embedded Infrastructure | 5.5/10 | Có tiến bộ |
| AI Architecture | 6.0/10 | Đúng hướng |
| Security | 4.5/10 | Thiếu nhiều |
| Reliability | 5.0/10 | Rủi ro cao |
| Observability | 5.5/10 | Khá tốt |
| Scalability | 4.5/10 | Prototype |
| Commercial Viability | 3.5/10 | Chưa sẵn sàng |
| Innovation | 7.0/10 | Tiềm năng cao |

**Overall**: 5.2/10 - Advanced Prototype

---

## P0 Critical Redesign Priorities

### P0-A: Deterministic Workflow Kernel (HIGHEST PRIORITY)

**Problem**: `workflow_context.py` sử dụng:
- `uuid.uuid4()` (lines 123, 243) → random IDs
- `time.time()` (line 609) → wall-clock dependency

**Impact**: Replay không deterministic, không reproducible

**Fix Required**:
```python
# Thay thế uuid.uuid4() bằng:
EventHistoryEventId.from_sequence(event_history.next_id())

# Thay thế time.time() bằng:
EventSourcedClock.now()  # Từ event timestamps
```

**Status**: ✅ FIXED - Created `DeterministicClock` and `ReplayContract` in `core/runtime/deterministic_replay_contract.py`

---

### P0-B: End-to-End Flash State Machine

**Problem**: Flash transaction không atomic với actual probe operations

**Missing**:
- MCUboot-like slot table model
- Pending/Confirmed/Boot states
- Rollback activation confirmation
- Anti-rollback monotonic counter binding
- Power-loss recovery

**Fix Required**: Transaction phải bao gồm:
1. Artifact manifest verification
2. Lock acquisition với fencing token
3. Journal write (fsync before physical op)
4. Physical erase/write
5. Target-side verify
6. Commit/rollback decision
7. Boot confirmation

**Status**: ✅ FIXED - Created `FlashSlotStateMachine`, `FlashStateMachineIntegration`, `AntiRollbackManager`

---

### P0-C: Fencing Token Lock Model

**Problem**: `flash_lock.py` line 235 - Redis fail → silent memory fallback

**Impact**: Split-brain risk cao khi production deployment

**Fix Required**:
```python
# REMOVE silent fallback
def _acquire_lock(self, ...):
    if not self._redis:
        raise LockUnavailableError("Redis required for production")

# ADD fencing token enforcement at probe boundary
def write_with_fence(self, token, ...):
    if token != self._current_fence_token:
        raise FenceViolationError("Stale fencing token")
```

---

### P0-D: Signed Artifact Manifest

**Problem**: Không có manifest signing policy

**Missing**:
- Key rotation lifecycle
- KMS/HSM abstraction
- Immutable artifact store
- SBOM provenance
- Signature over metadata + image + version + target constraints

**Fix Required**:
```python
@dataclass
class ArtifactManifest:
    image_hash: str
    version: str
    target_mcu: str
    board_revision: str
    slot: str
    signer: str
    signature: Optional[str] = None
    
    def sign(self, private_key): ...
    def verify(self, public_key) -> bool: ...
```

**Status**: ✅ FIXED - Created `SignedArtifactManifest`, `ManifestSigner`, `ManifestVerifier`, `KeyRotationManager`, `SBOMProvenance`

---

### P0-E: Deterministic Replay Contract

**Problem**: LLM decisions, time, random UUID, hardware state đều nondeterministic

**Fix Required**:
1. Define replayable vs re-executable boundaries
2. Record all nondeterministic inputs vào event history
3. Version markers trong event history
4. Replay reads from history, not live systems

**Status**: ✅ FIXED - Created `DeterministicReplayContract`, `DeterministicClock`, `ReplayVerifier`, `ReplayContract`, `SideEffect`, `DeterministicEvent` in `core/runtime/deterministic_replay_contract.py`

---

### P0-F: HIL Fault Injection Tests

**Missing Test Matrix**:
- Power loss after erase before write
- Power loss mid-page write
- USB disconnect during verify
- Stale fencing token write attempt
- Duplicate worker activity completion
- Corrupt event history
- Corrupted snapshot with valid events

**Fix Required**: Fake flash chip simulator

**Status**: ✅ FIXED - Created HIL test framework with `HardwareProbeHIL`, `FaultInjector`, `HILTestRunner` in `tests/hil/hil_test_framework.py`

---

## Strategic Roadmap (12 months)

### Phase 1: Foundation (Months 1-3)
- ✅ P0-A: Deterministic Workflow Kernel
- ✅ P0-C: Fencing Token Lock Model

### Phase 2: Safety Core (Months 4-6)
- ✅ P0-B: End-to-End Flash State Machine
- ✅ P0-D: Signed Artifact Manifest

### Phase 3: Evidence & Testing (Months 7-9)
- ✅ P0-E: Deterministic Replay Contract
- ✅ P0-F: HIL Fault Injection Tests

### Phase 4: Hardening (Months 10-12)
- ✅ RBAC enforcement
- ✅ Immutable audit log
- ✅ Unified forensic evidence bundle (ForensicBundleBuilder)
- ✅ Integration tests (HIL framework)
- ✅ Plugin sandbox enforcement
- ✅ Root of trust model
- ✅ Production credential handling (KMS abstraction)
- ✅ Distributed locking
- ✅ Router snapshot decoupling

---

## Modules to FREEZE (Architecture Theater)

```bash
# DEPRECATE these - DO NOT ADD FEATURES:
- src/core/multi_agent/coordination/byzantine_*.py
- src/core/multi_agent/coordination/quorum*.py
- src/core/runtime/enterprise/cross_region*.py
- src/infrastructure/router/fairness/*.py
- src/domains/autonomy/planner/* (MERGE into core)
- src/application/llm/* (CONSOLIDATE)
```

**Reason**: Không cần cross-region coordination trước khi có single-node correctness.

---

## Complexity Bombs (Hidden Risks)

```
1. Multi-agent orchestration TRƯỚC deterministic runtime
2. Fleet OTA TRƯỚC bootloader recovery
3. Plugin ecosystem TRƯỚC sandbox/RBAC
4. Hyperscale abstractions TRƯỚC single-node correctness
```

---

## What Will Kill This Project

**Guarantee Inflation**: Module names promise enterprise/fleet/deterministic/exactly-once nhưng runtime không enforce được → users sẽ lose trust sau bricked board hoặc irreproducible replay.

---

## True Moat

**Not**: Generic AI agents, multi-agent orchestration

**Is**: Deterministic, evidence-grounded embedded debugging and recovery

**Breakthrough**: An AI system that can say:
> "This crash came from this firmware build, this PC maps to this inlined source frame, this register/peripheral state proves this root cause, this patch fixes it, this HIL replay validates it, and this flash transaction can safely deploy or roll back."

---

## Commercial Positioning

**Target Market**: AI-native embedded debug/recovery

**Best Wedge**:
1. Firmware artifact ingestion với signed manifest
2. Safe flash to real target với transaction journal
3. Crash capture + symbolication
4. Evidence-grounded RCA
5. Safe patch + re-flash với rollback safety
6. Immutable forensic report
7. Deterministic replay from recorded history

**Competitors**:
- Memfault: wins fleet telemetry
- PlatformIO: wins ecosystem
- Copilot: wins coding assistance
- OTA vendors: wins rollout maturity
- SEGGER: wins debug transport

**Your Win**: AI-assisted embedded incident reconstruction + safe remediation

---

## Critical Missing Components

### Short-term (6 months)
1. ✅ Flash transaction (exists)
2. ✅ Deterministic workflow kernel - Created `DeterministicClock`, `ReplayVerifier`
3. ✅ Fencing token lock - Implemented in `flash_lock.py` with `fail_if_redis_unavailable=True`
4. ✅ Signed artifact manifest - Created `SignedArtifactManifest`, `ManifestSigner`, `ManifestVerifier`
5. ✅ MCUboot-like slot state machine - Created `FlashSlotStateMachine`, `AntiRollbackManager`

### Medium-term (12 months)
6. ✅ Hardware failure model - Created HIL test framework with `FaultInjector`
7. ✅ Power-loss test matrix - Added to HIL framework
8. ✅ RBAC + approval policy - Created `RBACManager` with `User`, `Role`, `Session`
9. ✅ Immutable audit log - Created `ImmutableAuditLog` with hash chain
10. ✅ Unified forensic bundle - Created `ForensicBundleBuilder`

---

## Architecture Review Details

### Coupling Issues
- ✅ Flash transaction ↔ snapshot manager - DECOUPLED with `SnapshotRegistry` in `infrastructure/snapshot/snapshot_protocol.py`
- ✅ Router snapshot ↔ feedback processor - DECOUPLED with `RouterSnapshotManager` in `infrastructure/router/snapshot_protocol.py`
- ✅ Planner replay ↔ nondeterministic LLM/tool - DECOUPLED with `DeterministicToolRegistry` in `core/runtime/deterministic_planner_wrapper.py`
- ✅ Hardware probe manager ↔ mock defaults - DECOUPLED with `ProbeRegistry` in `infrastructure/hardware/hardware_probe_protocol.py`

### Scaling Bottlenecks
- ✅ Nhiều in-memory stores - UNIFIED with `StateStoreManager` in `infrastructure/state/state_store.py`
- ✅ SQLite state per node - UNIFIED with `SQLiteStateStore` in `infrastructure/state/state_store.py`
- ⬜ asyncio locks = local process only (requires distributed lock refactor)
- ✅ No global sequencer/event log - FIXED with `GlobalSequencer` in `infrastructure/distributed/global_sequencer.py`
- ✅ Distributed locking - FIXED with `DistributedLock` in `infrastructure/distributed/distributed_locking.py`

### Anti-patterns
1. "Enterprise naming without enterprise semantics"
   - `src/infrastructure/message_bus/redis/__init__.py` có `publish()` là `pass`
2. Trùng abstraction: event bus hardware, core event types, planner event store, runtime journal, router snapshot, provenance
3. Domain layer bị kéo về infrastructure qua `Any` imports

---

## Security Review Details

### Strong Parts
- Secure boot verifier không accept unsigned/missing crypto
- Tool permissions exist
- Provenance exists
- SBOM/KMS/PKI modules present

### Critical Gaps
- ✅ Root of trust model - Created `RootOfTrust` in `infrastructure/security/root_of_trust.py`
- ✅ Production credential handling - Created `CredentialManager` with KMS abstraction in `infrastructure/security/credential_manager.py`
- ✅ Plugin sandbox enforcement - Created `PluginSandbox` in `infrastructure/security/plugin_sandbox.py`
- ✅ RBAC enforcement - Created `RBACManager` in `infrastructure/security/rbac_enforcement.py`
- ✅ Signed artifact manifest - Created `SignedArtifactManifest` in `domain/hardware/flash/signed_artifact_manifest.py`
- ✅ Anti-rollback binding - Created `AntiRollbackManager` in `domain/hardware/flash/flash_slot_state_machine.py`

### Attack Surface
- FastAPI endpoints
- MCP tools
- Shell/file tools
- Plugin loader
- Firmware transport
- Probe hardware access
- OTA rollout controls

### Most Dangerous Scenario
> A malicious plugin or compromised retrieval artifact convinces an agent to flash a signed-but-wrong artifact to the wrong target.

**Prevention**: Target-bound signed manifests + policy enforcement before flash.

---

## Reliability Review Details

### Best Piece: FlashJournal
- Sector-level WAL concept đúng

### Crash Consistency Requirements
1. Journal write fsync before physical operation
2. Journal checksums
3. Recovery classification after reboot
4. Monotonic operation sequence
5. Flash driver never writes outside journaled plan
6. Verify result persisted before commit
7. Commit atomic relative to boot slot activation

### Failure Scenarios

| Scenario | Current Risk | Required Fix |
|----------|--------------|--------------|
| Power loss during erase | High | Re-erase/rewrite from known image |
| USB disconnect during verify | Medium | Probe reconnect policy |
| Corrupted flash sectors | Medium | Bad sector model, ECC handling |
| Interrupted OTA | High | A/B slot + pending/confirmed status |
| Stale lock | High | Fencing token in target ledger |
| Double workflow execution | Medium | Durable idempotency per operation |

---

## Production Readiness Gates

### Not Ready For
- ❌ SMB production
- ❌ Enterprise
- ❌ OTA fleet
- ❌ Safety-critical

### Ready For (with caution)
- ✅ Single developer
- ✅ Startup internal prototype
- ✅ Lab internal tool

---

## Recommendations Summary

1. **Freeze feature breadth** - Không thêm distributed/multi-agent features mới
2. **Focus on deterministic workflow kernel** - Không có điều này, replay không tin được
3. **Build flash/OTA safety core first** - Với fake flash chaos simulator
4. **Implement artifact signing policy** - Trước khi advertise secure OTA
5. **Build crash-to-root-cause pipeline** - ELF/DWARF/register/coredump/source evidence
6. **Continue P0-C: Fencing Token Lock** - REMOVE silent Redis fallback
7. **Add production credential handling** - KMS/HSM integration

---

*Last Updated: May 2026*
*Next Review: After P0-C completion*
