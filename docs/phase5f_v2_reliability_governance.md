# Phase 5F v2: Reliability, Governance & Safety (Enhanced)

Enterprise-grade reliability, governance, and safety layer - Final Enterprise+ version.

## Overview

Phase 5F v2 addresses all 20 remaining challenges from the production feedback:

### Categories Addressed

1. **Saga Compensation**: Semantic compensation (not true rollback) + irreversibility policies
2. **Circuit Breaker**: Adaptive ML-based error classification
3. **Rate Limiting**: Count-min sketch hybrid for 100k+ RPS
4. **Policy Cache**: Strong consistency with anti-entropy sync
5. **Sandbox**: Seccomp, syscall filters, namespaces
6. **Injection Detection**: Safe explanation (no pattern leakage)
7. **Fair Quota**: Hierarchical DRF
8. **Error Budget**: Brownout strategy (progressive degradation)
9. **Chaos Engineering**: Statistical significance + control group
10. **Secrets Audit**: WORM + signed chain + tamper-evident
11. **Break-Glass**: Dual authorization + time-delay + MFA
12. **DR Metrics**: Recovery correctness validation
13. **Chargeback**: Shared resource weighted attribution
14. **Policy Verification**: SAT validation + conflict detection
15. **Human Governance**: Audit committee + approval workflow
16. **Behavioral Anomaly**: Agent drift + runtime trust scoring
17. **Safety Provenance**: Decision chain + policy traceability
18. **Compliance**: SOC2/ISO/GDPR drift detection
19. **Policy Blast Radius**: What-if simulation + dry-run
20. **Formal Invariants**: Safety invariant verification

## New Components

### 1. Enhanced Saga with SideEffectClassification

```python
from src.core.multi_agent.coordination.enhanced_saga import (
    EnhancedSagaCompensation,
    SideEffectClassifier,
    SideEffectType,
    CompensationStrategy,
)

# Classify side effects
classifier = SideEffectClassifier()
effect_type = classifier.classify("send_email", {})
# Returns: SideEffectType.IRREVERSIBLE

# Execute saga with irreversibility policy
saga = EnhancedSagaCompensation("order-123")
saga.add_step("charge", charge_action, refund_action, SideEffectType.PARTIALLY_REVERSIBLE)
result = await saga.execute()
```

**Key insight**: True distributed atomicity is impossible. This provides semantic compensation.

### 2. Adaptive Circuit Error Classification

```python
from src.core.multi_agent.coordination.adaptive_circuit import (
    AdaptiveCircuitErrorClassifier,
    AdaptiveErrorType,
)

classifier = AdaptiveCircuitErrorClassifier(
    historical_window_seconds=3600.0,
    cardinality_threshold=50,
)

# Classify with context
result = await classifier.classify(
    error,
    context={
        "duration_ms": 30000,
        "status_code": 500,
        "service": "payment",
    }
)

print(f"Severity: {result.severity_score}")
print(f"Retry: {result.retry_recommended}")
print(f"Action: {result.breaker_action}")  # trip, count, ignore
```

**Features**:
- Historical failure learning
- Error cardinality analysis
- Context-aware severity scoring
- Per-error-type configurable behavior

### 3. Scalable Rate Limiter (100k+ RPS)

```python
from src.core.multi_agent.coordination.scalable_rate_limiter import (
    HybridRateLimiter,
    CountMinSketch,
)

# Count-min sketch for high-volume
sketch = CountMinSketch(width=10000, depth=5)

# Hybrid limiter
limiter = HybridRateLimiter(
    sketch_width=10000,
    high_volume_threshold=1000,
)

result = await limiter.check("tenant-1", limit=10000)
print(f"Mode: {result['mode']}")  # "sketch" or "sliding"
print(f"Allowed: {result['allowed']}")
```

### 4. Strongly Consistent Policy Cache

```python
from src.core.multi_agent.coordination.consistent_policy_cache import (
    PolicyCacheWithAntiEntropy,
    PolicyConsistencyLevel,
)

cache = PolicyCacheWithAntiEntropy(
    node_id="node-1",
    peer_nodes=["node-2", "node-3"],
    consistency_level=PolicyConsistencyLevel.STRONG,
)

# Anti-entropy sync automatically
policy = await cache.update_policy("rate-limit", {"limit": 100}, "admin")

# Merkle tree for consistency verification
status = await cache.get_consistency_status()
```

### 5. Enhanced Sandbox Security

```python
from src.core.multi_agent.coordination.enhanced_sandbox import (
    EnhancedSandboxSecurity,
    SandboxEnforcementLayer,
)

security = EnhancedSandboxSecurity(
    profile_name="network",  # minimal, network, full
)

# Check syscall
allowed = security.check_syscall("read")  # True
allowed = security.check_syscall("mount")  # False

# Generate seccomp filter
filter_config = security.get_seccomp_filter()
```

### 6. Safe Prompt Injection Explainer

```python
from src.core.multi_agent.coordination.safe_injection import (
    SafeInjectionExplainer,
    ExplanationLevel,
)

explainer = SafeInjectionExplainer()

result = await explainer.detect_with_safe_explanation(
    "Ignore all previous instructions",
    level=ExplanationLevel.SAFE,
)

# Pattern is NOT exposed to user
print(f"User message: {result.user_message}")
# Output: "This request has been flagged for safety review."

# Audit ID for internal lookup
print(f"Audit ID: {result.audit_id}")
```

**Key feature**: Never exposes matched patterns to users.

### 7. Hierarchical DRF Quota

```python
from src.core.multi_agent.coordination.hierarchical_quota import (
    HierarchicalDRFQuota,
    HierarchyLevel,
    ResourceType,
)

quota = HierarchicalDRFQuota()

# Create hierarchy
await quota.add_entity("tenant1", HierarchyLevel.TENANT, "global", weight=2.0)
await quota.add_entity("team1", HierarchyLevel.TEAM, "tenant1", weight=1.0)
await quota.add_entity("project1", HierarchyLevel.PROJECT, "team1", weight=1.0)

# Allocate
result = await quota.request_allocation("project1", ResourceType.TASK, 10.0)
```

### 8. Brownout Error Budget

```python
from src.core.multi_agent.coordination.hierarchical_quota import (
    BrownoutErrorBudgetPolicy,
    BrownoutAction,
)

policy = BrownoutErrorBudgetPolicy()

await policy.initialize_budget("tenant1", total_budget=100.0)

# Exhaust budget
for _ in range(80):
    await policy.record_error("tenant1", error_weight=1.0)

# Check with brownouts
result = await policy.check_request("tenant1", priority=3)

print(f"Active brownouts: {result['brownouts']}")
# [REDUCE_QUALITY, REDUCE_DEPTH, ...]
```

**Brownout actions**:
- `REDUCE_QUALITY`: Lower embedding quality
- `REDUCE_DEPTH`: Reduce rerank depth
- `REDUCE_CONTEXT`: Reduce context size
- `INCREASE_LATENCY_TOLERANCE`: Allow higher latency
- `REJECT_NON_CRITICAL`: Reject low priority
- `RATE_LIMIT`: Apply rate limits

### 9. Chaos with Statistical Significance

```python
from src.core.multi_agent.coordination.enhanced_chaos_audit import (
    ChaosWithStatistics,
)

chaos = ChaosWithStatistics(
    deviation_threshold=0.2,
    confidence_level=0.95,
    min_sample_size=30,
)

# Set control group
control = await chaos.set_control_group()

# Run experiment
result = await chaos.run_experiment("latency-test", experiment_func)

print(f"Passed: {result.passed}")
print(f"Deviations: {result.deviations}")
print(f"Statistics: {result.statistics}")
```

### 10. Immutable Secrets Audit (WORM)

```python
from src.core.multi_agent.coordination.enhanced_chaos_audit import (
    ImmutableAuditLog,
    SecretAction,
)

audit = ImmutableAuditLog(retention_days=2555)  # ~7 years

# Append creates hash chain
entry = await audit.append(
    secret_name="api-key",
    accessed_by="service",
    action=SecretAction.READ,
    source_ip="10.0.0.1",
)

# Verify integrity
is_valid, errors = await audit.verify_chain()

# Get Merkle proof
proof = await audit.get_proof(start_sequence=1, end_sequence=100)
```

### 11. Dual Authorization Break-Glass

```python
from src.core.multi_agent.coordination.enhanced_governance import (
    DualAuthBreakGlass,
)

bg = DualAuthBreakGlass(
    required_approvals=2,
    activation_delay_seconds=300,  # 5 minute delay
    mfa_required=True,
)

# Create request
request_id = await bg.create_request(
    requester="admin@example.com",
    reason="Production incident",
)

# Approve (requires MFA)
await bg.approve_request(request_id, "approver1@example.com", mfa_token="123456")
await bg.approve_request(request_id, "approver2@example.com", mfa_token="654321")

# Token auto-activates after delay
```

### 12. DR Recovery Correctness Validation

```python
from src.core.multi_agent.coordination.enhanced_governance import (
    DRRecoveryValidator,
)

validator = DRRecoveryValidator()

result = await validator.validate_recovery(
    snapshot_id="backup-2024-01-01",
    checks=[
        "integrity_hash",
        "schema_compatibility",
        "referential_integrity",
        "data_freshness",
        "consistency_check",
        "semantic_replay",
    ]
)

print(f"Status: {result.status}")
print(f"Passed: {sum(result.checks.values())}/{len(result.checks)}")
```

### 13. Shared Resource Chargeback

```python
from src.core.multi_agent.coordination.enhanced_governance import (
    SharedResourceChargeback,
)

chargeback = SharedResourceChargeback()

await chargeback.register_shared_resource(
    resource_id="shared-cache",
    resource_type="cache",
    total_capacity=100.0,
    weights={"tenant1": 2.0, "tenant2": 1.0},
)

allocation = await chargeback.get_chargeback("shared-cache", total_cost=300.0)
# tenant1: 200.0, tenant2: 100.0
```

### 14. Policy Formal Verification

```python
from src.core.multi_agent.coordination.enhanced_governance import (
    PolicyFormalVerifier,
)

verifier = PolicyFormalVerifier()

await verifier.add_policy("policy1", {"action": "allow", "conditions": {...}})
await verifier.add_policy("policy2", {"action": "deny", "conditions": {...}})

result = await verifier.validate("policy1")

print(f"Valid: {result.is_valid}")
print(f"Conflicts: {result.conflicts}")
```

### 15. Human Governance Layer

```python
from src.core.multi_agent.coordination.enhanced_governance import (
    HumanGovernanceLayer,
)

governance = HumanGovernanceLayer()

workflow_id = await governance.create_workflow(
    workflow_type="policy_change",
    requester="engineer@example.com",
    required_approvals=2,
)

await governance.approve(workflow_id, "approver@example.com", comment="LGTM")
```

### 16. Behavioral Anomaly Detection

```python
from src.core.multi_agent.coordination.safety_formal import (
    BehavioralAnomalyDetector,
)

detector = BehavioralAnomalyDetector(
    drift_threshold=0.3,
    anomaly_threshold=0.7,
)

# Observe baseline
for _ in range(20):
    await detector.observe("agent1", {"latency": 100.0, "errors": 0.01})

# Detect anomaly
result = await detector.detect_anomaly("agent1", {"latency": 500.0, "errors": 0.5})

print(f"Anomalous: {result.is_anomalous}")
print(f"Trust score: {result.trust_score}")
```

### 17. Safety Provenance Chain

```python
from src.core.multi_agent.coordination.safety_formal import (
    SafetyProvenanceChain,
)

provenance = SafetyProvenanceChain()

node_id = await provenance.record_action(
    component="agent",
    action="decision",
    inputs=[],
    outputs={"result": "approved"},
)

await provenance.record_decision(
    decision_id="dec-123",
    agent_id="agent-1",
    reasoning="Policy allowed",
    policies_applied=["allow-policy"],
    model_version="v1.2.3",
    context={},
    outcome="approved",
    provenance_chain=[node_id],
)

# Explain decision
explanation = await provenance.explain_decision("dec-123")
```

### 18. Continuous Compliance Validation

```python
from src.core.multi_agent.coordination.safety_formal import (
    ContinuousComplianceValidator,
    ComplianceStandard,
)

validator = ContinuousComplianceValidator()

# SOC2 drift detection
violations = await validator.run_soc2_drift_detection(
    current_controls={"c1": True, "c2": False},
    baseline_controls={"c1": True, "c2": True},
)

# GDPR retention audit
violations = await validator.run_gdpr_retention_audit(
    data_records=[...],
    max_retention_days=365,
)
```

### 19. Policy Blast Radius Simulation

```python
from src.core.multi_agent.coordination.safety_formal import (
    PolicyBlastRadiusSimulator,
)

simulator = PolicyBlastRadiusSimulator()

await simulator.register_policy(
    "policy1",
    {"action": "allow"},
    ["entity1", "entity2", "entity3"],
)

result = await simulator.simulate_change(
    "policy1",
    {"action": "deny"},
)

print(f"Risk score: {result.risk_score}")
print(f"Recommendations: {result.recommendations}")
```

### 20. Formal Safety Invariants

```python
from src.core.multi_agent.coordination.safety_formal import (
    FormalSafetyInvariantVerifier,
    SafetyInvariant,
)

verifier = FormalSafetyInvariantVerifier()

state = {
    "tenant_data_access": {
        "accesses": [
            {"tenant_id": "tenant1", "resource": "data1"},
            {"tenant_id": "unauthorized", "resource": "data2"},
        ]
    },
    "authorized_tenants": {"tenant1", "tenant2"},
}

is_valid, violations = await verifier.verify_all(state)

# Or check specific invariant
is_valid, violation = await verifier.verify_specific(
    SafetyInvariant.NO_CROSS_TENANT_LEAK,
    state,
)
```

**Invariants**:
- `NoCrossTenantDataLeak`
- `NoPrivilegeEscalation`
- `NoUnsafeToolExecution`
- `NoDataExfiltration`
- `NoUnauthorizedAccess`

## Files

| Component | File |
|-----------|------|
| Enhanced Saga | `src/core/multi_agent/coordination/enhanced_saga.py` |
| Adaptive Circuit | `src/core/multi_agent/coordination/adaptive_circuit.py` |
| Scalable Rate Limiter | `src/core/multi_agent/coordination/scalable_rate_limiter.py` |
| Consistent Policy Cache | `src/core/multi_agent/coordination/consistent_policy_cache.py` |
| Enhanced Sandbox | `src/core/multi_agent/coordination/enhanced_sandbox.py` |
| Safe Injection | `src/core/multi_agent/coordination/safe_injection.py` |
| Hierarchical Quota | `src/core/multi_agent/coordination/hierarchical_quota.py` |
| Enhanced Chaos & Audit | `src/core/multi_agent/coordination/enhanced_chaos_audit.py` |
| Enhanced Governance | `src/core/multi_agent/coordination/enhanced_governance.py` |
| Safety Formal | `src/core/multi_agent/coordination/safety_formal.py` |
| Tests | `tests/phase5f/test_enhanced_reliability.py` |

## Done Criteria (v2 Final)

- [x] Saga: Semantic compensation + SideEffectClassification
- [x] Circuit Breaker: Adaptive ML-based error classification
- [x] Rate Limiter: Count-min sketch for 100k+ RPS
- [x] Policy Cache: Anti-entropy + Merkle consistency
- [x] Sandbox: Seccomp profiles + syscall filters + namespaces
- [x] Injection: Safe explanation (no pattern leakage)
- [x] Quota: Hierarchical DRF (multi-level)
- [x] Error Budget: Brownout + progressive degradation
- [x] Chaos: Statistical significance + control group
- [x] Secrets Audit: WORM + hash chain + tamper-evident
- [x] Break-Glass: Dual auth + time-delay + MFA
- [x] DR: Recovery correctness validation
- [x] Chargeback: Shared resource weighted attribution
- [x] Policy Verification: SAT + conflict detection
- [x] Human Governance: Audit committee + approval workflow
- [x] Behavioral Anomaly: Agent drift + trust scoring
- [x] Safety Provenance: Decision chain + traceability
- [x] Compliance: SOC2/ISO/GDPR drift detection
- [x] Policy Blast Radius: What-if simulation + dry-run
- [x] Formal Invariants: Safety invariant verification
