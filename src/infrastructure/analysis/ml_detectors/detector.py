"""Unified ML-specific bug detector combining AST and data flow analysis.

This module provides the main entry point for ML-specific static analysis,
combining AST-based detection with data flow tracking for accurate
identification of common ML bugs.

Features:
- Context-aware confidence scoring
- Graceful fallback to regex when AST unavailable
- Code examples in suggestions (before/after)
- Integration with SafeTreeSitterIndexer

Usage:
    from src.infrastructure.analysis.ml_detectors import MLDetector

    indexer = SafeTreeSitterIndexer()
    detector = MLDetector(indexer)

    findings = detector.detect_file(Path("train.py"), content, "python")
    for finding in findings:
        print(f"{finding.rule_id}: {finding.message}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.infrastructure.indexing.tree_sitter import SafeTreeSitterIndexer

from .ast_based import MLDetectorAST
from .data_flow import DataFlowAnalyzer

logger = logging.getLogger(__name__)


class MLSeverity(Enum):
    """ML rule severity levels."""
    CRITICAL = "CRITICAL"  # Data leakage, wrong loss
    HIGH = "HIGH"           # Device mismatch, missing no_grad
    MEDIUM = "MEDIUM"       # Missing seeds


# Confidence boost values for different detection contexts
AST_CONFIDENCE_BOOST = 0.15  # AST detection is more accurate
CONTEXT_CONFIDENCE_BOOST = 0.10  # Clear context (same function)
MULTI_FRAMEWORK_BOOST = 0.05  # Multiple indicators present


@dataclass
class MLFinding:
    """Represents an ML-specific finding with confidence scoring.

    Attributes:
        rule_id: Rule identifier (e.g., "ML001")
        severity: Finding severity (CRITICAL, HIGH, MEDIUM)
        line: Line number where issue was found
        end_line: End line for multi-line issues
        message: Human-readable message
        confidence: Confidence score (0.0 - 1.0)
        old_code: Original code snippet
        new_code: Suggested fixed code
        explanation: Detailed explanation of the issue
        detection_method: How the issue was detected ("ast", "regex", "data_flow")
        file_path: Path to the file containing the issue
    """
    rule_id: str
    severity: MLSeverity
    line: int
    message: str
    confidence: float
    old_code: str
    new_code: str
    explanation: str
    detection_method: str = "ast"
    end_line: Optional[int] = None
    file_path: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert finding to dictionary format."""
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "line": self.line,
            "end_line": self.end_line,
            "message": self.message,
            "confidence": round(self.confidence, 2),
            "old_code": self.old_code,
            "new_code": self.new_code,
            "explanation": self.explanation,
            "detection_method": self.detection_method,
            "file_path": self.file_path,
        }

    @property
    def is_high_confidence(self) -> bool:
        """Check if finding has high confidence (>= 0.85)."""
        return self.confidence >= 0.85


# Rule metadata and configurations
RULE_CONFIGS: dict[str, dict[str, Any]] = {
    "ML001": {
        "name": "data-leakage-scaler",
        "severity": MLSeverity.CRITICAL,
        "base_confidence": 0.85,
        "confidence_boost": 0.10,
        "description": "Scaler fit before train_test_split leaks information",
    },
    "ML002": {
        "name": "cross-entropy-multi-label",
        "severity": MLSeverity.CRITICAL,
        "base_confidence": 0.88,
        "confidence_boost": 0.05,
        "description": "CrossEntropyLoss used for multi-label classification",
    },
    "ML003": {
        "name": "device-mismatch",
        "severity": MLSeverity.HIGH,
        "base_confidence": 0.85,
        "confidence_boost": 0.15,
        "description": "Model and data on different devices causes runtime error",
    },
    "ML004": {
        "name": "missing-no-grad",
        "severity": MLSeverity.HIGH,
        "base_confidence": 0.80,
        "confidence_boost": 0.10,
        "description": "Inference code missing torch.no_grad() causes memory leak",
    },
    "ML005": {
        "name": "missing-seed",
        "severity": MLSeverity.MEDIUM,
        "base_confidence": 0.75,
        "confidence_boost": 0.05,
        "description": "No random seed set - training is not reproducible",
    },
    "ML006": {
        "name": "hardcoded-config",
        "severity": MLSeverity.MEDIUM,
        "base_confidence": 0.80,
        "confidence_boost": 0.05,
        "description": "Hardcoded ML hyperparameters should be configurable",
    },
}


class MLDetector:
    """Unified ML-specific bug detector.

    Combines AST-based detection with data flow analysis to provide
    accurate identification of common ML bugs. Uses graceful fallback
    to improved regex patterns when tree-sitter is unavailable.

    Usage:
        detector = MLDetector(indexer)
        findings = detector.detect_file(Path("train.py"), code, "python")
    """

    def __init__(
        self,
        indexer: Optional["SafeTreeSitterIndexer"] = None,
    ) -> None:
        """Initialize the ML detector.

        Args:
            indexer: SafeTreeSitterIndexer instance for AST analysis.
                    If None, will create one.
        """
        if indexer is None:
            from src.infrastructure.indexing.tree_sitter import SafeTreeSitterIndexer
            indexer = SafeTreeSitterIndexer()

        self.indexer = indexer
        self.ast_detector = MLDetectorAST(indexer)
        self.data_flow = DataFlowAnalyzer()
        self._rule_configs = RULE_CONFIGS

    def detect_file(
        self,
        file_path: Path,
        content: str,
        language: str = "python",
    ) -> list[MLFinding]:
        """Detect all ML-specific issues in a file.

        Args:
            file_path: Path to the file being analyzed
            content: Source code content
            language: Programming language (default: python)

        Returns:
            List of MLFinding objects with detected issues
        """
        findings: list[MLFinding] = []

        # Run all AST-based detectors
        findings.extend(self._detect_ml001(file_path, content, language))
        findings.extend(self._detect_ml002(content, language))
        findings.extend(self._detect_ml003(content, language))
        findings.extend(self._detect_ml004(content, language))
        findings.extend(self._detect_ml005(content, language))
        findings.extend(self._detect_ml006(file_path, content, language))

        # Apply confidence boosts based on context
        findings = self._boost_confidence(findings, content, language)

        # Set file paths
        for finding in findings:
            if finding.file_path is None:
                finding.file_path = str(file_path)

        return findings

    def _detect_ml001(
        self,
        file_path: Path,
        content: str,
        language: str,
    ) -> list[MLFinding]:
        """Detect data leakage: scaler.fit() before train_test_split."""
        findings: list[MLFinding] = []

        raw_findings = self.ast_detector.detect_ml001_data_leakage(
            file_path, content, language
        )

        for raw in raw_findings:
            finding = MLFinding(
                rule_id="ML001",
                severity=MLSeverity.CRITICAL,
                line=raw["line"],
                message=raw["message"],
                confidence=raw.get("confidence", 0.85),
                old_code=raw.get("old_code", ""),
                new_code=raw.get("new_code", ""),
                explanation=raw.get("explanation", ""),
                detection_method=raw.get("detection_method", "ast"),
            )
            findings.append(finding)

        return findings

    def _detect_ml002(
        self,
        content: str,
        language: str,
    ) -> list[MLFinding]:
        """Detect CrossEntropyLoss used for multi-label."""
        findings: list[MLFinding] = []

        raw_findings = self.ast_detector.detect_ml002_cross_entropy(content, language)

        for raw in raw_findings:
            finding = MLFinding(
                rule_id="ML002",
                severity=MLSeverity.CRITICAL,
                line=raw["line"],
                message=raw["message"],
                confidence=raw.get("confidence", 0.88),
                old_code=raw.get("old_code", ""),
                new_code=raw.get("new_code", ""),
                explanation=raw.get("explanation", ""),
                detection_method=raw.get("detection_method", "ast"),
            )
            findings.append(finding)

        return findings

    def _detect_ml003(
        self,
        content: str,
        language: str,
    ) -> list[MLFinding]:
        """Detect device mismatch between model and data."""
        findings: list[MLFinding] = []

        # Use data flow analysis for device consistency
        raw_findings = self.data_flow.find_data_leakage_patterns(content, language)

        # Check for device mismatch patterns
        device_findings = self.ast_detector.detect_ml003_device_mismatch(content, language)

        for raw in device_findings:
            finding = MLFinding(
                rule_id="ML003",
                severity=MLSeverity.HIGH,
                line=raw["line"],
                message=raw["message"],
                confidence=raw.get("confidence", 0.85),
                old_code=raw.get("old_code", ""),
                new_code=raw.get("new_code", ""),
                explanation=raw.get("explanation", ""),
                detection_method=raw.get("detection_method", "ast"),
            )
            findings.append(finding)

        return findings

    def _detect_ml004(
        self,
        content: str,
        language: str,
    ) -> list[MLFinding]:
        """Detect missing torch.no_grad() in inference functions."""
        findings: list[MLFinding] = []

        raw_findings = self.ast_detector.detect_ml004_missing_no_grad(content, language)

        for raw in raw_findings:
            finding = MLFinding(
                rule_id="ML004",
                severity=MLSeverity.HIGH,
                line=raw["line"],
                message=raw["message"],
                confidence=raw.get("confidence", 0.80),
                old_code=raw.get("old_code", ""),
                new_code=raw.get("new_code", ""),
                explanation=raw.get("explanation", ""),
                detection_method=raw.get("detection_method", "ast"),
            )
            findings.append(finding)

        return findings

    def _detect_ml005(
        self,
        content: str,
        language: str,
    ) -> list[MLFinding]:
        """Detect missing random seed for reproducibility."""
        findings: list[MLFinding] = []

        raw_findings = self.ast_detector.detect_ml005_missing_seed(content, language)

        for raw in raw_findings:
            finding = MLFinding(
                rule_id="ML005",
                severity=MLSeverity.MEDIUM,
                line=raw["line"],
                message=raw["message"],
                confidence=raw.get("confidence", 0.75),
                old_code=raw.get("old_code", ""),
                new_code=raw.get("new_code", ""),
                explanation=raw.get("explanation", ""),
                detection_method=raw.get("detection_method", "ast"),
            )
            findings.append(finding)

        return findings

    def _detect_ml006(
        self,
        file_path: Path,
        content: str,
        language: str,
    ) -> list[MLFinding]:
        """Detect hardcoded ML hyperparameters and paths."""
        findings: list[MLFinding] = []

        raw_findings = self.ast_detector.detect_ml006_hardcoded_config(
            content, language
        )

        for raw in raw_findings:
            finding = MLFinding(
                rule_id="ML006",
                severity=MLSeverity.MEDIUM,
                line=raw["line"],
                message=raw["message"],
                confidence=raw.get("confidence", 0.80),
                old_code=raw.get("old_code", ""),
                new_code=raw.get("new_code", ""),
                explanation=raw.get("explanation", ""),
                detection_method=raw.get("detection_method", "ast"),
            )
            findings.append(finding)

        return findings

    def _boost_confidence(
        self,
        findings: list[MLFinding],
        content: str,
        language: str,
    ) -> list[MLFinding]:
        """Boost confidence based on context and multiple indicators."""
        for finding in findings:
            config = self._rule_configs.get(finding.rule_id)
            if config is None:
                continue

            # Boost for AST detection
            if finding.detection_method == "ast":
                finding.confidence = min(
                    1.0,
                    finding.confidence + AST_CONFIDENCE_BOOST
                )

            # Boost for clear context
            lines = content.split("\n")
            if 0 <= finding.line - 1 < len(lines):
                line_content = lines[finding.line - 1]
                if "def " in line_content or any(
                    x in line_content for x in ["X_train", "X_test", "model", "data"]
                ):
                    finding.confidence = min(
                        1.0,
                        finding.confidence + CONTEXT_CONFIDENCE_BOOST
                    )

            # Boost from config
            finding.confidence = min(
                1.0,
                finding.confidence + config.get("confidence_boost", 0)
            )

        return findings

    def detect_batch(
        self,
        files: list[tuple[Path, str, str]],
    ) -> dict[str, list[MLFinding]]:
        """Detect issues across multiple files.

        Args:
            files: List of (path, content, language) tuples

        Returns:
            Dictionary mapping file paths to lists of findings
        """
        results: dict[str, list[MLFinding]] = {}

        for file_path, content, language in files:
            findings = self.detect_file(file_path, content, language)
            if findings:
                results[str(file_path)] = findings

        return results

    def get_stats(self, findings: list[MLFinding]) -> dict[str, Any]:
        """Get statistics about findings.

        Args:
            findings: List of MLFinding objects

        Returns:
            Dictionary with statistics
        """
        by_severity: dict[str, int] = {
            "CRITICAL": 0,
            "HIGH": 0,
            "MEDIUM": 0,
        }
        by_rule: dict[str, int] = {}
        by_method: dict[str, int] = {"ast": 0, "regex": 0, "data_flow": 0}
        total_confidence = 0.0

        for f in findings:
            by_severity[f.severity.value] += 1
            by_rule[f.rule_id] = by_rule.get(f.rule_id, 0) + 1
            by_method[f.detection_method] = by_method.get(f.detection_method, 0) + 1
            total_confidence += f.confidence

        avg_confidence = total_confidence / len(findings) if findings else 0.0

        return {
            "total": len(findings),
            "by_severity": by_severity,
            "by_rule": by_rule,
            "by_method": by_method,
            "avg_confidence": round(avg_confidence, 2),
            "high_confidence_count": sum(1 for f in findings if f.is_high_confidence),
        }

    def filter_findings(
        self,
        findings: list[MLFinding],
        min_confidence: float = 0.0,
        min_severity: Optional[MLSeverity] = None,
        rule_ids: Optional[list[str]] = None,
    ) -> list[MLFinding]:
        """Filter findings by various criteria.

        Args:
            findings: List of findings to filter
            min_confidence: Minimum confidence threshold
            min_severity: Minimum severity level
            rule_ids: List of rule IDs to include (None = all)

        Returns:
            Filtered list of findings
        """
        filtered = []

        severity_order = {
            MLSeverity.MEDIUM: 0,
            MLSeverity.HIGH: 1,
            MLSeverity.CRITICAL: 2,
        }

        for f in findings:
            if f.confidence < min_confidence:
                continue

            if min_severity is not None:
                if severity_order.get(f.severity, 0) < severity_order.get(min_severity, 0):
                    continue

            if rule_ids is not None and f.rule_id not in rule_ids:
                continue

            filtered.append(f)

        return filtered
