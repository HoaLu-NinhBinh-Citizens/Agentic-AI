"""Strict normalizer for cache keys.

Provides lossless canonicalization of tool arguments.
NO semantic transformation - only whitespace trim and deterministic sort.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from src.infrastructure.cache.tool.types import CacheKey


@dataclass
class NormalizationConfig:
    """Configuration for normalization behavior."""

    case_fold: bool = False
    sort_keys: bool = True
    trim_whitespace: bool = True
    remove_none: bool = False
    max_depth: int = 10


class StrictNormalizer:
    """Strict argument normalizer.

    Ensures deterministic, lossless normalization of tool arguments.
    Only allows:
    - Whitespace trim
    - Deterministic dict sort
    - Optional case-fold (config gated)

    STRICTLY PROHIBITED:
    - Semantic transformation
    - Unit conversion
    - Timezone conversion
    - Locale parsing
    """

    def __init__(self, config: NormalizationConfig | None = None) -> None:
        self.config = config or NormalizationConfig()

    def normalize(self, args: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
        """Normalize arguments to deterministic tuple form.

        Args:
            args: Raw tool arguments

        Returns:
            Sorted tuple of (key, value) pairs
        """
        normalized = self._normalize_value(args, depth=0)
        if self.config.sort_keys:
            sorted_items = sorted(normalized.items(), key=lambda x: str(x[0]))
            return tuple(sorted_items)
        return tuple(normalized.items())

    def _normalize_value(
        self,
        value: Any,
        depth: int,
    ) -> Any:
        """Recursively normalize a value.

        Args:
            value: Value to normalize
            depth: Current recursion depth

        Returns:
            Normalized value
        """
        if depth > self.config.max_depth:
            raise ValueError(f"Max normalization depth exceeded: {self.config.max_depth}")

        if value is None:
            return None if not self.config.remove_none else None

        if isinstance(value, str):
            return self._normalize_string(value)

        if isinstance(value, dict):
            return self._normalize_dict(value, depth + 1)

        if isinstance(value, (list, tuple)):
            return self._normalize_list(value, depth + 1)

        if isinstance(value, (int, float, bool)):
            return value

        if isinstance(value, (set, frozenset)):
            return tuple(sorted(self._normalize_value(item, depth + 1) for item in value))

        return value

    def _normalize_string(self, value: str) -> str:
        """Normalize a string value."""
        result = value
        if self.config.trim_whitespace:
            result = result.strip()
        if self.config.case_fold:
            result = result.casefold()
        return result

    def _normalize_dict(
        self,
        value: dict[str, Any],
        depth: int,
    ) -> dict[str, Any]:
        """Normalize a dictionary."""
        result = {}
        for k, v in value.items():
            key = self._normalize_string(k) if isinstance(k, str) else k
            result[key] = self._normalize_value(v, depth)
        return result

    def _normalize_list(
        self,
        value: list[Any] | tuple[Any, ...],
        depth: int,
    ) -> list[Any]:
        """Normalize a list or tuple."""
        return [self._normalize_value(item, depth) for item in value]


class KeyGenerator:
    """Versioned SHA256 key generator.

    Generates deterministic cache keys from tool name, version, and arguments.
    """

    VERSION = "v1"

    def __init__(self, normalizer: StrictNormalizer | None = None) -> None:
        self.normalizer = normalizer or StrictNormalizer()

    def generate(
        self,
        tool: str,
        version: str,
        args: dict[str, Any],
    ) -> str:
        """Generate cache key from tool and arguments.

        Args:
            tool: Tool name
            version: Tool version
            args: Tool arguments

        Returns:
            SHA256 hash as hex string
        """
        import hashlib

        cache_key = CacheKey(
            tool=tool,
            version=version,
            args=self.normalizer.normalize(args),
        )

        canonical = json.dumps(
            cache_key.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        )

        key_bytes = f"{self.VERSION}:{canonical}".encode("utf-8")
        return hashlib.sha256(key_bytes).hexdigest()

    def generate_from_key(self, cache_key: CacheKey) -> str:
        """Generate key from CacheKey object.

        Args:
            cache_key: CacheKey object

        Returns:
            SHA256 hash as hex string
        """
        import hashlib

        canonical = json.dumps(
            cache_key.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        )

        key_bytes = f"{self.VERSION}:{canonical}".encode("utf-8")
        return hashlib.sha256(key_bytes).hexdigest()

    @classmethod
    def create_cache_key(
        cls,
        tool: str,
        version: str,
        args: dict[str, Any],
    ) -> CacheKey:
        """Create a CacheKey from components.

        Args:
            tool: Tool name
            version: Tool version
            args: Tool arguments

        Returns:
            CacheKey object
        """
        normalizer = StrictNormalizer()
        return CacheKey(
            tool=tool,
            version=version,
            args=normalizer.normalize(args),
        )
