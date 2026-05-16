"""Integration module: multi-agent integration."""

from src.domains.hardware_engine.integration.hw_agent import HardwareAgent
from src.domains.hardware_engine.integration.adapter import HardwareEngineAdapter

__all__ = ["HardwareAgent", "HardwareEngineAdapter"]
