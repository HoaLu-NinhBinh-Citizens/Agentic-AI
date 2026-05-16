"""
AI_SUPPORT Security Module

Provides security validation for firmware generation:
- Pre-patch vulnerability scanning
- Dangerous action detection
- Permission model for AI operations
"""

from src.infrastructure.security.validator import (
    SecurityValidator,
    SecurityValidationResult,
    SecurityFinding,
    SecurityLevel,
    ActionCategory,
    validate_before_execution,
)

__all__ = [
    "SecurityValidator",
    "SecurityValidationResult",
    "SecurityFinding",
    "SecurityLevel",
    "ActionCategory",
    "validate_before_execution",
]
