"""Shared enums module.

Provides unified severity levels and other common enums for the codebase.
"""

from enum import Enum

# Import unified Severity and backward compatibility aliases
from src.shared.enums.severity import (
    Severity,
    MLSeverity,
    FindingSeverity,
    ReportSeverity,
    ml_to_unified,
    finding_to_unified,
    risk_to_unified,
)


class AgentState(Enum):
    """Agent execution states."""

    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPriority(Enum):
    """Task priority levels."""

    LOW = 1
    NORMAL = 5
    HIGH = 10


__all__ = [
    "Severity",
    "MLSeverity",
    "FindingSeverity",
    "ReportSeverity",
    "AgentState",
    "TaskPriority",
    "ml_to_unified",
    "finding_to_unified",
    "risk_to_unified",
]
