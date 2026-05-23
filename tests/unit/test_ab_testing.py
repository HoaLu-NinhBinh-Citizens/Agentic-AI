"""Tests for A/B testing framework."""

import pytest
from src.application.evaluation.ab_testing import (
    ABTestingFramework,
    ABConfig,
    Variant,
)


class TestABTestingFramework:
    def test_framework_creation(self):
        framework = ABTestingFramework()
        assert framework is not None

    def test_create_test(self):
        framework = ABTestingFramework()
        
        config = ABConfig(
            test_id="test_001",
            name="Test A/B",
            control_ratio=0.5,
            treatment_a_ratio=0.5,
        )
        
        test_id = framework.create_test(config)
        assert test_id == "test_001"

    def test_assign_user_deterministic(self):
        framework = ABTestingFramework()
        
        config = ABConfig(
            test_id="test_001",
            name="Test",
            control_ratio=0.5,
            treatment_a_ratio=0.5,
        )
        framework.create_test(config)
        
        # Same user should get same assignment
        variant1 = framework.assign_user("test_001", "user_001")
        variant2 = framework.assign_user("test_001", "user_001")
        assert variant1 == variant2

    def test_record_metric(self):
        framework = ABTestingFramework()
        
        config = ABConfig(
            test_id="test_001",
            name="Test",
        )
        framework.create_test(config)
        
        framework.assign_user("test_001", "user_001")
        framework.record_metric("test_001", "user_001", "accuracy", 0.85)

    def test_get_results(self):
        framework = ABTestingFramework()
        
        config = ABConfig(
            test_id="test_001",
            name="Test",
        )
        framework.create_test(config)
        
        framework.assign_user("test_001", "user_001")
        framework.record_metric("test_001", "user_001", "accuracy", 0.9)
        
        results = framework.get_results("test_001")
        assert len(results) > 0

    def test_stop_test(self):
        framework = ABTestingFramework()
        
        config = ABConfig(
            test_id="test_001",
            name="Test",
        )
        framework.create_test(config)
        
        framework.stop_test("test_001")
        
        # Should handle gracefully
