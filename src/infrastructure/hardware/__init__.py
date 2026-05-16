"""
Hardware-in-the-Loop (HIL) Testing Module

Provides hardware integration capabilities for AI Agent:
- UART Monitor: Real-time serial output monitoring
- CAN Analyzer: CAN bus message parsing and analysis
- HIL Agent: AI Agent integration for hardware testing
- E2E Pipeline: End-to-end firmware test pipeline

Usage:
    from src.infrastructure.hardware import UartMonitor, CanAnalyzer, HilAgent
    from src.infrastructure.hardware import E2EHILPipeline, FlashConfig, FlashMode
"""

from src.infrastructure.hardware.uart_monitor import UartMonitor, UartConfig, UartMessage
from src.infrastructure.hardware.can_analyzer import CanAnalyzer, CanConfig, CanMessage
from src.infrastructure.hardware.hil_agent import (
    HilAgent, HilSession, HilResult, HilPhase, HilStatus,
    MockUartMonitor,
)
from src.infrastructure.hardware.hil_e2e_pipeline import (
    E2EHILPipeline, E2EResult, TestConfig, TestPhase,
    FlashConfig, FlashMode,
)

__all__ = [
    # UART
    "UartMonitor",
    "UartConfig",
    "UartMessage",
    "MockUartMonitor",
    # CAN
    "CanAnalyzer",
    "CanConfig",
    "CanMessage",
    # HIL Agent
    "HilAgent",
    "HilSession",
    "HilResult",
    "HilPhase",
    "HilStatus",
    # E2E Pipeline
    "E2EHILPipeline",
    "E2EResult",
    "TestConfig",
    "TestPhase",
    "FlashConfig",
    "FlashMode",
]