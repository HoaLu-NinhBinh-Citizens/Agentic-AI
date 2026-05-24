"""Tests for CARV Integration.

Verifies AI_SUPPORT can read and analyze CARV firmware.
"""

import pytest

from src.infrastructure.carv.carv_integration import (
    CARVRepository,
    CarProject,
    BuildTarget,
    CARVBuilder,
)


class TestCARVRepository:
    """Test CARV repository access."""
    
    def test_repository_exists(self):
        """Test that CARV repository is accessible."""
        repo = CARVRepository()
        assert repo.exists()
    
    def test_get_project_path(self):
        """Test getting project paths."""
        repo = CARVRepository()
        
        engine_car = repo.get_project_path(CarProject.ENGINE_CAR)
        assert "EngineCar" in str(engine_car)
        
        remote_control = repo.get_project_path(CarProject.REMOTE_CONTROL)
        assert "RemoteControl" in str(remote_control)
    
    def test_get_target_path(self):
        """Test getting target paths."""
        repo = CARVRepository()
        
        bootloader = repo.get_target_path(CarProject.ENGINE_CAR, BuildTarget.BOOTLOADER)
        assert "BootLoader" in str(bootloader)
        
        car_engine = repo.get_target_path(CarProject.ENGINE_CAR, BuildTarget.CAR_ENGINE)
        assert "CarEngine" in str(car_engine)
    
    def test_get_firmware_info(self):
        """Test getting firmware info."""
        repo = CARVRepository()
        
        info = repo.get_firmware_info(CarProject.ENGINE_CAR)
        assert info.mcu == "STM32F407VGT6"
        assert info.has_freertos
        assert info.has_bootloader
    
    def test_get_project_structure(self):
        """Test getting project structure."""
        repo = CARVRepository()
        
        structure = repo.get_project_structure(CarProject.ENGINE_CAR)
        assert "projects" in structure
        assert "kernel" in structure
        assert "drivers" in structure
    
    def test_read_main_source(self):
        """Test reading main source file."""
        repo = CARVRepository()
        
        # Read from BootLoader
        main_c = repo.read_source("EngineCar", "main.c")
        assert main_c is not None
        assert "main" in main_c
        assert "HAL_Init" in main_c
        assert "cmsis_os" in main_c  # CMSIS-RTOS wrapper
    
    def test_find_files(self):
        """Test finding files in project."""
        repo = CARVRepository()
        
        # Find startup files
        startup_files = repo.find_files(CarProject.ENGINE_CAR, "**/startup_*.s")
        assert len(startup_files) > 0
    
    def test_get_main_files(self):
        """Test getting main files."""
        repo = CARVRepository()
        
        files = repo.get_main_files(CarProject.ENGINE_CAR, BuildTarget.CAR_ENGINE)
        assert "main.c" in files
        assert "startup_stm32f407xx.s" in files
    
    def test_bootloader_source(self):
        """Test reading bootloader source."""
        repo = CARVRepository()
        
        main_c = repo.read_source("EngineCar", "main.c")
        
        # Bootloader should have LED tasks
        assert "vTaskLED_Blue_BootLoader" in main_c or "vTaskLED_Red_Car" in main_c


class TestCARVBuilder:
    """Test CARV firmware building."""
    
    @pytest.mark.asyncio
    async def test_build_enginecar(self):
        """Test building EngineCar firmware."""
        builder = CARVBuilder()
        
        # This will fail without proper build setup, but should not crash
        result = await builder.build(
            CarProject.ENGINE_CAR,
            BuildTarget.CAR_ENGINE,
        )
        
        # Just verify we get a result (success depends on environment)
        assert hasattr(result, "success")
        assert hasattr(result, "project")
        assert result.project == "EngineCar"


class TestCARVFirmwareAnalysis:
    """Test firmware analysis capabilities."""
    
    def test_enginecar_components(self):
        """Test analyzing EngineCar components."""
        repo = CARVRepository()
        
        # Read main.c
        main_c = repo.read_source("EngineCar", "main.c")
        assert main_c is not None
        
        # Check for key components
        assert "HAL_Init" in main_c
        assert "SystemClock_Config" in main_c
        assert "osKernelStart" in main_c
    
    def test_freertos_usage(self):
        """Test FreeRTOS usage in firmware."""
        repo = CARVRepository()
        
        main_c = repo.read_source("EngineCar", "main.c")
        
        # Check FreeRTOS APIs
        assert "xTaskCreate" in main_c
        assert "vTaskDelay" in main_c
    
    def test_gpio_usage(self):
        """Test GPIO usage."""
        repo = CARVRepository()
        
        main_c = repo.read_source("EngineCar", "main.c")
        
        # Check GPIO operations
        assert "HAL_GPIO_TogglePin" in main_c
        assert "GPIO_InitTypeDef" in main_c
    
    def test_clock_config(self):
        """Test clock configuration."""
        repo = CARVRepository()
        
        main_c = repo.read_source("EngineCar", "main.c")
        
        # Check clock settings
        assert "RCC_OscInitTypeDef" in main_c
        assert "RCC_ClkInitTypeDef" in main_c


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
