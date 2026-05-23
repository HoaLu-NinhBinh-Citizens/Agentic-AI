"""Tests for auto fine-tuner."""

import pytest
from src.application.evaluation.auto_fine_tuner import (
    AutoFineTuner,
    FineTuneConfig,
    SchedulerStatus,
)


class TestAutoFineTuner:
    def test_tuner_creation(self):
        tuner = AutoFineTuner()
        assert tuner is not None

    def test_default_config(self):
        config = FineTuneConfig()
        assert config.schedule == "monthly"
        assert config.min_samples == 1000

    def test_start_collection(self):
        tuner = AutoFineTuner()
        schedule = tuner.start_collection()
        assert schedule is not None

    def test_add_training_data(self):
        tuner = AutoFineTuner()
        tuner.start_collection()
        tuner.add_training_data({"input": "test"}, 0.9)

    def test_should_trigger_training_insufficient_samples(self):
        tuner = AutoFineTuner(FineTuneConfig(min_samples=100))
        tuner.start_collection()
        should_train, reason = tuner.should_trigger_training()
        assert should_train is False

    def test_get_status(self):
        tuner = AutoFineTuner()
        status = tuner.get_status()
        assert "status" in status
        assert "schedule" in status

    def test_get_next_schedule_time(self):
        tuner = AutoFineTuner()
        next_time = tuner.get_next_schedule_time()
        assert next_time is not None
