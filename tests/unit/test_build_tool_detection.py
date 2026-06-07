"""Unit tests for ProjectDetector.detect_build_tools().

Tests build tool detection for Make, CMake, npm/yarn/pnpm, pip/poetry/setuptools,
Cargo, Go modules, Gradle, and Maven. Verifies relevance ranking, config
extraction, and empty-repo behavior.

Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7
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
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


# ─── No Build Tool Tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_build_tool_returns_empty_list(
    detector: ProjectDetector, repo_dir: Path
):
    """Empty repo returns empty list (caller reports no_build_tool_detected)."""
    result = await detector.detect_build_tools(repo_dir)
    assert result == []


@pytest.mark.asyncio
async def test_only_unrecognized_files_returns_empty(
    detector: ProjectDetector, repo_dir: Path
):
    """Repo with only non-config files returns empty list."""
    (repo_dir / "README.md").write_text("# Hello\n")
    (repo_dir / "data.csv").write_text("a,b,c\n")

    result = await detector.detect_build_tools(repo_dir)
    assert result == []


# ─── Make Detection Tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detects_make_from_makefile(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "Makefile").write_text(
        "all:\n\tgcc -o app main.c\n\nbuild:\n\tgcc -O2 main.c\n"
    )

    result = await detector.detect_build_tools(repo_dir)

    make_tools = [t for t in result if t.name == "make"]
    assert len(make_tools) == 1
    assert make_tools[0].config_file == repo_dir / "Makefile"
    assert "make" in make_tools[0].build_commands


# ─── CMake Detection Tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detects_cmake_from_cmakelists(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.16)\n"
        "project(MyApp)\n"
        "add_executable(myapp main.cpp)\n"
        "add_library(mylib STATIC lib.cpp)\n"
    )

    result = await detector.detect_build_tools(repo_dir)

    cmake_tools = [t for t in result if t.name == "cmake"]
    assert len(cmake_tools) == 1
    assert cmake_tools[0].config_file == repo_dir / "CMakeLists.txt"
    assert "cmake -B build" in cmake_tools[0].build_commands
    assert "cmake --build build" in cmake_tools[0].build_commands


@pytest.mark.asyncio
async def test_cmake_extracts_targets(
    detector: ProjectDetector, repo_dir: Path
):
    """CMake detection extracts target names from add_executable/add_library."""
    (repo_dir / "CMakeLists.txt").write_text(
        "add_executable(server src/main.cpp)\n"
        "add_library(utils SHARED utils.cpp)\n"
    )

    result = await detector.detect_build_tools(repo_dir)

    cmake_tools = [t for t in result if t.name == "cmake"]
    assert len(cmake_tools) == 1
    # Should have target-specific build commands
    target_commands = [
        c for c in cmake_tools[0].build_commands if "--target" in c
    ]
    assert any("server" in c for c in target_commands)
    assert any("utils" in c for c in target_commands)


# ─── npm/yarn/pnpm Detection Tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_detects_npm_by_default(
    detector: ProjectDetector, repo_dir: Path
):
    """Without any lockfile, defaults to npm."""
    (repo_dir / "package.json").write_text(
        '{"name": "app", "scripts": {"build": "tsc", "test": "jest"}}\n'
    )

    result = await detector.detect_build_tools(repo_dir)

    npm_tools = [t for t in result if t.name == "npm"]
    assert len(npm_tools) == 1
    assert "npm install" in npm_tools[0].build_commands


@pytest.mark.asyncio
async def test_detects_yarn_from_lockfile(
    detector: ProjectDetector, repo_dir: Path
):
    """yarn.lock presence identifies yarn as the package manager."""
    (repo_dir / "package.json").write_text(
        '{"name": "app", "scripts": {"dev": "next dev"}}\n'
    )
    (repo_dir / "yarn.lock").write_text("# yarn lockfile\n")

    result = await detector.detect_build_tools(repo_dir)

    yarn_tools = [t for t in result if t.name == "yarn"]
    assert len(yarn_tools) == 1
    assert "yarn install" in yarn_tools[0].build_commands


@pytest.mark.asyncio
async def test_detects_pnpm_from_lockfile(
    detector: ProjectDetector, repo_dir: Path
):
    """pnpm-lock.yaml presence identifies pnpm."""
    (repo_dir / "package.json").write_text(
        '{"name": "app", "scripts": {"build": "vite build"}}\n'
    )
    (repo_dir / "pnpm-lock.yaml").write_text("lockfileVersion: 5.4\n")

    result = await detector.detect_build_tools(repo_dir)

    pnpm_tools = [t for t in result if t.name == "pnpm"]
    assert len(pnpm_tools) == 1
    assert "pnpm install" in pnpm_tools[0].build_commands


@pytest.mark.asyncio
async def test_package_json_scripts_extracted(
    detector: ProjectDetector, repo_dir: Path
):
    """Build scripts from package.json are extracted into build_commands."""
    (repo_dir / "package.json").write_text(
        '{"name": "app", "scripts": {"build": "tsc", "lint": "eslint .", "test": "jest"}}\n'
    )

    result = await detector.detect_build_tools(repo_dir)

    npm_tools = [t for t in result if t.name == "npm"]
    assert len(npm_tools) == 1
    commands = npm_tools[0].build_commands
    assert any("build" in c for c in commands)
    assert any("lint" in c for c in commands)
    assert any("test" in c for c in commands)


# ─── Cargo Detection Tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detects_cargo_from_cargo_toml(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "Cargo.toml").write_text(
        '[package]\nname = "myapp"\nversion = "0.1.0"\n'
    )

    result = await detector.detect_build_tools(repo_dir)

    cargo_tools = [t for t in result if t.name == "cargo"]
    assert len(cargo_tools) == 1
    assert "cargo build" in cargo_tools[0].build_commands
    assert "cargo test" in cargo_tools[0].build_commands


@pytest.mark.asyncio
async def test_cargo_extracts_workspace_members(
    detector: ProjectDetector, repo_dir: Path
):
    """Cargo detection extracts workspace members from Cargo.toml."""
    (repo_dir / "Cargo.toml").write_text(
        '[workspace]\nmembers = ["crate-a", "crate-b", "crate-c"]\n'
    )

    result = await detector.detect_build_tools(repo_dir)

    cargo_tools = [t for t in result if t.name == "cargo"]
    assert len(cargo_tools) == 1
    commands = cargo_tools[0].build_commands
    assert any("crate-a" in c for c in commands)
    assert any("crate-b" in c for c in commands)
    assert any("crate-c" in c for c in commands)


# ─── Go Modules Detection Tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detects_go_modules_from_go_mod(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "go.mod").write_text("module example.com/app\n\ngo 1.21\n")

    result = await detector.detect_build_tools(repo_dir)

    go_tools = [t for t in result if t.name == "go"]
    assert len(go_tools) == 1
    assert "go build ./..." in go_tools[0].build_commands
    assert "go test ./..." in go_tools[0].build_commands


# ─── Python Build Tool Detection Tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_detects_poetry_from_pyproject(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "myapp"\n\n'
        '[build-system]\nrequires = ["poetry-core"]\n'
        'build-backend = "poetry.core.masonry.api"\n'
    )

    result = await detector.detect_build_tools(repo_dir)

    poetry_tools = [t for t in result if t.name == "poetry"]
    assert len(poetry_tools) == 1
    assert "poetry install" in poetry_tools[0].build_commands


@pytest.mark.asyncio
async def test_detects_setuptools_from_pyproject(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools>=68.0"]\n'
        'build-backend = "setuptools.build_meta"\n'
    )

    result = await detector.detect_build_tools(repo_dir)

    setuptools_tools = [t for t in result if t.name == "setuptools"]
    assert len(setuptools_tools) == 1


@pytest.mark.asyncio
async def test_detects_setuptools_from_setup_py(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "setup.py").write_text(
        "from setuptools import setup\nsetup(name='myapp')\n"
    )

    result = await detector.detect_build_tools(repo_dir)

    setuptools_tools = [t for t in result if t.name == "setuptools"]
    assert len(setuptools_tools) == 1
    assert setuptools_tools[0].config_file == repo_dir / "setup.py"


@pytest.mark.asyncio
async def test_detects_pip_from_plain_pyproject(
    detector: ProjectDetector, repo_dir: Path
):
    """pyproject.toml without specific backend defaults to pip."""
    (repo_dir / "pyproject.toml").write_text(
        '[project]\nname = "myapp"\nversion = "0.1.0"\n'
    )

    result = await detector.detect_build_tools(repo_dir)

    pip_tools = [t for t in result if t.name == "pip"]
    assert len(pip_tools) == 1


# ─── Gradle Detection Tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detects_gradle_from_build_gradle(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "build.gradle").write_text(
        "plugins {\n    id 'java'\n}\n"
    )

    result = await detector.detect_build_tools(repo_dir)

    gradle_tools = [t for t in result if t.name == "gradle"]
    assert len(gradle_tools) == 1
    assert "./gradlew build" in gradle_tools[0].build_commands


@pytest.mark.asyncio
async def test_detects_gradle_from_build_gradle_kts(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "build.gradle.kts").write_text(
        "plugins {\n    java\n}\n"
    )

    result = await detector.detect_build_tools(repo_dir)

    gradle_tools = [t for t in result if t.name == "gradle"]
    assert len(gradle_tools) == 1


# ─── Maven Detection Tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detects_maven_from_pom_xml(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "pom.xml").write_text(
        '<?xml version="1.0"?>\n<project>\n'
        "  <groupId>com.example</groupId>\n"
        "  <artifactId>myapp</artifactId>\n"
        "</project>\n"
    )

    result = await detector.detect_build_tools(repo_dir)

    maven_tools = [t for t in result if t.name == "maven"]
    assert len(maven_tools) == 1
    assert "mvn compile" in maven_tools[0].build_commands


# ─── Relevance Ranking Tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_relevance_ranking_multiple_tools(
    detector: ProjectDetector, repo_dir: Path
):
    """When multiple build tools present, results are sorted by relevance."""
    (repo_dir / "Cargo.toml").write_text('[package]\nname = "app"\n')
    (repo_dir / "Makefile").write_text("all:\n\tcargo build\n")

    result = await detector.detect_build_tools(repo_dir)

    assert len(result) == 2
    # Cargo (1.0) should rank higher than Make (0.75)
    assert result[0].name == "cargo"
    assert result[1].name == "make"
    assert result[0].relevance_score > result[1].relevance_score


@pytest.mark.asyncio
async def test_relevance_scores_are_between_zero_and_one(
    detector: ProjectDetector, repo_dir: Path
):
    """All relevance scores are in [0.0, 1.0] range."""
    (repo_dir / "package.json").write_text('{"name": "app"}\n')
    (repo_dir / "Makefile").write_text("all:\n\tnpm run build\n")
    (repo_dir / "go.mod").write_text("module example.com/app\n\ngo 1.21\n")

    result = await detector.detect_build_tools(repo_dir)

    for tool in result:
        assert 0.0 <= tool.relevance_score <= 1.0
