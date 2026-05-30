"""Legacy alias for src.core.config.output_policy module."""

from src.core.config.output_policy import OutputPolicy
from src.config.ai_support_config import (
    AISupportConfig,
    RuleConfig,
    MLRuleConfig,
    IndexingConfig,
    OutputConfig,
)

__all__ = ["OutputPolicy", "AISupportConfig", "RuleConfig", "MLRuleConfig", "IndexingConfig", "OutputConfig"]
