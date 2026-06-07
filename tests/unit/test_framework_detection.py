"""Unit tests for ProjectDetector.detect_frameworks().

Tests framework detection from config files (package.json, Cargo.toml,
pyproject.toml, requirements.txt, pom.xml, build.gradle, go.mod, CMakeLists.txt).

Requirements: 2.1
"""

from __future__ import annotations

import pytest
from pathlib import Path

from infrastructure.analysis.universal_repo.project_detector import ProjectDetector
from infrastructure.analysis.universal_repo.models import (
    LanguageDistribution,
    LanguageStats,
)


@pytest.fixture
def detector() -> ProjectDetector:
    return ProjectDetector()


@pytest.fixture
def repo_dir(tmp_path: Path) -> Path:
    """Create a temporary repository directory."""
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


def _make_lang_dist(languages: list[str]) -> LanguageDistribution:
    """Helper to create a LanguageDistribution with given languages."""
    lang_map = {}
    for lang in languages:
        lang_map[lang] = LanguageStats(
            file_count=1, lines_of_code=10,
            percentage_files=100.0 / len(languages),
            percentage_loc=100.0 / len(languages),
        )
    return LanguageDistribution(
        primary_language=languages[0] if languages else "unknown",
        languages=lang_map,
    )


# ─── JavaScript/TypeScript Framework Tests ────────────────────────────────────


@pytest.mark.asyncio
async def test_detects_react_from_package_json(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "package.json").write_text(
        '{"dependencies": {"react": "^18.2.0", "react-dom": "^18.2.0"}}'
    )
    languages = _make_lang_dist(["TypeScript"])

    result = await detector.detect_frameworks(repo_dir, languages)

    assert len(result) == 1
    assert result[0].name == "React"
    assert result[0].version == "18.2.0"
    assert result[0].language == "TypeScript"
    assert result[0].detected_from == "package.json"


@pytest.mark.asyncio
async def test_detects_multiple_js_frameworks(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "package.json").write_text(
        '{"dependencies": {"express": "~4.18.2", "jest": "^29.0.0"},'
        ' "devDependencies": {"vitest": "^1.0.0"}}'
    )
    languages = _make_lang_dist(["JavaScript"])

    result = await detector.detect_frameworks(repo_dir, languages)

    names = [f.name for f in result]
    assert "Express" in names
    assert "Jest" in names
    assert "Vitest" in names


@pytest.mark.asyncio
async def test_js_uses_typescript_language_when_ts_detected(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "package.json").write_text(
        '{"dependencies": {"vue": "^3.3.0"}}'
    )
    languages = _make_lang_dist(["TypeScript", "JavaScript"])

    result = await detector.detect_frameworks(repo_dir, languages)

    assert result[0].language == "TypeScript"


# ─── Python Framework Tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detects_django_from_requirements_txt(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "requirements.txt").write_text("django==4.2.0\ncelery>=5.3\n")
    languages = _make_lang_dist(["Python"])

    result = await detector.detect_frameworks(repo_dir, languages)

    names = [f.name for f in result]
    assert "Django" in names
    assert "Celery" in names
    django = next(f for f in result if f.name == "Django")
    assert django.version == "4.2.0"
    assert django.detected_from == "requirements.txt"


@pytest.mark.asyncio
async def test_detects_fastapi_from_pyproject_toml(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "pyproject.toml").write_text(
        '[project]\ndependencies = [\n  "fastapi>=0.100.0",\n  "pydantic>=2.0"\n]\n'
    )
    languages = _make_lang_dist(["Python"])

    result = await detector.detect_frameworks(repo_dir, languages)

    names = [f.name for f in result]
    assert "FastAPI" in names
    assert "Pydantic" in names
    fastapi = next(f for f in result if f.name == "FastAPI")
    assert fastapi.detected_from == "pyproject.toml"


@pytest.mark.asyncio
async def test_python_deduplicates_across_files(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "pyproject.toml").write_text(
        '[project]\ndependencies = ["flask>=2.0"]\n'
    )
    (repo_dir / "requirements.txt").write_text("flask==2.3.0\n")
    languages = _make_lang_dist(["Python"])

    result = await detector.detect_frameworks(repo_dir, languages)

    flask_entries = [f for f in result if f.name == "Flask"]
    assert len(flask_entries) == 1


# ─── Rust Framework Tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detects_tokio_from_cargo_toml(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "Cargo.toml").write_text(
        '[package]\nname = "myapp"\nversion = "0.1.0"\n\n'
        '[dependencies]\ntokio = "1.32.0"\nserde = { version = "1.0", features = ["derive"] }\n'
    )
    languages = _make_lang_dist(["Rust"])

    result = await detector.detect_frameworks(repo_dir, languages)

    names = [f.name for f in result]
    assert "Tokio" in names
    assert "Serde" in names
    tokio = next(f for f in result if f.name == "Tokio")
    assert tokio.version == "1.32.0"
    assert tokio.detected_from == "Cargo.toml"


@pytest.mark.asyncio
async def test_detects_actix_web_from_cargo_toml(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "Cargo.toml").write_text(
        '[dependencies]\nactix-web = "4.4.0"\n'
    )
    languages = _make_lang_dist(["Rust"])

    result = await detector.detect_frameworks(repo_dir, languages)

    assert any(f.name == "Actix Web" for f in result)


# ─── Java Framework Tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detects_spring_boot_from_pom_xml(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "pom.xml").write_text(
        '<?xml version="1.0"?>\n<project>\n'
        '  <dependencies>\n'
        '    <dependency>\n'
        '      <groupId>org.springframework.boot</groupId>\n'
        '      <artifactId>spring-boot-starter</artifactId>\n'
        '      <version>3.1.0</version>\n'
        '    </dependency>\n'
        '  </dependencies>\n'
        '</project>\n'
    )
    languages = _make_lang_dist(["Java"])

    result = await detector.detect_frameworks(repo_dir, languages)

    assert any(f.name == "Spring Boot" for f in result)
    sb = next(f for f in result if f.name == "Spring Boot")
    assert sb.version == "3.1.0"
    assert sb.detected_from == "pom.xml"


@pytest.mark.asyncio
async def test_detects_junit_from_build_gradle(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "build.gradle").write_text(
        "dependencies {\n"
        "    testImplementation 'org.junit.jupiter:junit-jupiter:5.9.3'\n"
        "}\n"
    )
    languages = _make_lang_dist(["Java"])

    result = await detector.detect_frameworks(repo_dir, languages)

    assert any(f.name == "JUnit 5" for f in result)


# ─── Go Framework Tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detects_gin_from_go_mod(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "go.mod").write_text(
        "module example.com/myapp\n\ngo 1.21\n\nrequire (\n"
        "\tgithub.com/gin-gonic/gin v1.9.1\n"
        "\tgithub.com/stretchr/testify v1.8.4\n"
        ")\n"
    )
    languages = _make_lang_dist(["Go"])

    result = await detector.detect_frameworks(repo_dir, languages)

    names = [f.name for f in result]
    assert "Gin" in names
    assert "Testify" in names
    gin = next(f for f in result if f.name == "Gin")
    assert gin.version == "1.9.1"
    assert gin.detected_from == "go.mod"


# ─── C/C++ Framework Tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detects_boost_from_cmakelists(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.20)\n"
        "project(MyApp)\n"
        "find_package(Boost 1.80 REQUIRED)\n"
        "find_package(GTest REQUIRED)\n"
    )
    languages = _make_lang_dist(["C++"])

    result = await detector.detect_frameworks(repo_dir, languages)

    names = [f.name for f in result]
    assert "Boost" in names
    assert "Google Test" in names
    boost = next(f for f in result if f.name == "Boost")
    assert boost.version == "1.80"
    assert boost.language == "C++"
    assert boost.detected_from == "CMakeLists.txt"


@pytest.mark.asyncio
async def test_cmake_uses_c_language_when_only_c_detected(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "CMakeLists.txt").write_text(
        "find_package(OpenSSL REQUIRED)\n"
    )
    languages = _make_lang_dist(["C"])

    result = await detector.detect_frameworks(repo_dir, languages)

    assert result[0].language == "C"


# ─── Edge Cases ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_config_files_returns_empty(
    detector: ProjectDetector, repo_dir: Path
):
    languages = _make_lang_dist(["Python"])

    result = await detector.detect_frameworks(repo_dir, languages)

    assert result == []


@pytest.mark.asyncio
async def test_empty_language_distribution_returns_empty(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "package.json").write_text(
        '{"dependencies": {"react": "^18.0.0"}}'
    )
    languages = LanguageDistribution(primary_language="unknown", languages={})

    result = await detector.detect_frameworks(repo_dir, languages)

    assert result == []


@pytest.mark.asyncio
async def test_version_cleaning_strips_caret_and_tilde(
    detector: ProjectDetector, repo_dir: Path
):
    (repo_dir / "package.json").write_text(
        '{"dependencies": {"next": "~13.4.0"}}'
    )
    languages = _make_lang_dist(["JavaScript"])

    result = await detector.detect_frameworks(repo_dir, languages)

    next_fw = next(f for f in result if f.name == "Next.js")
    assert next_fw.version == "13.4.0"
