"""Enhanced AgentHarness - Integrates all 5 Root Cause Solutions.

This module combines:
1. LongHorizonMemory - prevents context forgetting
2. ToolSchemaRegistry - prevents API hallucination
3. TraceAnalyzer - handles misleading logs
4. ArchitecturePreservation - prevents architecture collapse
5. RootCauseAnalyzer - distinguishes symptom fix from root cause fix

SOLUTION ARCHITECTURE:

┌────────────────────────────────────────────────────────────────────────┐
│                     EnhancedAgentHarness                                 │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │  Memory Layer                                                     │ │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐    │ │
│  │  │ LongHorizon    │  │ Checkpoint     │  │ Constraint     │    │ │
│  │  │ Memory         │  │ Manager        │  │ Preserver      │    │ │
│  │  └────────────────┘  └────────────────┘  └────────────────┘    │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                              ↓                                           │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │  Validation Layer                                                  │ │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐    │ │
│  │  │ ToolSchema      │  │ Trace          │  │ Architecture   │    │ │
│  │  │ Registry       │  │ Analyzer       │  │ Preservation   │    │ │
│  │  └────────────────┘  └────────────────┘  └────────────────┘    │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                              ↓                                           │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │  Analysis Layer                                                    │ │
│  │  ┌───────────────────────────────────────────────────────────┐  │ │
│  │  │ RootCauseAnalyzer                                          │  │ │
│  │  │ - Symptom → Root Cause → Fix Validation                   │  │ │
│  │  └───────────────────────────────────────────────────────────┘  │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                              ↓                                           │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │  Agent Loop (PLAN → VALIDATE → EXECUTE → OBSERVE → REFLECT)     │ │
│  └──────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

import structlog

from src.core.agent_runtime import AgentHarness as BaseAgentHarness
from src.core.agent_runtime import HarnessConfig, HarnessResult, HarnessState
from src.core.memory.long_horizon_memory import LongHorizonMemory, MemoryType
from src.core.tools.tool_schema_registry import ToolSchemaRegistry, ValidationReport
from src.core.tools.trace_analyzer import TraceAnalyzer, MisleadingLogDetector
from src.core.tools.architecture_preservation import (
    ArchitecturePreservation,
    ChangeImpact,
    PartialFixDetector,
)
from src.core.tools.root_cause_analyzer import (
    RootCauseAnalyzer,
    Symptom,
    AnalysisResult,
    FixValidation,
)

logger = structlog.get_logger(__name__)


class ValidationPhase(Enum):
    """Validation phases."""
    API_CHECK = "api_check"
    ARCHITECTURE_CHECK = "architecture_check"
    LOG_ANALYSIS = "log_analysis"
    ROOT_CAUSE_CHECK = "root_cause_check"
    FIX_VALIDATION = "fix_validation"


@dataclass
class EnhancedMetrics:
    """Enhanced metrics for the agent."""
    # From LongHorizonMemory
    memory_items: int = 0
    checkpoints_created: int = 0
    plan_consistency: float = 1.0
    constraints_preserved: int = 0

    # From ToolSchemaRegistry
    apis_validated: int = 0
    hallucinations_detected: int = 0
    suspicious_patterns_detected: int = 0

    # From TraceAnalyzer
    logs_analyzed: int = 0
    red_herrings_detected: int = 0
    root_causes_found: int = 0

    # From ArchitecturePreservation
    changes_analyzed: int = 0
    constraint_violations: int = 0
    breaking_changes_blocked: int = 0

    # From RootCauseAnalyzer
    symptoms_analyzed: int = 0
    partial_fixes_detected: int = 0
    full_fixes_validated: int = 0


@dataclass
class ValidationResult:
    """Result of validation."""
    passed: bool
    phase: ValidationPhase
    message: str
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


class EnhancedAgentHarness:
    """
    Enhanced AgentHarness with all 5 root cause solutions integrated.

    This harness:
    1. Maintains long-horizon context via memory architecture
    2. Validates API calls to prevent hallucination
    3. Analyzes logs to distinguish signal from noise
    4. Preserves architecture during modifications
    5. Validates fixes address root causes
    """

    def __init__(
        self,
        config: Optional[HarnessConfig] = None,
        base_harness: Optional[BaseAgentHarness] = None,
    ) -> None:
        # Base harness
        self._base = base_harness or BaseAgentHarness(config or HarnessConfig())

        # Component 1: Long-Horizon Memory
        self._memory = LongHorizonMemory(
            max_working_items=20,
            max_episodic_items=100,
            checkpoint_interval=5,
        )

        # Component 2: Tool Schema Registry
        self._schema_registry = ToolSchemaRegistry()

        # Component 3: Trace Analyzer
        self._trace_analyzer = TraceAnalyzer()

        # Component 4: Architecture Preservation
        self._arch_preservation = ArchitecturePreservation()

        # Component 5: Root Cause Analyzer
        self._root_cause_analyzer = RootCauseAnalyzer()

        # Metrics
        self._metrics = EnhancedMetrics()

        # Validation callbacks
        self._validation_enabled = True
        self._strict_mode = True  # Block breaking changes

    # =========================================================================
    # Component Accessors
    # =========================================================================

    @property
    def memory(self) -> LongHorizonMemory:
        return self._memory

    @property
    def schema_registry(self) -> ToolSchemaRegistry:
        return self._schema_registry

    @property
    def trace_analyzer(self) -> TraceAnalyzer:
        return self._trace_analyzer

    @property
    def arch_preservation(self) -> ArchitecturePreservation:
        return self._arch_preservation

    @property
    def root_cause_analyzer(self) -> RootCauseAnalyzer:
        return self._root_cause_analyzer

    @property
    def metrics(self) -> EnhancedMetrics:
        return self._metrics

    # =========================================================================
    # Memory Integration
    # =========================================================================

    def initialize_task(self, task: str, requirements: list[str]) -> None:
        """Initialize task with memory tracking."""
        self._memory.initialize_plan(task, requirements)

        # Preserve critical constraints
        for req in requirements:
            self._memory.preserve_constraint(req)

    def add_memory_context(self, content: str, importance: float = 1.0) -> None:
        """Add to working memory."""
        self._memory.add_working_memory(content, importance=importance)

    def create_checkpoint(self, phase: str, description: str) -> None:
        """Create milestone checkpoint."""
        cp = self._memory.create_checkpoint(phase, description)
        self._metrics.checkpoints_created += 1

    def preserve_api(self, api_name: str) -> None:
        """Mark API as preserved."""
        self._memory.preserve_api(api_name)
        self._arch_preservation.preserve_api(api_name)

    def preserve_file(self, file_path: str) -> None:
        """Mark file as preserved."""
        self._memory.preserve_file(file_path)
        self._arch_preservation.preserve_file(file_path)

    def get_context_for_llm(self) -> str:
        """Get full context for LLM prompt."""
        return self._memory.get_full_context()

    # =========================================================================
    # API Validation
    # =========================================================================

    def validate_api_call(
        self,
        api_name: str,
        parameters: Optional[dict[str, Any]] = None,
    ) -> ValidationResult:
        """
        Validate API call against schema registry.

        Prevents hallucination by checking:
        1. API exists in registry
        2. No suspicious patterns
        3. Parameters are valid
        """
        self._metrics.apis_validated += 1

        report = self._schema_registry.validate_api_call(api_name, parameters)

        if report.result.value == "valid":
            return ValidationResult(
                passed=True,
                phase=ValidationPhase.API_CHECK,
                message=f"API '{api_name}' is valid",
            )

        # Handle invalid API
        self._metrics.hallucinations_detected += 1

        result = ValidationResult(
            passed=False,
            phase=ValidationPhase.API_CHECK,
            message=report.message,
            warnings=[f"Did you mean: {', '.join(report.similar_apis[:3])}"],
            details={
                "api_name": api_name,
                "validation_result": report.result.value,
                "suggestions": report.suggestions,
                "similar_apis": report.similar_apis,
            },
        )

        if report.pattern_warning:
            self._metrics.suspicious_patterns_detected += 1
            result.warnings.append(report.pattern_warning)

        return result

    def scan_code_for_hallucinations(self, code: str) -> list[ValidationResult]:
        """Scan code for potential API hallucinations."""
        reports = self._schema_registry.check_code_for_hallucinations(code)
        results = []

        for report in reports:
            self._metrics.hallucinations_detected += 1
            results.append(ValidationResult(
                passed=False,
                phase=ValidationPhase.API_CHECK,
                message=f"Potential hallucination: {report.api_name}",
                warnings=[f"Did you mean: {', '.join(report.similar_apis[:2])}"],
                details={"api_name": report.api_name, "result": report.result.value},
            ))

        return results

    # =========================================================================
    # Log Analysis
    # =========================================================================

    def analyze_logs(self, log_text: str, symptom_time: Optional[float] = None) -> dict[str, Any]:
        """
        Analyze logs to find root cause, ignoring red herrings.

        Returns:
            Analysis with root cause and ignored red herrings
        """
        self._metrics.logs_analyzed += 1

        analysis = self._trace_analyzer.explain_misleading_logs(log_text)
        result = self._trace_analyzer.analyze(symptom_time=symptom_time)

        if result.red_herring_events:
            self._metrics.red_herrings_detected += len(result.red_herring_events)

        return {
            "root_cause": result.root_cause.event.description if result.root_cause else None,
            "confidence": result.confidence,
            "red_herrings": [
                {"message": e.description, "reason": e.metadata.get("reason", "Known misleading pattern")}
                for e in result.red_herring_events
            ],
            "candidates": [
                {"description": c.event.description, "score": c.score}
                for c in result.candidates[:5]
            ],
            "summary": result.summary,
        }

    def check_for_misleading_logs(self, error_message: str) -> Optional[dict[str, Any]]:
        """Check if error message is misleading and explain why."""
        detection = MisleadingLogDetector.detect(error_message)

        if detection:
            return {
                "is_misleading": True,
                "apparent_cause": detection["apparent_cause"],
                "actual_causes": detection["actual_causes"],
                "investigation": detection["investigation_hint"],
            }

        return None

    # =========================================================================
    # Architecture Preservation
    # =========================================================================

    def analyze_change_impact(
        self,
        change_type: str,  # "delete", "modify", "rename"
        target: str,
    ) -> ValidationResult:
        """
        Analyze impact of proposed change.

        Prevents:
        - Deleting files that are imported
        - Modifying preserved APIs
        - Breaking layer boundaries
        """
        self._metrics.changes_analyzed += 1

        impact = self._arch_preservation.analyze_change(change_type, target)

        if impact.breaking_change:
            self._metrics.breaking_changes_blocked += 1
            return ValidationResult(
                passed=not self._strict_mode,
                phase=ValidationPhase.ARCHITECTURE_CHECK,
                message=impact.explanation,
                warnings=impact.cascading_updates_needed,
                details={
                    "severity": impact.severity,
                    "affected_files": impact.affected_files,
                    "breaking": impact.breaking_change,
                },
            )

        return ValidationResult(
            passed=True,
            phase=ValidationPhase.ARCHITECTURE_CHECK,
            message=f"Change to '{target}' is safe",
            details={"severity": impact.severity},
        )

    def check_constraint_violation(self, action: str) -> Optional[str]:
        """Check if action violates preserved constraints."""
        return self._memory.check_constraint_violation(action)

    def detect_partial_fix(
        self,
        fix_description: str,
        symptom: str,
    ) -> Optional[dict[str, Any]]:
        """Detect if fix is a partial symptom treatment."""
        # Check for partial fix patterns
        partial = PartialFixDetector.detect_partial_fix(fix_description)

        if partial:
            self._metrics.partial_fixes_detected += 1
            return {
                "is_partial": True,
                "actual_root_cause": partial["actual_root_cause"],
                "investigate": partial["investigate"],
                "full_fix_needed": PartialFixDetector.suggest_full_fix(fix_description, symptom),
            }

        return None

    # =========================================================================
    # Root Cause Analysis
    # =========================================================================

    def analyze_root_cause(
        self,
        symptom: str,
        code_context: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Analyze symptom to find root cause.

        Uses 5 Whys pattern to drill down.
        """
        self._metrics.symptoms_analyzed += 1

        symptom_obj = Symptom(
            symptom_id=f"symptom_{self._metrics.symptoms_analyzed}",
            description=symptom,
            severity="high",
        )

        result = self._root_cause_analyzer.analyze(symptom_obj, code_context)

        if result.root_cause:
            self._metrics.root_causes_found += 1

        return {
            "root_cause": result.root_cause.description if result.root_cause else None,
            "confidence": result.root_cause.confidence if result.root_cause else 0.0,
            "hypotheses": [
                {"description": h.description, "confidence": h.confidence}
                for h in result.hypotheses[:5]
            ],
            "questions": [q.question for q in result.questions[:5]],
            "summary": result.summary,
            "fix_guidance": (
                self._root_cause_analyzer.generate_fix_guidance(result.root_cause)
                if result.root_cause else ""
            ),
        }

    def validate_fix(
        self,
        fix_description: str,
        symptom: str,
    ) -> dict[str, Any]:
        """
        Validate if fix addresses root cause or just symptom.

        Returns:
            Validation with whether fix is complete
        """
        # First get root cause analysis
        analysis = self.analyze_root_cause(symptom)

        root_cause = None
        if analysis["root_cause"]:
            root_cause = type("Hypothesis", (), {
                "description": analysis["root_cause"],
                "confidence": analysis["confidence"],
            })()

        validation = self._root_cause_analyzer.validate_fix(fix_description, root_cause)

        result = {
            "addresses_root_cause": validation.addresses_root_cause,
            "prevents_recurrence": validation.prevents_recurrence,
            "is_symptom_relief": validation.is_symptom_relief,
            "regression_risk": validation.regression_risk,
            "notes": validation.validation_notes,
        }

        if validation.is_symptom_relief and not validation.addresses_root_cause:
            result["recommendation"] = (
                "Fix treats symptom, not root cause. "
                "Check if root cause is properly addressed."
            )
            self._metrics.partial_fixes_detected += 1
        elif validation.addresses_root_cause:
            self._metrics.full_fixes_validated += 1

        return result

    # =========================================================================
    # Integrated Execution
    # =========================================================================

    async def execute_with_validation(
        self,
        action: str,
        target: Optional[str] = None,
    ) -> tuple[bool, list[str]]:
        """
        Execute action with full validation.

        Returns:
            (success, warnings)
        """
        warnings = []

        # 1. Check constraint violations
        violation = self.check_constraint_violation(action)
        if violation:
            warnings.append(f"Constraint violation: {violation}")

        # 2. Validate API calls in action
        import re
        api_pattern = r'\b([A-Z][A-Za-z0-9_]+)\s*\('
        for match in re.finditer(api_pattern, action):
            api_name = match.group(1)
            if api_name.startswith("HAL_") or api_name.startswith("USB_"):
                result = self.validate_api_call(api_name)
                if not result.passed:
                    warnings.append(f"API warning: {result.message}")
                    if result.warnings:
                        warnings.extend(result.warnings)

        # 3. Analyze change impact if modifying file
        if target and any(kw in action.lower() for kw in ["delete", "remove", "modify"]):
            change_type = "delete" if "delete" in action.lower() else "modify"
            result = self.analyze_change_impact(change_type, target)
            if not result.passed:
                warnings.append(f"Architecture warning: {result.message}")

        # 4. Check for partial fix patterns
        if "fix" in action.lower() or "patch" in action.lower():
            partial = self.detect_partial_fix(action, target or "")
            if partial:
                warnings.append(f"Partial fix detected: {partial.get('investigate', '')}")

        return len(warnings) == 0, warnings

    def get_full_report(self) -> dict[str, Any]:
        """Generate comprehensive report."""
        return {
            "metrics": {
                "memory": self._memory.get_stats(),
                "schema_registry": self._schema_registry.get_stats(),
                "enhanced_metrics": self._metrics.__dict__,
            },
            "plan_status": self._memory.get_plan_status(),
            "architecture": self._arch_preservation.generate_preservation_report(),
        }


# =============================================================================
# Convenience Functions
# =============================================================================

def create_enhanced_harness(
    config: Optional[HarnessConfig] = None,
) -> EnhancedAgentHarness:
    """Create enhanced harness with all components."""
    return EnhancedAgentHarness(config=config)


async def quick_validate_fix(
    symptom: str,
    fix: str,
    code_context: Optional[str] = None,
) -> dict[str, Any]:
    """
    Quick validation of a fix against symptom.

    Usage:
        result = await quick_validate_fix(
            symptom="Buffer overflow in ISR",
            fix="Increased buffer size to 256",
            code_context=code_snippet,
        )
    """
    harness = create_enhanced_harness()

    # Analyze root cause
    analysis = harness.analyze_root_cause(symptom, code_context)

    # Validate fix
    validation = harness.validate_fix(fix, symptom)

    # Check for partial fix
    partial = harness.detect_partial_fix(fix, symptom)

    return {
        "root_cause_analysis": analysis,
        "fix_validation": validation,
        "partial_fix_warning": partial,
        "recommendation": (
            validation.get("recommendation") or
            (partial.get("full_fix_needed") if partial else None) or
            "Fix appears complete"
        ),
    }
