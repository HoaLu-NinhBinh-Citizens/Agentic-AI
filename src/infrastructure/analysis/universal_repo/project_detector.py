"""Project Detector — Language and framework detection for multi-language repositories.

Scans file extensions, shebang lines, language-specific marker files,
and config files to identify all programming languages and frameworks
present in a repository.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 9.1, 9.2, 9.3, 9.4
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from typing import TYPE_CHECKING

from .models import (
    BuildToolInfo,
    Framework,
    LanguageDistribution,
    LanguageStats,
    ProjectProfile,
    MAX_SCAN_FILES,
    MIN_CONFIDENCE,
)
from ._framework_detection import (
    detect_cmake_frameworks,
    detect_go_frameworks,
    detect_java_frameworks,
    detect_js_ts_frameworks,
    detect_python_frameworks,
    detect_rust_frameworks,
)
from ._build_tool_detection import detect_build_tools_at_root

if TYPE_CHECKING:
    from . import StreamSink

# ─── Named Constants ─────────────────────────────────────────────────────────

SKIP_DIRECTORIES: frozenset[str] = frozenset({
    "node_modules", ".git", "__pycache__", "target", "build", "dist",
    "vendor", ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache",
    ".hypothesis", ".eggs", "egg-info",
})

EXTENSION_MAP: dict[str, str] = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".c": "C", ".h": "C", ".cpp": "C++",
    ".hpp": "C++", ".cc": "C++", ".cxx": "C++", ".rs": "Rust",
    ".go": "Go", ".java": "Java",
}

SHEBANG_PATTERNS: dict[str, str] = {
    "python": "Python", "python3": "Python", "node": "JavaScript",
    "bash": "Bash", "sh": "Bash", "ruby": "Ruby", "perl": "Perl",
}

LANGUAGE_MARKERS: dict[str, str] = {
    "go.mod": "Go", "Cargo.toml": "Rust", "tsconfig.json": "TypeScript",
    "package.json": "JavaScript", "pyproject.toml": "Python",
    "setup.py": "Python", "pom.xml": "Java", "build.gradle": "Java",
    "CMakeLists.txt": "C++", "Makefile": "C",
}

ENTRY_POINT_NAMES: frozenset[str] = frozenset({
    "main.py", "main.go", "main.rs", "Main.java", "index.js",
    "index.ts", "index.tsx", "app.py", "app.js", "app.ts",
    "main.c", "main.cpp",
})

DEPENDENCY_MANIFEST_NAMES: frozenset[str] = frozenset({
    "package.json", "Cargo.toml", "go.mod", "pyproject.toml",
    "requirements.txt", "pom.xml", "build.gradle", "setup.py", "setup.cfg",
})

CACHE_INVALIDATION_CONFIG_FILES: frozenset[str] = frozenset({
    "package.json", "Cargo.toml", "CMakeLists.txt", "pyproject.toml",
})


# ─── Project Detector ────────────────────────────────────────────────────────


class ProjectDetector:
    """Scans a repository and produces language/framework detection results."""

    def __init__(self) -> None:
        self._cache: dict[str, ProjectProfile] = {}
        self._cache_hashes: dict[str, str] = {}
        self._cache_config_mtimes: dict[str, dict[str, float]] = {}

    # ─── Caching (Requirements: 9.1, 9.2, 9.4) ──────────────────────────────

    def get_cached_profile(self, repo_path: Path) -> ProjectProfile | None:
        """Return cached profile if file tree hash and config mtimes match.

        Requirements: 9.1, 9.2, 9.4
        """
        key = str(repo_path)
        if key not in self._cache:
            return None
        current_hash = self._compute_file_tree_hash(repo_path)
        if current_hash != self._cache_hashes.get(key):
            return None
        cached_mtimes = self._cache_config_mtimes.get(key, {})
        for config_name in CACHE_INVALIDATION_CONFIG_FILES:
            config_path = repo_path / config_name
            if config_path.is_file():
                try:
                    current_mtime = os.path.getmtime(config_path)
                except OSError:
                    continue
                cached_mtime = cached_mtimes.get(config_name)
                if cached_mtime is None or current_mtime > cached_mtime:
                    return None
        return self._cache[key]

    def invalidate_cache(self, repo_path: Path) -> None:
        """Explicitly invalidate the cache for a repository. Requirements: 9.4"""
        key = str(repo_path)
        self._cache.pop(key, None)
        self._cache_hashes.pop(key, None)
        self._cache_config_mtimes.pop(key, None)

    def _store_in_cache(self, repo_path: Path, profile: ProjectProfile) -> None:
        """Store a profile in cache with its hash and config mtimes."""
        key = str(repo_path)
        self._cache[key] = profile
        self._cache_hashes[key] = profile.file_tree_hash

        # Snapshot config file modification times
        config_mtimes: dict[str, float] = {}
        for config_name in CACHE_INVALIDATION_CONFIG_FILES:
            config_path = repo_path / config_name
            if config_path.is_file():
                try:
                    config_mtimes[config_name] = os.path.getmtime(config_path)
                except OSError:
                    pass
        self._cache_config_mtimes[key] = config_mtimes

    # ─── Incremental Detection (Requirement: 9.3) ─────────────────────────────

    async def detect_incremental(
        self, repo_path: Path, added_files: list[Path], removed_files: list[Path],
    ) -> ProjectProfile:
        """Update only changed portions of the ProjectProfile incrementally.

        Falls back to full detect() if no cached profile exists.
        Updates frameworks/build_tools only when config files change.
        Requirements: 9.3
        """
        key = str(repo_path)
        profile = self._cache.get(key)
        if profile is None:
            return await self.detect(repo_path)

        file_counts, loc_counts = self._extract_counts(profile.languages)
        await self._apply_added_files(added_files, file_counts, loc_counts)
        self._apply_removed_files(removed_files, file_counts, loc_counts)

        if not file_counts:
            languages = LanguageDistribution(primary_language="unknown", languages={})
        else:
            languages = self._build_distribution(file_counts, loc_counts)

        config_changed = self._has_config_file_change(added_files, removed_files)
        frameworks = profile.frameworks
        build_tools = profile.build_tools
        if config_changed:
            frameworks = await self.detect_frameworks(repo_path, languages)
            build_tools = await self.detect_build_tools(repo_path)

        updated = ProjectProfile(
            repo_path=repo_path, languages=languages, frameworks=frameworks,
            build_tools=build_tools, entry_points=self._detect_entry_points(repo_path),
            dependency_manifests=self._detect_dependency_manifests(repo_path),
            confidence=self._compute_confidence(languages),
            detected_at=datetime.now(timezone.utc),
            file_tree_hash=self._compute_file_tree_hash(repo_path),
        )
        self._store_in_cache(repo_path, updated)
        return updated

    def _extract_counts(
        self, languages: LanguageDistribution,
    ) -> tuple[dict[str, int], dict[str, int]]:
        """Extract file_counts and loc_counts from a LanguageDistribution."""
        file_counts = {lang: s.file_count for lang, s in languages.languages.items()}
        loc_counts = {lang: s.lines_of_code for lang, s in languages.languages.items()}
        return file_counts, loc_counts

    async def _apply_added_files(
        self, added_files: list[Path], file_counts: dict[str, int], loc_counts: dict[str, int],
    ) -> None:
        """Detect language of added files and update counts."""
        for file_path in added_files:
            language = self._detect_file_language(file_path)
            if language is None:
                continue
            file_counts[language] = file_counts.get(language, 0) + 1
            loc_counts[language] = loc_counts.get(language, 0) + await self._count_lines(file_path)

    def _apply_removed_files(
        self, removed_files: list[Path], file_counts: dict[str, int], loc_counts: dict[str, int],
    ) -> None:
        """Subtract removed files' language contributions from counts."""
        for file_path in removed_files:
            language = self._detect_file_language(file_path)
            if language is None:
                continue
            file_counts[language] = max(0, file_counts.get(language, 0) - 1)
            loc_counts[language] = max(0, loc_counts.get(language, 0) - 1)
            if file_counts.get(language, 0) == 0:
                file_counts.pop(language, None)
                loc_counts.pop(language, None)

    def _has_config_file_change(self, added: list[Path], removed: list[Path]) -> bool:
        """Check if any added/removed files are config files needing redetection."""
        config_names = CACHE_INVALIDATION_CONFIG_FILES | frozenset({
            "go.mod", "pom.xml", "build.gradle", "build.gradle.kts",
            "Makefile", "makefile", "requirements.txt", "setup.py",
        })
        return any(f.name in config_names for f in (*added, *removed))

    # ─── Detection ───────────────────────────────────────────────────────────

    async def detect(
        self,
        repo_path: Path,
        progress_sink: "StreamSink | None" = None,
    ) -> ProjectProfile:
        """Full detection producing a complete ProjectProfile.

        Args:
            repo_path: Root path of the repository to detect.
            progress_sink: Optional sink for streaming detection progress events.

        Requirements: 1.2, 2.1, 9.1, 9.2, 10.1
        """
        from .progress_emitter import PipelineProgressEmitter

        emitter = PipelineProgressEmitter(sink=progress_sink)

        cached = self.get_cached_profile(repo_path)
        if cached is not None:
            return cached

        emitter.start_phase("detection")

        languages = await self._detect_languages_with_progress(repo_path, emitter)
        frameworks = await self.detect_frameworks(repo_path, languages)
        build_tools = await self.detect_build_tools(repo_path)

        entry_points = self._detect_entry_points(repo_path)
        dependency_manifests = self._detect_dependency_manifests(repo_path)
        file_tree_hash = self._compute_file_tree_hash(repo_path)
        confidence = self._compute_confidence(languages)

        profile = ProjectProfile(
            repo_path=repo_path,
            languages=languages,
            frameworks=frameworks,
            build_tools=build_tools,
            entry_points=entry_points,
            dependency_manifests=dependency_manifests,
            confidence=confidence,
            detected_at=datetime.now(timezone.utc),
            file_tree_hash=file_tree_hash,
        )

        self._store_in_cache(repo_path, profile)

        # Emit phase completion
        duration_ms = emitter.get_phase_duration_ms("detection")
        await emitter.emit_phase_complete(
            phase="detection",
            summary={
                "primary_language": languages.primary_language,
                "languages_detected": len(languages.languages),
                "frameworks_detected": len(frameworks),
                "build_tools_detected": len(build_tools),
                "confidence": confidence,
            },
            duration_ms=duration_ms,
        )

        return profile

    async def _detect_languages_with_progress(
        self,
        repo_path: Path,
        emitter: "PipelineProgressEmitter",
    ) -> LanguageDistribution:
        """Scan file extensions with progress emission during scanning."""
        file_counts: dict[str, int] = {}
        loc_counts: dict[str, int] = {}
        files_scanned = 0
        source_files = self._collect_source_files(repo_path)
        total_files = len(source_files)

        for file_path in source_files:
            if files_scanned >= MAX_SCAN_FILES:
                break

            language = self._detect_file_language(file_path)
            if language is None:
                files_scanned += 1
                # Emit progress every 50 files during scanning
                if files_scanned % 50 == 0:
                    await emitter.emit_detection_progress(
                        files_scanned=files_scanned,
                        total_files=total_files,
                        phase="language",
                    )
                continue

            file_counts[language] = file_counts.get(language, 0) + 1
            line_count = await self._count_lines(file_path)
            loc_counts[language] = loc_counts.get(language, 0) + line_count
            files_scanned += 1

            # Emit progress every 50 files during scanning
            if files_scanned % 50 == 0:
                await emitter.emit_detection_progress(
                    files_scanned=files_scanned,
                    total_files=total_files,
                    phase="language",
                )

        # Emit final scan progress
        await emitter.emit_detection_progress(
            files_scanned=files_scanned,
            total_files=total_files,
            phase="language",
        )

        self._apply_marker_detection(repo_path, file_counts, loc_counts)

        if not file_counts:
            return LanguageDistribution(primary_language="unknown", languages={})

        return self._build_distribution(file_counts, loc_counts)

    async def detect_languages(self, repo_path: Path) -> LanguageDistribution:
        """Scan file extensions, shebangs, and markers to detect languages."""
        file_counts: dict[str, int] = {}
        loc_counts: dict[str, int] = {}
        files_scanned = 0
        source_files = self._collect_source_files(repo_path)

        for file_path in source_files:
            if files_scanned >= MAX_SCAN_FILES:
                break

            language = self._detect_file_language(file_path)
            if language is None:
                files_scanned += 1
                continue

            file_counts[language] = file_counts.get(language, 0) + 1
            line_count = await self._count_lines(file_path)
            loc_counts[language] = loc_counts.get(language, 0) + line_count
            files_scanned += 1

        self._apply_marker_detection(repo_path, file_counts, loc_counts)

        if not file_counts:
            return LanguageDistribution(primary_language="unknown", languages={})

        return self._build_distribution(file_counts, loc_counts)

    async def detect_frameworks(
        self, repo_path: Path, languages: LanguageDistribution
    ) -> list[Framework]:
        """Identify frameworks from config files and import patterns."""
        frameworks: list[Framework] = []
        detected_langs = set(languages.languages.keys())

        if detected_langs & {"JavaScript", "TypeScript"}:
            lang = "TypeScript" if "TypeScript" in detected_langs else "JavaScript"
            frameworks.extend(detect_js_ts_frameworks(repo_path, lang))

        if "Python" in detected_langs:
            frameworks.extend(detect_python_frameworks(repo_path))

        if "Rust" in detected_langs:
            frameworks.extend(detect_rust_frameworks(repo_path))

        if "Java" in detected_langs:
            frameworks.extend(detect_java_frameworks(repo_path))

        if "Go" in detected_langs:
            frameworks.extend(detect_go_frameworks(repo_path))

        if detected_langs & {"C", "C++"}:
            lang = "C++" if "C++" in detected_langs else "C"
            frameworks.extend(detect_cmake_frameworks(repo_path, lang))

        return frameworks

    async def detect_build_tools(self, repo_path: Path) -> list[BuildToolInfo]:
        """Discover build tools from config files. Requirements: 2.2-2.7"""
        return detect_build_tools_at_root(repo_path)

    # ─── Source File Collection ──────────────────────────────────────────────

    def _collect_source_files(self, repo_path: Path) -> list[Path]:
        """Collect all candidate source files, skipping excluded directories."""
        files: list[Path] = []
        try:
            for item in repo_path.rglob("*"):
                if len(files) >= MAX_SCAN_FILES:
                    break
                if self._should_skip_path(item):
                    continue
                if item.is_file():
                    files.append(item)
        except (PermissionError, OSError):
            pass
        return files

    def _should_skip_path(self, path: Path) -> bool:
        """Check if a path is within a directory that should be skipped."""
        return any(part in SKIP_DIRECTORIES for part in path.parts)

    def _detect_file_language(self, file_path: Path) -> str | None:
        """Detect language of a single file by extension or shebang."""
        suffix = file_path.suffix.lower()
        if suffix in EXTENSION_MAP:
            return EXTENSION_MAP[suffix]
        return self._detect_shebang_language(file_path)

    def _detect_shebang_language(self, file_path: Path) -> str | None:
        """Detect language from shebang line (#!) in the file."""
        try:
            with open(file_path, "rb") as f:
                first_bytes = f.read(2)
                if first_bytes != b"#!":
                    return None
                first_line = (first_bytes + f.readline(254)).decode(
                    "utf-8", errors="replace"
                )
        except (OSError, PermissionError):
            return None
        return self._parse_shebang_line(first_line)

    def _parse_shebang_line(self, line: str) -> str | None:
        """Parse a shebang line to extract the interpreter language."""
        shebang = line[2:].strip()
        parts = shebang.split()
        if not parts:
            return None

        if parts[0].endswith("/env") and len(parts) > 1:
            interpreter = parts[1]
        else:
            interpreter = parts[0].split("/")[-1]

        base_interpreter = (
            interpreter.split(".")[0] if "." in interpreter else interpreter
        )
        for pattern, language in SHEBANG_PATTERNS.items():
            if base_interpreter == pattern or interpreter == pattern:
                return language
        return None

    def _apply_marker_detection(
        self,
        repo_path: Path,
        file_counts: dict[str, int],
        loc_counts: dict[str, int],
    ) -> None:
        """Check for language marker files at the repo root."""
        for marker_file, language in LANGUAGE_MARKERS.items():
            marker_path = repo_path / marker_file
            if marker_path.exists() and language not in file_counts:
                file_counts[language] = file_counts.get(language, 0)
                loc_counts[language] = loc_counts.get(language, 0)

    async def _count_lines(self, file_path: Path) -> int:
        """Count lines of code in a file asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._count_lines_sync, file_path)

    def _count_lines_sync(self, file_path: Path) -> int:
        """Synchronous line counting with error handling."""
        try:
            with open(file_path, "rb") as f:
                return sum(1 for _ in f)
        except (OSError, PermissionError):
            return 0

    def _build_distribution(
        self, file_counts: dict[str, int], loc_counts: dict[str, int]
    ) -> LanguageDistribution:
        """Build a LanguageDistribution from raw counts."""
        total_files = sum(file_counts.values())
        total_loc = sum(loc_counts.values())

        languages: dict[str, LanguageStats] = {}
        for lang in file_counts:
            fc = file_counts[lang]
            lc = loc_counts.get(lang, 0)
            pct_files = (fc / total_files * 100.0) if total_files > 0 else 0.0
            pct_loc = (lc / total_loc * 100.0) if total_loc > 0 else 0.0
            languages[lang] = LanguageStats(
                file_count=fc,
                lines_of_code=lc,
                percentage_files=round(pct_files, 2),
                percentage_loc=round(pct_loc, 2),
            )

        primary_language = max(loc_counts, key=lambda k: loc_counts[k])
        return LanguageDistribution(
            primary_language=primary_language, languages=languages
        )

    # ─── Full Detection Helpers ──────────────────────────────────────────────

    def _detect_entry_points(self, repo_path: Path) -> list[Path]:
        """Find common entry point files at root and one level deep."""
        entry_points: list[Path] = []
        for name in ENTRY_POINT_NAMES:
            candidate = repo_path / name
            if candidate.is_file():
                entry_points.append(Path(name))
        try:
            for child in repo_path.iterdir():
                if not child.is_dir() or child.name in SKIP_DIRECTORIES:
                    continue
                for name in ENTRY_POINT_NAMES:
                    candidate = child / name
                    if candidate.is_file():
                        entry_points.append(Path(child.name) / name)
        except (PermissionError, OSError):
            pass
        return sorted(entry_points)

    def _detect_dependency_manifests(self, repo_path: Path) -> list[Path]:
        """Find dependency manifest files at the repository root."""
        manifests: list[Path] = []
        for name in DEPENDENCY_MANIFEST_NAMES:
            candidate = repo_path / name
            if candidate.is_file():
                manifests.append(Path(name))
        return sorted(manifests)

    def _compute_file_tree_hash(self, repo_path: Path) -> str:
        """Compute SHA-256 hash of sorted relative file paths for caching."""
        hasher = hashlib.sha256()
        file_paths: list[str] = []

        try:
            for item in repo_path.rglob("*"):
                if self._should_skip_path(item):
                    continue
                if item.is_file():
                    relative = item.relative_to(repo_path).as_posix()
                    file_paths.append(relative)
        except (PermissionError, OSError):
            pass

        for path_str in sorted(file_paths):
            hasher.update(path_str.encode("utf-8"))
            hasher.update(b"\n")

        return hasher.hexdigest()

    def _compute_confidence(self, languages: LanguageDistribution) -> float:
        """Compute detection confidence from language distribution.

        Returns 0.0 for unknown language, otherwise 0.5-0.95 based on
        how dominant the primary language is by lines of code.
        """
        if languages.primary_language == "unknown" or not languages.languages:
            return MIN_CONFIDENCE
        primary_stats = languages.languages.get(languages.primary_language)
        if primary_stats is None:
            return MIN_CONFIDENCE
        dominance = primary_stats.percentage_loc / 100.0
        confidence = 0.5 + (dominance * 0.45)
        return round(min(confidence, 1.0), 4)
