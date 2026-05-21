"""Tests for Fleet Coordinator - Rollout management."""

import pytest
import asyncio
from datetime import datetime

from src.domain.hardware.flash.fleet_coordinator import (
    RolloutStrategy,
    RolloutState,
    DeploymentTarget,
    RolloutWave,
    RolloutConfig,
    FleetRollout,
    FleetCoordinator,
    CanaryAnalyzer,
)


class TestRolloutWave:
    """Test RolloutWave dataclass."""
    
    def test_create_wave(self):
        """Test creating rollout wave."""
        wave = RolloutWave(
            wave_id="wave_001",
            wave_number=1,
            target_percentage=10.0,
            target_count=50,
        )
        
        assert wave.wave_id == "wave_001"
        assert wave.target_percentage == 10.0
        assert wave.success_rate == 1.0  # No deployments yet
    
    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        wave = RolloutWave(
            wave_id="wave_001",
            wave_number=1,
            devices_deployed=10,
            devices_succeeded=8,
            devices_failed=2,
        )
        
        assert wave.success_rate == 0.8
        assert abs(wave.failure_rate - 0.2) < 0.001


class TestFleetRollout:
    """Test FleetRollout class."""
    
    def test_create_rollout(self):
        """Test creating fleet rollout."""
        config = RolloutConfig(
            strategy=RolloutStrategy.WAVES,
            wave_size_percentage=20.0,
        )
        
        rollout = FleetRollout(
            firmware_version="2.0.0",
            firmware_hash="abc123",
            config=config,
        )
        
        assert rollout.firmware_version == "2.0.0"
        assert rollout.state == RolloutState.CREATED
    
    def test_should_halt_failure_rate(self):
        """Test halt check based on failure rate."""
        config = RolloutConfig(
            strategy=RolloutStrategy.WAVES,
            max_failure_rate=0.1,  # 10%
        )
        
        rollout = FleetRollout(
            config=config,
            total_deployed=10,
            total_succeeded=8,
            total_failed=2,  # 20% failure rate
        )
        
        should_halt, reason = rollout.should_halt()
        
        assert should_halt is True
        assert "20" in reason  # Should mention 20%
    
    def test_should_halt_failure_count(self):
        """Test halt check based on failure count."""
        config = RolloutConfig(
            strategy=RolloutStrategy.WAVES,
            max_failure_count=5,
        )
        
        rollout = FleetRollout(
            config=config,
            total_deployed=10,
            total_failed=10,  # More than max
        )
        
        should_halt, reason = rollout.should_halt()
        
        assert should_halt is True
    
    def test_should_continue(self):
        """Test continue check."""
        config = RolloutConfig(
            strategy=RolloutStrategy.WAVES,
            min_success_rate=0.9,
        )
        
        rollout = FleetRollout(
            config=config,
            current_wave_index=0,
        )
        
        rollout.waves = [
            RolloutWave(
                wave_id="w1",
                wave_number=1,
                devices_deployed=10,
                devices_succeeded=9,
            )
        ]
        
        should_continue, _ = rollout.should_continue()
        
        assert should_continue is True


class TestFleetCoordinator:
    """Test FleetCoordinator class."""
    
    @pytest.fixture
    def coordinator(self):
        """Create coordinator with config."""
        config = RolloutConfig(
            strategy=RolloutStrategy.WAVES,
            wave_size_percentage=20.0,
        )
        
        rollout = FleetRollout(
            firmware_version="1.0.0",
            config=config,
            target_devices=[f"device_{i}" for i in range(10)],
        )
        
        return FleetCoordinator(rollout=rollout)
    
    def test_setup_waves_immediate(self):
        """Test wave setup for immediate strategy."""
        config = RolloutConfig(
            strategy=RolloutStrategy.IMMEDIATE,
        )
        
        rollout = FleetRollout(
            config=config,
            target_devices=[f"device_{i}" for i in range(5)],
        )
        
        coordinator = FleetCoordinator(rollout=rollout)
        
        # Should have single wave
        assert len(rollout.waves) == 1
        assert rollout.waves[0].target_percentage == 100.0
    
    def test_setup_waves_canary(self):
        """Test wave setup for canary strategy."""
        config = RolloutConfig(
            strategy=RolloutStrategy.CANARY,
            canary_percentage=10.0,
        )
        
        rollout = FleetRollout(
            config=config,
            target_devices=[f"device_{i}" for i in range(10)],
        )
        
        coordinator = FleetCoordinator(rollout=rollout)
        
        # Should have canary wave + main wave
        assert len(rollout.waves) == 2
        assert rollout.waves[0].target_percentage == 10.0  # Canary
    
    def test_setup_waves_staged(self):
        """Test wave setup for staged strategy."""
        config = RolloutConfig(
            strategy=RolloutStrategy.WAVES,
            initial_wave_size=10.0,
            wave_size_percentage=30.0,
        )
        
        rollout = FleetRollout(
            config=config,
            target_devices=[f"device_{i}" for i in range(10)],
        )
        
        coordinator = FleetCoordinator(rollout=rollout)
        
        # Should have multiple waves
        assert len(rollout.waves) >= 2
        # First wave is smaller
        assert rollout.waves[0].target_percentage == 10.0
    
    def test_get_next_wave_devices(self):
        """Test getting devices for next wave."""
        config = RolloutConfig(
            strategy=RolloutStrategy.IMMEDIATE,
        )
        
        rollout = FleetRollout(
            config=config,
            target_devices=[f"device_{i}" for i in range(5)],
        )
        
        coordinator = FleetCoordinator(rollout=rollout)
        
        # Should return all devices for immediate strategy
        devices = rollout.get_next_wave_devices()
        
        assert len(devices) == 5
    
    def test_get_rollout_status(self):
        """Test getting rollout status."""
        config = RolloutConfig(
            strategy=RolloutStrategy.IMMEDIATE,
        )
        
        rollout = FleetRollout(
            firmware_version="1.0.0",
            firmware_hash="abc123",
            config=config,
        )
        
        coordinator = FleetCoordinator(rollout=rollout)
        
        status = coordinator.get_rollout_status()
        
        assert "rollout_id" in status
        assert status["firmware_version"] == "1.0.0"


class TestCanaryAnalyzer:
    """Test CanaryAnalyzer class."""
    
    def test_analyze_stability_score(self):
        """Test stability score calculation."""
        config = RolloutConfig(
            strategy=RolloutStrategy.CANARY,
        )
        
        rollout = FleetRollout(
            config=config,
        )
        
        rollout.waves = [
            RolloutWave(
                wave_id="canary",
                wave_number=1,
                devices_deployed=10,
                devices_succeeded=9,
                devices_failed=1,
            )
        ]
        
        analyzer = CanaryAnalyzer(rollout=rollout)
        
        # Should calculate stability score
        # Success rate = 0.9, so score should be decent
        score = analyzer._calculate_stability_score(rollout.waves[0])
        
        assert 0.0 <= score <= 1.0
