"""Coordination Module Deprecation Notice.

Date: 2026-05-23
Status: CLEANUP_IN_PROGRESS

============================================================================
COORDINATION MODULE SIMPLIFICATION PLAN
============================================================================

This file documents which modules should be deprecated/removed to reduce
cognitive overhead and improve maintainability.

============================================================================
MODULES TO REMOVE (NOT NEEDED AT CURRENT SCALE)
============================================================================

1. byzantine_protection.py
   - Reason: Overkill for single-digit agent counts
   - Replacement: Use circuit breaker + health checks
   - Priority: HIGH

2. saga_compensation.py  
   - Reason: Already covered by compensation.py in workflow
   - Replacement: workflow/compensation.py
   - Priority: HIGH

3. worm_archive.py
   - Reason: Not implemented, no clear use case
   - Replacement: None
   - Priority: MEDIUM

4. safety_formal.py
   - Reason: IEC 61508 is framework-level, not coordination-level
   - Replacement: infrastructure/safety/iec61508.py
   - Priority: MEDIUM

5. chaos_secrets.py
   - Reason: No clear purpose, confusing name
   - Replacement: None
   - Priority: MEDIUM

6. cdc_consistency.py
   - Reason: Complex CDC patterns not needed at current scale
   - Replacement: Event bus with streams
   - Priority: MEDIUM

7. injection_explainer.py
   - Reason: Duplicate of safe_injection.py
   - Replacement: safe_injection.py
   - Priority: MEDIUM

============================================================================
MODULES TO CONSOLIDATE
============================================================================

ENHANCED_* modules should be merged with base modules:
- enhanced_governance.py → governance.py
- enhanced_sandbox.py → Remove (not needed)
- enhanced_saga.py → saga_compensation.py → workflow/compensation.py
- enhanced_health.py → health.py
- enhanced_leader_election.py → leader_election.py
- enhanced_chaos_audit.py → Remove (chaos testing is separate)

============================================================================
CORE MODULES TO KEEP (ESSENTIAL)
============================================================================

Required at all scales:
- coordinator.py (main facade)
- types.py (shared types)
- config.py (configuration)
- circuit_breaker.py (failure isolation)
- health.py (health monitoring)
- backpressure.py (load protection)
- leader_election.py (HA)
- quota.py (resource limits)
- rate_limiter.py (rate limiting)
- batch_idempotency.py (idempotent processing)
- tenant_isolation.py (multi-tenancy)
- message_ordering.py (causal ordering)
- schema_evolution.py (API versioning)
- dead_letter_alert.py (DLQ alerting)

============================================================================
MODULE REDUCTION TARGET
============================================================================

Current: 50 modules
Target: 20-25 modules
Reduction: ~50%

============================================================================
ACTION ITEMS
============================================================================

1. Mark deprecated modules with DeprecationWarning
2. Update imports in coordinator.py
3. Update STRUCTURE_TREE.md
4. Run tests to verify no breakage
5. Remove deprecated modules

============================================================================
"""

# List of modules marked for deprecation (import will warn)
DEPRECATED_MODULES = {
    "byzantine_protection": {
        "reason": "Overkill for small agent counts",
        "替代": "circuit_breaker + health",
        "priority": "HIGH",
    },
    "saga_compensation": {
        "reason": "Duplicate of workflow/compensation",
        "替代": "workflow/compensation.py",
        "priority": "HIGH",
    },
    "worm_archive": {
        "reason": "Not implemented, no use case",
        "替代": "None",
        "priority": "MEDIUM",
    },
    "safety_formal": {
        "reason": "Wrong layer for safety concerns",
        "替代": "infrastructure/safety/iec61508.py",
        "priority": "MEDIUM",
    },
    "chaos_secrets": {
        "reason": "Confusing name, no clear purpose",
        "替代": "None",
        "priority": "MEDIUM",
    },
    "cdc_consistency": {
        "reason": "CDC patterns not needed at current scale",
        "替代": "Event bus with streams",
        "priority": "MEDIUM",
    },
    "injection_explainer": {
        "reason": "Duplicate of safe_injection.py",
        "替代": "safe_injection.py",
        "priority": "MEDIUM",
    },
}

# Modules to consolidate
CONSOLIDATION_MAP = {
    "enhanced_governance": "governance",
    "enhanced_sandbox": None,  # Remove
    "enhanced_saga": "saga_compensation",
    "enhanced_health": "health",
    "enhanced_leader_election": "leader_election",
    "enhanced_chaos_audit": None,  # Remove
}

# Essential modules (DO NOT REMOVE)
ESSENTIAL_MODULES = {
    "coordinator",
    "types",
    "config",
    "circuit_breaker",
    "health",
    "backpressure",
    "leader_election",
    "quota",
    "rate_limiter",
    "batch_idempotency",
    "tenant_isolation",
    "message_ordering",
    "schema_evolution",
    "dead_letter_alert",
    "governance",
    "deterministic_scheduler",
}


def get_module_status(module_name: str) -> dict:
    """Get deprecation status for a module."""
    if module_name in DEPRECATED_MODULES:
        return {"status": "DEPRECATED", **DEPRECATED_MODULES[module_name]}
    if module_name in CONSOLIDATION_MAP:
        target = CONSOLIDATION_MAP[module_name]
        if target:
            return {"status": "CONSOLIDATE", "into": target}
        return {"status": "REMOVE", "reason": "Not needed"}
    if module_name in ESSENTIAL_MODULES:
        return {"status": "KEEP"}
    return {"status": "UNKNOWN"}


if __name__ == "__main__":
    print("Coordination Module Status")
    print("=" * 50)
    
    for module, info in DEPRECATED_MODULES.items():
        print(f"[DEPRECATED] {module}")
        print(f"  Reason: {info['reason']}")
        print(f"  Replacement: {info['替代']}")
        print()
    
    print(f"Total to remove: {len(DEPRECATED_MODULES)}")
    print(f"Essential modules: {len(ESSENTIAL_MODULES)}")
