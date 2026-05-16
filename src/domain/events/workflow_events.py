"""Workflow events domain module."""

from dataclasses import dataclass


@dataclass
class WorkflowEvent:
    """Workflow event."""
    workflow_id: str
    step: int
