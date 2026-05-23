"""Tests for OTA orchestrator."""

import pytest
from src.infrastructure.ota.ota_orchestrator import (
    OTAOrchestrator,
    OTAConfig,
    OTAStatus,
)


class TestOTAOrchestrator:
    def test_orchestrator_creation(self):
        orch = OTAOrchestrator()
        assert orch is not None

    def test_create_rollout(self):
        orch = OTAOrchestrator()
        config = OTAConfig(
            rollout_id="rollout_001",
            firmware_version="1.0.0",
            target_version="1.1.0",
            target_boards=["board_001", "board_002"],
        )
        rollout_id = orch.create_rollout(config)
        assert rollout_id == "rollout_001"

    def test_start_rollout(self):
        orch = OTAOrchestrator()
        config = OTAConfig(
            rollout_id="rollout_001",
            firmware_version="1.0.0",
            target_version="1.1.0",
            target_boards=["board_001"],
        )
        orch.create_rollout(config)
        result = orch.start_rollout("rollout_001")
        assert result is True

    def test_update_device_status(self):
        orch = OTAOrchestrator()
        config = OTAConfig(
            rollout_id="rollout_001",
            firmware_version="1.0.0",
            target_version="1.1.0",
            target_boards=["board_001"],
        )
        orch.create_rollout(config)
        orch.start_rollout("rollout_001")
        
        orch.update_device_status(
            "rollout_001",
            "board_001",
            OTAStatus.COMPLETED,
            success=True,
        )
        
        status = orch.get_rollout_status("rollout_001")
        assert status is not None
        assert status.completed >= 1

    def test_list_active_rollouts(self):
        orch = OTAOrchestrator()
        config = OTAConfig(
            rollout_id="rollout_001",
            firmware_version="1.0.0",
            target_version="1.1.0",
            target_boards=["board_001"],
        )
        orch.create_rollout(config)
        orch.start_rollout("rollout_001")
        
        active = orch.list_active_rollouts()
        assert "rollout_001" in active

    def test_pause_and_resume(self):
        orch = OTAOrchestrator()
        config = OTAConfig(
            rollout_id="rollout_001",
            firmware_version="1.0.0",
            target_version="1.1.0",
            target_boards=["board_001"],
        )
        orch.create_rollout(config)
        orch.start_rollout("rollout_001")
        
        result = orch.pause_rollout("rollout_001")
        assert result is True
        
        result = orch.resume_rollout("rollout_001")
        assert result is True
