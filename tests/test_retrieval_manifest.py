"""
Tests for retrieval manifest and incremental rebuild system.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.infrastructure.retrieval.manifest import IndexManifest, compute_content_hash, MANIFEST_FILE


class TestIndexManifest:
    """Tests for IndexManifest class."""

    @pytest.fixture
    def temp_workspace(self, tmp_path):
        """Create a temporary workspace."""
        return tmp_path

    @pytest.fixture
    def manifest(self, temp_workspace):
        """Create a fresh IndexManifest instance."""
        return IndexManifest(temp_workspace)

    def test_empty_manifest_structure(self, manifest):
        """Manifest should have correct initial structure."""
        data = manifest.load()
        assert "schema_version" in data
        assert "indexed_at" in data
        assert "sources" in data
        assert "chunk_count" in data

    def test_manifest_persists_to_disk(self, manifest, temp_workspace):
        """Manifest should save and load correctly."""
        manifest.record_build("v9", 100)
        manifest.save()

        # Create new instance and verify data persists
        new_manifest = IndexManifest(temp_workspace)
        data = new_manifest.load()

        assert data["schema_version"] == "v9"
        assert data["chunk_count"] == 100

    def test_needs_full_rebuild_schema_mismatch(self, manifest):
        """Full rebuild needed when schema version doesn't match."""
        from src.core.config.agent_prompts import RAG_SCHEMA_VERSION

        # Current schema version
        assert manifest.schema_version == RAG_SCHEMA_VERSION
        assert manifest.needs_full_rebuild() is False

        # Simulate old version stored on disk
        data = manifest.load()
        data["schema_version"] = "v8"
        manifest.save()

        # Should detect version mismatch
        assert manifest.schema_version == "v8"
        assert manifest.needs_full_rebuild() is True

    def test_needs_full_rebuild_when_schema_changed(self, manifest):
        """Schema version change should trigger full rebuild."""
        # Simulate manifest from old version
        data = manifest.load()
        data["schema_version"] = "v8"
        data["sources"] = {"doc1.pdf": {"content_hash": "hash1", "chunk_ids": ["c1"]}}
        manifest.save()

        # Should detect version mismatch
        from src.core.config.agent_prompts import RAG_SCHEMA_VERSION
        assert manifest.schema_version == "v8"
        assert manifest.schema_version != RAG_SCHEMA_VERSION
        assert manifest.needs_full_rebuild() is True

    def test_no_full_rebuild_when_schema_matches(self, manifest):
        """Matching schema version should not trigger full rebuild."""
        # Record a build with current schema version
        from src.core.config.agent_prompts import RAG_SCHEMA_VERSION
        manifest.record_build(RAG_SCHEMA_VERSION, 50)

        # Verify schema version matches
        assert manifest.schema_version == RAG_SCHEMA_VERSION
        assert manifest.needs_full_rebuild() is False

    def test_update_source(self, manifest):
        """Should track individual sources."""
        manifest.update_source(
            source_id="doc1.pdf",
            content_hash="abc123",
            chunk_ids=["chunk1", "chunk2"],
            metadata={"page_count": 100},
        )
        manifest.save()

        source = manifest.get_source("doc1.pdf")
        assert source is not None
        assert source["content_hash"] == "abc123"
        assert source["chunk_ids"] == ["chunk1", "chunk2"]
        assert source["metadata"]["page_count"] == 100

    def test_is_source_current(self, manifest):
        """Should detect unchanged sources."""
        manifest.update_source("doc1.pdf", "hash123", ["chunk1"])
        manifest.save()

        assert manifest.is_source_current("doc1.pdf", "hash123") is True
        assert manifest.is_source_current("doc1.pdf", "different_hash") is False
        assert manifest.is_source_current("nonexistent.pdf", "hash") is False

    def test_get_stale_sources(self, manifest):
        """Should identify sources that need re-indexing."""
        manifest.update_source("doc1.pdf", "hash1", ["c1"])
        manifest.update_source("doc2.pdf", "hash2", ["c2"])
        manifest.save()

        # New source (not in manifest)
        stale = manifest.get_stale_sources({"doc1.pdf": "hash1", "doc2.pdf": "hash2", "doc3.pdf": "hash3"})
        assert "doc3.pdf" in stale  # New source

        # Source removed - no stale for removed sources
        stale = manifest.get_stale_sources({"doc1.pdf": "hash1"})
        assert len(stale) == 0  # No new sources

        # Source changed
        stale = manifest.get_stale_sources({"doc1.pdf": "hash1", "doc2.pdf": "new_hash"})
        assert "doc2.pdf" in stale  # Changed hash

    def test_remove_source(self, manifest):
        """Should remove sources from manifest."""
        manifest.update_source("doc1.pdf", "hash1", ["c1"])
        manifest.update_source("doc2.pdf", "hash2", ["c2"])
        manifest.save()

        removed = manifest.remove_source("doc1.pdf")
        assert removed is True
        manifest.save()
        assert manifest.get_source("doc1.pdf") is None
        assert manifest.get_source("doc2.pdf") is not None

        # Non-existent source
        removed = manifest.remove_source("nonexistent.pdf")
        assert removed is False

    def test_get_removed_sources(self, manifest):
        """Should identify sources that were indexed but removed."""
        manifest.update_source("doc1.pdf", "hash1", ["c1"])
        manifest.update_source("doc2.pdf", "hash2", ["c2"])
        manifest.save()

        removed = manifest.get_removed_sources({"doc1.pdf": "hash1"})
        assert "doc2.pdf" in removed
        assert "doc1.pdf" not in removed

    def test_record_build(self, manifest):
        """Should record successful build."""
        manifest.record_build("v9", 500)

        assert manifest.schema_version == "v9"
        assert manifest.chunk_count == 500
        assert manifest.indexed_at != ""

    def test_reset(self, manifest):
        """Should reset manifest to empty state."""
        manifest.update_source("doc1.pdf", "hash1", ["c1"])
        manifest.record_build("v9", 100)
        manifest.save()

        manifest.reset()

        assert manifest.chunk_count == 0
        assert manifest.get_source("doc1.pdf") is None


class TestComputeHash:
    """Tests for hash computation utilities."""

    def test_compute_content_hash(self):
        """Should compute consistent hash for content."""
        hash1 = compute_content_hash("test content")
        hash2 = compute_content_hash("test content")
        hash3 = compute_content_hash("different content")

        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 64  # SHA256 hex length

    def test_compute_content_hash_deterministic(self):
        """Hash should be deterministic across calls."""
        content = "Lorem ipsum dolor sit amet"
        hashes = [compute_content_hash(content) for _ in range(10)]
        assert len(set(hashes)) == 1
