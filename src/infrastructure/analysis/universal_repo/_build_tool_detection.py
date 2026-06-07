"""Build tool detection helpers — private module for ProjectDetector.

Contains logic for detecting build tools from config files at the project root,
extracting build commands/scripts, workspace members, targets, and computing
relevance scores based on proximity and dependency graph position.

Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7
"""

from __future__ import annotations

import re
from pathlib import Path

from .models import BuildToolInfo

# ─── Named Constants ─────────────────────────────────────────────────────────

# Base relevance scores for build tools at root level.
# Higher scores indicate more "primary" build tools that typically orchestrate
# the entire project build, vs auxiliary tools.
BASE_RELEVANCE_SCORES: dict[str, float] = {
    "cargo": 1.0,
    "go": 1.0,
    "cmake": 0.95,
    "gradle": 0.95,
    "maven": 0.95,
    "npm": 0.90,
    "yarn": 0.90,
    "pnpm": 0.90,
    "poetry": 0.85,
    "pip": 0.80,
    "setuptools": 0.80,
    "make": 0.75,
}

# Depth penalty factor per directory level below root
DEPTH_PENALTY_FACTOR = 0.1


# ─── Public Detection Functions ──────────────────────────────────────────────


def detect_build_tools_at_root(repo_path: Path) -> list[BuildToolInfo]:
    """Detect all build tools from config files at and below the repo root.

    Scans for known build tool config files, extracts build commands,
    and ranks results by relevance score.

    Args:
        repo_path: Root path of the repository to scan.

    Returns:
        List of BuildToolInfo sorted by relevance_score descending.
        Empty list when no build tool config is found.
    """
    tools: list[BuildToolInfo] = []

    # Check each known build tool config at root
    tools.extend(_detect_make(repo_path))
    tools.extend(_detect_cmake(repo_path))
    tools.extend(_detect_js_package_manager(repo_path))
    tools.extend(_detect_cargo(repo_path))
    tools.extend(_detect_go_modules(repo_path))
    tools.extend(_detect_python_build_tools(repo_path))
    tools.extend(_detect_gradle(repo_path))
    tools.extend(_detect_maven(repo_path))

    # Sort by relevance_score descending
    tools.sort(key=lambda t: t.relevance_score, reverse=True)

    return tools


# ─── Individual Build Tool Detectors ─────────────────────────────────────────


def _detect_make(repo_path: Path) -> list[BuildToolInfo]:
    """Detect Make from Makefile presence."""
    makefile = repo_path / "Makefile"
    if not makefile.exists():
        return []

    build_commands = ["make"]
    targets = _extract_make_targets(makefile)
    if targets:
        build_commands.extend(f"make {t}" for t in targets[:5])

    return [
        BuildToolInfo(
            name="make",
            config_file=makefile,
            build_commands=build_commands,
            relevance_score=_compute_relevance("make", repo_path, makefile),
        )
    ]


def _detect_cmake(repo_path: Path) -> list[BuildToolInfo]:
    """Detect CMake from CMakeLists.txt and extract targets."""
    cmake_file = repo_path / "CMakeLists.txt"
    if not cmake_file.exists():
        return []

    build_commands = [
        "cmake -B build",
        "cmake --build build",
    ]
    targets = _extract_cmake_targets(cmake_file)
    if targets:
        build_commands.extend(
            f"cmake --build build --target {t}" for t in targets[:5]
        )

    return [
        BuildToolInfo(
            name="cmake",
            config_file=cmake_file,
            build_commands=build_commands,
            relevance_score=_compute_relevance("cmake", repo_path, cmake_file),
        )
    ]


def _detect_js_package_manager(repo_path: Path) -> list[BuildToolInfo]:
    """Detect npm/yarn/pnpm from package.json and lockfiles."""
    package_json = repo_path / "package.json"
    if not package_json.exists():
        return []

    # Determine which package manager by lockfile presence
    manager_name = _identify_js_package_manager(repo_path)
    scripts = _extract_package_json_scripts(package_json)

    build_commands: list[str] = []
    if manager_name == "yarn":
        build_commands.append("yarn install")
        build_commands.extend(f"yarn {s}" for s in scripts[:5])
    elif manager_name == "pnpm":
        build_commands.append("pnpm install")
        build_commands.extend(f"pnpm run {s}" for s in scripts[:5])
    else:
        build_commands.append("npm install")
        build_commands.extend(f"npm run {s}" for s in scripts[:5])

    return [
        BuildToolInfo(
            name=manager_name,
            config_file=package_json,
            build_commands=build_commands,
            relevance_score=_compute_relevance(
                manager_name, repo_path, package_json
            ),
        )
    ]


def _detect_cargo(repo_path: Path) -> list[BuildToolInfo]:
    """Detect Cargo from Cargo.toml and extract workspace members."""
    cargo_toml = repo_path / "Cargo.toml"
    if not cargo_toml.exists():
        return []

    build_commands = ["cargo build", "cargo test", "cargo run"]
    workspace_members = _extract_cargo_workspace_members(cargo_toml)
    if workspace_members:
        build_commands.extend(
            f"cargo build -p {m}" for m in workspace_members[:5]
        )

    return [
        BuildToolInfo(
            name="cargo",
            config_file=cargo_toml,
            build_commands=build_commands,
            relevance_score=_compute_relevance("cargo", repo_path, cargo_toml),
        )
    ]


def _detect_go_modules(repo_path: Path) -> list[BuildToolInfo]:
    """Detect Go modules from go.mod."""
    go_mod = repo_path / "go.mod"
    if not go_mod.exists():
        return []

    build_commands = ["go build ./...", "go test ./...", "go run ."]

    return [
        BuildToolInfo(
            name="go",
            config_file=go_mod,
            build_commands=build_commands,
            relevance_score=_compute_relevance("go", repo_path, go_mod),
        )
    ]


def _detect_python_build_tools(repo_path: Path) -> list[BuildToolInfo]:
    """Detect pip/poetry/setuptools from pyproject.toml or setup.py."""
    tools: list[BuildToolInfo] = []

    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        tool_name = _identify_python_build_backend(pyproject)
        build_commands = _get_python_build_commands(tool_name)
        tools.append(
            BuildToolInfo(
                name=tool_name,
                config_file=pyproject,
                build_commands=build_commands,
                relevance_score=_compute_relevance(
                    tool_name, repo_path, pyproject
                ),
            )
        )
        return tools

    setup_py = repo_path / "setup.py"
    if setup_py.exists():
        tools.append(
            BuildToolInfo(
                name="setuptools",
                config_file=setup_py,
                build_commands=["pip install -e .", "python setup.py build"],
                relevance_score=_compute_relevance(
                    "setuptools", repo_path, setup_py
                ),
            )
        )

    return tools


def _detect_gradle(repo_path: Path) -> list[BuildToolInfo]:
    """Detect Gradle from build.gradle or build.gradle.kts."""
    gradle_file = repo_path / "build.gradle"
    if not gradle_file.exists():
        gradle_file = repo_path / "build.gradle.kts"
    if not gradle_file.exists():
        return []

    build_commands = ["./gradlew build", "./gradlew test", "./gradlew clean"]

    return [
        BuildToolInfo(
            name="gradle",
            config_file=gradle_file,
            build_commands=build_commands,
            relevance_score=_compute_relevance(
                "gradle", repo_path, gradle_file
            ),
        )
    ]


def _detect_maven(repo_path: Path) -> list[BuildToolInfo]:
    """Detect Maven from pom.xml."""
    pom_xml = repo_path / "pom.xml"
    if not pom_xml.exists():
        return []

    build_commands = ["mvn compile", "mvn test", "mvn package"]

    return [
        BuildToolInfo(
            name="maven",
            config_file=pom_xml,
            build_commands=build_commands,
            relevance_score=_compute_relevance("maven", repo_path, pom_xml),
        )
    ]


# ─── Extraction Helpers ──────────────────────────────────────────────────────


def _extract_make_targets(makefile: Path) -> list[str]:
    """Extract named targets from a Makefile.

    Looks for lines matching `target_name:` pattern at the start of a line.
    Excludes phony declarations and internal targets starting with '.'.
    """
    try:
        content = makefile.read_text(encoding="utf-8")
    except (OSError, PermissionError):
        return []

    targets: list[str] = []
    target_re = re.compile(r'^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:', re.MULTILINE)
    for match in target_re.finditer(content):
        target = match.group(1)
        if target not in ("all", "clean", "install", "uninstall"):
            targets.append(target)

    return targets


def _extract_cmake_targets(cmake_file: Path) -> list[str]:
    """Extract target names from CMakeLists.txt.

    Looks for add_executable() and add_library() calls.
    """
    try:
        content = cmake_file.read_text(encoding="utf-8")
    except (OSError, PermissionError):
        return []

    targets: list[str] = []
    target_re = re.compile(
        r'(?:add_executable|add_library)\s*\(\s*(\w+)', re.IGNORECASE
    )
    for match in target_re.finditer(content):
        targets.append(match.group(1))

    return targets


def _extract_package_json_scripts(package_json: Path) -> list[str]:
    """Extract script names from package.json "scripts" field.

    Uses regex parsing to avoid json module dependency for robustness
    with malformed files.
    """
    try:
        content = package_json.read_text(encoding="utf-8")
    except (OSError, PermissionError):
        return []

    scripts: list[str] = []
    # Find the "scripts" block
    scripts_match = re.search(
        r'"scripts"\s*:\s*\{([^}]*)\}', content, re.DOTALL
    )
    if not scripts_match:
        return []

    scripts_block = scripts_match.group(1)
    script_name_re = re.compile(r'"([^"]+)"\s*:')
    for match in script_name_re.finditer(scripts_block):
        scripts.append(match.group(1))

    return scripts


def _extract_cargo_workspace_members(cargo_toml: Path) -> list[str]:
    """Extract workspace members from Cargo.toml [workspace] section."""
    try:
        content = cargo_toml.read_text(encoding="utf-8")
    except (OSError, PermissionError):
        return []

    # Look for [workspace] section with members array
    workspace_match = re.search(
        r'\[workspace\].*?members\s*=\s*\[([^\]]*)\]',
        content,
        re.DOTALL,
    )
    if not workspace_match:
        return []

    members_str = workspace_match.group(1)
    member_re = re.compile(r'"([^"]+)"')
    return [m.group(1) for m in member_re.finditer(members_str)]


def _identify_js_package_manager(repo_path: Path) -> str:
    """Identify JS package manager by lockfile presence.

    Returns "yarn", "pnpm", or "npm" (default).
    """
    if (repo_path / "yarn.lock").exists():
        return "yarn"
    if (repo_path / "pnpm-lock.yaml").exists():
        return "pnpm"
    return "npm"


def _identify_python_build_backend(pyproject: Path) -> str:
    """Identify Python build tool from pyproject.toml build-system.

    Checks the [build-system] requires or build-backend fields.
    Returns "poetry", "setuptools", or "pip".
    """
    try:
        content = pyproject.read_text(encoding="utf-8")
    except (OSError, PermissionError):
        return "pip"

    if "poetry" in content.lower():
        # Check for poetry-specific markers
        if re.search(
            r'build-backend\s*=\s*"poetry', content
        ) or re.search(r'\[tool\.poetry\]', content):
            return "poetry"

    if re.search(r'build-backend\s*=\s*"setuptools', content):
        return "setuptools"

    if re.search(r'build-backend\s*=\s*"flit', content):
        return "pip"

    # Default: if pyproject.toml exists with no specific backend, use pip
    return "pip"


def _get_python_build_commands(tool_name: str) -> list[str]:
    """Get build commands for a Python build tool."""
    if tool_name == "poetry":
        return ["poetry install", "poetry build", "poetry run pytest"]
    if tool_name == "setuptools":
        return ["pip install -e .", "python -m build"]
    # Default pip
    return ["pip install -e .", "pip install -r requirements.txt"]


# ─── Relevance Scoring ───────────────────────────────────────────────────────


def _compute_relevance(
    tool_name: str, repo_path: Path, config_file: Path
) -> float:
    """Compute relevance score based on tool importance and file proximity.

    Score = base_relevance - (depth * DEPTH_PENALTY_FACTOR)

    Files at root get full base score; deeper files get progressively lower.

    Args:
        tool_name: Name of the build tool.
        repo_path: Repository root path.
        config_file: Path to the config file.

    Returns:
        Relevance score between 0.0 and 1.0.
    """
    base_score = BASE_RELEVANCE_SCORES.get(tool_name, 0.7)

    # Calculate depth relative to repo root
    try:
        relative = config_file.relative_to(repo_path)
        depth = len(relative.parts) - 1  # Subtract 1 for the file itself
    except ValueError:
        depth = 0

    score = base_score - (depth * DEPTH_PENALTY_FACTOR)
    return max(0.0, min(1.0, round(score, 2)))
