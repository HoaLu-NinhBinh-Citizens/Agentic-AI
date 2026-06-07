"""Unit tests for ProjectDetector caching behavior.

Tests cache hit/miss, invalidation, automatic invalidation
when config files are modified, and incremental detection
when files are added or removed.

Requirements: 9.1, 9.2, 9.3, 9.4
"""

from __future__ import annotations

import os
import time

import pytest
from pathlib import Path

from infrastructure.analysis.universal_repo.project_detector import ProjectDetector


@pytest.fixture
def detector() -> ProjectDetector:
    return ProjectDetector()


@pytest.fixture
def repo_dir(tmp_path: Path) -> Path:
    """Create a temporary repository directory with a Python file."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hello')\n")
    return repo


# ─── Cache Hit Tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_hit_returns_without_rescan(
    detector: ProjectDetector, repo_dir: Path
):
    """After detect(), get_cached_profile() returns the same profile."""
    profile = await detector.detect(repo_dir)
    cached = detector.get_cached_profile(repo_dir)

    assert cached is not None
    assert cached is profile
    assert cached.repo_path == repo_dir


@pytest.mark.asyncio
async def test_second_detect_returns_cached(
    detector: ProjectDetector, repo_dir: Path
):
    """Second call to detect() returns cached profile (same object)."""
    profile1 = await detector.detect(repo_dir)
    profile2 = await detector.detect(repo_dir)

    assert profile2 is profile1


# ─── Cache Miss Tests ────────────────────────────────────────────────────────


def test_cache_miss_when_no_prior_detection(
    detector: ProjectDetector, repo_dir: Path
):
    """get_cached_profile() returns None before any detection."""
    result = detector.get_cached_profile(repo_dir)
    assert result is None


@pytest.mark.asyncio
async def test_cache_miss_when_file_added(
    detector: ProjectDetector, repo_dir: Path
):
    """Adding a file changes file tree hash, causing cache miss."""
    await detector.detect(repo_dir)

    # Add a new file to change the file tree hash
    (repo_dir / "new_module.py").write_text("x = 1\n")

    cached = detector.get_cached_profile(repo_dir)
    assert cached is None


@pytest.mark.asyncio
async def test_cache_miss_when_file_removed(
    detector: ProjectDetector, repo_dir: Path
):
    """Removing a file changes file tree hash, causing cache miss."""
    (repo_dir / "extra.py").write_text("y = 2\n")
    await detector.detect(repo_dir)

    # Remove the file
    (repo_dir / "extra.py").unlink()

    cached = detector.get_cached_profile(repo_dir)
    assert cached is None


# ─── Config File Invalidation Tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_invalidated_when_package_json_modified(
    detector: ProjectDetector, repo_dir: Path
):
    """Modifying package.json invalidates the cache (Req 9.4)."""
    (repo_dir / "package.json").write_text('{"name": "app"}\n')
    await detector.detect(repo_dir)

    # Modify package.json after a brief delay to ensure mtime changes
    time.sleep(0.05)
    (repo_dir / "package.json").write_text('{"name": "app", "version": "2.0"}\n')

    cached = detector.get_cached_profile(repo_dir)
    assert cached is None


@pytest.mark.asyncio
async def test_cache_invalidated_when_cargo_toml_modified(
    detector: ProjectDetector, repo_dir: Path
):
    """Modifying Cargo.toml invalidates the cache (Req 9.4)."""
    (repo_dir / "Cargo.toml").write_text('[package]\nname = "app"\n')
    (repo_dir / "main.rs").write_text("fn main() {}\n")
    await detector.detect(repo_dir)

    time.sleep(0.05)
    (repo_dir / "Cargo.toml").write_text('[package]\nname = "app"\nversion = "2.0"\n')

    cached = detector.get_cached_profile(repo_dir)
    assert cached is None


@pytest.mark.asyncio
async def test_cache_invalidated_when_cmakelists_modified(
    detector: ProjectDetector, repo_dir: Path
):
    """Modifying CMakeLists.txt invalidates the cache (Req 9.4)."""
    (repo_dir / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)\n")
    await detector.detect(repo_dir)

    time.sleep(0.05)
    (repo_dir / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.25)\nproject(app)\n"
    )

    cached = detector.get_cached_profile(repo_dir)
    assert cached is None


@pytest.mark.asyncio
async def test_cache_invalidated_when_pyproject_toml_modified(
    detector: ProjectDetector, repo_dir: Path
):
    """Modifying pyproject.toml invalidates the cache (Req 9.4)."""
    (repo_dir / "pyproject.toml").write_text('[project]\nname = "app"\n')
    await detector.detect(repo_dir)

    time.sleep(0.05)
    (repo_dir / "pyproject.toml").write_text(
        '[project]\nname = "app"\nversion = "2.0"\n'
    )

    cached = detector.get_cached_profile(repo_dir)
    assert cached is None


@pytest.mark.asyncio
async def test_cache_valid_when_unrelated_file_modified(
    detector: ProjectDetector, repo_dir: Path
):
    """Modifying a non-config file that doesn't change tree hash keeps cache valid."""
    await detector.detect(repo_dir)

    # Modify contents of existing file (doesn't change file tree hash)
    (repo_dir / "main.py").write_text("print('modified')\n")

    cached = detector.get_cached_profile(repo_dir)
    assert cached is not None


# ─── Explicit Invalidation Tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalidate_cache_removes_entry(
    detector: ProjectDetector, repo_dir: Path
):
    """invalidate_cache() removes cached profile."""
    await detector.detect(repo_dir)
    assert detector.get_cached_profile(repo_dir) is not None

    detector.invalidate_cache(repo_dir)
    assert detector.get_cached_profile(repo_dir) is None


@pytest.mark.asyncio
async def test_invalidate_cache_nonexistent_repo_is_safe(
    detector: ProjectDetector, tmp_path: Path
):
    """invalidate_cache() on unknown repo doesn't raise."""
    nonexistent = tmp_path / "nonexistent"
    detector.invalidate_cache(nonexistent)  # Should not raise


@pytest.mark.asyncio
async def test_detect_after_invalidation_rescans(
    detector: ProjectDetector, repo_dir: Path
):
    """After invalidation, detect() performs a full rescan."""
    profile1 = await detector.detect(repo_dir)
    detector.invalidate_cache(repo_dir)
    profile2 = await detector.detect(repo_dir)

    # New profile is a different object
    assert profile2 is not profile1
    # But has same content
    assert profile2.languages.primary_language == profile1.languages.primary_language


# ─── Incremental Detection Tests (Req 9.3) ───────────────────────────────────


@pytest.mark.asyncio
async def test_incremental_update_reflects_added_file(
    detector: ProjectDetector, repo_dir: Path
):
    """After adding a new language file, re-detection includes the new language (Req 9.3)."""
    profile1 = await detector.detect(repo_dir)
    # Only Python detected initially
    assert "Python" in profile1.languages.languages

    # Add a Rust file — changes file tree, cache miss triggers re-detection
    (repo_dir / "lib.rs").write_text("fn main() {}\n")
    profile2 = await detector.detect(repo_dir)

    # Profile reflects the added Rust file
    assert profile2 is not profile1
    assert "Rust" in profile2.languages.languages


@pytest.mark.asyncio
async def test_incremental_update_reflects_removed_language(
    detector: ProjectDetector, repo_dir: Path
):
    """After removing the only file of a language, re-detection no longer includes it (Req 9.3)."""
    # Start with Python and Go files
    (repo_dir / "service.go").write_text("package main\n\nfunc main() {}\n")
    profile1 = await detector.detect(repo_dir)
    assert "Go" in profile1.languages.languages

    # Remove the Go file — triggers cache miss and re-detection
    (repo_dir / "service.go").unlink()
    profile2 = await detector.detect(repo_dir)

    assert profile2 is not profile1
    assert "Go" not in profile2.languages.languages


@pytest.mark.asyncio
async def test_incremental_update_preserves_unchanged_languages(
    detector: ProjectDetector, repo_dir: Path
):
    """Adding files in a new language preserves existing language stats (Req 9.3)."""
    profile1 = await detector.detect(repo_dir)
    python_stats_before = profile1.languages.languages["Python"]

    # Add a JavaScript file — should not alter Python file count
    (repo_dir / "app.js").write_text("console.log('hi');\n")
    profile2 = await detector.detect(repo_dir)

    python_stats_after = profile2.languages.languages["Python"]
    assert python_stats_after.file_count == python_stats_before.file_count
    assert python_stats_after.lines_of_code == python_stats_before.lines_of_code


@pytest.mark.asyncio
async def test_incremental_update_on_multiple_file_additions(
    detector: ProjectDetector, repo_dir: Path
):
    """Adding multiple files triggers proper re-detection with updated profile (Req 9.3)."""
    profile1 = await detector.detect(repo_dir)
    initial_file_hash = profile1.file_tree_hash

    # Add several new files
    (repo_dir / "util.py").write_text("def helper(): pass\n")
    (repo_dir / "lib.py").write_text("class Lib: pass\n")
    (repo_dir / "test.py").write_text("assert True\n")

    profile2 = await detector.detect(repo_dir)

    # File tree hash should have changed
    assert profile2.file_tree_hash != initial_file_hash
    # Python file count should reflect the additions
    assert profile2.languages.languages["Python"].file_count == 4
