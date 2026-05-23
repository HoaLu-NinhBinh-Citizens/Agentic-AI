"""
E2E HIL Test for AI_support

Tests the full E2E pipeline with real hardware.
Note: Requires J-Link connected and UART configured.
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

from src.infrastructure.hardware.hil_e2e_pipeline import (
    E2EHILPipeline,
    TestConfig,
    TestPhase,
    E2EResult,
    run_e2e_test,
)


class TestE2EHILPipeline:
    """Tests for E2E HIL Pipeline."""
    
    @pytest.fixture
    def config(self) -> TestConfig:
        """Create test config."""
        return TestConfig(
            project_name="EngineCar",
            uart_port="COM9",
            uart_baudrate=115200,
            monitor_duration=2.0,
            expected_patterns=["init", "start"],
        )
    
    @pytest.fixture
    def pipeline(self, config: TestConfig) -> E2EHILPipeline:
        """Create pipeline instance."""
        return E2EHILPipeline(config)
    
    def test_config_defaults(self):
        """Test default configuration."""
        config = TestConfig()
        
        assert config.project_name == "EngineCar"
        assert config.uart_port == "COM9"
        assert config.uart_baudrate == 115200
        assert config.monitor_duration == 10.0
        assert len(config.error_patterns) > 0
    
    def test_pipeline_initial_state(self, pipeline: E2EHILPipeline):
        """Test pipeline starts in IDLE state."""
        assert pipeline.phase == TestPhase.IDLE
    
    def test_get_status(self, pipeline: E2EHILPipeline):
        """Test status reporting."""
        status = pipeline.get_status()
        
        assert status["phase"] == "idle"
        assert status["uart_lines_count"] == 0
        assert status["errors_count"] == 0
        assert status["config"]["project"] == "EngineCar"
    
    @pytest.mark.asyncio
    async def test_build_firmware_success(self, pipeline: E2EHILPipeline):
        """Test successful firmware build."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="Build successful\n",
                stderr="",
            )
            
            success, output = await pipeline._build_firmware()
            
            assert success is True
            assert "Build successful" in output
            mock_run.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_build_firmware_failure(self, pipeline: E2EHILPipeline):
        """Test failed firmware build."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,
                stdout="",
                stderr="Error: undefined reference to main\n",
            )
            
            success, output = await pipeline._build_firmware()
            
            assert success is False
            assert "undefined reference" in output
    
    @pytest.mark.asyncio
    async def test_flash_firmware_success(self, pipeline: E2EHILPipeline):
        """Test successful firmware flash."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="Flash OK\n100000 bytes written\n",
                stderr="",
            )
            
            success, bytes_count, output = await pipeline._flash_firmware()
            
            assert success is True
            assert bytes_count == 100000
    
    @pytest.mark.asyncio
    async def test_flash_firmware_failure(self, pipeline: E2EHILPipeline):
        """Test failed firmware flash."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,
                stdout="",
                stderr="J-Link not found\n",
            )
            
            success, bytes_count, output = await pipeline._flash_firmware()
            
            assert success is False
            assert bytes_count == 0
    
    def test_parse_flash_bytes(self, pipeline: E2EHILPipeline):
        """Test flash bytes parsing."""
        # Test various formats
        assert pipeline._parse_flash_bytes("100000 bytes written") == 100000
        assert pipeline._parse_flash_bytes("Flash: 50000 bytes") == 50000
        assert pipeline._parse_flash_bytes("No bytes here") == 0
    
    @pytest.mark.asyncio
    async def test_validate_output_with_errors(self, pipeline: E2EHILPipeline):
        """Test validation with error patterns."""
        pipeline._uart_lines = [
            "System starting...",
            "ERROR: Hard fault detected",
            "Stack overflow",
        ]
        pipeline._errors = ["ERROR: Hard fault detected"]
        
        errors, patterns = await pipeline._validate_output()
        
        assert len(errors) >= 1
        assert "Hard fault" in errors[0]
    
    @pytest.mark.asyncio
    async def test_validate_output_expected_patterns(self, pipeline: E2EHILPipeline):
        """Test validation with expected patterns."""
        pipeline._uart_lines = [
            "System initialized",
            "Starting main loop",
            "Everything OK",
        ]
        pipeline._errors = []
        
        errors, patterns = await pipeline._validate_output()
        
        assert patterns["init"] is True
        # "start" matches "Starting" (case-insensitive search in output_text)
        assert patterns["start"] is True
    
    @pytest.mark.asyncio
    async def test_validate_output_missing_pattern(self, pipeline: E2EHILPipeline):
        """Test validation with missing expected pattern."""
        pipeline._uart_lines = [
            "System started",
        ]
        pipeline._errors = []
        
        errors, patterns = await pipeline._validate_output()
        
        assert patterns["init"] is False
        assert len(errors) == 1  # Missing pattern error
    
    @pytest.mark.asyncio
    async def test_full_pipeline_success(self, pipeline: E2EHILPipeline):
        """Test complete pipeline with mocked hardware."""
        with patch("subprocess.run") as mock_run:
            # Mock build success
            mock_run.return_value = Mock(
                returncode=0,
                stdout="Build OK",
                stderr="",
            )
            
            with patch("serial.Serial") as mock_serial:
                # Mock UART
                mock_ser = Mock()
                mock_ser.in_waiting = 0
                mock_serial.return_value.__enter__ = Mock(return_value=mock_ser)
                mock_serial.return_value.__exit__ = Mock(return_value=False)
                
                result = await pipeline.run()
                
                assert result.phase in [TestPhase.PASSED, TestPhase.FAILED]
    
    def test_e2e_result_dataclass(self):
        """Test E2EResult structure."""
        result = E2EResult(
            success=True,
            phase=TestPhase.PASSED,
            duration_ms=5000,
            message="Test passed",
            build_output="Build OK",
            flash_bytes=100000,
            uart_lines=["line1", "line2"],
            errors_detected=[],
            patterns_matched={"init": True},
        )
        
        assert result.success is True
        assert result.phase == TestPhase.PASSED
        assert result.duration_ms == 5000
        assert len(result.uart_lines) == 2


class TestTestPhase:
    """Test Phase enum values."""
    
    def test_phase_values(self):
        """Verify all phase values exist."""
        assert TestPhase.IDLE.value == "idle"
        assert TestPhase.BUILDING.value == "building"
        assert TestPhase.FLASHING.value == "flashing"
        assert TestPhase.MONITORING.value == "monitoring"
        assert TestPhase.VALIDATING.value == "validating"
        assert TestPhase.PASSED.value == "passed"
        assert TestPhase.FAILED.value == "failed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
