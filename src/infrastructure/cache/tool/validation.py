"""Poison Validation Engine with Pydantic/strict schema validation.

Never silently cache invalid data.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Any, Callable, Optional, Type

from typing_extensions import Self

from src.infrastructure.cache.tool.types import ValidationReason, ValidationResult

logger = logging.getLogger(__name__)


@dataclass
class ValidationConfig:
    """Configuration for validation."""

    max_value_size_bytes: int = 10 * 1024 * 1024
    enable_pydantic: bool = True
    enable_strict_mode: bool = True
    allow_none: bool = False
    allow_complex_types: bool = True


class PoisonValidationEngine:
    """Poison validation engine.

    Modes:
    - Pydantic schema validation
    - Custom validator function

    Fail behavior:
    - set() → (False, reason)
    - reason ∈ {NOT_CACHEABLE, VALIDATION_FAILED, SIZE_LIMIT_EXCEEDED, SERIALIZATION_ERROR}

    Rule: Never silently cache invalid data.
    """

    def __init__(self, config: ValidationConfig | None = None) -> None:
        self.config = config or ValidationConfig()
        self._pydantic_schemas: dict[str, Type] = {}
        self._custom_validators: dict[str, Callable[[Any], ValidationResult]] = {}

    def register_pydantic_schema(
        self,
        tool_name: str,
        schema_class: Type,
    ) -> None:
        """Register a Pydantic schema for a tool.

        Args:
            tool_name: Tool name
            schema_class: Pydantic model class
        """
        self._pydantic_schemas[tool_name] = schema_class
        logger.debug(f"Registered Pydantic schema for tool: {tool_name}")

    def register_custom_validator(
        self,
        tool_name: str,
        validator: Callable[[Any], ValidationResult],
    ) -> None:
        """Register a custom validator for a tool.

        Args:
            tool_name: Tool name
            validator: Function that returns ValidationResult
        """
        self._custom_validators[tool_name] = validator
        logger.debug(f"Registered custom validator for tool: {tool_name}")

    def validate(
        self,
        tool_name: str,
        value: Any,
    ) -> ValidationResult:
        """Validate a value for caching.

        Args:
            tool_name: Tool name
            value: Value to validate

        Returns:
            ValidationResult with success/failure
        """
        if value is None:
            if not self.config.allow_none:
                return ValidationResult.failure(
                    ValidationReason.NOT_CACHEABLE,
                    "None values are not cacheable",
                )
            return ValidationResult.success()

        size_result = self._check_size(value)
        if not size_result.valid:
            return size_result

        if tool_name in self._custom_validators:
            return self._custom_validators[tool_name](value)

        if tool_name in self._pydantic_schemas and self.config.enable_pydantic:
            return self._validate_pydantic(tool_name, value)

        return self._validate_basic(tool_name, value)

    def _check_size(self, value: Any) -> ValidationResult:
        """Check if value size is within limits."""
        size = self._estimate_size(value)

        if size > self.config.max_value_size_bytes:
            return ValidationResult.failure(
                ValidationReason.SIZE_LIMIT_EXCEEDED,
                f"Value size {size} exceeds limit {self.config.max_value_size_bytes}",
            )

        return ValidationResult.success()

    def _estimate_size(self, value: Any) -> int:
        """Estimate size of value in bytes."""
        if value is None:
            return 0

        if isinstance(value, str):
            return len(value.encode("utf-8"))

        if isinstance(value, (int, float, bool)):
            return sys.getsizeof(value)

        if isinstance(value, bytes):
            return len(value)

        if isinstance(value, dict):
            size = sys.getsizeof(value)
            for k, v in value.items():
                size += self._estimate_size(k) + self._estimate_size(v)
            return size

        if isinstance(value, (list, tuple)):
            size = sys.getsizeof(value)
            for item in value:
                size += self._estimate_size(item)
            return size

        try:
            serialized = str(value)
            return len(serialized.encode("utf-8"))
        except Exception:
            return sys.getsizeof(value)

    def _validate_basic(self, tool_name: str, value: Any) -> ValidationResult:
        """Basic validation for unregistered tools."""
        if not self.config.allow_complex_types:
            allowed = (int, float, bool, str, type(None), list, tuple, dict)
            if not isinstance(value, allowed):
                return ValidationResult.failure(
                    ValidationReason.NOT_CACHEABLE,
                    f"Type {type(value).__name__} is not cacheable",
                )

        if self.config.enable_strict_mode:
            if isinstance(value, dict):
                if not all(isinstance(k, (str, int)) for k in value.keys()):
                    return ValidationResult.failure(
                        ValidationReason.VALIDATION_FAILED,
                        "Dict keys must be str or int in strict mode",
                    )

        try:
            self._test_serializable(value)
            return ValidationResult.success()
        except Exception as e:
            return ValidationResult.failure(
                ValidationReason.SERIALIZATION_ERROR,
                f"Value is not serializable: {e}",
            )

    def _validate_pydantic(self, tool_name: str, value: Any) -> ValidationResult:
        """Validate using Pydantic schema."""
        schema_class = self._pydantic_schemas[tool_name]

        try:
            if hasattr(schema_class, "model_validate"):
                schema_class.model_validate(value)
            elif hasattr(schema_class, "validate"):
                schema_class.validate(value)
            else:
                schema_class(value)

            return ValidationResult.success()
        except Exception as e:
            return ValidationResult.failure(
                ValidationReason.VALIDATION_FAILED,
                f"Pydantic validation failed: {e}",
            )

    def _test_serializable(self, value: Any) -> None:
        """Test if value is JSON serializable."""
        import json

        json.dumps(value, default=str)

    def clear(self) -> None:
        """Clear all registered validators."""
        self._pydantic_schemas.clear()
        self._custom_validators.clear()
