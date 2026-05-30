"""Unit tests for ML rule engine (legacy - use ml_detectors instead).

DEPRECATED: This test module is deprecated. Use test_ml_detectors.py instead.
This module tests the legacy MLRuleEngine which wraps ml_rules.py.
"""

import pytest
import warnings
from src.infrastructure.analysis.ml_detectors import MLDetector, MLFinding, MLSeverity


class TestMLRuleEngine:
    """Legacy tests - these test the old API that wraps ml_detectors."""

    def setup_method(self):
        """Suppress deprecation warnings during tests."""
        warnings.filterwarnings("ignore", category=DeprecationWarning)

    def test_detect_scaler_before_split(self):
        """Test ML001: scaler.fit() before split."""
        from src.infrastructure.analysis.ml_rules import MLRuleEngine
        engine = MLRuleEngine()
        code = "scaler = StandardScaler()\nscaler.fit(X)\nX_train, X_test = train_test_split(X)"
        findings = engine.detect("train.py", code)
        assert len(findings) >= 1
        assert any(f.rule_id == "ML001" for f in findings)

    def test_detect_wrong_loss_multi_label(self):
        """Test ML002: CrossEntropyLoss with multi-label."""
        from src.infrastructure.analysis.ml_rules import MLRuleEngine
        engine = MLRuleEngine()
        code = "criterion = nn.CrossEntropyLoss()\nloss = criterion(outputs, multi_label_targets)"
        findings = engine.detect("model.py", code)
        assert len(findings) >= 1

    def test_detect_missing_no_grad(self):
        """Test ML006: missing no_grad in inference."""
        from src.infrastructure.analysis.ml_rules import MLRuleEngine
        engine = MLRuleEngine()
        code = "def evaluate(model, data):\n    outputs = model(data)\n    return outputs"
        findings = engine.detect("eval.py", code)
        assert any(f.rule_id == "ML006" for f in findings)

    def test_stats(self):
        """Test statistics generation."""
        from src.infrastructure.analysis.ml_rules import MLRuleEngine
        engine = MLRuleEngine()
        findings = engine.detect("test.py", "torch.manual_seed(42)\ntorch.cuda.manual_seed(42)")
        stats = engine.get_stats(findings)
        assert stats["total"] >= 1
        assert "critical" in stats["by_severity"] or "high" in stats["by_severity"]
