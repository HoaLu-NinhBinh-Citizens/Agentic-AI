"""Unit tests for ML rule engine."""
import pytest
from src.infrastructure.analysis.ml_rules import MLRuleEngine, MLSeverity


class TestMLRuleEngine:
    def test_detect_scaler_before_split(self):
        engine = MLRuleEngine()
        code = "scaler = StandardScaler()\nscaler.fit(X)\nX_train, X_test = train_test_split(X)"
        findings = engine.detect("train.py", code)
        assert len(findings) >= 1
        assert any(f.rule_id == "ML001" for f in findings)

    def test_detect_wrong_loss_multi_label(self):
        engine = MLRuleEngine()
        code = "criterion = nn.CrossEntropyLoss()\nloss = criterion(outputs, multi_label_targets)"
        findings = engine.detect("model.py", code)
        assert len(findings) >= 1

    def test_detect_missing_no_grad(self):
        engine = MLRuleEngine()
        code = "def evaluate(model, data):\n    outputs = model(data)\n    return outputs"
        findings = engine.detect("eval.py", code)
        assert any(f.rule_id == "ML006" for f in findings)

    def test_stats(self):
        engine = MLRuleEngine()
        findings = engine.detect("test.py", "torch.manual_seed(42)\ntorch.cuda.manual_seed(42)")
        stats = engine.get_stats(findings)
        assert stats["total"] >= 1
        assert "critical" in stats["by_severity"] or "high" in stats["by_severity"]
