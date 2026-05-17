"""Unit tests for validation engine."""

import pytest

from src.infrastructure.cache.tool.validation import (
    PoisonValidationEngine,
    ValidationConfig,
)
from src.infrastructure.cache.tool.types import ValidationResult, ValidationReason


class TestPoisonValidationEngine:
    """Tests for PoisonValidationEngine."""

    @pytest.fixture
    def validator(self):
        """Create a fresh validator."""
        return PoisonValidationEngine()

    def test_validate_none_rejected(self, validator):
        """Test that None values are rejected."""
        result = validator.validate("tool1", None)

        assert result.valid is False
        assert result.reason == ValidationReason.NOT_CACHEABLE

    def test_validate_primitive_types(self, validator):
        """Test validation of primitive types."""
        assert validator.validate("tool1", "string").valid
        assert validator.validate("tool1", 123).valid
        assert validator.validate("tool1", 45.67).valid
        assert validator.validate("tool1", True).valid
        assert validator.validate("tool1", {"key": "value"}).valid
        assert validator.validate("tool1", [1, 2, 3]).valid

    def test_validate_allows_none_when_configured(self, validator):
        """Test None allowed when configured."""
        validator.config.allow_none = True
        result = validator.validate("tool1", None)

        assert result.valid

    def test_size_limit_exceeded(self, validator):
        """Test size limit enforcement."""
        validator.config.max_value_size_bytes = 10

        large_value = "x" * 100
        result = validator.validate("tool1", large_value)

        assert result.valid is False
        assert result.reason == ValidationReason.SIZE_LIMIT_EXCEEDED

    def test_custom_validator(self, validator):
        """Test custom validator registration."""
        def my_validator(value):
            if not isinstance(value, dict):
                return ValidationResult.failure(
                    ValidationReason.VALIDATION_FAILED,
                    "Must be a dict",
                )
            return ValidationResult.success()

        validator.register_custom_validator("tool1", my_validator)

        assert validator.validate("tool1", {"key": "value"}).valid
        assert validator.validate("tool1", "not a dict").valid is False

    def test_basic_validation_dict_keys(self, validator):
        """Test strict mode validation of dict keys."""
        validator.config.enable_strict_mode = True

        result = validator.validate("tool1", {(1, 2): "value"})
        assert result.valid is False
        assert result.reason == ValidationReason.VALIDATION_FAILED

    def test_clear(self, validator):
        """Test clearing registered validators."""
        validator.register_custom_validator("tool1", lambda v: ValidationResult.success())
        validator.clear()

        assert "tool1" not in validator._custom_validators


class TestValidationConfig:
    """Tests for ValidationConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ValidationConfig()

        assert config.max_value_size_bytes == 10 * 1024 * 1024
        assert config.enable_pydantic is True
        assert config.enable_strict_mode is True
        assert config.allow_none is False
