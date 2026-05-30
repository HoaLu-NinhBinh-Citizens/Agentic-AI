"""Detectors package — specialized code review detectors.

Available detectors:
- MlDetector: ML-based pattern detection using tree-sitter AST queries
- SecurityDetector: Security vulnerability detection
- QualityDetector: Code quality and style issues
- EmbeddedDetector: Embedded C/firmware issues (CRASH, ASSERT, memory)
"""

from src.application.workflows.unified.detectors.ml_detector import MlDetector
from src.application.workflows.unified.detectors.security_detector import SecurityDetector
from src.application.workflows.unified.detectors.quality_detector import QualityDetector
from src.application.workflows.unified.detectors.embedded_detector import EmbeddedDetector

__all__ = [
    "MlDetector",
    "SecurityDetector",
    "QualityDetector",
    "EmbeddedDetector",
]
