"""
Behavioral Anomaly Detection, Safety Provenance, Compliance Validation, and Formal Invariants.

Features:
- Behavioral anomaly models
- Agent drift detection
- Runtime trust scoring
- Safety provenance chain
- Decision traceability
- SOC2/ISO/GDPR drift detection
- Policy blast radius simulation
- Formal safety invariants
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import random
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ============== BEHAVIORAL ANOMALY DETECTION ==============

@dataclass
class AgentBehaviorProfile:
    """Behavior profile for an agent."""
    agent_id: str
    baseline_metrics: Dict[str, Any]
    trained_at: datetime
    sample_count: int
    is_trained: bool = False


@dataclass
class AnomalyDetectionResult:
    """Result of anomaly detection."""
    agent_id: str
    is_anomalous: bool
    anomaly_score: float  # 0-1
    deviation_factors: Dict[str, float]
    drift_detected: bool
    trust_score: float  # 0-1


class BehavioralAnomalyDetector:
    """
    Behavioral anomaly detection for agents.
    
    Features:
    - Behavior profiling
    - Drift detection
    - Runtime trust scoring
    - Statistical anomaly detection
    """
    
    def __init__(
        self,
        drift_threshold: float = 0.3,
        anomaly_threshold: float = 0.7,
        profile_window_samples: int = 100,
    ):
        self.drift_threshold = drift_threshold
        self.anomaly_threshold = anomaly_threshold
        self.profile_window = profile_window_samples
        
        # Agent profiles
        self._profiles: Dict[str, AgentBehaviorProfile] = {}
        
        # Recent observations
        self._observations: Dict[str, deque] = {}
        
        self._lock = asyncio.Lock()
    
    async def observe(
        self,
        agent_id: str,
        metrics: Dict[str, float],
    ) -> None:
        """Observe agent behavior."""
        async with self._lock:
            if agent_id not in self._observations:
                self._observations[agent_id] = deque(maxlen=self.profile_window)
            
            self._observations[agent_id].append(metrics)
    
    async def detect_anomaly(
        self,
        agent_id: str,
        current_metrics: Dict[str, float],
    ) -> AnomalyDetectionResult:
        """Detect behavioral anomaly."""
        async with self._lock:
            # Get or create profile
            profile = self._profiles.get(agent_id)
            
            if not profile or not profile.is_trained:
                # Create new profile
                profile = await self._create_profile(agent_id, current_metrics)
                self._profiles[agent_id] = profile
            
            # Calculate deviations
            deviations = self._calculate_deviations(profile, current_metrics)
            
            # Calculate anomaly score
            anomaly_score = sum(deviations.values()) / len(deviations) if deviations else 0.0
            
            # Detect drift
            drift = await self._detect_drift(agent_id)
            
            # Calculate trust score
            trust_score = self._calculate_trust_score(anomaly_score, drift)
            
            return AnomalyDetectionResult(
                agent_id=agent_id,
                is_anomalous=anomaly_score > self.anomaly_threshold,
                anomaly_score=anomaly_score,
                deviation_factors=deviations,
                drift_detected=drift,
                trust_score=trust_score,
            )
    
    async def _create_profile(
        self,
        agent_id: str,
        initial_metrics: Dict[str, float],
    ) -> AgentBehaviorProfile:
        """Create behavior profile."""
        # Collect samples for baseline
        observations = self._observations.get(agent_id, deque())
        
        if len(observations) < 10:
            # Not enough samples yet
            return AgentBehaviorProfile(
                agent_id=agent_id,
                baseline_metrics=initial_metrics,
                trained_at=datetime.now(),
                sample_count=len(observations),
                is_trained=False,
            )
        
        # Calculate baseline from observations
        baseline = {}
        for key in initial_metrics.keys():
            values = [obs.get(key, 0) for obs in observations if key in obs]
            if values:
                baseline[key] = sum(values) / len(values)
        
        return AgentBehaviorProfile(
            agent_id=agent_id,
            baseline_metrics=baseline,
            trained_at=datetime.now(),
            sample_count=len(observations),
            is_trained=True,
        )
    
    def _calculate_deviations(
        self,
        profile: AgentBehaviorProfile,
        current: Dict[str, float],
    ) -> Dict[str, float]:
        """Calculate metric deviations from baseline."""
        deviations = {}
        
        for key, value in current.items():
            baseline = profile.baseline_metrics.get(key, value)
            if baseline > 0:
                deviation = abs(value - baseline) / baseline
                deviations[key] = min(1.0, deviation)
        
        return deviations
    
    async def _detect_drift(self, agent_id: str) -> bool:
        """Detect if agent behavior has drifted."""
        observations = self._observations.get(agent_id, deque())
        
        if len(observations) < 20:
            return False
        
        # Compare recent observations with older ones
        recent = list(observations)[-10:]
        older = list(observations)[:10]
        
        # Calculate average deviation between periods
        deviations = []
        for key in recent[0].keys():
            recent_avg = sum(o.get(key, 0) for o in recent) / len(recent)
            older_avg = sum(o.get(key, 0) for o in older) / len(older)
            
            if older_avg > 0:
                dev = abs(recent_avg - older_avg) / older_avg
                deviations.append(dev)
        
        avg_deviation = sum(deviations) / len(deviations) if deviations else 0.0
        return avg_deviation > self.drift_threshold
    
    def _calculate_trust_score(
        self,
        anomaly_score: float,
        drift: bool,
    ) -> float:
        """Calculate runtime trust score."""
        score = 1.0
        
        # Reduce for anomalies
        score -= anomaly_score * 0.5
        
        # Reduce more for drift
        if drift:
            score -= 0.3
        
        return max(0.0, min(1.0, score))
    
    async def get_trust_scores(self) -> Dict[str, float]:
        """Get trust scores for all agents."""
        scores = {}
        for agent_id in self._profiles:
            observations = list(self._observations.get(agent_id, []))
            if observations:
                current = observations[-1]
                result = await self.detect_anomaly(agent_id, current)
                scores[agent_id] = result.trust_score
        return scores


# ============== SAFETY PROVENANCE CHAIN ==============

@dataclass
class ProvenanceNode:
    """Node in provenance chain."""
    node_id: str
    timestamp: datetime
    component: str  # "agent", "policy", "model"
    action: str
    inputs: List[str]  # Previous node IDs
    outputs: Dict[str, Any]
    metadata: Dict[str, Any]


@dataclass
class DecisionTrace:
    """Trace of a decision."""
    decision_id: str
    agent_id: str
    timestamp: datetime
    reasoning: str
    policies_applied: List[str]
    model_version: str
    context: Dict[str, Any]
    outcome: str
    provenance_chain: List[str]  # Node IDs


class SafetyProvenanceChain:
    """
    Safety provenance chain for decision traceability.
    
    Features:
    - Decision tracing
    - Policy attribution
    - Model version tracking
    - Why/how explanations
    """
    
    def __init__(self):
        self._nodes: Dict[str, ProvenanceNode] = {}
        self._decisions: Dict[str, DecisionTrace] = {}
        self._lock = asyncio.Lock()
    
    async def record_action(
        self,
        component: str,
        action: str,
        inputs: List[str],
        outputs: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record action in provenance chain."""
        async with self._lock:
            node_id = hashlib.sha256(
                f"{component}:{action}:{datetime.now().isoformat()}".encode()
            ).hexdigest()[:16]
            
            node = ProvenanceNode(
                node_id=node_id,
                timestamp=datetime.now(),
                component=component,
                action=action,
                inputs=inputs,
                outputs=outputs,
                metadata=metadata or {},
            )
            
            self._nodes[node_id] = node
            return node_id
    
    async def record_decision(
        self,
        decision_id: str,
        agent_id: str,
        reasoning: str,
        policies_applied: List[str],
        model_version: str,
        context: Dict[str, Any],
        outcome: str,
        provenance_chain: List[str],
    ) -> None:
        """Record decision trace."""
        async with self._lock:
            trace = DecisionTrace(
                decision_id=decision_id,
                agent_id=agent_id,
                timestamp=datetime.now(),
                reasoning=reasoning,
                policies_applied=policies_applied,
                model_version=model_version,
                context=context,
                outcome=outcome,
                provenance_chain=provenance_chain,
            )
            
            self._decisions[decision_id] = trace
    
    async def get_decision_trace(
        self,
        decision_id: str,
    ) -> Optional[DecisionTrace]:
        """Get decision trace."""
        return self._decisions.get(decision_id)
    
    async def get_provenance_chain(
        self,
        node_id: str,
    ) -> List[ProvenanceNode]:
        """Get full provenance chain for node."""
        chain = []
        visited = set()
        
        async def traverse(current_id: str):
            if current_id in visited:
                return
            visited.add(current_id)
            
            node = self._nodes.get(current_id)
            if node:
                chain.append(node)
                for input_id in node.inputs:
                    await traverse(input_id)
        
        await traverse(node_id)
        return chain
    
    async def explain_decision(
        self,
        decision_id: str,
    ) -> Dict[str, Any]:
        """Generate explanation for decision."""
        trace = self._decisions.get(decision_id)
        if not trace:
            return {}
        
        # Get provenance chain
        chain = []
        for node_id in trace.provenance_chain:
            node = self._nodes.get(node_id)
            if node:
                chain.append({
                    "component": node.component,
                    "action": node.action,
                    "timestamp": node.timestamp.isoformat(),
                })
        
        return {
            "decision_id": decision_id,
            "agent_id": trace.agent_id,
            "reasoning": trace.reasoning,
            "policies_applied": trace.policies_applied,
            "model_version": trace.model_version,
            "outcome": trace.outcome,
            "provenance_chain": chain,
        }


# ============== CONTINUOUS COMPLIANCE VALIDATION ==============

class ComplianceStandard(str, Enum):
    """Compliance standards."""
    SOC2 = "soc2"
    ISO27001 = "iso27001"
    GDPR = "gdpr"
    PCI_DSS = "pci_dss"
    HIPAA = "hipaa"


@dataclass
class ComplianceViolation:
    """Compliance violation."""
    standard: ComplianceStandard
    control: str
    description: str
    severity: str  # low, medium, high, critical
    detected_at: datetime


class ContinuousComplianceValidator:
    """
    Continuous compliance validation.
    
    Features:
    - SOC2 drift detection
    - ISO policy validation
    - GDPR retention audit
    - PCI segmentation checks
    """
    
    def __init__(self):
        self._violations: List[ComplianceViolation] = []
        self._last_audit: Optional[datetime] = None
        self._lock = asyncio.Lock()
    
    async def run_soc2_drift_detection(
        self,
        current_controls: Dict[str, Any],
        baseline_controls: Dict[str, Any],
    ) -> List[ComplianceViolation]:
        """Detect SOC2 control drift."""
        violations = []
        
        for control_id, current in current_controls.items():
            baseline = baseline_controls.get(control_id)
            
            if baseline is None:
                violations.append(ComplianceViolation(
                    standard=ComplianceStandard.SOC2,
                    control=control_id,
                    description="Control not in baseline",
                    severity="high",
                    detected_at=datetime.now(),
                ))
            
            elif current != baseline:
                violations.append(ComplianceViolation(
                    standard=ComplianceStandard.SOC2,
                    control=control_id,
                    description=f"Control value changed from {baseline} to {current}",
                    severity="medium",
                    detected_at=datetime.now(),
                ))
        
        async with self._lock:
            self._violations.extend(violations)
        
        return violations
    
    async def run_gdpr_retention_audit(
        self,
        data_records: List[Dict[str, Any]],
        max_retention_days: int = 365,
    ) -> List[ComplianceViolation]:
        """Audit GDPR data retention."""
        violations = []
        cutoff = datetime.now() - timedelta(days=max_retention_days)
        
        for record in data_records:
            created = record.get("created_at")
            if created and created < cutoff:
                violations.append(ComplianceViolation(
                    standard=ComplianceStandard.GDPR,
                    control="retention",
                    description=f"Record {record.get('id')} exceeds retention limit",
                    severity="high",
                    detected_at=datetime.now(),
                ))
        
        async with self._lock:
            self._violations.extend(violations)
        
        return violations
    
    async def run_pci_segmentation_check(
        self,
        network_segments: Dict[str, List[str]],
    ) -> List[ComplianceViolation]:
        """Check PCI cardholder data environment segmentation."""
        violations = []
        
        # Check for improper cardholder data access
        cardholder_segment = network_segments.get("cardholder_data_env", [])
        public_segment = network_segments.get("public", [])
        
        shared_ips = set(cardholder_segment) & set(public_segment)
        if shared_ips:
            violations.append(ComplianceViolation(
                standard=ComplianceStandard.PCI_DSS,
                control="segmentation",
                description=f"Cardholder data environment shares IPs with public: {shared_ips}",
                severity="critical",
                detected_at=datetime.now(),
            ))
        
        async with self._lock:
            self._violations.extend(violations)
        
        return violations
    
    async def get_compliance_status(
        self,
        standard: Optional[ComplianceStandard] = None,
    ) -> Dict[str, Any]:
        """Get compliance status."""
        async with self._lock:
            violations = self._violations
            
            if standard:
                violations = [v for v in violations if v.standard == standard]
            
            by_severity = {}
            for v in violations:
                by_severity[v.severity] = by_severity.get(v.severity, 0) + 1
            
            return {
                "standard": standard.value if standard else "all",
                "total_violations": len(violations),
                "by_severity": by_severity,
                "last_audit": self._last_audit.isoformat() if self._last_audit else None,
            }


# ============== POLICY BLAST RADIUS SIMULATION ==============

@dataclass
class BlastRadiusResult:
    """Result of blast radius simulation."""
    policy_change: Dict[str, Any]
    affected_entities: List[str]
    risk_score: float
    estimated_impact: Dict[str, Any]
    recommendations: List[str]


class PolicyBlastRadiusSimulator:
    """
    Policy blast radius simulation.
    
    Features:
    - What-if simulation
    - Policy dry-run mode
    - Blast radius estimation
    """
    
    def __init__(self):
        self._policy_rules: Dict[str, Dict[str, Any]] = {}
        self._entity_policies: Dict[str, List[str]] = {}  # entity -> policies
        self._lock = asyncio.Lock()
    
    async def register_policy(
        self,
        policy_id: str,
        policy: Dict[str, Any],
        affected_entities: List[str],
    ) -> None:
        """Register policy for simulation."""
        async with self._lock:
            self._policy_rules[policy_id] = policy
            
            for entity in affected_entities:
                if entity not in self._entity_policies:
                    self._entity_policies[entity] = []
                self._entity_policies[entity].append(policy_id)
    
    async def simulate_change(
        self,
        current_policy_id: str,
        new_policy: Dict[str, Any],
    ) -> BlastRadiusResult:
        """Simulate blast radius of policy change."""
        current_policy = self._policy_rules.get(current_policy_id, {})
        
        # Find affected entities
        affected = []
        for entity, policies in self._entity_policies.items():
            if current_policy_id in policies:
                affected.append(entity)
        
        # Calculate risk score
        risk_score = await self._calculate_risk_score(current_policy, new_policy, affected)
        
        # Estimate impact
        impact = await self._estimate_impact(new_policy, affected)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(risk_score, affected)
        
        return BlastRadiusResult(
            policy_change=new_policy,
            affected_entities=affected,
            risk_score=risk_score,
            estimated_impact=impact,
            recommendations=recommendations,
        )
    
    async def _calculate_risk_score(
        self,
        current: Dict[str, Any],
        new: Dict[str, Any],
        affected: List[str],
    ) -> float:
        """Calculate risk score for change."""
        risk = 0.0
        
        # Size of change
        change_keys = set(new.keys()) - set(current.keys())
        if change_keys:
            risk += 0.2
        
        # Scope of affected entities
        if len(affected) > 100:
            risk += 0.3
        elif len(affected) > 10:
            risk += 0.1
        
        # Action change (deny -> allow is higher risk)
        if current.get("action") != new.get("action"):
            risk += 0.3
        
        return min(1.0, risk)
    
    async def _estimate_impact(
        self,
        policy: Dict[str, Any],
        affected: List[str],
    ) -> Dict[str, Any]:
        """Estimate impact of policy change."""
        return {
            "affected_entities": len(affected),
            "action": policy.get("action"),
            "scope": policy.get("scope", "unknown"),
        }
    
    def _generate_recommendations(
        self,
        risk_score: float,
        affected: List[str],
    ) -> List[str]:
        """Generate recommendations based on risk."""
        recs = []
        
        if risk_score > 0.7:
            recs.append("HIGH RISK: Consider gradual rollout with canary")
            recs.append("Schedule change during maintenance window")
        
        if len(affected) > 10:
            recs.append("Large blast radius: Consider more targeted policy")
        
        if risk_score > 0.3:
            recs.append("Enable dry-run mode before full deployment")
            recs.append("Prepare rollback plan")
        
        return recs


# ============== FORMAL SAFETY INVARIANTS ==============

@dataclass
class InvariantViolation:
    """Safety invariant violation."""
    invariant: str
    description: str
    detected_at: datetime
    context: Dict[str, Any]


class SafetyInvariant(str, Enum):
    """Safety invariants."""
    NO_CROSS_TENANT_LEAK = "NoCrossTenantDataLeak"
    NO_PRIVILEGE_ESCALATION = "NoPrivilegeEscalation"
    NO_UNSAFE_TOOL_EXECUTION = "NoUnsafeToolExecution"
    NO_DATA_EXFILTRATION = "NoDataExfiltration"
    NO_UNAUTHORIZED_ACCESS = "NoUnauthorizedAccess"


class FormalSafetyInvariantVerifier:
    """
    Formal safety invariant verification.
    
    Invariants:
    - NoCrossTenantDataLeak
    - NoPrivilegeEscalation
    - NoUnsafeToolExecution
    - NoDataExfiltration
    - NoUnauthorizedAccess
    """
    
    def __init__(self):
        self._violations: List[InvariantViolation] = []
        self._lock = asyncio.Lock()
    
    async def verify_all(
        self,
        state: Dict[str, Any],
    ) -> Tuple[bool, List[InvariantViolation]]:
        """Verify all safety invariants."""
        all_violations = []
        
        # Check each invariant
        violations = await self._check_cross_tenant_leak(state)
        all_violations.extend(violations)
        
        violations = await self._check_privilege_escalation(state)
        all_violations.extend(violations)
        
        violations = await self._check_unsafe_tool_execution(state)
        all_violations.extend(violations)
        
        violations = await self._check_data_exfiltration(state)
        all_violations.extend(violations)
        
        violations = await self._check_unauthorized_access(state)
        all_violations.extend(violations)
        
        async with self._lock:
            self._violations.extend(all_violations)
        
        return len(all_violations) == 0, all_violations
    
    async def _check_cross_tenant_leak(
        self,
        state: Dict[str, Any],
    ) -> List[InvariantViolation]:
        """Verify NoCrossTenantDataLeak."""
        violations = []
        
        # Check for cross-tenant data access
        tenant_data = state.get("tenant_data_access", {})
        authorized_tenants = state.get("authorized_tenants", set())
        
        for access in tenant_data.get("accesses", []):
            accessed_tenant = access.get("tenant_id")
            
            if accessed_tenant not in authorized_tenants:
                violations.append(InvariantViolation(
                    invariant=SafetyInvariant.NO_CROSS_TENANT_LEAK.value,
                    description=f"Unauthorized tenant access: {accessed_tenant}",
                    detected_at=datetime.now(),
                    context=access,
                ))
        
        return violations
    
    async def _check_privilege_escalation(
        self,
        state: Dict[str, Any],
    ) -> List[InvariantViolation]:
        """Verify NoPrivilegeEscalation."""
        violations = []
        
        # Check for privilege escalation
        current_privileges = state.get("current_privileges", set())
        requested_privileges = state.get("requested_privileges", set())
        
        unauthorized_escalations = requested_privileges - current_privileges
        
        if unauthorized_escalations:
            violations.append(InvariantViolation(
                invariant=SafetyInvariant.NO_PRIVILEGE_ESCALATION.value,
                description=f"Unauthorized privilege escalation: {unauthorized_escalations}",
                detected_at=datetime.now(),
                context={"escalations": list(unauthorized_escalations)},
            ))
        
        return violations
    
    async def _check_unsafe_tool_execution(
        self,
        state: Dict[str, Any],
    ) -> List[InvariantViolation]:
        """Verify NoUnsafeToolExecution."""
        violations = []
        
        # Check for unsafe tool execution
        executed_tools = state.get("executed_tools", [])
        safe_tools = state.get("safe_tool_whitelist", set())
        
        for tool in executed_tools:
            if tool not in safe_tools:
                violations.append(InvariantViolation(
                    invariant=SafetyInvariant.NO_UNSAFE_TOOL_EXECUTION.value,
                    description=f"Unsafe tool execution: {tool}",
                    detected_at=datetime.now(),
                    context={"tool": tool},
                ))
        
        return violations
    
    async def _check_data_exfiltration(
        self,
        state: Dict[str, Any],
    ) -> List[InvariantViolation]:
        """Verify NoDataExfiltration."""
        violations = []
        
        # Check for data exfiltration
        egress_points = state.get("egress_points", [])
        allowed_egress = state.get("allowed_egress", set())
        
        for point in egress_points:
            if point not in allowed_egress:
                violations.append(InvariantViolation(
                    invariant=SafetyInvariant.NO_DATA_EXFILTRATION.value,
                    description=f"Unauthorized egress: {point}",
                    detected_at=datetime.now(),
                    context={"egress": point},
                ))
        
        return violations
    
    async def _check_unauthorized_access(
        self,
        state: Dict[str, Any],
    ) -> List[InvariantViolation]:
        """Verify NoUnauthorizedAccess."""
        violations = []
        
        # Check for unauthorized access attempts
        access_attempts = state.get("access_attempts", [])
        
        for attempt in access_attempts:
            if not attempt.get("authorized"):
                violations.append(InvariantViolation(
                    invariant=SafetyInvariant.NO_UNAUTHORIZED_ACCESS.value,
                    description=f"Unauthorized access: {attempt.get('resource')}",
                    detected_at=datetime.now(),
                    context=attempt,
                ))
        
        return violations
    
    async def get_violations(
        self,
        since: Optional[datetime] = None,
    ) -> List[InvariantViolation]:
        """Get violations since timestamp."""
        async with self._lock:
            if since:
                return [v for v in self._violations if v.detected_at >= since]
            return self._violations.copy()
    
    async def verify_specific(
        self,
        invariant: SafetyInvariant,
        state: Dict[str, Any],
    ) -> Tuple[bool, Optional[InvariantViolation]]:
        """Verify specific invariant."""
        if invariant == SafetyInvariant.NO_CROSS_TENANT_LEAK:
            violations = await self._check_cross_tenant_leak(state)
        elif invariant == SafetyInvariant.NO_PRIVILEGE_ESCALATION:
            violations = await self._check_privilege_escalation(state)
        elif invariant == SafetyInvariant.NO_UNSAFE_TOOL_EXECUTION:
            violations = await self._check_unsafe_tool_execution(state)
        elif invariant == SafetyInvariant.NO_DATA_EXFILTRATION:
            violations = await self._check_data_exfiltration(state)
        elif invariant == SafetyInvariant.NO_UNAUTHORIZED_ACCESS:
            violations = await self._check_unauthorized_access(state)
        else:
            return True, None
        
        is_valid = len(violations) == 0
        return is_valid, violations[0] if violations else None
