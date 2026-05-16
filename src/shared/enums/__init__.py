"""Shared enums module."""

from enum import Enum


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
