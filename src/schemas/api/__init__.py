"""API schemas module."""

from typing import Any


class TaskSchema:
    """Task request/response schema."""
    
    @staticmethod
    def validate(data: dict[str, Any]) -> bool:
        """Validate task data."""
        return "description" in data
