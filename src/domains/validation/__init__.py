"""
Validation Domain Module — Cross-Validator for full validation chain.

Cross-Validator orchestrates multiple validation layers:
  1. Hardware allocation (pin, clock, interrupt, register)
  2. Initialization order (dependency graph)
  3. Flash + bootloader chain
  4. Code correctness (generated code)
  5. Automotive safety (CAN/LIN/UDS)
  6. End-to-end consistency

Architecture:
    Input → Allocation Validation → Dependency Validation
          → Flash Chain Validation → Code Validation
          → Safety Validation → Cross-Consistency → Result
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

from src.domains.hardware_engine.core.peripheral_graph import PeripheralGraph
from src.domains.hardware_engine.core.models import (
    AllocationContext,
    HardwareConstraint,
    ResourceAllocation,
    ValidationFinding,
    ValidationResult,
    ValidationSeverity,
)
from src.domains.hardware_engine.validator.hw_validator import HardwareValidator
from src.domains.hardware_engine.validator.rules import HardwareRules
from src.domains.safety import SafetyValidator as DomainSafetyValidator, ASIL

logger = structlog.get_logger(__name__)


class ValidationStage(Enum):
    """Stages in the cross-validation pipeline."""
    ALLOCATION = "allocation"           # Pin/clock/IRQ/register allocation
    DEPENDENCY = "dependency"           # Peripheral dependencies and init order
    FLASH_CHAIN = "flash_chain"         # Flash/bootloader/OTA consistency
    CODE_GENERATION = "code_generation"  # Generated C code correctness
    SAFETY = "safety"                   # Automotive safety constraints
    CROSS_CONSISTENCY = "cross_consistency"  # End-to-end consistency
    FINAL = "final"                     # Aggregated result


@dataclass
class ValidationStageResult:
    """Result from a single validation stage."""
    stage: ValidationStage
    valid: bool
    duration_ms: float
    findings: list[ValidationFinding] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class CrossValidationResult:
    """Full cross-validation result."""
    valid: bool
    overall_errors: int = 0
    overall_warnings: int = 0
    stage_results: list[ValidationStageResult] = field(default_factory=list)
    critical_issues: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "overall_errors": self.overall_errors,
            "overall_warnings": self.overall_warnings,
            "stages": [
                {
                    "stage": r.stage.value,
                    "valid": r.valid,
                    "duration_ms": r.duration_ms,
                    "errors": sum(1 for f in r.findings if f.severity == ValidationSeverity.ERROR),
                    "warnings": sum(1 for f in r.findings if f.severity == ValidationSeverity.WARNING),
                }
                for r in self.stage_results
            ],
            "critical_issues": self.critical_issues,
            "summary": self.summary,
        }


class CrossValidator:
    """
    Cross-validator for embedded firmware.

    Orchestrates 6 validation layers:
    1. Allocation Validation — pin, clock, IRQ, register via HardwareValidator
    2. Dependency Validation — peripheral init order via PeripheralGraph
    3. Flash Chain Validation — flash/bootloader/OTA consistency
    4. Code Validation — generated C code correctness
    5. Safety Validation — automotive safety constraints
    6. Cross-Consistency — end-to-end consistency checks

    Usage:
        validator = CrossValidator(
            peripheral_graph=graph,
            hardware_validator=hw_validator,
        )
        result = await validator.validate_allocation(
            allocation={"peripheral": "CAN1", ...}
        )
    """

    def __init__(
        self,
        peripheral_graph: PeripheralGraph | None = None,
        hardware_validator: HardwareValidator | None = None,
        safety_validator: DomainSafetyValidator | None = None,
    ):
        self.graph = peripheral_graph
        self.hw_validator = hardware_validator
        self._safety_validator = safety_validator
        self._rules = HardwareRules()

    async def validate_allocation(
        self,
        allocation: dict[str, Any],
        context: AllocationContext | None = None,
    ) -> CrossValidationResult:
        """
        Run full cross-validation on a hardware allocation.

        Args:
            allocation: Raw allocation dict (pin_assignments, clock_assignment, etc.)
            context: Optional AllocationContext for richer validation

        Returns:
            CrossValidationResult with all stage results
        """
        started = datetime.now()
        stage_results: list[ValidationStageResult] = []

        # Stage 1: Allocation validation
        stage1 = await self._validate_allocation(allocation)
        stage_results.append(stage1)

        # Stage 2: Dependency validation
        stage2 = await self._validate_dependencies(allocation)
        stage_results.append(stage2)

        # Stage 3: Flash chain validation
        stage3 = await self._validate_flash_chain(allocation)
        stage_results.append(stage3)

        # Stage 4: Code generation validation (if code present)
        if allocation.get("generated_code"):
            stage4 = await self._validate_code_generation(allocation)
            stage_results.append(stage4)

        # Stage 5: Safety validation
        stage5 = await self._validate_safety(allocation)
        stage_results.append(stage5)

        # Stage 6: Cross-consistency
        stage6 = await self._validate_cross_consistency(allocation, stage_results)
        stage_results.append(stage6)

        # Aggregate
        total_errors = sum(
            sum(1 for f in r.findings if f.severity == ValidationSeverity.ERROR)
            for r in stage_results
        )
        total_warnings = sum(
            sum(1 for f in r.findings if f.severity == ValidationSeverity.WARNING)
            for r in stage_results
        )
        critical = self._extract_critical_issues(stage_results)
        summary = self._build_summary(stage_results, total_errors, total_warnings)

        result = CrossValidationResult(
            valid=total_errors == 0,
            overall_errors=total_errors,
            overall_warnings=total_warnings,
            stage_results=stage_results,
            critical_issues=critical,
            summary=summary,
            metadata={
                "total_duration_ms": (datetime.now() - started).total_seconds() * 1000,
                "stages_run": len(stage_results),
            },
        )

        logger.info(
            "cross_validation_complete",
            valid=result.valid,
            errors=total_errors,
            warnings=total_warnings,
            stages=len(stage_results),
        )

        return result

    # ─── Stage 1: Allocation ──────────────────────────────────────────

    async def _validate_allocation(
        self, allocation: dict[str, Any]
    ) -> ValidationStageResult:
        """Validate pin, clock, IRQ, register allocation."""
        started = datetime.now()
        result = ValidationResult(valid=True)

        if self.hw_validator:
            result = self.hw_validator.validate_allocation(allocation)

        return ValidationStageResult(
            stage=ValidationStage.ALLOCATION,
            valid=result.valid,
            duration_ms=(datetime.now() - started).total_seconds() * 1000,
            findings=result.findings,
            metadata={
                "pin_count": len(allocation.get("pin_assignments", [])),
                "clock_configured": "clock_assignment" in allocation,
                "interrupt_configured": "interrupt_assignment" in allocation,
            },
        )

    # ─── Stage 2: Dependency ──────────────────────────────────────────

    async def _validate_dependencies(
        self, allocation: dict[str, Any]
    ) -> ValidationStageResult:
        """Validate peripheral dependency chain and init order."""
        started = datetime.now()
        result = ValidationResult(valid=True)
        peripheral = allocation.get("peripheral", "")

        if not self.graph:
            return ValidationStageResult(
                stage=ValidationStage.DEPENDENCY,
                valid=True,
                duration_ms=(datetime.now() - started).total_seconds() * 1000,
                metadata={"note": "no graph available"},
            )

        # Check peripheral exists
        if not self.graph.has_peripheral(peripheral):
            result.add_warning(
                "DEP_001",
                f"Peripheral '{peripheral}' not found in hardware graph",
                peripheral=peripheral,
            )

        # Check dependencies are satisfied
        deps = self.graph.get_dependencies(peripheral)
        for dep in deps:
            if not self.graph.has_peripheral(dep):
                result.add_error(
                    "DEP_002",
                    f"Peripheral '{peripheral}' depends on unknown '{dep}'",
                    peripheral=peripheral,
                )

        # Check clock domain consistency
        domain = self.graph.get_clock_domain(peripheral)
        if domain and allocation.get("clock_assignment"):
            assigned_domain = allocation["clock_assignment"].get("domain", "")
            if assigned_domain and assigned_domain != domain:
                result.add_warning(
                    "DEP_003",
                    f"Assigned clock domain '{assigned_domain}' differs from expected '{domain}'",
                    peripheral=peripheral,
                )

        # Topological order validation
        if self.graph.validate_dependencies():
            errors = self.graph.validate_dependencies()
            for err in errors:
                result.add_error("DEP_004", err)

        return ValidationStageResult(
            stage=ValidationStage.DEPENDENCY,
            valid=result.valid,
            duration_ms=(datetime.now() - started).total_seconds() * 1000,
            findings=result.findings,
            metadata={
                "peripheral": peripheral,
                "dependencies": list(deps),
                "clock_domain": domain,
                "init_order": self.graph.topological_sort() if self.graph else [],
            },
        )

    # ─── Stage 3: Flash Chain ─────────────────────────────────────────

    async def _validate_flash_chain(
        self, allocation: dict[str, Any]
    ) -> ValidationStageResult:
        """Validate flash/bootloader/OTA consistency."""
        started = datetime.now()
        result = ValidationResult(valid=True)

        # Check flash-related allocations
        flash_config = allocation.get("flash_config", {})
        ota_config = allocation.get("ota_config", {})
        boot_config = allocation.get("boot_config", {})

        if not flash_config and not ota_config and not boot_config:
            return ValidationStageResult(
                stage=ValidationStage.FLASH_CHAIN,
                valid=True,
                duration_ms=(datetime.now() - started).total_seconds() * 1000,
                metadata={"note": "no flash/boot/ota config present"},
            )

        # OTA partition validation
        if ota_config:
            slots = ota_config.get("slots", [])
            if len(slots) < 2:
                result.add_error(
                    "FLASH_001",
                    "OTA requires at least 2 partition slots (A/B)",
                )
            # Check slot sizes
            total_size = sum(s.get("size", 0) for s in slots)
            if total_size > allocation.get("flash_total_size", 0):
                result.add_error(
                    "FLASH_002",
                    f"OTA slots total ({total_size}KB) exceed flash size",
                )

        # Bootloader consistency
        if boot_config:
            entry = boot_config.get("entry_point", 0)
            if entry == 0:
                result.add_error(
                    "FLASH_003",
                    "Bootloader entry point not set",
                )
            # Check entry point is in valid flash region
            flash_start = allocation.get("flash_start", 0x08000000)
            flash_end = allocation.get("flash_end", 0x081FFFFF)
            if not (flash_start <= entry < flash_end):
                result.add_error(
                    "FLASH_004",
                    f"Entry point 0x{entry:08X} outside flash region",
                )

        # Encryption validation
        if flash_config.get("encrypted") and not flash_config.get("key"):
            result.add_warning(
                "FLASH_005",
                "Flash is marked encrypted but no encryption key configured",
            )

        return ValidationStageResult(
            stage=ValidationStage.FLASH_CHAIN,
            valid=result.valid,
            duration_ms=(datetime.now() - started).total_seconds() * 1000,
            findings=result.findings,
            metadata={
                "ota_configured": bool(ota_config),
                "bootloader_configured": bool(boot_config),
                "encryption_enabled": flash_config.get("encrypted", False),
            },
        )

    # ─── Stage 4: Code Generation ──────────────────────────────────────

    async def _validate_code_generation(
        self, allocation: dict[str, Any]
    ) -> ValidationStageResult:
        """Validate generated C code correctness."""
        started = datetime.now()
        result = ValidationResult(valid=True)
        code = allocation.get("generated_code", "")

        import re

        # Check for missing clock enable
        peripheral = allocation.get("peripheral", "")
        if "RCC->" not in code and "HAL_" not in code:
            result.add_warning(
                "CODE_001",
                "No RCC clock enable found in generated code",
                peripheral=peripheral,
            )

        # Check for missing interrupt NVIC setup
        if "IRQ" in code and "NVIC_" not in code and "HAL_" not in code:
            result.add_warning(
                "CODE_002",
                "ISR defined but NVIC configuration not found",
                peripheral=peripheral,
            )

        # Check for bare magic numbers
        magic_pattern = r"(?<!//)\s+([0-9]{5,})\s*;"
        magic_numbers = re.findall(magic_pattern, code)
        if magic_numbers:
            result.add_info(
                "CODE_003",
                f"Found {len(magic_numbers)} potential magic numbers — consider named constants",
            )

        # Check for hardcoded addresses
        addr_pattern = r"0x[0-9A-Fa-f]{8}"
        addrs = re.findall(addr_pattern, code)
        if addrs:
            result.add_info(
                "CODE_004",
                f"Found {len(addrs)} hardcoded addresses — ensure they match hardware schema",
            )

        # Validate via hardware validator if available
        if self.hw_validator and code:
            hw_result = self.hw_validator.validate_code(code, allocation)
            result.findings.extend(hw_result.findings)
            if not hw_result.valid:
                result.valid = False

        return ValidationStageResult(
            stage=ValidationStage.CODE_GENERATION,
            valid=result.valid,
            duration_ms=(datetime.now() - started).total_seconds() * 1000,
            findings=result.findings,
            metadata={
                "lines": len(code.splitlines()),
                "has_rcc": "RCC" in code,
                "has_nvic": "NVIC" in code,
            },
        )

    # ─── Stage 5: Safety ───────────────────────────────────────────────

    async def _validate_safety(
        self, allocation: dict[str, Any]
    ) -> ValidationStageResult:
        """Validate automotive safety constraints using ISO 26262 SafetyValidator."""
        started = datetime.now()
        peripheral = allocation.get("peripheral", "")

        # Use DomainSafetyValidator if available
        if self._safety_validator:
            from src.domains.safety import SafetySeverity as DomainSeverity
            safety_result = self._safety_validator.validate_allocation(allocation)

            # Convert safety findings to validation findings
            findings: list[ValidationFinding] = []
            for sf in safety_result.findings:
                sev = ValidationSeverity.ERROR if sf.severity in (
                    DomainSeverity.VIOLATION, DomainSeverity.CRITICAL
                ) else ValidationSeverity.WARNING if sf.severity == DomainSeverity.WARNING else ValidationSeverity.INFO

                finding = ValidationFinding(
                    severity=sev,
                    rule_id=sf.finding_id,
                    message=sf.description,
                    location=sf.affected_component,
                    peripheral=peripheral,
                    fix_suggestion=sf.fix_suggestion,
                    citation={"iso_reference": sf.iso_26262_reference},
                )
                findings.append(finding)

            return ValidationStageResult(
                stage=ValidationStage.SAFETY,
                valid=safety_result.valid,
                duration_ms=(datetime.now() - started).total_seconds() * 1000,
                findings=findings,
                metadata={
                    "ASIL": allocation.get("ASIL", "QM"),
                    "metrics": safety_result.metrics,
                    "safety_goals_met": safety_result.safety_goals_met,
                },
            )

        # No safety_validator — return empty (handled by DomainSafetyValidator in cross_validate)
        return ValidationStageResult(
            stage=ValidationStage.SAFETY,
            valid=True,
            duration_ms=(datetime.now() - started).total_seconds() * 1000,
            findings=[],
            metadata={"note": "use DomainSafetyValidator for full ISO 26262 checks"},
        )

    # ─── Stage 6: Cross-Consistency ──────────────────────────────────

    async def _validate_cross_consistency(
        self,
        allocation: dict[str, Any],
        prior_stages: list[ValidationStageResult],
    ) -> ValidationStageResult:
        """Validate end-to-end consistency across all stages."""
        started = datetime.now()
        result = ValidationResult(valid=True)
        peripheral = allocation.get("peripheral", "")

        # Aggregate all errors/warnings by category
        error_counts: dict[str, int] = {}
        for stage in prior_stages:
            for f in stage.findings:
                if f.severity == ValidationSeverity.ERROR:
                    key = f.rule_id.split("_")[0]
                    error_counts[key] = error_counts.get(key, 0) + 1

        # Check: If allocation has errors, code should not be generated
        alloc_errors = sum(
            1 for f in prior_stages[0].findings
            if f.severity == ValidationSeverity.ERROR
        ) if prior_stages else 0
        if alloc_errors > 0 and allocation.get("generated_code"):
            result.add_warning(
                "CONSIST_001",
                f"Code was generated despite {alloc_errors} allocation error(s) — review carefully",
                peripheral=peripheral,
            )

        # Check: Pin assignments must match peripheral signals
        pin_assigns = allocation.get("pin_assignments", [])
        for pa in pin_assigns:
            signal = pa.get("signal", "")
            if signal and peripheral:
                # Infer if pin makes sense for peripheral
                if peripheral.upper().startswith("CAN") and "RX" not in signal and "TX" not in signal:
                    result.add_info(
                        "CONSIST_002",
                        f"Pin {pa.get('pin')} signal '{signal}' may not be standard CAN signal",
                        peripheral=peripheral,
                    )

        # Check: Clock config must match bus domain
        clock = allocation.get("clock_assignment", {})
        if clock and self.graph:
            expected_domain = self.graph.get_clock_domain(peripheral)
            assigned_domain = clock.get("domain", "")
            if expected_domain and assigned_domain and expected_domain != assigned_domain:
                result.add_error(
                    "CONSIST_003",
                    f"Clock domain mismatch: expected {expected_domain}, assigned {assigned_domain}",
                    peripheral=peripheral,
                )

        # Check: DMA + interrupt consistency
        if allocation.get("dma_config") and not allocation.get("interrupt_assignment"):
            result.add_warning(
                "CONSIST_004",
                "DMA is configured but no interrupt assigned — ensure DMA completion is handled",
                peripheral=peripheral,
            )

        return ValidationStageResult(
            stage=ValidationStage.CROSS_CONSISTENCY,
            valid=result.valid,
            duration_ms=(datetime.now() - started).total_seconds() * 1000,
            findings=result.findings,
            metadata={
                "error_distribution": error_counts,
                "stages_validated": len(prior_stages),
            },
        )

    # ─── Helpers ──────────────────────────────────────────────────────

    def _extract_critical_issues(
        self, stages: list[ValidationStageResult]
    ) -> list[dict[str, Any]]:
        """Extract critical (error-level) issues for quick review."""
        critical = []
        for stage in stages:
            for f in stage.findings:
                if f.severity == ValidationSeverity.ERROR:
                    critical.append({
                        "stage": stage.stage.value,
                        "rule_id": f.rule_id,
                        "message": f.message,
                        "location": f.location,
                        "peripheral": f.peripheral,
                    })
        return critical

    def _build_summary(
        self,
        stages: list[ValidationStageResult],
        errors: int,
        warnings: int,
    ) -> str:
        """Build human-readable summary."""
        valid_stages = sum(1 for s in stages if s.valid)
        total_stages = len(stages)

        if errors == 0:
            return f"VALID — {valid_stages}/{total_stages} stages passed, {warnings} warning(s)"

        error_lines = []
        for stage in stages:
            stage_errors = [
                f"[{f.rule_id}] {f.message}"
                for f in stage.findings
                if f.severity == ValidationSeverity.ERROR
            ]
            if stage_errors:
                error_lines.append(f"{stage.stage.value}:")
                for e in stage_errors:
                    error_lines.append(f"  - {e}")

        return (
            f"INVALID — {errors} error(s), {warnings} warning(s)\n"
            + "\n".join(error_lines)
        )
