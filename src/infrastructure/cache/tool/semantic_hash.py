"""Semantic Cache Hash - Content-aware hashing for tool cache.

W-012: Fixes semantic cache fragmentation by creating stable hashes
that ignore semantically irrelevant differences.

Problem:
- Structural hash (SHA256) is sensitive to whitespace, key ordering, default values
- "read_file(path='a.txt')" vs "read_file(path='a.txt', encoding='utf-8')" should share cache
- Trailing spaces, formatting differences cause cache misses
- Unbounded cache leads to memory leaks

Solution:
- Semantic normalizer that strips irrelevant differences
- Content-aware hashing for file/directory arguments
- Schema-aware default value handling
- LRU cache with eviction policy
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from threading import Lock


@dataclass
class SemanticHashConfig:
    """Configuration for semantic hashing."""

    ignore_whitespace: bool = True
    ignore_key_order: bool = True
    ignore_defaults: bool = True
    content_hash_size: int = 32
    max_content_hash_files: int = 100
    max_file_size_for_hash: int = 10 * 1024 * 1024
    include_file_mtime: bool = True
    include_file_size: bool = True
    strip_comments: bool = True
    strip_docstrings: bool = True


@dataclass
class CacheEntry:
    """Cache entry with TTL support."""
    value: str
    created_at: float
    last_accessed: float
    access_count: int = 0


@dataclass
class TTLCache:
    """LRU Cache with TTL eviction.
    
    Features:
    - LRU eviction policy
    - TTL-based expiration
    - Thread-safe operations
    - Hit/miss statistics
    """
    
    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: float = 3600.0,
    ):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = Lock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expired": 0,
        }
    
    def get(self, key: str) -> str | None:
        """Get value from cache if exists and not expired."""
        with self._lock:
            if key not in self._cache:
                self._stats["misses"] += 1
                return None
            
            entry = self._cache[key]
            
            # Check TTL
            if time.time() - entry.created_at > self.ttl_seconds:
                del self._cache[key]
                self._stats["expired"] += 1
                self._stats["misses"] += 1
                return None
            
            # Update access stats (LRU)
            entry.last_accessed = time.time()
            entry.access_count += 1
            self._cache.move_to_end(key)
            
            self._stats["hits"] += 1
            return entry.value
    
    def put(self, key: str, value: str) -> None:
        """Put value in cache with LRU eviction."""
        with self._lock:
            # Check if key exists
            if key in self._cache:
                entry = self._cache[key]
                entry.value = value
                entry.last_accessed = time.time()
                entry.access_count += 1
                self._cache.move_to_end(key)
                return
            
            # Evict if needed
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
                self._stats["evictions"] += 1
            
            # Add new entry
            self._cache[key] = CacheEntry(
                value=value,
                created_at=time.time(),
                last_accessed=time.time(),
                access_count=1,
            )
    
    def invalidate(self, key: str) -> bool:
        """Remove key from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> int:
        """Clear all entries."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count
    
    def cleanup_expired(self) -> int:
        """Remove all expired entries."""
        with self._lock:
            now = time.time()
            expired_keys = [
                k for k, v in self._cache.items()
                if now - v.created_at > self.ttl_seconds
            ]
            for key in expired_keys:
                del self._cache[key]
            self._stats["expired"] += len(expired_keys)
            return len(expired_keys)
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = self._stats["hits"] / total if total > 0 else 0.0
            return {
                **self._stats,
                "size": len(self._cache),
                "max_size": self.max_size,
                "hit_rate": hit_rate,
            }


@dataclass
class SemanticHashResult:
    """Result of semantic hash computation."""

    semantic_hash: str
    structural_hash: str
    content_hashes: dict[str, str]
    ignored_fields: set[str]
    normalization_applied: list[str]
    is_approximate: bool = False


class SemanticNormalizer:
    """Normalizes arguments for semantic hash computation.

    Handles:
    - Whitespace normalization
    - Default value stripping
    - Key ordering normalization
    - Path normalization
    - Content-aware hashing for files
    """

    def __init__(self, config: SemanticHashConfig | None = None) -> None:
        self.config = config or SemanticHashConfig()
        self._content_cache: dict[str, str] = {}

    def normalize(self, args: dict[str, Any]) -> dict[str, Any]:
        """Normalize arguments for semantic hashing."""
        normalized = {}

        for key, value in args.items():
            normalized_key = self._normalize_key(key)
            normalized_value = self._normalize_value(value, key)
            normalized[normalized_key] = normalized_value

        if self.config.ignore_key_order:
            return dict(sorted(normalized.items(), key=lambda x: x[0]))
        return normalized

    def _normalize_key(self, key: str) -> str:
        """Normalize argument key."""
        return key.strip().lower()

    def _normalize_value(self, value: Any, key: str) -> Any:
        """Normalize argument value based on type and context."""
        if value is None:
            return None

        if isinstance(value, str):
            return self._normalize_string(value, key)

        if isinstance(value, (int, float, bool)):
            return value

        if isinstance(value, list):
            return [self._normalize_value(v, key) for v in value]

        if isinstance(value, dict):
            return self.normalize(value)

        if isinstance(value, (Path, os.PathLike)):
            return self._normalize_path(str(value))

        return value

    def _normalize_string(self, value: str, context: str) -> str:
        """Normalize string value based on context."""
        if self.config.ignore_whitespace:
            value = self._strip_whitespace(value, context)

        return value

    def _strip_whitespace(self, value: str, context: str) -> str:
        """Strip semantically irrelevant whitespace."""
        value = value.strip()

        if context in ("content", "text", "body", "data", "payload"):
            value = re.sub(r"[ \t]+", " ", value)
            value = re.sub(r"\n[ \t]+", "\n", value)

        return value

    def _normalize_path(self, path: str) -> str:
        """Normalize file/directory path."""
        try:
            p = Path(path).resolve()
            return str(p)
        except (OSError, RuntimeError):
            return str(Path(path))


class ContentHasher:
    """Content-aware hasher for file and directory arguments.

    Computes content hash for file arguments to enable:
    - Cache sharing for same file content with different path representations
    - Detecting file changes without relying solely on mtime
    - LRU eviction to prevent memory leaks
    """

    def __init__(
        self,
        config: SemanticHashConfig | None = None,
        max_cache_size: int = 1000,
    ) -> None:
        self.config = config or SemanticHashConfig()
        self.max_cache_size = max_cache_size
        self._file_cache: OrderedDict[str, str] = OrderedDict()
        self._cache_lock = Lock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
        }

    def _evict_if_needed(self) -> None:
        """Evict oldest entries if cache exceeds max size."""
        while len(self._file_cache) >= self.max_cache_size:
            self._file_cache.popitem(last=False)  # Remove oldest
            self._stats["evictions"] += 1

    def _move_to_end(self, key: str) -> None:
        """Move accessed key to end (most recently used)."""
        self._file_cache.move_to_end(key)

    def hash_file(self, path: str) -> str | None:
        """Compute semantic hash of file content.

        Returns None if file doesn't exist or is too large.
        """
        cache_key = f"file:{path}"
        
        with self._cache_lock:
            if cache_key in self._file_cache:
                self._stats["hits"] += 1
                self._move_to_end(cache_key)
                return self._file_cache[cache_key]
            
            self._stats["misses"] += 1
            self._evict_if_needed()

        try:
            p = Path(path)
            if not p.exists() or not p.is_file():
                return None

            if p.stat().st_size > self.config.max_file_size_for_hash:
                return None

            content = p.read_bytes()
            content_hash = hashlib.sha256(content).hexdigest()[
                : self.config.content_hash_size
            ]

            metadata_parts = []
            if self.config.include_file_mtime:
                metadata_parts.append(f"mtime:{int(p.stat().st_mtime)}")
            if self.config.include_file_size:
                metadata_parts.append(f"size:{p.stat().st_size}")

            if metadata_parts:
                combined = f"{content_hash}:{':'.join(metadata_parts)}"
            else:
                combined = content_hash

            self._file_cache[cache_key] = combined
            return combined

        except (OSError, PermissionError, UnicodeDecodeError):
            return None

    def hash_directory(self, path: str) -> str | None:
        """Compute semantic hash of directory contents.

        Only hashes up to max_content_hash_files to avoid performance issues.
        """
        cache_key = f"dir:{path}"
        
        with self._cache_lock:
            if cache_key in self._file_cache:
                self._stats["hits"] += 1
                self._move_to_end(cache_key)
                return self._file_cache[cache_key]
            
            self._stats["misses"] += 1
            self._evict_if_needed()

        try:
            p = Path(path)
            if not p.exists() or not p.is_dir():
                return None

            file_hashes = []
            file_count = 0

            for entry in sorted(p.rglob("*")):
                if not entry.is_file():
                    continue
                if file_count >= self.config.max_content_hash_files:
                    break

                file_hash = self.hash_file(str(entry))
                if file_hash:
                    rel_path = str(entry.relative_to(p))
                    file_hashes.append(f"{rel_path}:{file_hash}")
                    file_count += 1

            if not file_hashes:
                return None

            combined_content = "|".join(sorted(file_hashes))
            dir_hash = hashlib.sha256(combined_content.encode()).hexdigest()[
                : self.config.content_hash_size
            ]

            self._file_cache[cache_key] = dir_hash
            return dir_hash

        except (OSError, PermissionError):
            return None

    def hash_content(self, content: str | bytes, context: str = "default") -> str:
        """Compute semantic hash of content string."""
        if isinstance(content, bytes):
            return hashlib.sha256(content).hexdigest()[: self.config.content_hash_size]

        processed = content
        if self.config.strip_comments and context in (
            "code",
            "script",
            "source",
        ):
            processed = self._strip_comments(processed, context)

        if self.config.strip_docstrings and context in (
            "code",
            "script",
            "source",
        ):
            processed = self._strip_docstrings(processed, context)

        return hashlib.sha256(processed.encode()).hexdigest()[
            : self.config.content_hash_size
        ]

    def _strip_comments(self, content: str, language: str) -> str:
        """Strip comments from code content."""
        if language == "python":
            lines = content.split("\n")
            result = []
            in_multiline_string = False
            string_char = ""

            for line in lines:
                stripped = line.strip()
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    if '"""' in stripped[3:]:
                        continue
                    if "'''" in stripped[3:]:
                        continue
                    in_multiline_string = not in_multiline_string
                    continue

                if in_multiline_string:
                    continue

                if stripped.startswith("#"):
                    continue

                result.append(line)

            return "\n".join(result)

        return content

    def _strip_docstrings(self, content: str, language: str) -> str:
        """Strip docstrings from code content."""
        if language == "python":
            import re

            content = re.sub(r'""".*?"""', "", content, flags=re.DOTALL)
            content = re.sub(r"'''.*?'''", "", content, flags=re.DOTALL)

        return content


class SemanticCacheHasher:
    """Main facade for semantic cache hashing.

    Combines:
    - SemanticNormalizer for argument normalization
    - ContentHasher for file/directory content hashing
    - Standard SHA256 for final hash computation
    - TTLCache for LRU eviction with TTL
    """

    def __init__(
        self,
        config: SemanticHashConfig | None = None,
        max_cache_size: int = 1000,
        cache_ttl_seconds: float = 3600.0,
    ) -> None:
        self.config = config or SemanticHashConfig()
        self._normalizer = SemanticNormalizer(config)
        self._content_hasher = ContentHasher(config, max_cache_size=max_cache_size)
        self._semantic_hash_cache = TTLCache(
            max_size=max_cache_size,
            ttl_seconds=cache_ttl_seconds,
        )
        self._structural_hash_cache = TTLCache(
            max_size=max_cache_size,
            ttl_seconds=cache_ttl_seconds,
        )
        self._lock = Lock()
    
    def get_cache_stats(self) -> dict:
        """Get statistics for all caches."""
        return {
            "semantic_hash": self._semantic_hash_cache.get_stats(),
            "structural_hash": self._structural_hash_cache.get_stats(),
            "content_hash": self._content_hasher._stats,
        }
    
    def clear_caches(self) -> dict:
        """Clear all caches and return stats before clear."""
        stats = self.get_cache_stats()
        self._semantic_hash_cache.clear()
        self._structural_hash_cache.clear()
        return stats

    def compute_hash(
        self,
        tool_name: str,
        args: dict[str, Any],
        tool_version: str | None = None,
    ) -> SemanticHashResult:
        """Compute semantic hash for tool call.

        Args:
            tool_name: Name of the tool
            args: Tool arguments
            tool_version: Optional tool version

        Returns:
            SemanticHashResult with both semantic and structural hashes
        """
        # Create cache key from inputs
        cache_key_parts = {
            "tool": tool_name,
            "args": args,
            "version": tool_version,
        }
        cache_key = json.dumps(cache_key_parts, sort_keys=True)
        
        # Check semantic hash cache first
        cached_result = self._semantic_hash_cache.get(cache_key)
        if cached_result:
            return json.loads(cached_result)
        
        content_hashes: dict[str, str] = {}
        normalization_applied: list[str] = []
        ignored_fields: set[str] = set()

        processed_args = self._process_args_with_content(
            args, content_hashes, normalization_applied
        )

        normalized_args = self._normalizer.normalize(processed_args)
        semantic_canonical = self._build_canonical(
            tool_name, normalized_args, tool_version, content_hashes
        )
        semantic_hash = self._compute_hash(semantic_canonical)

        structural_canonical = self._build_canonical(
            tool_name, args, tool_version, {}
        )
        structural_hash = self._compute_hash(structural_canonical)

        is_approximate = len(content_hashes) > 0

        result = SemanticHashResult(
            semantic_hash=semantic_hash,
            structural_hash=structural_hash,
            content_hashes=content_hashes,
            ignored_fields=ignored_fields,
            normalization_applied=normalization_applied,
            is_approximate=is_approximate,
        )
        
        # Cache the result
        self._semantic_hash_cache.put(cache_key, json.dumps({
            "semantic_hash": result.semantic_hash,
            "structural_hash": result.structural_hash,
            "content_hashes": result.content_hashes,
            "ignored_fields": list(result.ignored_fields),
            "normalization_applied": result.normalization_applied,
            "is_approximate": result.is_approximate,
        }))
        
        return result

    def _process_args_with_content(
        self,
        args: dict[str, Any],
        content_hashes: dict[str, str],
        normalization_applied: list[str],
    ) -> dict[str, Any]:
        """Process arguments, replacing file paths with content hashes."""
        processed = {}

        for key, value in args.items():
            if self._is_file_path_arg(key, value):
                file_hash = self._content_hasher.hash_file(str(value))
                if file_hash:
                    content_hashes[str(value)] = file_hash
                    processed[key] = f"file_hash:{file_hash}"
                    normalization_applied.append(f"file_content:{key}")
                else:
                    processed[key] = self._normalizer._normalize_path(str(value))
                    normalization_applied.append(f"path_normalized:{key}")

            elif self._is_directory_arg(key, value):
                dir_hash = self._content_hasher.hash_directory(str(value))
                if dir_hash:
                    content_hashes[str(value)] = dir_hash
                    processed[key] = f"dir_hash:{dir_hash}"
                    normalization_applied.append(f"dir_content:{key}")
                else:
                    processed[key] = self._normalizer._normalize_path(str(value))

            elif isinstance(value, dict):
                processed[key] = self._process_args_with_content(
                    value, content_hashes, normalization_applied
                )

            elif isinstance(value, list):
                processed[key] = [
                    self._process_args_in_list(item, content_hashes, normalization_applied)
                    for item in value
                ]

            else:
                processed[key] = value

        return processed

    def _process_args_in_list(
        self,
        item: Any,
        content_hashes: dict[str, str],
        normalization_applied: list[str],
    ) -> Any:
        """Process items in argument lists."""
        if isinstance(item, dict):
            return self._process_args_with_content(
                item, content_hashes, normalization_applied
            )
        return item

    def _is_file_path_arg(self, key: str, value: Any) -> bool:
        """Check if argument is a file path."""
        file_indicators = (
            "path",
            "file",
            "filename",
            "filepath",
            "src",
            "source",
            "target",
            "dest",
            "output",
        )
        return (
            key.lower() in file_indicators
            and isinstance(value, (str, Path, os.PathLike))
        )

    def _is_directory_arg(self, key: str, value: Any) -> bool:
        """Check if argument is a directory path."""
        dir_indicators = ("dir", "directory", "folder", "root", "cwd", "basedir")
        return (
            key.lower() in dir_indicators
            and isinstance(value, (str, Path, os.PathLike))
        )

    def _build_canonical(
        self,
        tool_name: str,
        args: dict[str, Any],
        tool_version: str | None,
        content_hashes: dict[str, str],
    ) -> dict[str, Any]:
        """Build canonical representation for hashing."""
        canonical: dict[str, Any] = {"tool": tool_name}

        if tool_version:
            canonical["version"] = tool_version

        canonical["args"] = args

        if content_hashes:
            canonical["_content_hashes"] = dict(
                sorted(content_hashes.items(), key=lambda x: x[0])
            )

        return canonical

    def _compute_hash(self, canonical: dict[str, Any]) -> str:
        """Compute SHA256 hash of canonical representation."""
        serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode()).hexdigest()

    def get_semantic_key(self, tool_name: str, args: dict[str, Any]) -> str:
        """Get semantic cache key for tool call.

        Convenience method that returns only the semantic hash.
        """
        result = self.compute_hash(tool_name, args)
        return result.semantic_hash

    def verify_equivalence(self, args1: dict[str, Any], args2: dict[str, Any]) -> bool:
        """Verify if two argument sets are semantically equivalent.

        Returns True if they would produce the same cache key.
        """
        normalized1 = self._normalizer.normalize(args1)
        normalized2 = self._normalizer.normalize(args2)
        return normalized1 == normalized2


def create_semantic_hasher(config: SemanticHashConfig | None = None) -> SemanticCacheHasher:
    """Factory function to create SemanticCacheHasher."""
    return SemanticCacheHasher(config)
