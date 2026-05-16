"""
RAG index manifest tracking for incremental rebuilds.

Tracks source files, hashes, and timestamps to enable selective re-indexing
instead of full rebuilds when schema version changes.
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.core.config.agent_prompts import RAG_INDEX_ROOT, RAG_SCHEMA_VERSION

logger = logging.getLogger(__name__)

MANIFEST_FILE = f"{RAG_INDEX_ROOT}/manifest.json"


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except OSError:
        return ""


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of string content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class IndexManifest:
    """
    Tracks the state of the RAG index to enable incremental rebuilds.

    Instead of full rebuild on schema version change, this manifest:
    1. Tracks which source files were indexed
    2. Stores hashes of source content
    3. Records timestamps of last indexing
    4. Enables selective re-indexing of changed sources only
    """

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.manifest_path = workspace_root / MANIFEST_FILE
        self._data: Dict = {}
        self._loaded = False

    def load(self) -> Dict:
        """Load manifest from disk."""
        if self._loaded:
            return self._data
        self._loaded = True

        if not self.manifest_path.exists():
            self._data = self._empty_manifest()
            return self._data

        try:
            self._data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load manifest: %s", exc)
            self._data = self._empty_manifest()

        return self._data

    def save(self) -> None:
        """Save manifest to disk."""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.manifest_path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to save manifest: %s", exc)

    def _empty_manifest(self) -> Dict:
        return {
            "schema_version": RAG_SCHEMA_VERSION,
            "indexed_at": datetime.now().isoformat(timespec="seconds"),
            "sources": {},
            "chunk_count": 0,
        }

    @property
    def schema_version(self) -> str:
        return self.load().get("schema_version", "")

    @property
    def indexed_at(self) -> str:
        return self.load().get("indexed_at", "")

    @property
    def chunk_count(self) -> int:
        return int(self.load().get("chunk_count", 0))

    def get_source(self, source_id: str) -> Optional[Dict]:
        """Get metadata for a specific source."""
        return self.load().get("sources", {}).get(source_id)

    def get_all_sources(self) -> Dict[str, Dict]:
        """Get all tracked sources."""
        return dict(self.load().get("sources", {}))

    def is_source_current(self, source_id: str, content_hash: str) -> bool:
        """Check if a source hasn't changed since last indexing."""
        source = self.get_source(source_id)
        if not source:
            return False
        return source.get("content_hash") == content_hash

    def update_source(
        self,
        source_id: str,
        content_hash: str,
        chunk_ids: List[str],
        metadata: Optional[Dict] = None,
    ) -> None:
        """Update or add a source entry."""
        data = self.load()
        if "sources" not in data:
            data["sources"] = {}

        data["sources"][source_id] = {
            "content_hash": content_hash,
            "indexed_at": datetime.now().isoformat(timespec="seconds"),
            "chunk_ids": chunk_ids,
            "metadata": metadata or {},
        }

    def remove_source(self, source_id: str) -> bool:
        """Remove a source from the manifest."""
        data = self.load()
        if "sources" in data and source_id in data["sources"]:
            del data["sources"][source_id]
            return True
        return False

    def needs_full_rebuild(self) -> bool:
        """
        Check if a full rebuild is needed vs incremental update.

        Full rebuild is needed when:
        1. Schema version changed
        2. No manifest exists (empty data)
        """
        data = self.load()

        # Schema version mismatch → need migration or full rebuild
        if data.get("schema_version", "") != RAG_SCHEMA_VERSION:
            return True

        # Empty manifest (no schema version set) → full rebuild needed
        if not data.get("schema_version"):
            return True

        # Manifest exists with matching version → no full rebuild needed
        # Even if sources is empty, that's valid (no docs indexed yet)
        return False

    def get_stale_sources(self, current_sources: Dict[str, str]) -> List[str]:
        """
        Get list of source IDs that need re-indexing.

        Args:
            current_sources: Dict mapping source_id -> content_hash

        Returns:
            List of source_ids that are missing or have changed content
        """
        manifest_sources = self.get_all_sources()
        stale = []

        for source_id, content_hash in current_sources.items():
            if source_id not in manifest_sources:
                stale.append(source_id)
            elif manifest_sources[source_id].get("content_hash") != content_hash:
                stale.append(source_id)

        return stale

    def get_removed_sources(self, current_sources: Dict[str, str]) -> List[str]:
        """
        Get list of source IDs that were indexed but no longer exist.

        Args:
            current_sources: Dict of currently existing source_ids

        Returns:
            List of source_ids that should be removed from index
        """
        manifest_sources = self.get_all_sources()
        return [sid for sid in manifest_sources if sid not in current_sources]

    def set_chunk_count(self, count: int) -> None:
        """Update total chunk count."""
        data = self.load()
        data["chunk_count"] = count

    def record_build(
        self,
        schema_version: str,
        chunk_count: int,
    ) -> None:
        """Record a successful index build."""
        data = self.load()
        data["schema_version"] = schema_version
        data["indexed_at"] = datetime.now().isoformat(timespec="seconds")
        data["chunk_count"] = chunk_count
        self.save()

    def migrate_from_schema(self, old_version: str) -> bool:
        """
        Attempt to migrate manifest from an old schema version.

        For now, returns False (meaning full rebuild is needed).
        This can be extended to support actual schema migrations.

        Args:
            old_version: The schema version we're migrating from

        Returns:
            True if migration was successful, False if full rebuild needed
        """
        # For v9, we don't have a migration path from v8 or earlier
        # Return False to indicate full rebuild is needed
        logger.info(
            "Manifest migration from %s to %s not supported, full rebuild needed",
            old_version,
            RAG_SCHEMA_VERSION,
        )
        return False

    def reset(self) -> None:
        """Reset manifest to empty state."""
        self._data = self._empty_manifest()
        self.save()
