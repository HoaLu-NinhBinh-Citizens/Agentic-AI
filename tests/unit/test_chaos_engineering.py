"""Tests for chaos engineering."""

import pytest
from src.infrastructure.chaos.chaos_engineering import (
    ChaosEngineer,
    ChaosExperiment,
    ChaosTarget,
    ExperimentStatus,
    FailureType,
)


class TestChaosExperiment:
    def test_experiment_creation(self):
        engineer = ChaosEngineer()
        
        experiment = engineer.create_experiment(
            name="Test Experiment",
            description="Testing chaos",
            target=ChaosTarget.BOARD_HARDWARE,
            failure_type=FailureType.HARDWARE_MALFUNCTION,
            target_ids=["board_001"],
        )
        
        assert experiment.name == "Test Experiment"
        assert experiment.status == ExperimentStatus.PENDING

    def test_register_target(self):
        engineer = ChaosEngineer()
        engineer.register_target("board_001", {"type": "STM32F407"})
        
        # Should not raise


class TestChaosEngineer:
    def test_engineer_creation(self):
        engineer = ChaosEngineer()
        assert engineer is not None

    def test_create_experiment(self):
        engineer = ChaosEngineer()
        
        experiment = engineer.create_experiment(
            name="Hardware Test",
            description="Test hardware failure",
            target=ChaosTarget.BOARD_HARDWARE,
            failure_type=FailureType.HARDWARE_MALFUNCTION,
            duration_seconds=60,
        )
        
        assert experiment.experiment_id is not None
        assert experiment.target == ChaosTarget.BOARD_HARDWARE

    def test_get_experiment(self):
        engineer = ChaosEngineer()
        
        experiment = engineer.create_experiment(
            name="Test",
            description="Test",
            target=ChaosTarget.NETWORK,
            failure_type=FailureType.CONNECTION_LOSS,
        )
        
        retrieved = engineer.get_experiment(experiment.experiment_id)
        assert retrieved is not None
        assert retrieved.name == "Test"

    def test_list_experiments(self):
        engineer = ChaosEngineer()
        
        engineer.create_experiment(
            name="Exp1",
            description="Test",
            target=ChaosTarget.BOARD_HARDWARE,
            failure_type=FailureType.HARDWARE_MALFUNCTION,
        )
        
        engineer.create_experiment(
            name="Exp2",
            description="Test",
            target=ChaosTarget.NETWORK,
            failure_type=FailureType.CONNECTION_LOSS,
        )
        
        experiments = engineer.list_experiments()
        assert len(experiments) >= 2

    def test_abort_experiment(self):
        engineer = ChaosEngineer()
        
        experiment = engineer.create_experiment(
            name="Test Abort",
            description="Test",
            target=ChaosTarget.BOARD_HARDWARE,
            failure_type=FailureType.HARDWARE_MALFUNCTION,
        )
        
        # Cannot abort non-running experiment
        result = engineer.abort_experiment(experiment.experiment_id)
        assert result is False
