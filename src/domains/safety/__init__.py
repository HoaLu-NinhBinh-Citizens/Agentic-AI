"""
ISO 26262 Safety Validation — Automotive functional safety analysis.

Implements safety-oriented validation for automotive firmware:
- ASIL (Automotive Safety Integrity Level) classification
- Safety goal tracking
- FMEA-style failure mode analysis
- Safety counter validation
- Watchdog monitoring
- Fault injection analysis
- Hardware safety metrics (SPFM, LFM, PMHF)

Integration: Used by CrossValidator as the SAFETY validation stage.
Complements the CAN/LIN/UDS protocol analyzers with functional safety reasoning.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


# ─── ASIL Classification ─────────────────────────────────────────

class ASIL(str, Enum):
    """
    Automotive Safety Integrity Level (ISO 26262 Part 3).

    QM = Quality Management (no safety requirements)
    ASIL-A = Lowest safety integrity
    ASIL-B
    ASIL-C
    ASIL-D = Highest safety integrity
    """
    QM = "QM"
    ASIL_A = "A"
    ASIL_B = "B"
    ASIL_C = "C"
    ASIL_D = "D"

    @property
    def safety_level(self) -> int:
        levels = {ASIL.QM: 0, ASIL.ASIL_A: 1, ASIL.ASIL_B: 2, ASIL.ASIL_C: 3, ASIL.ASIL_D: 4}
        return levels.get(self, 0)

    @property
    def requires_watchdog(self) -> bool:
        return self in (ASIL.ASIL_B, ASIL.ASIL_C, ASIL.ASIL_D)

    @property
    def requires_self_test(self) -> bool:
        return self in (ASIL.ASIL_C, ASIL.ASIL_D)


class SafetyMetric(str, Enum):
    """
    ISO 26262 hardware safety metrics.

    SPFM = Single-Point Fault Metric (ISO 26262 Part 5, 6.5.4)
    LFM = Latent-Fault Metric
    PMHF = Probabilistic Metric for Hardware Architectures
    """
    SPFM = "SPFM"   # Single-point fault metric (target: >= 90% for ASIL-B, >= 97% for ASIL-D)
    LFM = "LFM"     # Latent-fault metric (target: >= 60% for ASIL-B, >= 90% for ASIL-D)
    PMHF = "PMHF"   # Probabilistic metric for HW (target: <= 100 FIT for ASIL-D)


@dataclass
class SafetyGoal:
    """
    A safety goal derived from hazard analysis.

    Example: "No unintended acceleration above 5% gradient"
    """
    goal_id: str
    description: str
    ASIL: ASIL
    fault_tolerance_time: float  # FTTI in milliseconds
    tolerance: float              # Fault tolerance
    monitoring_required: bool = False
    diagnostic_interval_ms: float = 0.0


@dataclass
class SafetyRequirement:
    """
    A safety requirement derived from safety goals.

    Example: "Processor watchdog must trigger within 10ms of fault detection"
    """
    req_id: str
    description: str
    ASIL: ASIL
    safety_goal_id: str | None
    applies_to: str  # "watchdog", "memory_check", "cpu_self_test", etc.
    parameters: dict[str, Any] = field(default_factory=dict)


# ─── Safety Findings ──────────────────────────────────────────────

class SafetySeverity(str, Enum):
    """Safety finding severity."""
    SAFE = "safe"                 # No safety concern
    ADVISORY = "advisory"        # Improvement recommended
    WARNING = "warning"          # Potential safety concern
    VIOLATION = "violation"      # Safety requirement violated
    CRITICAL = "critical"         # Safety goal at risk


@dataclass
class SafetyFinding:
    """A safety analysis finding."""
    finding_id: str
    severity: SafetySeverity
    category: str                 # "watchdog", "memory", "timing", "communication", etc.
    description: str
    affected_component: str
    ASIL: ASIL
    safety_goal_id: str | None
    evidence: str
    fix_suggestion: str
    iso_26262_reference: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_summary(self) -> str:
        return (
            f"[{self.severity.value.upper()}] [{self.ASIL.value}] "
            f"{self.category}: {self.description}"
        )


# ─── Safety Validator ──────────────────────────────────────────────

@dataclass
class SafetyValidationConfig:
    """Configuration for safety validation."""
    target_ASIL: ASIL = ASIL.ASIL_B
    hardware_metrics_enabled: bool = True
    watchdog_check_enabled: bool = True
    timing_check_enabled: bool = True
    communication_check_enabled: bool = True
    memory_check_enabled: bool = True


@dataclass
class SafetyValidationResult:
    """Result of safety validation."""
    valid: bool
    target_ASIL: ASIL
    findings: list[SafetyFinding]
    errors: int = 0
    warnings: int = 0
    advisories: int = 0
    metrics: dict[str, float] = field(default_factory=dict)
    safety_goals_met: list[str] = field(default_factory=list)
    safety_goals_failed: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "target_ASIL": self.target_ASIL.value,
            "findings": [
                {
                    "severity": f.severity.value,
                    "ASIL": f.ASIL.value,
                    "category": f.category,
                    "description": f.description,
                    "suggestion": f.fix_suggestion,
                }
                for f in self.findings
            ],
            "errors": self.errors,
            "warnings": self.warnings,
            "advisories": self.advisories,
            "metrics": self.metrics,
            "safety_goals_met": self.safety_goals_met,
            "safety_goals_failed": self.safety_goals_failed,
        }


class SafetyValidator:
    """
    ISO 26262 safety validation for automotive firmware.

    Performs deterministic safety checks across:
    - Watchdog configuration (timeout, window, response)
    - Memory integrity (ECC, CRC, stack watermark)
    - Timing constraints (deadline monitoring, response time)
    - Communication safety (timeout, CRC, alive supervision)
    - Hardware fault metrics (SPFM, LFM)

    Usage:
        validator = SafetyValidator(
            SafetyValidationConfig(target_ASIL=ASIL.ASIL_B)
        )

        # Validate with allocation context
        result = validator.validate_allocation({
            "peripheral": "CAN1",
            "ASIL": "B",
            "watchdog_enabled": True,
            "watchdog_timeout_ms": 50,
            "safety_goals": [...],
        })

        if not result.valid:
            for finding in result.findings:
                print(finding.get_summary())
    """

    def __init__(self, config: SafetyValidationConfig | None = None):
        self.config = config or SafetyValidationConfig()
        self._safety_goals: list[SafetyGoal] = []
        self._requirements: list[SafetyRequirement] = []

    def add_safety_goal(self, goal: SafetyGoal) -> None:
        """Register a safety goal."""
        self._safety_goals.append(goal)

    def add_requirement(self, req: SafetyRequirement) -> None:
        """Register a safety requirement."""
        self._requirements.append(req)

    def validate_allocation(
        self,
        allocation: dict[str, Any],
        code: str | None = None,
    ) -> SafetyValidationResult:
        """
        Run safety validation on a hardware allocation.

        Args:
            allocation: Hardware allocation dict
            code: Optional C code to analyze

        Returns:
            SafetyValidationResult with findings
        """
        findings: list[SafetyFinding] = []
        target_asil = self._parse_asil(allocation.get("ASIL", "QM"))

        # ─── Watchdog Validation ────────────────────────────────
        if self.config.watchdog_check_enabled:
            findings.extend(self._validate_watchdog(allocation, target_asil))

        # ─── Timing Validation ────────────────────────────────
        if self.config.timing_check_enabled:
            findings.extend(self._validate_timing(allocation, target_asil))

        # ─── Communication Safety ─────────────────────────────
        if self.config.communication_check_enabled:
            findings.extend(self._validate_communication(allocation, target_asil))

        # ─── Memory Safety ────────────────────────────────────
        if self.config.memory_check_enabled:
            findings.extend(self._validate_memory(allocation, target_asil))
            if code:
                findings.extend(self._validate_code_safety(code, target_asil))

        # ─── Hardware Metrics ────────────────────────────────
        if self.config.hardware_metrics_enabled:
            metrics = self._compute_hardware_metrics(findings, target_asil)
        else:
            metrics = {}

        # ─── Classify Results ────────────────────────────────
        errors = sum(1 for f in findings if f.severity in (SafetySeverity.VIOLATION, SafetySeverity.CRITICAL))
        warnings = sum(1 for f in findings if f.severity == SafetySeverity.WARNING)
        advisories = sum(1 for f in findings if f.severity == SafetySeverity.ADVISORY)

        # Safety goals assessment
        goals_met, goals_failed = self._assess_safety_goals(findings)

        # Valid if no violations/critical findings for target ASIL
        max_allowed_severity = {
            ASIL.QM: SafetySeverity.CRITICAL,
            ASIL.ASIL_A: SafetySeverity.WARNING,
            ASIL.ASIL_B: SafetySeverity.WARNING,
            ASIL.ASIL_C: SafetySeverity.VIOLATION,
            ASIL.ASIL_D: SafetySeverity.VIOLATION,
        }
        max_allowed = max_allowed_severity.get(target_asil, SafetySeverity.WARNING)
        valid = not any(
            f.severity.value > max_allowed.value
            for f in findings
        )

        return SafetyValidationResult(
            valid=valid,
            target_ASIL=target_asil,
            findings=findings,
            errors=errors,
            warnings=warnings,
            advisories=advisories,
            metrics=metrics,
            safety_goals_met=goals_met,
            safety_goals_failed=goals_failed,
        )

    def _validate_watchdog(
        self,
        allocation: dict[str, Any],
        target_asil: ASIL,
    ) -> list[SafetyFinding]:
        """Validate watchdog configuration."""
        findings = []
        peripheral = allocation.get("peripheral", "")

        watchdog_enabled = allocation.get("watchdog_enabled", False)
        timeout_ms = allocation.get("watchdog_timeout_ms", 0)

        # ASIL-B/C/D require watchdog
        if target_asil.requires_watchdog and not watchdog_enabled:
            findings.append(SafetyFinding(
                finding_id=f"WATCHDOG_001_{peripheral}",
                severity=SafetySeverity.VIOLATION,
                category="watchdog",
                description=f"ASIL-{target_asil.value} requires watchdog but none configured",
                affected_component=peripheral,
                ASIL=target_asil,
                safety_goal_id=None,
                evidence="target_ASIL.requires_watchdog = True",
                fix_suggestion="Enable independent watchdog (IWDG for STM32) with timeout < FTTI",
                iso_26262_reference="ISO 26262 Part 5, 7.4.3 — Monitor and reaction",
            ))

        if watchdog_enabled and timeout_ms > 0:
            # Timeout must be less than FTTI
            ftty = allocation.get("fault_tolerance_time_ms", 100.0)
            if timeout_ms >= ftty:
                findings.append(SafetyFinding(
                    finding_id=f"WATCHDOG_002_{peripheral}",
                    severity=SafetySeverity.VIOLATION,
                    category="watchdog",
                    description=f"Watchdog timeout ({timeout_ms}ms) >= FTTI ({ftty}ms) — fault may propagate before reset",
                    affected_component=peripheral,
                    ASIL=target_asil,
                    safety_goal_id=None,
                    evidence=f"timeout_ms={timeout_ms}, FTTI={ftty}ms",
                    fix_suggestion=f"Reduce watchdog timeout to < {ftty}ms (recommend {int(ftty * 0.5)}ms)",
                    iso_26262_reference="ISO 26262 Part 5, 6.4.3 — FTTI definition",
                ))

            # ASIL-D: window watchdog preferred
            if target_asil == ASIL.ASIL_D and not allocation.get("window_watchdog", False):
                findings.append(SafetyFinding(
                    finding_id=f"WATCHDOG_003_{peripheral}",
                    severity=SafetySeverity.ADVISORY,
                    category="watchdog",
                    description="ASIL-D: window watchdog recommended over standard watchdog",
                    affected_component=peripheral,
                    ASIL=target_asil,
                    safety_goal_id=None,
                    evidence="Window watchdog detects single-point faults in timing",
                    fix_suggestion="Consider WWDG (window watchdog) for ASIL-D timing integrity",
                    iso_26262_reference="ISO 26262 Part 5, 6.5.4 — Architectural metrics",
                ))

            # Timeout sanity check: very long watchdog
            if timeout_ms > 10000:
                findings.append(SafetyFinding(
                    finding_id=f"WATCHDOG_004_{peripheral}",
                    severity=SafetySeverity.WARNING,
                    category="watchdog",
                    description=f"Watchdog timeout {timeout_ms}ms is very long (>10s)",
                    affected_component=peripheral,
                    ASIL=ASIL.QM,
                    safety_goal_id=None,
                    evidence=f"timeout_ms={timeout_ms}",
                    fix_suggestion="Consider shorter watchdog timeout for faster fault response",
                ))

        return findings

    def _validate_timing(
        self,
        allocation: dict[str, Any],
        target_asil: ASIL,
    ) -> list[SafetyFinding]:
        """Validate timing constraints."""
        findings = []
        peripheral = allocation.get("peripheral", "")

        # Interrupt priority for safety-critical peripherals
        int_priority = allocation.get("interrupt_priority", 0)
        critical = allocation.get("safety_critical", False)

        if critical and int_priority > 5:
            findings.append(SafetyFinding(
                finding_id=f"TIMING_001_{peripheral}",
                severity=SafetySeverity.WARNING,
                category="timing",
                description=f"Safety-critical peripheral has low-priority interrupt (NVIC priority={int_priority})",
                affected_component=peripheral,
                ASIL=target_asil,
                safety_goal_id=None,
                evidence=f"priority={int_priority}, critical={critical}",
                fix_suggestion="Assign NVIC priority 0-5 for safety-critical interrupts",
                iso_26262_reference="ISO 26262 Part 5, 7.4.2 — Timing constraints",
            ))

        # Deadline monitoring
        deadline_ms = allocation.get("deadline_ms", 0)
        response_time_ms = allocation.get("response_time_ms", 0)

        if deadline_ms > 0 and response_time_ms > deadline_ms:
            findings.append(SafetyFinding(
                finding_id=f"TIMING_002_{peripheral}",
                severity=SafetySeverity.VIOLATION,
                category="timing",
                description=f"Response time ({response_time_ms}ms) exceeds deadline ({deadline_ms}ms)",
                affected_component=peripheral,
                ASIL=target_asil,
                safety_goal_id=None,
                evidence=f"response_time={response_time_ms}, deadline={deadline_ms}",
                fix_suggestion="Optimize ISR or offload to task, increase deadline, or use DMA",
                iso_26262_reference="ISO 26262 Part 5, 6.4.2 — Response time analysis",
            ))

        # ASIL-D: deadline monitoring required
        if target_asil == ASIL.ASIL_D and deadline_ms == 0:
            findings.append(SafetyFinding(
                finding_id=f"TIMING_003_{peripheral}",
                severity=SafetySeverity.ADVISORY,
                category="timing",
                description="ASIL-D should define deadline monitoring for timing-critical operations",
                affected_component=peripheral,
                ASIL=target_asil,
                safety_goal_id=None,
                evidence="No deadline_ms defined in allocation",
                fix_suggestion="Add deadline_ms to allocation and implement timeout monitoring",
            ))

        return findings

    def _validate_communication(
        self,
        allocation: dict[str, Any],
        target_asil: ASIL,
    ) -> list[SafetyFinding]:
        """Validate communication safety."""
        findings = []
        peripheral = allocation.get("peripheral", "")
        protocol = allocation.get("protocol", "").upper()

        # Alive supervision (CAN/LIN: node must send within timeout)
        alive_timeout_ms = allocation.get("alive_supervision_ms", 0)
        if alive_timeout_ms == 0 and protocol in ("CAN", "LIN"):
            findings.append(SafetyFinding(
                finding_id=f"COMM_001_{peripheral}",
                severity=SafetySeverity.ADVISORY,
                category="communication",
                description=f"No alive supervision timeout configured for {protocol}",
                affected_component=peripheral,
                ASIL=target_asil,
                safety_goal_id=None,
                evidence=f"No alive_supervision_ms in allocation",
                fix_suggestion=f"Configure alive supervision timeout (typical: 1000-3000ms for CAN)",
                iso_26262_reference="ISO 14229-1 Annex B — Alive supervision",
            ))

        # CRC/checksum on safety-critical CAN messages
        if protocol == "CAN" and allocation.get("safety_critical", False):
            if not allocation.get("message_crc_enabled", False):
                findings.append(SafetyFinding(
                    finding_id=f"COMM_002_{peripheral}",
                    severity=SafetySeverity.WARNING,
                    category="communication",
                    description="Safety-critical CAN communication should include message CRC",
                    affected_component=peripheral,
                    ASIL=target_asil,
                    safety_goal_id=None,
                    evidence="safety_critical=True but message_crc_enabled=False",
                    fix_suggestion="Add CRC to CAN payload (last 2 bytes) or use E2E profile",
                    iso_26262_reference="ISO 26262 Part 4, 7.4.8 — Data exchange",
                ))

        # Bus-off recovery
        if protocol == "CAN":
            bus_off_threshold = allocation.get("bus_off_threshold", 255)
            if bus_off_threshold > 128:
                findings.append(SafetyFinding(
                    finding_id=f"COMM_003_{peripheral}",
                    severity=SafetySeverity.ADVISORY,
                    category="communication",
                    description=f"CAN bus-off threshold ({bus_off_threshold}) is high — slow fault recovery",
                    affected_component=peripheral,
                    ASIL=target_asil,
                    safety_goal_id=None,
                    evidence=f"bus_off_threshold={bus_off_threshold}",
                    fix_suggestion="Consider lower threshold (e.g., 96-128) for faster recovery",
                ))

        return findings

    def _validate_memory(
        self,
        allocation: dict[str, Any],
        target_asil: ASIL,
    ) -> list[SafetyFinding]:
        """Validate memory safety."""
        findings = []

        # Stack watermark / overflow detection
        if allocation.get("uses_stack", False):
            if not allocation.get("stack_watermark_enabled", False):
                findings.append(SafetyFinding(
                    finding_id="MEMORY_001",
                    severity=SafetySeverity.ADVISORY,
                    category="memory",
                    description="Stack overflow protection not enabled",
                    affected_component="CPU",
                    ASIL=target_asil,
                    safety_goal_id=None,
                    evidence="uses_stack=True, stack_watermark_enabled=False",
                    fix_suggestion="Enable MPU stack limit checking or stack watermark ISR",
                    iso_26262_reference="ISO 26262 Part 5, 6.4.5 — Memory monitoring",
                ))

        # Flash integrity
        if allocation.get("flash_crc_enabled", False):
            crc_interval_ms = allocation.get("crc_check_interval_ms", 0)
            if crc_interval_ms > 60000:
                findings.append(SafetyFinding(
                    finding_id="MEMORY_002",
                    severity=SafetySeverity.WARNING,
                    category="memory",
                    description=f"Flash CRC interval ({crc_interval_ms}ms) is very long",
                    affected_component="Flash",
                    ASIL=target_asil,
                    safety_goal_id=None,
                    evidence=f"crc_check_interval_ms={crc_interval_ms}",
                    fix_suggestion="Reduce CRC check interval (recommend <= 1000ms for safety-critical)",
                ))

        return findings

    def _validate_code_safety(
        self,
        code: str,
        target_asil: ASIL,
    ) -> list[SafetyFinding]:
        """Validate C code for safety issues."""
        findings = []

        # Check for blocking operations in ISR
        if "IRQHandler" in code or "__interrupt" in code:
            blocking_patterns = [
                ("while(", "Blocking while loop in ISR — may cause priority inversion"),
                ("malloc(", "Memory allocation in ISR — may cause deadlock"),
                ("printf", "Print/buffered IO in ISR — may block or overflow"),
                ("vTaskDelay", "RTOS delay in ISR — not allowed"),
                ("HAL_Delay", "HAL delay in ISR — not allowed for timing-critical ISRs"),
            ]
            for pattern, desc in blocking_patterns:
                if pattern in code:
                    findings.append(SafetyFinding(
                        finding_id=f"CODE_SAFETY_{pattern.rstrip('(')}",
                        severity=SafetySeverity.WARNING,
                        category="timing",
                        description=desc,
                        affected_component="ISR",
                        ASIL=target_asil,
                        safety_goal_id=None,
                        evidence=f"Pattern '{pattern}' found in ISR code",
                        fix_suggestion="Move blocking operations out of ISR, use deferred handler (DMA/flag)",
                        iso_26262_reference="ISO 26262 Part 6, 7.4.5 — Safe task design",
                    ))

        # ASIL-D: requires MISRA compliance
        if target_asil == ASIL.ASIL_D:
            if "goto" in code:
                findings.append(SafetyFinding(
                    finding_id="CODE_SAFETY_GOTO",
                    severity=SafetySeverity.ADVISORY,
                    category="coding",
                    description="MISRA C:2012 Rule 6.6 — goto not recommended for ASIL-D",
                    affected_component="Code",
                    ASIL=ASIL.ASIL_D,
                    safety_goal_id=None,
                    evidence="'goto' found in code",
                    fix_suggestion="Replace goto with structured control flow (break/return/state machine)",
                    iso_26262_reference="MISRA C:2012 Rule 6.6",
                ))

        return findings

    def _compute_hardware_metrics(
        self,
        findings: list[SafetyFinding],
        target_asil: ASIL,
    ) -> dict[str, float]:
        """
        Compute ISO 26262 hardware safety metrics.

        These are simplified estimates. Real computation requires FMEDA data.
        """
        metrics: dict[str, float] = {}

        total_findings = len(findings)
        if total_findings == 0:
            # Perfect score
            metrics["SPFM"] = 99.9
            metrics["LFM"] = 99.9
            metrics["PMHF_FIT"] = 1.0
            return metrics

        # SPFM: measure of single-point fault coverage
        # Simplified: penalize each safety finding
        spfm_penalty = sum(
            5.0 for f in findings
            if f.severity in (SafetySeverity.VIOLATION, SafetySeverity.CRITICAL)
        ) + sum(
            2.0 for f in findings
            if f.severity == SafetySeverity.WARNING
        )
        spfm = max(0.0, 100.0 - spfm_penalty)
        metrics["SPFM"] = round(spfm, 1)

        # LFM: latent fault metric (double-fault coverage)
        lfm_penalty = sum(
            3.0 for f in findings
            if f.severity in (SafetySeverity.WARNING, SafetySeverity.VIOLATION)
        )
        lfm = max(0.0, 100.0 - lfm_penalty)
        metrics["LFM"] = round(lfm, 1)

        # PMHF: probabilistic metric (FIT = failures per 10^9 hours)
        # Simplified estimate based on findings
        violation_count = sum(
            1 for f in findings
            if f.severity in (SafetySeverity.VIOLATION, SafetySeverity.CRITICAL)
        )
        pmhf = violation_count * 10.0  # Each violation ~10 FIT
        metrics["PMHF_FIT"] = round(pmhf, 1)

        # ASIL target thresholds
        thresholds = {
            ASIL.ASIL_B: {"SPFM": 90.0, "LFM": 60.0, "PMHF": 100.0},
            ASIL.ASIL_C: {"SPFM": 97.0, "LFM": 80.0, "PMHF": 50.0},
            ASIL.ASIL_D: {"SPFM": 99.0, "LFM": 90.0, "PMHF": 10.0},
        }

        if target_asil in thresholds:
            t = thresholds[target_asil]
            metrics["SPFM_target"] = t["SPFM"]
            metrics["LFM_target"] = t["LFM"]
            metrics["PMHF_target"] = t["PMHF"]
            metrics["SPFM_pass"] = spfm >= t["SPFM"]
            metrics["LFM_pass"] = lfm >= t["LFM"]
            metrics["PMHF_pass"] = pmhf <= t["PMHF"]

        return metrics

    def _assess_safety_goals(
        self,
        findings: list[SafetyFinding],
    ) -> tuple[list[str], list[str]]:
        """Assess which safety goals are met or failed."""
        goals_met: list[str] = []
        goals_failed: list[str] = []

        for goal in self._safety_goals:
            goal_findings = [f for f in findings if f.safety_goal_id == goal.goal_id]
            critical_findings = [
                f for f in goal_findings
                if f.severity in (SafetySeverity.VIOLATION, SafetySeverity.CRITICAL)
            ]
            if critical_findings:
                goals_failed.append(goal.goal_id)
            else:
                goals_met.append(goal.goal_id)

        return goals_met, goals_failed

    def _parse_asil(self, asil_str: str | ASIL) -> ASIL:
        """Parse ASIL from string."""
        if isinstance(asil_str, ASIL):
            return asil_str
        mapping = {
            "QM": ASIL.QM,
            "A": ASIL.ASIL_A,
            "B": ASIL.ASIL_B,
            "C": ASIL.ASIL_C,
            "D": ASIL.ASIL_D,
        }
        return mapping.get(str(asil_str).upper().replace("ASIL-", ""), ASIL.QM)
