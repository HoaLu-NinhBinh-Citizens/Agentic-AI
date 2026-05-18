"""
Byzantine Agent Protection.

Provides:
- Message signature and verification
- Agent attestation
- Behavior anomaly detection
- Protocol violation detection
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ThreatLevel(str, Enum):
    """Threat level classification."""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ViolationType(str, Enum):
    """Types of protocol violations."""
    INVALID_SIGNATURE = "invalid_signature"
    TIMESTAMP_DRIFT = "timestamp_drift"
    RATE_EXCEEDED = "rate_exceeded"
    MALFORMED_MESSAGE = "malformed_message"
    POLICY_VIOLATION = "policy_violation"
    ANOMALY_DETECTED = "anomaly_detected"
    COMPROMISED = "compromised"


@dataclass
class SignedMessage:
    """Message with cryptographic signature."""
    message_id: str
    sender: str
    content: Dict[str, Any]
    signature: str
    timestamp: float
    sequence: int
    nonce: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentAttestation:
    """Agent attestation record."""
    agent_id: str
    public_key: str
    timestamp: datetime
    capabilities: List[str]
    policy_version: str
    signature: str
    expires_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at


@dataclass
class Violation:
    """Protocol violation record."""
    violation_id: str
    agent_id: str
    violation_type: ViolationType
    threat_level: ThreatLevel
    details: str
    timestamp: datetime
    evidence: Dict[str, Any] = field(default_factory=dict)


class MessageSigner:
    """
    Signs and verifies messages.
    
    Uses HMAC for message authentication.
    Production would use Ed25519 or RSA.
    """
    
    def __init__(self, secret_key: bytes):
        self.secret_key = secret_key
    
    def sign(self, data: Dict[str, Any]) -> str:
        """Sign a message."""
        # Create deterministic representation
        canonical = self._canonicalize(data)
        signature = hmac.new(
            self.secret_key,
            canonical.encode(),
            hashlib.sha256,
        ).hexdigest()
        return signature
    
    def verify(self, data: Dict[str, Any], signature: str) -> bool:
        """Verify a message signature."""
        expected = self.sign(data)
        return hmac.compare_digest(expected, signature)
    
    def _canonicalize(self, data: Dict[str, Any]) -> str:
        """Create canonical string representation."""
        items = sorted(data.items())
        parts = []
        for k, v in items:
            if k == "signature":
                continue
            if isinstance(v, dict):
                v = self._canonicalize(v)
            parts.append(f"{k}:{v}")
        return "|".join(parts)


class AnomalyDetector:
    """
    Detects anomalous behavior patterns.
    
    Tracks:
    - Message rate
    - Response time
    - Error rate
    - Resource usage
    - Behavioral patterns
    """
    
    def __init__(
        self,
        baseline_rate: float = 10.0,
        baseline_latency_ms: float = 100.0,
        baseline_error_rate: float = 0.01,
        detection_threshold: float = 3.0,  # Standard deviations
    ):
        self.baseline_rate = baseline_rate
        self.baseline_latency = baseline_latency_ms
        self.baseline_error_rate = baseline_error_rate
        self.detection_threshold = detection_threshold
        
        self._agent_metrics: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: {
                "rates": [],
                "latencies": [],
                "errors": [],
            }
        )
        self._violations: Dict[str, List[Violation]] = defaultdict(list)
        self._last_check: Dict[str, float] = {}
    
    def record_metric(
        self,
        agent_id: str,
        metric_type: str,
        value: float,
    ) -> None:
        """Record a metric for an agent."""
        self._agent_metrics[agent_id][metric_type].append(value)
        
        # Keep only recent values (last 100)
        if len(self._agent_metrics[agent_id][metric_type]) > 100:
            self._agent_metrics[agent_id][metric_type] = \
                self._agent_metrics[agent_id][metric_type][-100:]
    
    def detect_anomalies(self, agent_id: str) -> List[Violation]:
        """Detect anomalies for an agent."""
        violations = []
        metrics = self._agent_metrics.get(agent_id)
        
        if not metrics:
            return violations
        
        now = time.time()
        last_check = self._last_check.get(agent_id, now)
        elapsed = now - last_check
        self._last_check[agent_id] = now
        
        # Check message rate
        if metrics["rates"]:
            avg_rate = sum(metrics["rates"]) / len(metrics["rates"])
            std_rate = self._std(metrics["rates"])
            current_rate = len(metrics["rates"]) / max(1, elapsed)
            
            if std_rate > 0 and abs(current_rate - avg_rate) > self.detection_threshold * std_rate:
                violations.append(Violation(
                    violation_id=f"{agent_id}:rate:{now}",
                    agent_id=agent_id,
                    violation_type=ViolationType.RATE_EXCEEDED,
                    threat_level=ThreatLevel.MEDIUM,
                    details=f"Rate anomaly: current={current_rate:.1f}, baseline={avg_rate:.1f}",
                    timestamp=datetime.now(),
                    evidence={"current_rate": current_rate, "baseline": avg_rate},
                ))
        
        # Check error rate
        if metrics["errors"]:
            error_rate = sum(metrics["errors"]) / len(metrics["errors"])
            if error_rate > self.baseline_error_rate * 10:
                violations.append(Violation(
                    violation_id=f"{agent_id}:error:{now}",
                    agent_id=agent_id,
                    violation_type=ViolationType.ANOMALY_DETECTED,
                    threat_level=ThreatLevel.HIGH,
                    details=f"High error rate: {error_rate:.2%}",
                    timestamp=datetime.now(),
                    evidence={"error_rate": error_rate},
                ))
        
        self._violations[agent_id].extend(violations)
        return violations
    
    def _std(self, values: List[float]) -> float:
        """Calculate standard deviation."""
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5


class ByzantineProtection:
    """
    Byzantine fault tolerance for multi-agent coordination.
    
    Features:
    - Message signature verification
    - Agent attestation
    - Anomaly detection
    - Policy enforcement
    - Quarantine management
    """
    
    def __init__(
        self,
        secret_key: bytes,
        attestation_ttl_seconds: float = 3600,
        max_violations_before_quarantine: int = 10,
        quarantine_duration_seconds: float = 300,
    ):
        self.secret_key = secret_key
        self.attestation_ttl = attestation_ttl_seconds
        self.max_violations = max_violations_before_quarantine
        self.quarantine_duration = quarantine_duration_seconds
        
        self.signer = MessageSigner(secret_key)
        self.anomaly_detector = AnomalyDetector()
        
        self._attestations: Dict[str, AgentAttestation] = {}
        self._quarantined_agents: Set[str] = set()
        self._quarantine_expiry: Dict[str, datetime] = {}
        self._violation_counts: Dict[str, int] = defaultdict(int)
        self._policy_violations: Dict[str, List[Violation]] = defaultdict(list)
        self._lock = asyncio.Lock()
        
        # Callbacks
        self._quarantine_callbacks: List[Callable[[str, bool], None]] = []
    
    def register_quarantine_callback(
        self,
        callback: Callable[[str, bool], None],
    ) -> None:
        """Register callback for quarantine events."""
        self._quarantine_callbacks.append(callback)
    
    async def attest_agent(
        self,
        agent_id: str,
        public_key: str,
        capabilities: List[str],
        policy_version: str,
    ) -> AgentAttestation:
        """Create attestation for an agent."""
        now = datetime.now()
        
        attestation_data = {
            "agent_id": agent_id,
            "public_key": public_key,
            "capabilities": capabilities,
            "policy_version": policy_version,
            "timestamp": now.isoformat(),
        }
        
        signature = self.signer.sign(attestation_data)
        
        attestation = AgentAttestation(
            agent_id=agent_id,
            public_key=public_key,
            timestamp=now,
            capabilities=capabilities,
            policy_version=policy_version,
            signature=signature,
            expires_at=now + timedelta(seconds=self.attestation_ttl),
        )
        
        async with self._lock:
            self._attestations[agent_id] = attestation
        
        logger.info(f"Attested agent: {agent_id}")
        return attestation
    
    async def verify_attestation(self, agent_id: str) -> bool:
        """Verify an agent's attestation."""
        async with self._lock:
            attestation = self._attestations.get(agent_id)
        
        if not attestation:
            return False
        
        if attestation.is_expired():
            return False
        
        # Verify signature
        data = {
            "agent_id": attestation.agent_id,
            "public_key": attestation.public_key,
            "capabilities": attestation.capabilities,
            "policy_version": attestation.policy_version,
            "timestamp": attestation.timestamp.isoformat(),
        }
        
        return self.signer.verify(data, attestation.signature)
    
    async def sign_message(
        self,
        message_id: str,
        sender: str,
        content: Dict[str, Any],
        sequence: int,
    ) -> SignedMessage:
        """Sign a message."""
        import secrets
        
        data = {
            "message_id": message_id,
            "sender": sender,
            "content": content,
            "sequence": sequence,
            "timestamp": time.time(),
        }
        
        signature = self.signer.sign(data)
        
        return SignedMessage(
            message_id=message_id,
            sender=sender,
            content=content,
            signature=signature,
            timestamp=data["timestamp"],
            sequence=sequence,
            nonce=secrets.token_hex(16),
        )
    
    async def verify_message(self, signed: SignedMessage) -> bool:
        """
        Verify a signed message.
        
        Checks:
        - Signature validity
        - Timestamp freshness
        - Agent not quarantined
        """
        # Check quarantine
        if signed.sender in self._quarantined_agents:
            logger.warning(f"Message from quarantined agent: {signed.sender}")
            return False
        
        # Check timestamp freshness
        age = time.time() - signed.timestamp
        if age > 300:  # 5 minutes
            logger.warning(f"Stale message from {signed.sender}: age={age}s")
            return False
        
        # Check attestation
        if not await self.verify_attestation(signed.sender):
            logger.warning(f"Unverified agent: {signed.sender}")
            # Not critical, just log
        
        # Verify signature
        data = {
            "message_id": signed.message_id,
            "sender": signed.sender,
            "content": signed.content,
            "sequence": signed.sequence,
            "timestamp": signed.timestamp,
        }
        
        return self.signer.verify(data, signed.signature)
    
    async def record_violation(self, violation: Violation) -> None:
        """Record a protocol violation."""
        async with self._lock:
            self._violation_counts[violation.agent_id] += 1
            
            if violation.agent_id not in self._policy_violations:
                self._policy_violations[violation.agent_id] = []
            self._policy_violations[violation.agent_id].append(violation)
        
        # Record in anomaly detector
        if violation.violation_type == ViolationType.RATE_EXCEEDED:
            self.anomaly_detector.record_metric(
                violation.agent_id, "rate", 1.0
            )
        elif violation.violation_type == ViolationType.ANOMALY_DETECTED:
            self.anomaly_detector.record_metric(
                violation.agent_id, "errors", 1.0
            )
        
        # Check quarantine threshold
        count = self._violation_counts[violation.agent_id]
        if count >= self.max_violations:
            await self.quarantine_agent(violation.agent_id, "violation_threshold")
    
    async def quarantine_agent(
        self,
        agent_id: str,
        reason: str,
    ) -> bool:
        """Quarantine an agent."""
        async with self._lock:
            if agent_id in self._quarantined_agents:
                return False
            
            self._quarantined_agents.add(agent_id)
            self._quarantine_expiry[agent_id] = datetime.now() + timedelta(
                seconds=self.quarantine_duration
            )
        
        logger.warning(f"Quarantined agent {agent_id}: {reason}")
        
        # Notify callbacks
        for callback in self._quarantine_callbacks:
            try:
                callback(agent_id, True)
            except Exception as e:
                logger.error(f"Quarantine callback failed: {e}")
        
        return True
    
    async def release_quarantine(self, agent_id: str) -> bool:
        """Release an agent from quarantine."""
        async with self._lock:
            if agent_id not in self._quarantined_agents:
                return False
            
            self._quarantined_agents.discard(agent_id)
            self._quarantine_expiry.pop(agent_id, None)
            self._violation_counts[agent_id] = 0
        
        logger.info(f"Released agent from quarantine: {agent_id}")
        
        # Notify callbacks
        for callback in self._quarantine_callbacks:
            try:
                callback(agent_id, False)
            except Exception as e:
                logger.error(f"Release callback failed: {e}")
        
        return True
    
    async def check_quarantine_expiry(self) -> List[str]:
        """Check and release expired quarantines."""
        now = datetime.now()
        released = []
        
        async with self._lock:
            expired = [
                agent_id for agent_id, expiry in self._quarantine_expiry.items()
                if now > expiry
            ]
            
            for agent_id in expired:
                self._quarantined_agents.discard(agent_id)
                self._quarantine_expiry.pop(agent_id, None)
                self._violation_counts[agent_id] = 0
                released.append(agent_id)
        
        for agent_id in released:
            logger.info(f"Auto-released from quarantine: {agent_id}")
            for callback in self._quarantine_callbacks:
                try:
                    callback(agent_id, False)
                except Exception as e:
                    logger.error(f"Release callback failed: {e}")
        
        return released
    
    async def is_quarantined(self, agent_id: str) -> bool:
        """Check if agent is quarantined."""
        async with self._lock:
            if agent_id not in self._quarantined_agents:
                return False
            
            # Check expiry
            expiry = self._quarantine_expiry.get(agent_id)
            if expiry and datetime.now() > expiry:
                # Auto-release
                self._quarantined_agents.discard(agent_id)
                self._quarantine_expiry.pop(agent_id, None)
                return False
            
            return True
    
    async def enforce_policy(
        self,
        agent_id: str,
        action: str,
        policy: Dict[str, Any],
    ) -> bool:
        """Enforce a policy on an agent action."""
        # Check quarantine
        if await self.is_quarantined(agent_id):
            violation = Violation(
                violation_id=f"{agent_id}:policy:{time.time()}",
                agent_id=agent_id,
                violation_type=ViolationType.POLICY_VIOLATION,
                threat_level=ThreatLevel.HIGH,
                details=f"Action from quarantined agent: {action}",
                timestamp=datetime.now(),
            )
            await self.record_violation(violation)
            return False
        
        # Check attestation
        if not await self.verify_attestation(agent_id):
            # Soft check - just warn
            logger.warning(f"Unattested action from {agent_id}: {action}")
        
        # Check rate limits from policy
        rate_limit = policy.get("max_rate", float("inf"))
        # Would implement rate limiting here
        
        return True
    
    def get_agent_status(self, agent_id: str) -> Dict[str, Any]:
        """Get protection status for an agent."""
        return {
            "agent_id": agent_id,
            "quarantined": agent_id in self._quarantined_agents,
            "quarantine_expiry": self._quarantine_expiry.get(agent_id).isoformat()
                if agent_id in self._quarantine_expiry else None,
            "violation_count": self._violation_counts.get(agent_id, 0),
            "violations": [
                v.details for v in self._policy_violations.get(agent_id, [])[-5:]
            ],
            "attested": agent_id in self._attestations,
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get protection metrics."""
        return {
            "total_attestations": len(self._attestations),
            "quarantined_agents": len(self._quarantined_agents),
            "total_violations": sum(self._violation_counts.values()),
            "active_violations": len([
                v for violations in self._policy_violations.values()
                for v in violations if (datetime.now() - v.timestamp).total_seconds() < 3600
            ]),
        }
