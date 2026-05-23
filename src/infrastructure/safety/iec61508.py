"""IEC 61508 Safety Integrity Level (SIL) Framework.

Provides:
- SIL level definitions (SIL1-SIL4)
- Safety function classification
- Diagnostic coverage calculation
- MTBF/MTTF estimation
- Common cause failure analysis
- Safety lifecycle management

Target: IEC 61508-2 SIL2 compliance for embedded systems.

Usage:
    safety = SafetyFramework(target_sil=2)
    
    # Define safety function
    sf = safety.create_safety_function(
        name="firmware_verification",
        sil=2,
        mode=SafetyMode.HIGH_DEMAND,
    )
    
    # Calculate metrics
    metrics = safety.calculate_sil_metrics(sf)
    if metrics.sil_achieved >= target_sil:
        print("Safety function compliant!")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SafetyIntegrityLevel(Enum):
    """IEC 61508 Safety Integrity Levels."""
    SIL0 = 0  # No safety function
    SIL1 = 1  # Low integrity
    SIL2 = 2  # Medium integrity (our target)
    SIL3 = 3  # High integrity
    SIL4 = 4  # Highest integrity


class SafetyMode(Enum):
    """Operating modes per IEC 61508-2."""
    LOW_DEMAND = "low_demand"  # <1 demand per year
    HIGH_DEMAND = "high_demand"  # >=1 demand per year
    CONTINUOUS = "continuous"  # Continuous operation


class DiagnosticType(Enum):
    """Type of diagnostics."""
    NONE = "none"
    SELF_TEST = "self_test"
    PERIODIC = "periodic"
    ONLINE = "online"
    COMPREHENSIVE = "comprehensive"


@dataclass
class ComponentMetrics:
    """Reliability metrics for a component."""
    lambda_b: float = 0.0  # Base failure rate (failures/hour)
    lambda_s: float = 0.0  # Safe failure rate
    lambda_d: float = 0.0  # Dangerous failure rate
    beta: float = 0.02  # Common cause factor (typically 2-10%)
    tau: float = 8.76  # Proof test interval (hours)
    mrt: float = 24.0  # Mean repair time (hours)
    diagnostic_interval: float = 1.0  # Hours between diagnostics


@dataclass
class SILMetrics:
    """Safety Integrity Level metrics."""
    sil_achieved: SafetyIntegrityLevel
    pfd_avg: float  # Average probability of dangerous failure on demand
    pfh: float  # Probability of dangerous failure per hour
    dc: float  # Diagnostic coverage (0-1)
    ccf: float  # Common cause factor (0-1)
    mtbf: float  # Mean time between failures (hours)
    safe_failure_fraction: float  # Proportion of safe failures
    
    # Thresholds per IEC 61508-2
    pfd_low_demand_threshold: float = 1e-2  # SIL2: 10^-2 to 10^-3
    pfh_high_demand_threshold: float = 1e-7  # SIL2: 10^-7 to 10^-8


@dataclass
class SafetyFunction:
    """A safety function per IEC 61508."""
    name: str
    description: str
    target_sil: SafetyIntegrityLevel
    mode: SafetyMode
    architecture: str  # "1oo1", "1oo2", "2oo3", etc.
    
    # Subsystem metrics
    sensors: list[ComponentMetrics] = field(default_factory=list)
    logic: ComponentMetrics | None = None
    actuators: list[ComponentMetrics] = field(default_factory=list)
    
    # Diagnostic configuration
    diagnostic_type: DiagnosticType = DiagnosticType.ONLINE
    proof_test_interval_hours: float = 8760.0  # 1 year
    
    # Computed metrics
    metrics: SILMetrics | None = None
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    validated_at: datetime | None = None
    approved_by: str | None = None


@dataclass
class SafetyLifecyclePhase:
    """Phase in IEC 61508 safety lifecycle."""
    phase_id: str
    name: str
    description: str
    required_outputs: list[str]
    artifacts: list[str] = field(default_factory=list)
    completed: bool = False
    completed_at: datetime | None = None
    reviewer: str | None = None


class SafetyFramework:
    """Framework for IEC 61508 SIL2 compliance.
    
    Provides:
    - Safety lifecycle management
    - SIL metric calculations
    - Diagnostic coverage estimation
    - Common cause failure analysis
    - Evidence collection for audits
    
    Usage:
        framework = SafetyFramework(target_sil=2)
        
        # Create safety function
        sf = framework.create_safety_function(
            name="flash_verification",
            sil=2,
            mode=SafetyMode.HIGH_DEMAND,
        )
        
        # Calculate metrics
        metrics = framework.calculate_sil_metrics(sf)
        if metrics.sil_achieved >= target_sil:
            print("PASS")
    """
    
    # IEC 61508-2 SIL thresholds
    SIL_THRESHOLDS = {
        SafetyMode.LOW_DEMAND: {
            SafetyIntegrityLevel.SIL0: (1.0, float('inf')),
            SafetyIntegrityLevel.SIL1: (1e-2, 1.0),
            SafetyIntegrityLevel.SIL2: (1e-3, 1e-2),
            SafetyIntegrityLevel.SIL3: (1e-4, 1e-3),
            SafetyIntegrityLevel.SIL4: (0.0, 1e-4),
        },
        SafetyMode.HIGH_DEMAND: {
            SafetyIntegrityLevel.SIL0: (1e-5, float('inf')),
            SafetyIntegrityLevel.SIL1: (1e-6, 1e-5),
            SafetyIntegrityLevel.SIL2: (1e-7, 1e-6),
            SafetyIntegrityLevel.SIL3: (1e-8, 1e-7),
            SafetyIntegrityLevel.SIL4: (0.0, 1e-8),
        },
    }
    
    # Diagnostic coverage values
    DC_VALUES = {
        DiagnosticType.NONE: 0.0,
        DiagnosticType.SELF_TEST: 0.5,
        DiagnosticType.PERIODIC: 0.6,
        DiagnosticType.ONLINE: 0.9,
        DiagnosticType.COMPREHENSIVE: 0.99,
    }
    
    def __init__(self, target_sil: SafetyIntegrityLevel = SafetyIntegrityLevel.SIL2):
        self.target_sil = target_sil
        self.safety_functions: dict[str, SafetyFunction] = {}
        self.lifecycle_phases = self._init_lifecycle_phases()
    
    def _init_lifecycle_phases(self) -> list[SafetyLifecyclePhase]:
        """Initialize IEC 61508 safety lifecycle phases."""
        return [
            SafetyLifecyclePhase(
                phase_id="1",
                name="Hazard Analysis",
                description="Identify hazards and hazardous events",
                required_outputs=["Hazard log", "Safety requirements"],
            ),
            SafetyLifecyclePhase(
                phase_id="2",
                name="Overall Safety Requirements",
                description="Define safety functions and SIL targets",
                required_outputs=["Safety requirements specification"],
            ),
            SafetyLifecyclePhase(
                phase_id="3",
                name="Safety Function Allocation",
                description="Allocate safety functions to subsystems",
                required_outputs=["Safety allocation matrix"],
            ),
            SafetyLifecyclePhase(
                phase_id="4",
                name="Overall Safety Planning",
                description="Create safety validation plan",
                required_outputs=["Safety plan", "Safety case outline"],
            ),
            SafetyLifecyclePhase(
                phase_id="5",
                name="Safety-Related System Design",
                description="Architectural and detailed design",
                required_outputs=["Design documents", "Architecture diagram"],
            ),
            SafetyLifecyclePhase(
                phase_id="6",
                name="Safety Validation Planning",
                description="Plan validation tests",
                required_outputs=["Validation plan", "Test specifications"],
            ),
            SafetyLifecyclePhase(
                phase_id="7",
                name="Installation & Commissioning",
                description="Install and verify safety functions",
                required_outputs=["Installation records", "Commissioning report"],
            ),
            SafetyLifecyclePhase(
                phase_id="8",
                name="Safety Validation",
                description="Execute validation tests",
                required_outputs=["Validation report", "Test results"],
            ),
            SafetyLifecyclePhase(
                phase_id="9",
                name="Operation & Maintenance",
                description="Maintain safety during operation",
                required_outputs=["Maintenance procedures", "Proof test records"],
            ),
            SafetyLifecyclePhase(
                phase_id="10",
                name="Modification",
                description="Manage modifications to safety functions",
                required_outputs=["Modification request", "Impact analysis"],
            ),
            SafetyLifecyclePhase(
                phase_id="11",
                name="Decommissioning",
                description="Safely decommission safety functions",
                required_outputs=["Decommissioning record"],
            ),
        ]
    
    def create_safety_function(
        self,
        name: str,
        description: str,
        target_sil: SafetyIntegrityLevel,
        mode: SafetyMode,
        architecture: str = "1oo1",
    ) -> SafetyFunction:
        """Create a new safety function.
        
        Args:
            name: Unique identifier
            description: What the function does
            target_sil: Required SIL level
            mode: Operating mode
            architecture: Redundancy (1oo1, 1oo2, 2oo3, etc.)
            
        Returns:
            SafetyFunction ready for metric calculation
        """
        sf = SafetyFunction(
            name=name,
            description=description,
            target_sil=target_sil,
            mode=mode,
            architecture=architecture,
        )
        
        self.safety_functions[name] = sf
        logger.info("safety_function_created", name=name, target_sil=target_sil.value)
        
        return sf
    
    def add_sensor(
        self,
        safety_function: SafetyFunction,
        metrics: ComponentMetrics,
    ) -> None:
        """Add a sensor to a safety function."""
        safety_function.sensors.append(metrics)
    
    def set_logic_solver(self, safety_function: SafetyFunction, metrics: ComponentMetrics) -> None:
        """Set the logic solver (controller) metrics."""
        safety_function.logic = metrics
    
    def add_actuator(
        self,
        safety_function: SafetyFunction,
        metrics: ComponentMetrics,
    ) -> None:
        """Add an actuator to a safety function."""
        safety_function.actuators.append(metrics)
    
    def calculate_sil_metrics(self, safety_function: SafetyFunction) -> SILMetrics:
        """Calculate SIL metrics for a safety function.
        
        Implements IEC 61508-2 formulas for:
        - PFD_avg (probability of dangerous failure on demand)
        - PFH (probability of dangerous failure per hour)
        - DC (diagnostic coverage)
        - CCF (common cause failure factor)
        """
        # Get architecture parameters
        n_total, n_required = self._parse_architecture(safety_function.architecture)
        
        # Calculate combined failure rates
        lambda_total = 0.0
        lambda_safe = 0.0
        lambda_dangerous = 0.0
        
        # Sensors
        for sensor in safety_function.sensors:
            lambda_total += sensor.lambda_b
            lambda_safe += sensor.lambda_s
            lambda_dangerous += sensor.lambda_d
        
        # Logic solver
        if safety_function.logic:
            lambda_total += safety_function.logic.lambda_b
            lambda_safe += safety_function.logic.lambda_s
            lambda_dangerous += safety_function.logic.lambda_d
        
        # Actuators
        for actuator in safety_function.actuators:
            lambda_total += actuator.lambda_b
            lambda_safe += actuator.lambda_s
            lambda_dangerous += actuator.lambda_d
        
        # Calculate diagnostic coverage
        dc = self.DC_VALUES[safety_function.diagnostic_type]
        
        # Calculate CCF (beta factor method)
        ccf = self._calculate_ccf(n_total, n_required)
        
        # Calculate PFD or PFH based on mode
        if safety_function.mode == SafetyMode.LOW_DEMAND:
            pfd = self._calculate_pfd(
                lambda_dangerous=lambda_dangerous * (1 - dc),
                beta=ccf,
                tau=safety_function.proof_test_interval_hours,
            )
            pfh = 0.0
        else:
            pfd = 0.0
            pfh = self._calculate_pfh(
                lambda_dangerous=lambda_dangerous * (1 - dc),
                beta=ccf,
                diagnostic_interval=safety_function.diagnostic_interval,
            )
        
        # Determine achieved SIL
        sil_achieved = self._determine_sil(safety_function.mode, pfd, pfh)
        
        # Calculate MTBF
        mtbf = 1.0 / lambda_total if lambda_total > 0 else float('inf')
        
        # Calculate safe failure fraction
        sff = lambda_safe / lambda_total if lambda_total > 0 else 1.0
        
        metrics = SILMetrics(
            sil_achieved=sil_achieved,
            pfd_avg=pfd,
            pfh=pfh,
            dc=dc,
            ccf=ccf,
            mtbf=mtbf,
            safe_failure_fraction=sff,
        )
        
        safety_function.metrics = metrics
        
        logger.info(
            "sil_metrics_calculated",
            function=safety_function.name,
            sil_achieved=sil_achieved.value,
            pfd=pfd,
            pfh=pfh,
        )
        
        return metrics
    
    def _parse_architecture(self, architecture: str) -> tuple[int, int]:
        """Parse architecture string to MooN format.
        
        Returns (total_channels, required_channels).
        """
        parts = architecture.lower().replace("oo", "oo").split("oo")
        if len(parts) == 2:
            n_total = int(parts[0])
            n_required = int(parts[1])
            return n_total, n_required
        return 1, 1  # Default 1oo1
    
    def _calculate_ccf(self, n_total: int, n_required: int) -> float:
        """Calculate common cause factor based on redundancy.
        
        Beta factor model from IEC 61508-6.
        """
        if n_total == 1:
            return 0.10  # Single channel - higher CCF
        elif n_total == 2:
            if n_required == 2:
                return 0.05  # 2oo2 - very low CCF
            else:
                return 0.02  # 1oo2 - low CCF
        elif n_total >= 3:
            if n_required == n_total:
                return 0.02  # MooM
            else:
                return 0.05  # MooN where N < M
        return 0.10
    
    def _calculate_pfd(
        self,
        lambda_dangerous: float,
        beta: float,
        tau: float,
    ) -> float:
        """Calculate PFD_avg for low/high demand mode.
        
        Formula from IEC 61508-6 Clause B.3:
        PFD_avg = (lambda_dD * ti)^2 / 2 + lambda_dD * MTTR
                 + (beta * lambda_dD * tau) / 2
        
        Simplified for architectural constraints.
        """
        # Convert failure rates
        lambda_dd = lambda_dangerous  # Dangerous undetected
        
        # Simplified PFD calculation
        t_ce = tau / 2  # Channel equivalent mean downtime
        t_cm = 24.0  # Mean time to restoration
        
        pfd = (lambda_dd * t_ce) ** 2 / 2 + lambda_dd * t_cm
        
        # Add common cause contribution
        pfd_cc = (beta * lambda_dangerous * tau) / 2
        pfd_total = pfd + pfd_cc
        
        return min(pfd_total, 1.0)
    
    def _calculate_pfh(
        self,
        lambda_dangerous: float,
        beta: float,
        diagnostic_interval: float,
    ) -> float:
        """Calculate PFH for high demand/continuous mode.
        
        Formula from IEC 61508-6 Clause B.4:
        PFH = lambda_dD * (1 - DC) * T + lambda_dD * MTTR
        
        Simplified for architectural constraints.
        """
        lambda_dd = lambda_dangerous
        
        # Diagnostic coverage reduces dangerous failures
        t = diagnostic_interval
        
        # PFH = lambda_ddu * T + lambda_dd * MTTR
        pfh = lambda_dd * t + lambda_dd * 1.0  # Assume 1 hour MTTR
        
        # Add CCF contribution
        pfh_cc = beta * lambda_dangerous * 100.0  # Assuming 100 hour mission time
        pfh_total = pfh + pfh_cc
        
        return min(pfh_total, 1e-4)  # Cap at reasonable value
    
    def _determine_sil(
        self,
        mode: SafetyMode,
        pfd: float,
        pfh: float,
    ) -> SafetyIntegrityLevel:
        """Determine achieved SIL based on PFD/PFH values."""
        if mode == SafetyMode.LOW_DEMAND:
            thresholds = self.SIL_THRESHOLDS[SafetyMode.LOW_DEMAND]
            for sil, (low, high) in thresholds.items():
                if low <= pfd < high:
                    return sil
        else:
            thresholds = self.SIL_THRESHOLDS[SafetyMode.HIGH_DEMAND]
            for sil, (low, high) in thresholds.items():
                if low <= pfh < high:
                    return sil
        
        return SafetyIntegrityLevel.SIL0
    
    def verify_compliance(self, safety_function: SafetyFunction) -> tuple[bool, list[str]]:
        """Verify a safety function meets SIL requirements.
        
        Returns (is_compliant, list of violations).
        """
        violations = []
        
        if safety_function.metrics is None:
            violations.append("Metrics not calculated")
            return False, violations
        
        metrics = safety_function.metrics
        
        # Check SIL achieved
        if metrics.sil_achieved.value < safety_function.target_sil.value:
            violations.append(
                f"SIL achieved ({metrics.sil_achieved.value}) < "
                f"target ({safety_function.target_sil.value})"
            )
        
        # Check PFD/PFH thresholds
        if safety_function.mode == SafetyMode.LOW_DEMAND:
            threshold = self.SIL_THRESHOLDS[SafetyMode.LOW_DEMAND][safety_function.target_sil][0]
            if metrics.pfd_avg >= threshold:
                violations.append(
                    f"PFD_avg ({metrics.pfd_avg:.2e}) exceeds "
                    f"threshold ({threshold:.2e})"
                )
        else:
            threshold = self.SIL_THRESHOLDS[SafetyMode.HIGH_DEMAND][safety_function.target_sil][0]
            if metrics.pfh >= threshold:
                violations.append(
                    f"PFH ({metrics.pfh:.2e}) exceeds "
                    f"threshold ({threshold:.2e})"
                )
        
        # Check diagnostic coverage
        if metrics.dc < 0.6:
            violations.append(f"Diagnostic coverage ({metrics.dc:.0%}) too low (<60%)")
        
        # Check CCF
        if metrics.ccf > 0.1:
            violations.append(f"Common cause factor ({metrics.ccf:.0%}) too high (>10%)")
        
        return len(violations) == 0, violations
    
    def generate_safety_case(self, safety_function: SafetyFunction) -> dict[str, Any]:
        """Generate safety case evidence for audit.
        
        Returns structured evidence for IEC 61508-7 compliance.
        """
        if safety_function.metrics is None:
            self.calculate_sil_metrics(safety_function)
        
        metrics = safety_function.metrics
        is_compliant, violations = self.verify_compliance(safety_function)
        
        return {
            "safety_function": {
                "name": safety_function.name,
                "description": safety_function.description,
                "target_sil": safety_function.target_sil.value,
                "mode": safety_function.mode.value,
                "architecture": safety_function.architecture,
            },
            "metrics": {
                "sil_achieved": metrics.sil_achieved.value,
                "pfd_avg": f"{metrics.pfd_avg:.2e}",
                "pfh": f"{metrics.pfh:.2e}",
                "diagnostic_coverage": f"{metrics.dc:.1%}",
                "ccf": f"{metrics.ccf:.1%}",
                "mtbf_hours": f"{metrics.mtbf:.0f}",
                "safe_failure_fraction": f"{metrics.safe_failure_fraction:.1%}",
            },
            "compliance": {
                "compliant": is_compliant,
                "violations": violations,
                "verified_at": datetime.now().isoformat(),
            },
            "lifecycle": {
                "phases_completed": sum(1 for p in self.lifecycle_phases if p.completed),
                "total_phases": len(self.lifecycle_phases),
            },
        }
    
    def collect_audit_evidence(self) -> dict[str, Any]:
        """Collect all evidence for external audit.
        
        Returns structured evidence package for certification.
        """
        evidence = {
            "audit_package": {
                "generated_at": datetime.now().isoformat(),
                "framework_version": "1.0.0",
                "standard": "IEC 61508-2",
                "target_sil": self.target_sil.value,
            },
            "safety_functions": [],
            "lifecycle_compliance": [],
            "summary": {
                "total_functions": len(self.safety_functions),
                "compliant_functions": 0,
                "non_compliant_functions": 0,
            },
        }
        
        compliant_count = 0
        
        for name, sf in self.safety_functions.items():
            sf_evidence = self.generate_safety_case(sf)
            evidence["safety_functions"].append(sf_evidence)
            
            if sf_evidence["compliance"]["compliant"]:
                compliant_count += 1
        
        evidence["summary"]["compliant_functions"] = compliant_count
        evidence["summary"]["non_compliant_functions"] = len(self.safety_functions) - compliant_count
        
        # Lifecycle phases
        for phase in self.lifecycle_phases:
            evidence["lifecycle_compliance"].append({
                "phase_id": phase.phase_id,
                "name": phase.name,
                "completed": phase.completed,
                "completed_at": phase.completed_at.isoformat() if phase.completed_at else None,
                "reviewer": phase.reviewer,
            })
        
        return evidence


# Convenience function for quick SIL calculation
def quick_sil_check(
    target_sil: int,
    mode: str = "high_demand",
    failure_rate: float = 1e-6,
    diagnostic_coverage: float = 0.9,
) -> dict[str, Any]:
    """Quick SIL check without full framework setup.
    
    Args:
        target_sil: Target SIL level (1-4)
        mode: "lowDemand" or "highDemand"
        failure_rate: Component failure rate per hour
        diagnostic_coverage: DC value (0-1)
        
    Returns:
        Dict with compliance status
    """
    framework = SafetyFramework(target_sil=SafetyIntegrityLevel(target_sil))
    
    sf = framework.create_safety_function(
        name="quick_check",
        description="Quick SIL verification",
        target_sil=SafetyIntegrityLevel(target_sil),
        mode=SafetyMode.HIGH_DEMAND if mode == "highDemand" else SafetyMode.LOW_DEMAND,
    )
    
    # Add a simple sensor with given failure rate
    metrics = ComponentMetrics(
        lambda_b=failure_rate,
        lambda_s=failure_rate * 0.5,
        lambda_d=failure_rate * 0.5,
    )
    sf.sensors.append(metrics)
    
    sil_metrics = framework.calculate_sil_metrics(sf)
    is_compliant, violations = framework.verify_compliance(sf)
    
    return {
        "target_sil": target_sil,
        "achieved_sil": sil_metrics.sil_achieved.value,
        "compliant": is_compliant,
        "violations": violations,
        "metrics": {
            "pfd": sil_metrics.pfd_avg,
            "pfh": sil_metrics.pfh,
            "dc": sil_metrics.dc,
            "mtbf_hours": sil_metrics.mtbf,
        },
    }
