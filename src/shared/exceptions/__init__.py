"""Shared exceptions module."""


class AISupportError(Exception):
    """Base exception for AI_support."""
    pass


class AgentError(AISupportError):
    """Agent execution error."""
    pass


class ConfigurationError(AISupportError):
    """Configuration error."""
    pass


class ValidationError(AISupportError):
    """Validation error."""
    pass
