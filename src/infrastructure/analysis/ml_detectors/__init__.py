"""ML-specific detectors using AST-based analysis.

This module provides context-aware ML bug detection with tree-sitter AST queries,
falling back to improved regex patterns when AST analysis is unavailable.

Exports:
    MLDetector: Unified ML-specific bug detector combining all rules.
    MLDetectorAST: AST-based ML detector implementations.
    DataFlowAnalyzer: Data flow tracking for ML pattern analysis.
    MLFinding: Dataclass for ML-specific findings with confidence scoring.
"""

from __future__ import annotations

from .detector import MLDetector, MLFinding, MLSeverity
from .ast_based import MLDetectorAST
from .data_flow import DataFlowAnalyzer

__all__ = [
    "MLDetector",
    "MLFinding",
    "MLSeverity",
    "MLDetectorAST",
    "DataFlowAnalyzer",
]
