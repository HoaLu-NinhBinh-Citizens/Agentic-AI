"""Unit tests for config system."""
import os
import pytest
from src.core.config.ai_support_config import AISupportConfig, RuleConfig, MLRuleConfig, IndexingConfig, OutputConfig


class TestAISupportConfig:
    def test_default_config(self):
        cfg = AISupportConfig()
        assert cfg.rules.max_function_lines == 50
        assert cfg.ml_rules.check_data_leakage is True
        assert cfg.indexing.incremental is True

    def test_env_override(self):
        os.environ["AI_SUPPORT_CONCURRENCY"] = "8"
        cfg = AISupportConfig()
        assert cfg.indexing.concurrency == 8
        del os.environ["AI_SUPPORT_CONCURRENCY"]

    def test_rule_config(self):
        cfg = RuleConfig(max_function_lines=30)
        assert cfg.max_function_lines == 30

    def test_ml_rule_config(self):
        cfg = MLRuleConfig(check_data_leakage=False)
        assert cfg.check_data_leakage is False
