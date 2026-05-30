"""Configuration loader for detector rules.

This module provides a unified interface for loading and managing detector
rule configurations from YAML files.

Usage:
    loader = DetectorConfigLoader()
    ml_rules = loader.load_ml_rules()
    security_rules = loader.load_security_rules()
    quality_rules = loader.load_quality_rules()

    # Hot reload configs
    loader.reload()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class RuleConfig:
    """Configuration for a single detector rule.

    Attributes:
        name: Human-readable rule name
        enabled: Whether the rule is active
        severity: Rule severity level (critical, high, medium, warning, info)
        confidence_threshold: Minimum confidence to report findings
        description: Brief description of what the rule detects
        patterns: List of regex patterns or code snippets to match
        fix_template: Template for suggested fix
        explanation: Detailed explanation of the issue
        cwe_id: Related CWE identifier
        tags: List of tags for categorization
        max_lines_per_function: Optional limit for function-related rules
        max_parameters: Optional limit for parameter-related rules
        max_cyclomatic_complexity: Optional limit for complexity rules
    """
    name: str
    enabled: bool = True
    severity: str = "medium"
    confidence_threshold: float = 0.70
    description: str = ""
    patterns: list[str] = field(default_factory=list)
    fix_template: str = ""
    explanation: str = ""
    cwe_id: str = ""
    tags: list[str] = field(default_factory=list)
    # Optional fields for specific rule types
    max_lines_per_function: Optional[int] = None
    max_parameters: Optional[int] = None
    max_cyclomatic_complexity: Optional[int] = None

    @classmethod
    def from_dict(cls, rule_id: str, data: dict[str, Any]) -> "RuleConfig":
        """Create RuleConfig from a dictionary.

        Args:
            rule_id: The rule identifier (e.g., "ML001")
            data: Dictionary containing rule configuration

        Returns:
            RuleConfig instance
        """
        return cls(
            name=data.get("name", rule_id),
            enabled=data.get("enabled", True),
            severity=data.get("severity", "medium"),
            confidence_threshold=data.get("confidence_threshold", 0.70),
            description=data.get("description", ""),
            patterns=data.get("patterns", []),
            fix_template=data.get("fix_template", ""),
            explanation=data.get("explanation", ""),
            cwe_id=data.get("cwe_id", ""),
            tags=data.get("tags", []),
            max_lines_per_function=data.get("max_lines_per_function"),
            max_parameters=data.get("max_parameters"),
            max_cyclomatic_complexity=data.get("max_cyclomatic_complexity"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            "name": self.name,
            "enabled": self.enabled,
            "severity": self.severity,
            "confidence_threshold": self.confidence_threshold,
            "description": self.description,
            "patterns": self.patterns,
            "fix_template": self.fix_template,
            "explanation": self.explanation,
            "cwe_id": self.cwe_id,
            "tags": self.tags,
        }
        if self.max_lines_per_function is not None:
            result["max_lines_per_function"] = self.max_lines_per_function
        if self.max_parameters is not None:
            result["max_parameters"] = self.max_parameters
        if self.max_cyclomatic_complexity is not None:
            result["max_cyclomatic_complexity"] = self.max_cyclomatic_complexity
        return result


class DetectorConfigLoader:
    """Loads and manages detector rule configurations from YAML files.

    This class provides a unified interface for loading ML, security, and
    quality detection rules from configuration files. It supports hot reloading
    for development workflows.

    Attributes:
        config_dir: Directory containing YAML configuration files
        _ml_rules: Cached ML rules configuration
        _security_rules: Cached security rules configuration
        _quality_rules: Cached quality rules configuration

    Example:
        >>> loader = DetectorConfigLoader()
        >>> ml_rules = loader.load_ml_rules()
        >>> rule = ml_rules.get("ML001")
        >>> if rule and rule.enabled:
        ...     print(f"ML001 is enabled with {rule.confidence_threshold} threshold")
    """

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        """Initialize the config loader.

        Args:
            config_dir: Directory containing detector YAML files.
                       Defaults to configs/detectors/ relative to project root.
        """
        if config_dir is None:
            # Default to configs/detectors/ in project root
            config_dir = Path(__file__).parent.parent.parent.parent / "configs" / "detectors"

        self.config_dir = Path(config_dir)
        self._ml_rules: Optional[dict[str, RuleConfig]] = None
        self._security_rules: Optional[dict[str, RuleConfig]] = None
        self._quality_rules: Optional[dict[str, RuleConfig]] = None
        self._last_load_time: float = 0.0

    def _load_yaml(self, filename: str) -> dict[str, Any]:
        """Load and parse a YAML configuration file.

        Args:
            filename: Name of the YAML file (e.g., "ml_rules.yaml")

        Returns:
            Parsed YAML content as dictionary

        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If YAML parsing fails
        """
        config_path = self.config_dir / filename

        if not config_path.exists():
            logger.warning(f"Config file not found: {config_path}")
            return {}

        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def load_ml_rules(self, use_cache: bool = True) -> dict[str, RuleConfig]:
        """Load ML detection rules from YAML configuration.

        Args:
            use_cache: If True, return cached rules if available

        Returns:
            Dictionary mapping rule IDs to RuleConfig objects
        """
        if use_cache and self._ml_rules is not None:
            return self._ml_rules

        self._ml_rules = {}
        data = self._load_yaml("ml_rules.yaml")

        if "ml_rules" in data:
            for rule_id, rule_data in data["ml_rules"].items():
                self._ml_rules[rule_id] = RuleConfig.from_dict(rule_id, rule_data)

        logger.debug(f"Loaded {len(self._ml_rules)} ML rules")
        return self._ml_rules

    def load_security_rules(self, use_cache: bool = True) -> dict[str, RuleConfig]:
        """Load security detection rules from YAML configuration.

        Args:
            use_cache: If True, return cached rules if available

        Returns:
            Dictionary mapping rule IDs to RuleConfig objects
        """
        if use_cache and self._security_rules is not None:
            return self._security_rules

        self._security_rules = {}
        data = self._load_yaml("security_rules.yaml")

        if "security_rules" in data:
            for rule_id, rule_data in data["security_rules"].items():
                self._security_rules[rule_id] = RuleConfig.from_dict(rule_id, rule_data)

        logger.debug(f"Loaded {len(self._security_rules)} security rules")
        return self._security_rules

    def load_quality_rules(self, use_cache: bool = True) -> dict[str, RuleConfig]:
        """Load quality detection rules from YAML configuration.

        Args:
            use_cache: If True, return cached rules if available

        Returns:
            Dictionary mapping rule IDs to RuleConfig objects
        """
        if use_cache and self._quality_rules is not None:
            return self._quality_rules

        self._quality_rules = {}
        data = self._load_yaml("quality_rules.yaml")

        if "quality_rules" in data:
            for rule_id, rule_data in data["quality_rules"].items():
                self._quality_rules[rule_id] = RuleConfig.from_dict(rule_id, rule_data)

        logger.debug(f"Loaded {len(self._quality_rules)} quality rules")
        return self._quality_rules

    def load_all_rules(self) -> dict[str, dict[str, RuleConfig]]:
        """Load all detector rule configurations.

        Returns:
            Dictionary with keys "ml", "security", "quality" mapping to rule dictionaries
        """
        return {
            "ml": self.load_ml_rules(),
            "security": self.load_security_rules(),
            "quality": self.load_quality_rules(),
        }

    def reload(self) -> None:
        """Hot reload all configurations from disk.

        Clears the cache and reloads all YAML files. Useful for development
        workflows where config changes should take effect without restart.
        """
        logger.info("Reloading detector configurations")
        self._ml_rules = None
        self._security_rules = None
        self._quality_rules = None
        # Pre-load to verify all configs are valid
        self.load_all_rules()
        logger.info("Detector configurations reloaded successfully")

    def get_rule(
        self,
        category: str,
        rule_id: str,
    ) -> Optional[RuleConfig]:
        """Get a specific rule by category and ID.

        Args:
            category: Rule category ("ml", "security", or "quality")
            rule_id: Rule identifier (e.g., "ML001", "SEC001")

        Returns:
            RuleConfig if found, None otherwise
        """
        if category == "ml":
            rules = self.load_ml_rules()
        elif category == "security":
            rules = self.load_security_rules()
        elif category == "quality":
            rules = self.load_quality_rules()
        else:
            logger.warning(f"Unknown rule category: {category}")
            return None

        return rules.get(rule_id)

    def get_enabled_rules(self, category: str) -> dict[str, RuleConfig]:
        """Get only enabled rules from a category.

        Args:
            category: Rule category ("ml", "security", or "quality")

        Returns:
            Dictionary of only enabled rules
        """
        rules = self.load_all_rules().get(category, {})
        return {rid: cfg for rid, cfg in rules.items() if cfg.enabled}

    def validate_config(self) -> list[str]:
        """Validate all loaded configurations.

        Returns:
            List of validation error messages (empty if all valid)
        """
        errors: list[str] = []

        for category in ["ml", "security", "quality"]:
            rules = self.load_all_rules().get(category, {})

            for rule_id, rule in rules.items():
                # Check for empty name
                if not rule.name:
                    errors.append(f"{rule_id}: Rule name is empty")

                # Check for invalid severity
                valid_severities = {"critical", "high", "medium", "warning", "info"}
                if rule.severity.lower() not in valid_severities:
                    errors.append(
                        f"{rule_id}: Invalid severity '{rule.severity}'"
                    )

                # Check confidence threshold range
                if not 0.0 <= rule.confidence_threshold <= 1.0:
                    errors.append(
                        f"{rule_id}: Invalid confidence_threshold "
                        f"{rule.confidence_threshold} (must be 0.0-1.0)"
                    )

        return errors


# Global config loader instance for convenience
_default_loader: Optional[DetectorConfigLoader] = None


def get_config_loader() -> DetectorConfigLoader:
    """Get the global config loader instance.

    Returns:
        Singleton DetectorConfigLoader instance
    """
    global _default_loader
    if _default_loader is None:
        _default_loader = DetectorConfigLoader()
    return _default_loader


def load_ml_rules() -> dict[str, RuleConfig]:
    """Convenience function to load ML rules.

    Returns:
        Dictionary of ML rule configurations
    """
    return get_config_loader().load_ml_rules()


def load_security_rules() -> dict[str, RuleConfig]:
    """Convenience function to load security rules.

    Returns:
        Dictionary of security rule configurations
    """
    return get_config_loader().load_security_rules()


def load_quality_rules() -> dict[str, RuleConfig]:
    """Convenience function to load quality rules.

    Returns:
        Dictionary of quality rule configurations
    """
    return get_config_loader().load_quality_rules()
