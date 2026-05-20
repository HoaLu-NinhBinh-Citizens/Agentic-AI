"""Compatibility matrix for target-firmware-toolchain compatibility.

This module defines compatibility checking between targets, firmware,
toolchains, and probes using semantic versioning and version ranges.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .firmware import FirmwareMetadata
from .target import ChipSpec


class VersionOperator(Enum):
    """Version comparison operators for specifiers."""

    EQUAL = "=="
    NOT_EQUAL = "!="
    GREATER = ">"
    GREATER_EQUAL = ">="
    LESS = "<"
    LESS_EQUAL = "<="
    COMPATIBLE = "~="  # Compatible operator (major version match)


@dataclass
class VersionSpecifier:
    """A single version specification.

    Examples:
        ">=1.0.0" - Version 1.0.0 or greater
        "==2.1.0" - Exactly version 2.1.0
        "~=1.2" - Compatible with 1.2.x (>=1.2.0, <2.0.0)
        ">=1.0.0,<2.0.0" - Range
    """

    operator: VersionOperator
    major: int
    minor: int
    patch: int
    prerelease: str = ""

    def __str__(self) -> str:
        """String representation."""
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            base += f"-{self.prerelease}"
        return f"{self.operator.value}{base}"

    @classmethod
    def parse(cls, spec: str) -> "VersionSpecifier":
        """Parse version specifier string.

        Args:
            spec: Version specifier string (e.g., ">=1.0.0")

        Returns:
            VersionSpecifier instance
        """
        # Match operator and version
        pattern = r"^(==|!=|>=|<=|>|<|~=)?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-([a-zA-Z0-9.]+))?$"
        match = re.match(pattern, spec.strip())

        if not match:
            raise ValueError(f"Invalid version specifier: {spec}")

        op_str = match.group(1) or "=="
        major = int(match.group(2))
        minor = int(match.group(3) or 0)
        patch = int(match.group(4) or 0)
        prerelease = match.group(5) or ""

        # Map operator string to enum
        op_map = {
            "==": VersionOperator.EQUAL,
            "!=": VersionOperator.NOT_EQUAL,
            ">=": VersionOperator.GREATER_EQUAL,
            "<=": VersionOperator.LESS_EQUAL,
            ">": VersionOperator.GREATER,
            "<": VersionOperator.LESS,
            "~=": VersionOperator.COMPATIBLE,
        }
        operator = op_map.get(op_str, VersionOperator.EQUAL)

        return cls(
            operator=operator,
            major=major,
            minor=minor,
            patch=patch,
            prerelease=prerelease,
        )

    def matches(self, version: tuple[int, int, int, int, int]) -> bool:
        """Check if version tuple matches this specifier.

        Args:
            version: Tuple of (major, minor, patch, prerelease_idx, build_idx)

        Returns:
            True if version matches
        """
        v_maj, v_min, v_pat, v_pre, v_build = version

        if self.operator == VersionOperator.EQUAL:
            return (v_maj, v_min, v_pat) == (self.major, self.minor, self.patch)

        if self.operator == VersionOperator.NOT_EQUAL:
            return (v_maj, v_min, v_pat) != (self.major, self.minor, self.patch)

        if self.operator == VersionOperator.GREATER:
            return (v_maj, v_min, v_pat) > (self.major, self.minor, self.patch)

        if self.operator == VersionOperator.GREATER_EQUAL:
            return (v_maj, v_min, v_pat) >= (self.major, self.minor, self.patch)

        if self.operator == VersionOperator.LESS:
            return (v_maj, v_min, v_pat) < (self.major, self.minor, self.patch)

        if self.operator == VersionOperator.LESS_EQUAL:
            return (v_maj, v_min, v_pat) <= (self.major, self.minor, self.patch)

        # Compatible (~=) - same major, minor >= specified
        if self.operator == VersionOperator.COMPATIBLE:
            if v_maj != self.major:
                return False
            return v_min >= self.minor

        return False


@dataclass
class VersionSpecSet:
    """A set of version specifiers (AND logic)."""

    specifiers: list[VersionSpecifier] = field(default_factory=list)

    def __str__(self) -> str:
        """String representation."""
        return ",".join(str(s) for s in self.specifiers)

    @classmethod
    def parse(cls, spec: str) -> "VersionSpecSet":
        """Parse version specifier set string.

        Args:
            spec: Version specifier string (e.g., ">=1.0.0,<2.0.0")

        Returns:
            VersionSpecSet instance
        """
        parts = spec.split(",")
        specifiers = [VersionSpecifier.parse(p.strip()) for p in parts]
        return cls(specifiers=specifiers)

    def matches(self, version: tuple[int, int, int, int, int]) -> bool:
        """Check if version matches all specifiers.

        Args:
            version: Version tuple

        Returns:
            True if all specifiers match
        """
        return all(s.matches(version) for s in self.specifiers)


@dataclass
class CompatibilityRule:
    """A single compatibility rule."""

    target_family: str
    firmware_version: VersionSpecSet | None = None
    toolchain_version: VersionSpecSet | None = None
    probe_types: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "target_family": self.target_family,
            "firmware_version": str(self.firmware_version) if self.firmware_version else None,
            "toolchain_version": str(self.toolchain_version) if self.toolchain_version else None,
            "probe_types": self.probe_types,
            "warnings": self.warnings,
            "errors": self.errors,
        }


@dataclass
class CompatibilityResult:
    """Result of compatibility check."""

    compatible: bool
    target_family: str
    firmware_version: str | None = None
    toolchain_version: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    matched_rule: CompatibilityRule | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "compatible": self.compatible,
            "target_family": self.target_family,
            "firmware_version": self.firmware_version,
            "toolchain_version": self.toolchain_version,
            "warnings": self.warnings,
            "errors": self.errors,
        }


class CompatibilityMatrix:
    """Matrix of target ↔ firmware ↔ toolchain ↔ probe compatibility.

    This class manages compatibility rules and checks whether
    a specific combination of target, firmware, toolchain, and probe
    is compatible.

    Example YAML configuration:
        compatibility:
          rules:
            - target_family: STM32F4
              firmware_version: ">=1.0.0,<3.0.0"
              toolchain_version: ">=10.0"
              warnings:
                - "Firmware 2.x requires toolchain >= 9.4"
            - target_family: ESP32
              firmware_version: ">=1.0.0"
              probe_types: [ESP_PROG, JLink]
    """

    def __init__(self):
        self._rules: list[CompatibilityRule] = []
        self._default_toolchain_version = ">=0.0"

    def add_rule(self, rule: CompatibilityRule) -> None:
        """Add a compatibility rule.

        Args:
            rule: Compatibility rule to add
        """
        self._rules.append(rule)

    def add_rule_from_dict(self, data: dict[str, Any]) -> None:
        """Add a rule from dictionary.

        Args:
            data: Dictionary with rule data
        """
        firmware_spec = None
        if data.get("firmware_version"):
            firmware_spec = VersionSpecSet.parse(data["firmware_version"])

        toolchain_spec = None
        if data.get("toolchain_version"):
            toolchain_spec = VersionSpecSet.parse(data["toolchain_version"])

        rule = CompatibilityRule(
            target_family=data.get("target_family", ""),
            firmware_version=firmware_spec,
            toolchain_version=toolchain_spec,
            probe_types=data.get("probe_types", []),
            warnings=data.get("warnings", []),
            errors=data.get("errors", []),
        )
        self.add_rule(rule)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompatibilityMatrix":
        """Create from dictionary.

        Args:
            data: Dictionary with compatibility data

        Returns:
            CompatibilityMatrix instance
        """
        matrix = cls()

        rules_data = data.get("rules", [])
        for rule_data in rules_data:
            matrix.add_rule_from_dict(rule_data)

        return matrix

    @classmethod
    def from_yaml_file(cls, path: str) -> "CompatibilityMatrix":
        """Load from YAML file.

        Args:
            path: Path to YAML file

        Returns:
            CompatibilityMatrix instance
        """
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)

        compat_data = data.get("compatibility", data)
        return cls.from_dict(compat_data)

    def check(
        self,
        target_family: str,
        firmware: FirmwareMetadata | None = None,
        toolchain_version: str | None = None,
        probe_type: str | None = None,
    ) -> CompatibilityResult:
        """Check compatibility.

        Args:
            target_family: Target chip family
            firmware: Optional firmware metadata
            toolchain_version: Optional toolchain version string
            probe_type: Optional probe type

        Returns:
            CompatibilityResult with compatibility status and warnings/errors
        """
        warnings: list[str] = []
        errors: list[str] = []
        matched_rule: CompatibilityRule | None = None

        # Find matching rules
        for rule in self._rules:
            if rule.target_family != target_family:
                continue

            matched_rule = rule
            is_match = True

            # Check firmware version
            if rule.firmware_version and firmware:
                version_tuple = firmware.semver_tuple
                if not rule.firmware_version.matches(version_tuple):
                    errors.append(
                        f"Firmware version {firmware.version} does not match "
                        f"requirement {rule.firmware_version}"
                    )
                    is_match = False

            # Check toolchain version
            if rule.toolchain_version and toolchain_version:
                try:
                    toolchain_spec = VersionSpecSet.parse(toolchain_version)
                    # For simplicity, just check if it matches >=0.0
                    # In production, parse actual toolchain version
                    if not toolchain_spec.matches((0, 0, 0, 0, 0)):
                        warnings.append(
                            f"Toolchain version {toolchain_version} may not be compatible"
                        )
                except ValueError:
                    warnings.append(f"Could not parse toolchain version: {toolchain_version}")

            # Check probe type
            if rule.probe_types and probe_type:
                if probe_type not in rule.probe_types:
                    errors.append(
                        f"Probe type {probe_type} not in allowed types: {rule.probe_types}"
                    )
                    is_match = False

            # Add rule-specific warnings
            warnings.extend(rule.warnings)
            errors.extend(rule.errors)

            if is_match:
                break

        return CompatibilityResult(
            compatible=len(errors) == 0,
            target_family=target_family,
            firmware_version=firmware.version if firmware else None,
            toolchain_version=toolchain_version,
            warnings=warnings,
            errors=errors,
            matched_rule=matched_rule,
        )

    def get_rules_for_family(self, family: str) -> list[CompatibilityRule]:
        """Get all rules for a target family.

        Args:
            family: Target family name

        Returns:
            List of matching rules
        """
        return [r for r in self._rules if r.target_family == family]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rules": [r.to_dict() for r in self._rules],
        }
