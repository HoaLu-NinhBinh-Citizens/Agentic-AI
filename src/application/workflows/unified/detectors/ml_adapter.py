"""ML Detector Adapter — bridges infrastructure MLDetector to unified pipeline.

This adapter wraps the actual ML detector from `src.infrastructure.analysis.ml_detectors`
(which detects real ML bugs like data leakage, wrong loss, missing no_grad, device mismatch,
missing seed) and converts its findings to the unified pipeline's Finding format.

The original `MlDetector` in `detectors/` was a placeholder that only detected generic
patterns (dead-code, unused-param, null-check, resource-leak). This adapter provides
the REAL ML-specific bug detection.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from src.application.workflows.unified.code_context import CodeContext
from src.application.workflows.unified.detector_base import (
    Detector,
    DetectorConfig,
    Finding,
    FindingSeverity,
)

if TYPE_CHECKING:
    from src.infrastructure.analysis.ml_detectors import MLDetector as InfraMLDetector
    from src.infrastructure.analysis.ml_detectors import MLFinding

logger = logging.getLogger(__name__)

# Map MLSeverity to FindingSeverity
_ML_SEVERITY_MAP = {
    "CRITICAL": FindingSeverity.ERROR,
    "HIGH": FindingSeverity.WARNING,
    "MEDIUM": FindingSeverity.INFO,
}


class MLDetectorAdapter(Detector):
    """Adapter that wraps infrastructure MLDetector for the unified pipeline.

    This detector provides AST-based ML bug detection with:
    - ML001: Data leakage (scaler.fit before train_test_split)
    - ML002: Wrong loss function (CrossEntropyLoss for multi-label)
    - ML003: Device mismatch (model and data on different devices)
    - ML004: Missing no_grad (memory leak in inference)
    - ML005: Missing random seed (non-reproducible training)

    Usage:
        config = DetectorConfig(focus_areas=["ml"])
        detector = MLDetectorAdapter(config)
        findings = detector.detect(context)
    """

    def __init__(self, config: DetectorConfig | None = None) -> None:
        """Initialize the ML detector adapter.

        Args:
            config: Detector configuration
        """
        super().__init__(config)
        self._name = "ml"
        self._infra_detector: Optional["InfraMLDetector"] = None

    def _get_infra_detector(self) -> "InfraMLDetector":
        """Get or create the infrastructure ML detector lazily."""
        if self._infra_detector is None:
            from src.infrastructure.analysis.ml_detectors import MLDetector

            self._infra_detector = MLDetector()
        return self._infra_detector

    def detect(self, context: CodeContext) -> list[Finding]:
        """Detect ML-specific bugs using the infrastructure detector.

        Args:
            context: Unified code context

        Returns:
            List of ML findings in unified Finding format
        """
        findings: list[Finding] = []

        # Only process Python files for ML detection
        if context.language != "python":
            return findings

        try:
            infra_detector = self._get_infra_detector()

            # Get file content
            file_path = Path(context.file_path)
            content = "\n".join(context.lines)

            # Run infrastructure detector
            ml_findings = infra_detector.detect_file(file_path, content, context.language)

            # Convert to unified Finding format
            for ml_finding in ml_findings:
                finding = self._map_finding(ml_finding, context)
                findings.append(finding)

            logger.debug(
                "ML detector found %d issues in %s",
                len(ml_findings),
                context.file_path,
            )

        except ImportError as e:
            logger.warning("ML detector unavailable (tree-sitter not installed?): %s", e)
        except Exception as e:
            logger.warning("ML detector failed on %s: %s", context.file_path, e)

        return findings

    def detect_batch(
        self,
        contexts: dict[str, CodeContext],
    ) -> list[Finding]:
        """Run ML detection on multiple files.

        Args:
            contexts: Dict mapping file paths to contexts

        Returns:
            Combined list of findings
        """
        findings: list[Finding] = []

        for file_path, context in contexts.items():
            try:
                file_findings = self.detect(context)
                findings.extend(file_findings)
                self._stats.increment_files()
                self._stats.add_findings(len(file_findings))
            except Exception as e:
                logger.warning(
                    "ML detector failed on %s: %s",
                    file_path,
                    e,
                )
                self._stats.add_error()

        return findings

    def _map_finding(self, ml_finding: "MLFinding", context: CodeContext) -> Finding:
        """Map infrastructure MLFinding to unified Finding.

        Args:
            ml_finding: MLFinding from infrastructure
            context: Code context

        Returns:
            Unified Finding object
        """
        # Map severity
        ml_severity = ml_finding.severity.value
        unified_severity = _ML_SEVERITY_MAP.get(
            ml_severity, FindingSeverity.WARNING
        )

        # Extract code context
        context_lines = context.get_surrounding_code(ml_finding.line)

        # Build fix suggestion from old_code and new_code
        fix = ""
        if ml_finding.new_code:
            fix = f"# Suggested fix:\n{ml_finding.new_code}"

        return Finding(
            rule_id=ml_finding.rule_id,
            rule_name=self._get_rule_name(ml_finding.rule_id),
            severity=unified_severity,
            file=str(context.file_path),
            line=ml_finding.line,
            end_line=ml_finding.end_line or ml_finding.line,
            message=ml_finding.message,
            fix=fix,
            confidence=ml_finding.confidence,
            context=context_lines or ml_finding.old_code,
            detector=self._name,
            metadata={
                "tags": ["ml", "machine-learning"],
                "detection_method": ml_finding.detection_method,
                "explanation": ml_finding.explanation,
                "old_code": ml_finding.old_code,
                "new_code": ml_finding.new_code,
            },
        )

    def _get_rule_name(self, rule_id: str) -> str:
        """Get human-readable rule name from rule ID.

        Args:
            rule_id: Rule identifier (e.g., "ML001")

        Returns:
            Human-readable name
        """
        names = {
            "ML001": "data-leakage",
            "ML002": "wrong-loss-function",
            "ML003": "device-mismatch",
            "ML004": "missing-no-grad",
            "ML005": "missing-random-seed",
        }
        return names.get(rule_id, f"ml-{rule_id.lower()}")

    def get_supported_rules(self) -> list[dict[str, Any]]:
        """Get list of supported ML rules.

        Returns:
            List of rule metadata
        """
        return [
            {
                "id": "ML001",
                "name": "data-leakage",
                "description": "Scaler fit before train_test_split leaks test data",
                "severity": "CRITICAL",
                "confidence": 0.85,
            },
            {
                "id": "ML002",
                "name": "wrong-loss-function",
                "description": "CrossEntropyLoss used for multi-label classification",
                "severity": "CRITICAL",
                "confidence": 0.88,
            },
            {
                "id": "ML003",
                "name": "device-mismatch",
                "description": "Model and data on different devices",
                "severity": "HIGH",
                "confidence": 0.85,
            },
            {
                "id": "ML004",
                "name": "missing-no-grad",
                "description": "Inference without torch.no_grad() causes memory leak",
                "severity": "HIGH",
                "confidence": 0.80,
            },
            {
                "id": "ML005",
                "name": "missing-random-seed",
                "description": "No random seed set - training is not reproducible",
                "severity": "MEDIUM",
                "confidence": 0.75,
            },
        ]
