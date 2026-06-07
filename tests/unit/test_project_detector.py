"""Unit tests for ProjectDetector.detect_languages().

Tests language detection by file extension, shebang line,
language markers, and edge cases (empty repos, unknown files).

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
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
    """Create a temporary repository directory."""
    return tmp_path / "repo"


# ─── Extension Detection Tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detects_python_by_extension(detector: ProjectDetector, repo_dir: Path):
    repo_dir.mkdir()
    (repo_dir / "main.py").write_text("print('hello')\n")
    (repo_dir / "utils.py").write_text("def foo():\n    pass\n")

    result = await detector.detect_languages(repo_dir)

    assert result.primary_language == "Python"
    assert "Python" in result.languages
    assert result.languages["Python"].file_count == 2


@pytest.mark.asyncio
async def test_detects_javascript_by_extension(detector: ProjectDetector, repo_dir: Path):
    repo_dir.mkdir()
    (repo_dir / "index.js").write_text("console.log('hi');\n")

    result = await detector.detect_languages(repo_dir)

    assert result.primary_language == "JavaScript"
    assert result.languages["JavaScript"].file_count == 1


@pytest.mark.asyncio
async def test_detects_typescript_by_extension(detector: ProjectDetector, repo_dir: Path):
    repo_dir.mkdir()
    (repo_dir / "app.ts").write_text("const x: number = 1;\n")
    (repo_dir / "component.tsx").write_text("export const C = () => <div/>;\n")

    result = await detector.detect_languages(repo_dir)

    assert result.primary_language == "TypeScript"
    assert result.languages["TypeScript"].file_count == 2


@pytest.mark.asyncio
async def test_detects_c_by_extension(detector: ProjectDetector, repo_dir: Path):
    repo_dir.mkdir()
    (repo_dir / "main.c").write_text("#include <stdio.h>\nint main() { return 0; }\n")
    (repo_dir / "util.h").write_text("#pragma once\nvoid foo();\n")

    result = await detector.detect_languages(repo_dir)

    assert result.primary_language == "C"
    assert result.languages["C"].file_count == 2


@pytest.mark.asyncio
async def test_detects_cpp_by_extension(detector: ProjectDetector, repo_dir: Path):
    repo_dir.mkdir()
    (repo_dir / "main.cpp").write_text("#include <iostream>\nint main() {}\n")
    (repo_dir / "util.hpp").write_text("#pragma once\n")
    (repo_dir / "algo.cc").write_text("void algo() {}\n")
    (repo_dir / "extra.cxx").write_text("void extra() {}\n")

    result = await detector.detect_languages(repo_dir)

    assert result.primary_language == "C++"
    assert result.languages["C++"].file_count == 4


@pytest.mark.asyncio
async def test_detects_rust_by_extension(detector: ProjectDetector, repo_dir: Path):
    repo_dir.mkdir()
    (repo_dir / "main.rs").write_text("fn main() {\n    println!(\"hello\");\n}\n")

    result = await detector.detect_languages(repo_dir)

    assert result.primary_language == "Rust"
    assert result.languages["Rust"].file_count == 1


@pytest.mark.asyncio
async def test_detects_go_by_extension(detector: ProjectDetector, repo_dir: Path):
    repo_dir.mkdir()
    (repo_dir / "main.go").write_text("package main\n\nfunc main() {}\n")

    result = await detector.detect_languages(repo_dir)

    assert result.primary_language == "Go"
    assert result.languages["Go"].file_count == 1


@pytest.mark.asyncio
async def test_detects_java_by_extension(detector: ProjectDetector, repo_dir: Path):
    repo_dir.mkdir()
    (repo_dir / "Main.java").write_text("public class Main {\n    public static void main(String[] args) {}\n}\n")

    result = await detector.detect_languages(repo_dir)

    assert result.primary_language == "Java"
    assert result.languages["Java"].file_count == 1


# ─── Shebang Detection Tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detects_python_by_shebang(detector: ProjectDetector, repo_dir: Path):
    repo_dir.mkdir()
    script = repo_dir / "run_script"
    script.write_text("#!/usr/bin/env python3\nprint('hello')\n")

    result = await detector.detect_languages(repo_dir)

    assert "Python" in result.languages


@pytest.mark.asyncio
async def test_detects_node_by_shebang(detector: ProjectDetector, repo_dir: Path):
    repo_dir.mkdir()
    script = repo_dir / "server"
    script.write_text("#!/usr/bin/env node\nconsole.log('hi');\n")

    result = await detector.detect_languages(repo_dir)

    assert "JavaScript" in result.languages


@pytest.mark.asyncio
async def test_detects_python_by_direct_shebang(detector: ProjectDetector, repo_dir: Path):
    repo_dir.mkdir()
    script = repo_dir / "tool"
    script.write_text("#!/usr/bin/python3\nimport sys\n")

    result = await detector.detect_languages(repo_dir)

    assert "Python" in result.languages


# ─── Empty/Unknown Repository Tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_repo_returns_unknown(detector: ProjectDetector, repo_dir: Path):
    repo_dir.mkdir()

    result = await detector.detect_languages(repo_dir)

    assert result.primary_language == "unknown"
    assert result.languages == {}


@pytest.mark.asyncio
async def test_unrecognized_files_returns_unknown(detector: ProjectDetector, repo_dir: Path):
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text("# Hello\n")
    (repo_dir / "data.csv").write_text("a,b,c\n1,2,3\n")
    (repo_dir / "image.png").write_bytes(b"\x89PNG\r\n")

    result = await detector.detect_languages(repo_dir)

    assert result.primary_language == "unknown"
    assert result.languages == {}


# ─── Percentage Calculation Tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_percentage_calculation(detector: ProjectDetector, repo_dir: Path):
    repo_dir.mkdir()
    (repo_dir / "app.py").write_text("line1\nline2\nline3\n")
    (repo_dir / "main.js").write_text("line1\n")

    result = await detector.detect_languages(repo_dir)

    assert result.languages["Python"].file_count == 1
    assert result.languages["JavaScript"].file_count == 1
    # 1 of 2 files each = 50%
    assert result.languages["Python"].percentage_files == 50.0
    assert result.languages["JavaScript"].percentage_files == 50.0
    # Python has 3 lines, JS has 1 line → Python 75%, JS 25%
    assert result.languages["Python"].percentage_loc == 75.0
    assert result.languages["JavaScript"].percentage_loc == 25.0
    # Primary language is Python (more LOC)
    assert result.primary_language == "Python"


# ─── Skip Directories Tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_skips_node_modules(detector: ProjectDetector, repo_dir: Path):
    repo_dir.mkdir()
    nm = repo_dir / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("module.exports = {};\n")
    (repo_dir / "src.py").write_text("pass\n")

    result = await detector.detect_languages(repo_dir)

    assert "JavaScript" not in result.languages
    assert result.primary_language == "Python"


@pytest.mark.asyncio
async def test_skips_git_directory(detector: ProjectDetector, repo_dir: Path):
    repo_dir.mkdir()
    git_dir = repo_dir / ".git" / "objects"
    git_dir.mkdir(parents=True)
    (git_dir / "pack.py").write_text("# git internal\n")
    (repo_dir / "app.rs").write_text("fn main() {}\n")

    result = await detector.detect_languages(repo_dir)

    assert "Python" not in result.languages
    assert result.primary_language == "Rust"


# ─── Language Marker Tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_marker_file_detects_go(detector: ProjectDetector, repo_dir: Path):
    repo_dir.mkdir()
    (repo_dir / "go.mod").write_text("module example.com/app\n\ngo 1.21\n")

    result = await detector.detect_languages(repo_dir)

    assert "Go" in result.languages


@pytest.mark.asyncio
async def test_marker_file_detects_rust(detector: ProjectDetector, repo_dir: Path):
    repo_dir.mkdir()
    (repo_dir / "Cargo.toml").write_text("[package]\nname = \"app\"\n")

    result = await detector.detect_languages(repo_dir)

    assert "Rust" in result.languages


@pytest.mark.asyncio
async def test_marker_does_not_override_extension_detection(
    detector: ProjectDetector, repo_dir: Path
):
    """When both marker and extension files exist, extension files dominate stats."""
    repo_dir.mkdir()
    (repo_dir / "go.mod").write_text("module example.com/app\n\ngo 1.21\n")
    (repo_dir / "main.go").write_text("package main\n\nfunc main() {}\n")

    result = await detector.detect_languages(repo_dir)

    assert result.primary_language == "Go"
    assert result.languages["Go"].file_count == 1


# ─── Multi-Language Tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_multi_language_repo(detector: ProjectDetector, repo_dir: Path):
    repo_dir.mkdir()
    (repo_dir / "app.py").write_text("x = 1\ny = 2\nz = 3\n")
    (repo_dir / "index.js").write_text("const a = 1;\n")
    (repo_dir / "main.go").write_text("package main\nfunc main() {}\n")

    result = await detector.detect_languages(repo_dir)

    assert len(result.languages) == 3
    assert "Python" in result.languages
    assert "JavaScript" in result.languages
    assert "Go" in result.languages
    # Python has most LOC (3 lines)
    assert result.primary_language == "Python"
