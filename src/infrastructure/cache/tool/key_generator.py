"""Key Generator with versioned SHA256 hashing.

Implements strict canonicalization for cache key generation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class KeyGeneratorConfig:
    """Configuration for key generation."""

    include_version: bool = True
    include_args_hash: bool = True
    case_fold: bool = False
    version: str = "1.0.0"


class KeyGenerator:
    """Generates consistent SHA256 keys for cache entries.

    Canonical key structure:
    {
        "tool": "tool_name",
        "version": "1.0.0",
        "args": {...}
    }

    Key = SHA256(JSON_SORTED(canonical))
    """

    def __init__(
        self,
        normalizer: Any,
        config: KeyGeneratorConfig | None = None,
    ) -> None:
        self._normalizer = normalizer
        self.config = config or KeyGeneratorConfig()

    def generate(
        self,
        tool_name: str,
        args: dict[str, Any],
        tool_version: str | None = None,
    ) -> str:
        """Generate a cache key for the given tool and arguments.

        Args:
            tool_name: Name of the tool
            args: Tool arguments (will be normalized)
            tool_version: Optional tool version (uses config version if not provided)

        Returns:
            SHA256 hash as cache key
        """
        canonical = self._build_canonical(tool_name, args, tool_version)
        return self._hash(canonical)

    def _build_canonical(
        self,
        tool_name: str,
        args: dict[str, Any],
        tool_version: str | None = None,
    ) -> dict[str, Any]:
        """Build canonical representation of key components."""
        canonical: dict[str, Any] = {
            "tool": tool_name,
        }

        if self.config.include_version:
            canonical["version"] = tool_version or self.config.version

        if self.config.include_args_hash:
            normalized_args = self._normalize_args(args)
            canonical["args_hash"] = self._hash_args(normalized_args)

        return canonical

    def _normalize_args(self, args: dict[str, Any]) -> dict[str, Any]:
        """Normalize arguments using the normalizer."""
        return self._normalizer.normalize(args)

    def _hash_args(self, args: dict[str, Any]) -> str:
        """Create deterministic hash of normalized arguments."""
        serialized = self._serialize_for_hash(args)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def _serialize_for_hash(self, obj: Any) -> str:
        """Serialize object to deterministic JSON for hashing."""
        return json.dumps(obj, sort_keys=True, separators=(",", ":"))

    def _hash(self, canonical: dict[str, Any]) -> str:
        """Generate SHA256 hash of canonical representation."""
        serialized = self._serialize_for_hash(canonical)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def generate_with_full_args(
        self,
        tool_name: str,
        args: dict[str, Any],
        tool_version: str | None = None,
    ) -> str:
        """Generate key including full normalized args (not just hash).

        Use when full args are needed for debugging/tracing.
        """
        canonical = {
            "tool": tool_name,
        }

        if self.config.include_version:
            canonical["version"] = tool_version or self.config.version

        normalized_args = self._normalize_args(args)
        canonical["args"] = normalized_args

        return self._hash(canonical)

    def verify_key(self, key: str) -> bool:
        """Verify key is valid SHA256 format.

        Args:
            key: Key to verify

        Returns:
            True if key is valid SHA256 hex string
        """
        if len(key) != 64:
            return False
        try:
            int(key, 16)
            return True
        except ValueError:
            return False


def create_key_generator(normalizer: Any) -> KeyGenerator:
    """Factory function to create KeyGenerator with default config."""
    return KeyGenerator(normalizer, KeyGeneratorConfig())
