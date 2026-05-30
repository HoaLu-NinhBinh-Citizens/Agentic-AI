"""ML Detector — redirect to MLDetectorAdapter.

This file exists for backwards compatibility. The actual ML detection is now
handled by MLDetectorAdapter in ml_adapter.py, which wraps the infrastructure
ML detector (src.infrastructure.analysis.ml_detectors) with unified pipeline support.

For the real ML-specific bug detection (ML001-ML005), use:
    from src.application.workflows.unified.detectors.ml_adapter import MLDetectorAdapter

The MlDetector alias in __init__.py points to MLDetectorAdapter.
"""

# Redirect to the actual implementation
from src.application.workflows.unified.detectors.ml_adapter import MLDetectorAdapter as MlDetector

__all__ = ["MlDetector"]
