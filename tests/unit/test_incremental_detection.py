"""Unit tests for ProjectDetector.detect_incremental().

Tests incremental profile updates when files are added or removed,
without requiring a full re-scan.

Requirements: 9.3
"""

from __future__ import annotations

import pytest
from pathlib import Path

from infrastructure.analysis.universal_repo.project_detector import ProjectDetector


@pytest.fixture
def detector() -> ProjectDetector:
    return ProjectDetector()


@pytest.fixture
def repo_dir(tmp_path: Path) -> Path:
    """Create a repo with a few Python files for baseline detection."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hello')\nprint('world')\n")
    (repo / "utils.py").write_text("x = 1\n")
    return repo


@pytest.mark.asyncio
async def test_incremental_adds_new_language(
    detector: ProjectDetector, repo_dir: Path,
):
    """Adding a file of a new language updates the profile incrementally."""
    await detector.detect(repo_dir)

    new_file = repo_dir / "app.js"
    new_file.write_text("console.log('hi');\n")

    profile = await detector.detect_incremental(
        repo_dir, added_files=[new_file], removed_files=[],
    )

    assert "JavaScript" in profile.languages.languages
    assert profile.languages.languages["JavaScript"].file_count == 1


@pytest.mark.asyncio
async def test_incremental_removes_language_when_last_file_removed(
    detector: ProjectDetector, repo_dir: Path,
):
    """Removing the last file of a language drops it from the profile."""
    js_file = repo_dir / "index.js"
    js_file.write_text("const x = 1;\n")
    await detector.detect(repo_dir)
    assert "JavaScript" in (await detector.detect(repo_dir)).languages.languages

    # Simulate removal
    js_file.unlink()
    profile = await detector.detect_incremental(
        repo_dir, added_files=[], removed_files=[js_file],
    )

    assert "JavaScript" not in profile.languages.languages


@pytest.mark.asyncio
async def test_incremental_updates_file_count(
    detector: ProjectDetector, repo_dir: Path,
):
    """Adding files of an existing language increases file_count."""
    await detector.detect(repo_dir)

    new_file = repo_dir / "extra.py"
    new_file.write_text("y = 2\nz = 3\n")

    profile = await detector.detect_incremental(
        repo_dir, added_files=[new_file], removed_files=[],
    )

    # Started with 2 Python files, now 3
    assert profile.languages.languages["Python"].file_count == 3


@pytest.mark.asyncio
async def test_incremental_recomputes_percentages(
    detector: ProjectDetector, repo_dir: Path,
):
    """Percentages are recomputed after incremental update."""
    await detector.detect(repo_dir)

    js_file = repo_dir / "app.js"
    js_file.write_text("x\n")

    profile = await detector.detect_incremental(
        repo_dir, added_files=[js_file], removed_files=[],
    )

    # Total percentages should sum to ~100%
    total_pct = sum(
        s.percentage_files for s in profile.languages.languages.values()
    )
    assert abs(total_pct - 100.0) < 0.1


@pytest.mark.asyncio
async def test_incremental_recomputes_primary_language(
    detector: ProjectDetector, repo_dir: Path,
):
    """Primary language updates if a new language has more LOC."""
    await detector.detect(repo_dir)

    # Add a large Rust file that dominates by LOC
    rs_file = repo_dir / "lib.rs"
    rs_file.write_text("\n".join(f"fn f{i}() {{}}" for i in range(100)) + "\n")

    profile = await detector.detect_incremental(
        repo_dir, added_files=[rs_file], removed_files=[],
    )

    assert profile.languages.primary_language == "Rust"


@pytest.mark.asyncio
async def test_incremental_updates_file_tree_hash(
    detector: ProjectDetector, repo_dir: Path,
):
    """file_tree_hash is recomputed after incremental update."""
    original = await detector.detect(repo_dir)

    new_file = repo_dir / "new.py"
    new_file.write_text("pass\n")

    updated = await detector.detect_incremental(
        repo_dir, added_files=[new_file], removed_files=[],
    )

    assert updated.file_tree_hash != original.file_tree_hash


@pytest.mark.asyncio
async def test_incremental_triggers_framework_redetect_on_config_add(
    detector: ProjectDetector, repo_dir: Path,
):
    """Adding a config file triggers framework/build tool redetection."""
    await detector.detect(repo_dir)

    pkg_json = repo_dir / "package.json"
    pkg_json.write_text('{"name":"app","dependencies":{"express":"^4.0.0"}}\n')
    js_file = repo_dir / "server.js"
    js_file.write_text("const express = require('express');\n")

    profile = await detector.detect_incremental(
        repo_dir, added_files=[pkg_json, js_file], removed_files=[],
    )

    # Frameworks should have been re-detected
    framework_names = [f.name for f in profile.frameworks]
    assert "Express" in framework_names


@pytest.mark.asyncio
async def test_incremental_skips_framework_redetect_for_non_config(
    detector: ProjectDetector, repo_dir: Path,
):
    """Non-config file changes do not trigger framework redetection."""
    original = await detector.detect(repo_dir)

    new_file = repo_dir / "helper.py"
    new_file.write_text("def helper(): pass\n")

    updated = await detector.detect_incremental(
        repo_dir, added_files=[new_file], removed_files=[],
    )

    # Frameworks unchanged (same list)
    assert updated.frameworks == original.frameworks


@pytest.mark.asyncio
async def test_incremental_falls_back_to_full_detect_without_cache(
    detector: ProjectDetector, repo_dir: Path,
):
    """Without a cached profile, detect_incremental does a full detect."""
    new_file = repo_dir / "extra.py"
    new_file.write_text("a = 1\n")

    profile = await detector.detect_incremental(
        repo_dir, added_files=[new_file], removed_files=[],
    )

    # Should still produce a valid profile
    assert profile.languages.primary_language == "Python"
    assert profile.languages.languages["Python"].file_count >= 2


@pytest.mark.asyncio
async def test_incremental_stores_updated_profile_in_cache(
    detector: ProjectDetector, repo_dir: Path,
):
    """The updated profile is stored in the internal cache."""
    await detector.detect(repo_dir)

    new_file = repo_dir / "mod.py"
    new_file.write_text("pass\n")

    updated = await detector.detect_incremental(
        repo_dir, added_files=[new_file], removed_files=[],
    )

    # Cache should now hold the updated profile
    cached = detector._cache.get(str(repo_dir))
    assert cached is updated
