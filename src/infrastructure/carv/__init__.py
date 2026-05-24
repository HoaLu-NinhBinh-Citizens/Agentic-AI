"""CARV Firmware Integration for AI_SUPPORT.

Provides AI-powered access to CARV firmware:
- Repository access and analysis
- Firmware building
- Hardware flashing
- Debug and verification
"""

from src.infrastructure.carv.carv_integration import (
    CARVRepository,
    CARVBuilder,
    CARVFlashing,
    CarProject,
    BuildTarget,
    CARVFirmwareInfo,
    BuildResult,
    FlashResult,
)
from src.infrastructure.carv.carv_tools import (
    CARVTools,
    FirmwareAnalysis,
    EngineeringTask,
    get_crv_tools,
)

__all__ = [
    # Core
    "CARVRepository",
    "CARVBuilder",
    "CARVFlashing",
    # Enums
    "CarProject",
    "BuildTarget",
    # Types
    "CARVFirmwareInfo",
    "BuildResult",
    "FlashResult",
    "FirmwareAnalysis",
    "EngineeringTask",
    # Tools
    "CARVTools",
    "get_crv_tools",
]
