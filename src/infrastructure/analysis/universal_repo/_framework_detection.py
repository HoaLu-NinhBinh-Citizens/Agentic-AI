"""Framework detection helpers — private module for ProjectDetector.

Contains language-specific framework detection logic, config file parsers,
and the known framework mappings used by detect_frameworks().

Requirements: 2.1
"""

from __future__ import annotations

import re
from pathlib import Path

from .models import Framework

# ─── Known Framework Mappings ────────────────────────────────────────────────

JS_TS_FRAMEWORKS: dict[str, str] = {
    "react": "React",
    "react-dom": "React",
    "@angular/core": "Angular",
    "vue": "Vue",
    "express": "Express",
    "next": "Next.js",
    "@nestjs/core": "NestJS",
    "svelte": "Svelte",
    "nuxt": "Nuxt",
    "gatsby": "Gatsby",
    "koa": "Koa",
    "fastify": "Fastify",
    "hapi": "Hapi",
    "electron": "Electron",
    "jest": "Jest",
    "mocha": "Mocha",
    "vitest": "Vitest",
}

PYTHON_FRAMEWORKS: dict[str, str] = {
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "pytest": "pytest",
    "celery": "Celery",
    "sqlalchemy": "SQLAlchemy",
    "tornado": "Tornado",
    "aiohttp": "aiohttp",
    "starlette": "Starlette",
    "pydantic": "Pydantic",
    "numpy": "NumPy",
    "pandas": "Pandas",
    "tensorflow": "TensorFlow",
    "torch": "PyTorch",
    "scipy": "SciPy",
}

RUST_FRAMEWORKS: dict[str, str] = {
    "actix-web": "Actix Web",
    "actix-rt": "Actix",
    "tokio": "Tokio",
    "rocket": "Rocket",
    "serde": "Serde",
    "axum": "Axum",
    "warp": "Warp",
    "hyper": "Hyper",
    "diesel": "Diesel",
    "sqlx": "SQLx",
    "clap": "Clap",
    "tonic": "Tonic",
}

JAVA_FRAMEWORKS: dict[str, str] = {
    "spring-boot": "Spring Boot",
    "spring-core": "Spring",
    "spring-web": "Spring Web",
    "hibernate-core": "Hibernate",
    "junit-jupiter": "JUnit 5",
    "junit": "JUnit",
    "mockito": "Mockito",
    "lombok": "Lombok",
    "jackson": "Jackson",
    "quarkus": "Quarkus",
    "micronaut": "Micronaut",
}

GO_FRAMEWORKS: dict[str, str] = {
    "github.com/gin-gonic/gin": "Gin",
    "github.com/labstack/echo": "Echo",
    "github.com/gofiber/fiber": "Fiber",
    "github.com/gorilla/mux": "Gorilla Mux",
    "github.com/go-chi/chi": "Chi",
    "gorm.io/gorm": "GORM",
    "github.com/stretchr/testify": "Testify",
    "google.golang.org/grpc": "gRPC",
    "github.com/spf13/cobra": "Cobra",
    "github.com/spf13/viper": "Viper",
}

CMAKE_PACKAGES: dict[str, str] = {
    "Boost": "Boost",
    "OpenCV": "OpenCV",
    "Qt5": "Qt5",
    "Qt6": "Qt6",
    "GTest": "Google Test",
    "Protobuf": "Protobuf",
    "OpenSSL": "OpenSSL",
    "CURL": "cURL",
    "Threads": "Threads",
    "SDL2": "SDL2",
}


# ─── Detection Functions ─────────────────────────────────────────────────────


def detect_js_ts_frameworks(repo_path: Path, language: str) -> list[Framework]:
    """Detect JS/TS frameworks from package.json dependencies."""
    package_json = repo_path / "package.json"
    if not package_json.exists():
        return []

    try:
        content = package_json.read_text(encoding="utf-8")
    except (OSError, PermissionError):
        return []

    frameworks: list[Framework] = []
    for pkg_name, framework_name in JS_TS_FRAMEWORKS.items():
        pattern = rf'"{re.escape(pkg_name)}"\s*:\s*"([^"]*)"'
        match = re.search(pattern, content)
        if match:
            version = _clean_version(match.group(1))
            if not any(f.name == framework_name for f in frameworks):
                frameworks.append(
                    Framework(
                        name=framework_name,
                        version=version,
                        language=language,
                        detected_from="package.json",
                    )
                )

    return frameworks


def detect_python_frameworks(repo_path: Path) -> list[Framework]:
    """Detect Python frameworks from pyproject.toml, setup.py, requirements.txt."""
    frameworks: list[Framework] = []

    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        frameworks.extend(_parse_python_config(pyproject, "pyproject.toml"))

    requirements = repo_path / "requirements.txt"
    if requirements.exists():
        frameworks.extend(_parse_requirements_txt(requirements))

    setup_py = repo_path / "setup.py"
    if setup_py.exists() and not frameworks:
        frameworks.extend(_parse_python_config(setup_py, "setup.py"))

    return _deduplicate_frameworks(frameworks)


def detect_rust_frameworks(repo_path: Path) -> list[Framework]:
    """Detect Rust frameworks from Cargo.toml [dependencies]."""
    cargo_toml = repo_path / "Cargo.toml"
    if not cargo_toml.exists():
        return []

    try:
        content = cargo_toml.read_text(encoding="utf-8")
    except (OSError, PermissionError):
        return []

    frameworks: list[Framework] = []
    for crate_name, framework_name in RUST_FRAMEWORKS.items():
        pattern_simple = rf'^{re.escape(crate_name)}\s*=\s*"([^"]*)"'
        pattern_table = (
            rf'^{re.escape(crate_name)}\s*=\s*\{{[^}}]*version\s*=\s*"([^"]*)"'
        )

        match = re.search(pattern_simple, content, re.MULTILINE)
        if not match:
            match = re.search(pattern_table, content, re.MULTILINE)

        if match:
            version = _clean_version(match.group(1))
            frameworks.append(
                Framework(
                    name=framework_name,
                    version=version,
                    language="Rust",
                    detected_from="Cargo.toml",
                )
            )

    return frameworks


def detect_java_frameworks(repo_path: Path) -> list[Framework]:
    """Detect Java frameworks from pom.xml and build.gradle."""
    frameworks: list[Framework] = []

    pom_xml = repo_path / "pom.xml"
    if pom_xml.exists():
        frameworks.extend(_parse_pom_xml(pom_xml))

    build_gradle = repo_path / "build.gradle"
    if build_gradle.exists():
        frameworks.extend(_parse_build_gradle(build_gradle))

    build_gradle_kts = repo_path / "build.gradle.kts"
    if build_gradle_kts.exists() and not frameworks:
        frameworks.extend(_parse_build_gradle(build_gradle_kts))

    return _deduplicate_frameworks(frameworks)


def detect_go_frameworks(repo_path: Path) -> list[Framework]:
    """Detect Go frameworks from go.mod require lines."""
    go_mod = repo_path / "go.mod"
    if not go_mod.exists():
        return []

    try:
        content = go_mod.read_text(encoding="utf-8")
    except (OSError, PermissionError):
        return []

    frameworks: list[Framework] = []
    for module_path, framework_name in GO_FRAMEWORKS.items():
        pattern = rf'{re.escape(module_path)}\s+v([0-9][0-9a-zA-Z.\-]*)'
        match = re.search(pattern, content)
        if match:
            version = match.group(1)
            frameworks.append(
                Framework(
                    name=framework_name,
                    version=version,
                    language="Go",
                    detected_from="go.mod",
                )
            )

    return frameworks


def detect_cmake_frameworks(repo_path: Path, language: str) -> list[Framework]:
    """Detect C/C++ frameworks from CMakeLists.txt find_package() calls."""
    cmake_file = repo_path / "CMakeLists.txt"
    if not cmake_file.exists():
        return []

    try:
        content = cmake_file.read_text(encoding="utf-8")
    except (OSError, PermissionError):
        return []

    frameworks: list[Framework] = []
    find_package_re = r'find_package\s*\(\s*(\w+)(?:\s+([0-9][0-9.]*))?'
    for match in re.finditer(find_package_re, content):
        pkg_name = match.group(1)
        version = match.group(2) if match.group(2) else None
        framework_name = CMAKE_PACKAGES.get(pkg_name, pkg_name)
        frameworks.append(
            Framework(
                name=framework_name,
                version=version,
                language=language,
                detected_from="CMakeLists.txt",
            )
        )

    return frameworks


# ─── Private Helpers ─────────────────────────────────────────────────────────


def _parse_python_config(config_path: Path, source: str) -> list[Framework]:
    """Parse a Python config file for known framework references."""
    try:
        content = config_path.read_text(encoding="utf-8")
    except (OSError, PermissionError):
        return []

    frameworks: list[Framework] = []
    for pkg_name, framework_name in PYTHON_FRAMEWORKS.items():
        pattern = (
            rf'(?:^|[\s"\',=])({re.escape(pkg_name)})'
            rf'(?:\s*[><=~!]+\s*([0-9][0-9a-zA-Z.*]*)|(?=[\s"\',\]\)])|\s*$)'
        )
        match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
        if match:
            version = match.group(2) if match.group(2) else None
            frameworks.append(
                Framework(
                    name=framework_name,
                    version=version,
                    language="Python",
                    detected_from=source,
                )
            )

    return frameworks


def _parse_requirements_txt(req_path: Path) -> list[Framework]:
    """Parse requirements.txt for known Python frameworks."""
    try:
        content = req_path.read_text(encoding="utf-8")
    except (OSError, PermissionError):
        return []

    frameworks: list[Framework] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue

        for pkg_name, framework_name in PYTHON_FRAMEWORKS.items():
            pattern = (
                rf'^{re.escape(pkg_name)}(?:\s*[><=~!]+\s*([0-9][0-9a-zA-Z.]*)|$)'
            )
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                version = match.group(1) if match.group(1) else None
                frameworks.append(
                    Framework(
                        name=framework_name,
                        version=version,
                        language="Python",
                        detected_from="requirements.txt",
                    )
                )
                break

    return frameworks


def _parse_pom_xml(pom_path: Path) -> list[Framework]:
    """Parse pom.xml for known Java framework artifactIds."""
    try:
        content = pom_path.read_text(encoding="utf-8")
    except (OSError, PermissionError):
        return []

    frameworks: list[Framework] = []
    for artifact_pattern, framework_name in JAVA_FRAMEWORKS.items():
        artifact_re = (
            rf'<artifactId>\s*{re.escape(artifact_pattern)}[^<]*</artifactId>'
        )
        if re.search(artifact_re, content):
            version_re = (
                rf'<artifactId>\s*{re.escape(artifact_pattern)}[^<]*</artifactId>'
                rf'[^<]*(?:<[^>]*>[^<]*)*?<version>\s*([^<]+?)\s*</version>'
            )
            version_match = re.search(version_re, content)
            version = version_match.group(1) if version_match else None
            if version and version.startswith("$"):
                version = None

            if not any(f.name == framework_name for f in frameworks):
                frameworks.append(
                    Framework(
                        name=framework_name,
                        version=version,
                        language="Java",
                        detected_from="pom.xml",
                    )
                )

    return frameworks


def _parse_build_gradle(gradle_path: Path) -> list[Framework]:
    """Parse build.gradle for known Java framework dependencies."""
    try:
        content = gradle_path.read_text(encoding="utf-8")
    except (OSError, PermissionError):
        return []

    frameworks: list[Framework] = []
    for artifact_pattern, framework_name in JAVA_FRAMEWORKS.items():
        pattern = (
            rf"""['"]\S*:{re.escape(artifact_pattern)}"""
            rf"""[^'"]*?(?::([0-9][0-9a-zA-Z.]*))?\s*['"]"""
        )
        match = re.search(pattern, content)
        if match:
            version = match.group(1) if match.group(1) else None
            if not any(f.name == framework_name for f in frameworks):
                frameworks.append(
                    Framework(
                        name=framework_name,
                        version=version,
                        language="Java",
                        detected_from=gradle_path.name,
                    )
                )

    return frameworks


def _clean_version(version_str: str) -> str | None:
    """Clean a version string by stripping semver range prefixes."""
    if not version_str:
        return None
    cleaned = re.sub(r'^[^0-9]*', '', version_str)
    return cleaned if cleaned else None


def _deduplicate_frameworks(frameworks: list[Framework]) -> list[Framework]:
    """Remove duplicate frameworks, keeping the first occurrence."""
    seen: set[str] = set()
    result: list[Framework] = []
    for fw in frameworks:
        if fw.name not in seen:
            seen.add(fw.name)
            result.append(fw)
    return result
