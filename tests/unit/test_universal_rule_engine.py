"""Unit tests for the UniversalRuleEngine — analyze_file and analyze_project.

Validates:
- Rule loading for JavaScript, C, Rust, Go (minimum counts per language)
- analyze_file() returns findings with all required fields
- analyze_project() iterates all project files with applicable rules
- Finding output includes: file_path (file), line, column, severity, rule_id, message
- Clean code produces fewer/no findings
- Progress streaming callback is called during analyze_project

Requirements: 3.1, 3.7, 3.8
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from src.infrastructure.analysis.rule_engine import Finding, RuleSeverity
from src.infrastructure.analysis.universal_repo.models import (
    LanguageDistribution,
    LanguageStats,
    PipelineProgressEvent,
    ProjectProfile,
)
from src.infrastructure.analysis.universal_repo.rule_engine import UniversalRuleEngine


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def engine() -> UniversalRuleEngine:
    """Create a fresh UniversalRuleEngine instance."""
    return UniversalRuleEngine()


@pytest.fixture
def js_profile() -> ProjectProfile:
    """Profile with JavaScript as sole language."""
    return ProjectProfile(
        repo_path=Path("/tmp/test_repo"),
        languages=LanguageDistribution(
            primary_language="javascript",
            languages={
                "javascript": LanguageStats(
                    file_count=5, lines_of_code=200,
                    percentage_files=100.0, percentage_loc=100.0,
                ),
            },
        ),
        frameworks=[],
        build_tools=[],
        entry_points=[],
        dependency_manifests=[],
        confidence=0.9,
        detected_at=datetime.now(),
        file_tree_hash="abc123",
    )


@pytest.fixture
def c_profile() -> ProjectProfile:
    """Profile with C as sole language."""
    return ProjectProfile(
        repo_path=Path("/tmp/test_repo"),
        languages=LanguageDistribution(
            primary_language="c",
            languages={
                "c": LanguageStats(
                    file_count=3, lines_of_code=150,
                    percentage_files=100.0, percentage_loc=100.0,
                ),
            },
        ),
        frameworks=[],
        build_tools=[],
        entry_points=[],
        dependency_manifests=[],
        confidence=0.9,
        detected_at=datetime.now(),
        file_tree_hash="def456",
    )


@pytest.fixture
def multi_lang_profile() -> ProjectProfile:
    """Profile with multiple languages for project analysis."""
    return ProjectProfile(
        repo_path=Path("/tmp/test_repo"),
        languages=LanguageDistribution(
            primary_language="javascript",
            languages={
                "javascript": LanguageStats(
                    file_count=3, lines_of_code=100,
                    percentage_files=50.0, percentage_loc=50.0,
                ),
                "c": LanguageStats(
                    file_count=3, lines_of_code=100,
                    percentage_files=50.0, percentage_loc=50.0,
                ),
            },
        ),
        frameworks=[],
        build_tools=[],
        entry_points=[],
        dependency_manifests=[],
        confidence=0.9,
        detected_at=datetime.now(),
        file_tree_hash="multi789",
    )


# ─── Rule Loading Tests ──────────────────────────────────────────────────────


class TestRuleLoading:
    """Validates: Requirements 3.1, 3.8 — Rule loading per language."""

    def test_javascript_rules_minimum_30(self, engine: UniversalRuleEngine, js_profile: ProjectProfile):
        """JS/TS must have at least 30 rules loaded."""
        engine.load_rules_for_profile(js_profile)
        rules = engine.get_language_rules("javascript")
        assert len(rules) >= 30, f"Expected >=30 JS rules, got {len(rules)}"

    def test_c_rules_minimum_30(self, engine: UniversalRuleEngine, c_profile: ProjectProfile):
        """C/C++ must have at least 30 rules loaded."""
        engine.load_rules_for_profile(c_profile)
        rules = engine.get_language_rules("c")
        assert len(rules) >= 30, f"Expected >=30 C rules, got {len(rules)}"

    def test_rust_rules_minimum_15(self, engine: UniversalRuleEngine):
        """Rust must have at least 15 rules loaded."""
        profile = ProjectProfile(
            repo_path=Path("/tmp/test_repo"),
            languages=LanguageDistribution(
                primary_language="rust",
                languages={
                    "rust": LanguageStats(
                        file_count=2, lines_of_code=100,
                        percentage_files=100.0, percentage_loc=100.0,
                    ),
                },
            ),
            frameworks=[],
            build_tools=[],
            entry_points=[],
            dependency_manifests=[],
            confidence=0.9,
            detected_at=datetime.now(),
            file_tree_hash="rust123",
        )
        engine.load_rules_for_profile(profile)
        rules = engine.get_language_rules("rust")
        assert len(rules) >= 15, f"Expected >=15 Rust rules, got {len(rules)}"

    def test_go_rules_minimum_15(self, engine: UniversalRuleEngine):
        """Go must have at least 15 rules loaded."""
        profile = ProjectProfile(
            repo_path=Path("/tmp/test_repo"),
            languages=LanguageDistribution(
                primary_language="go",
                languages={
                    "go": LanguageStats(
                        file_count=2, lines_of_code=100,
                        percentage_files=100.0, percentage_loc=100.0,
                    ),
                },
            ),
            frameworks=[],
            build_tools=[],
            entry_points=[],
            dependency_manifests=[],
            confidence=0.9,
            detected_at=datetime.now(),
            file_tree_hash="go456",
        )
        engine.load_rules_for_profile(profile)
        rules = engine.get_language_rules("go")
        assert len(rules) >= 15, f"Expected >=15 Go rules, got {len(rules)}"

    def test_loading_same_language_twice_is_idempotent(
        self, engine: UniversalRuleEngine, js_profile: ProjectProfile
    ):
        """Loading rules for the same language multiple times doesn't duplicate."""
        engine.load_rules_for_profile(js_profile)
        count_first = len(engine.get_language_rules("javascript"))
        engine.load_rules_for_profile(js_profile)
        count_second = len(engine.get_language_rules("javascript"))
        assert count_first == count_second


# ─── analyze_file Tests ──────────────────────────────────────────────────────


class TestAnalyzeFile:
    """Validates: Requirement 3.7 — analyze_file returns findings with all fields."""

    def test_js_file_with_eval_produces_findings(
        self, engine: UniversalRuleEngine, js_profile: ProjectProfile, tmp_path: Path
    ):
        """JS file using eval() should produce at least one finding."""
        engine.load_rules_for_profile(js_profile)

        js_file = tmp_path / "bad.js"
        js_file.write_text(
            'const x = eval("1+1");\nconsole.log(x);\n',
            encoding="utf-8",
        )

        findings = asyncio.run(engine.analyze_file(js_file, "javascript"))
        assert len(findings) > 0, "Expected findings from eval() usage"

        # Check that at least one finding relates to eval
        eval_findings = [f for f in findings if "eval" in f.rule_id.lower() or "eval" in f.rule_name.lower()]
        assert len(eval_findings) > 0, "Expected finding specifically for eval()"

    def test_js_file_with_console_log_produces_findings(
        self, engine: UniversalRuleEngine, js_profile: ProjectProfile, tmp_path: Path
    ):
        """JS file with console.log should produce a finding."""
        engine.load_rules_for_profile(js_profile)

        js_file = tmp_path / "debug.js"
        js_file.write_text(
            'function greet(name) {\n  console.log("Hello " + name);\n}\n',
            encoding="utf-8",
        )

        findings = asyncio.run(engine.analyze_file(js_file, "javascript"))
        console_findings = [
            f for f in findings if "console" in f.rule_name.lower()
        ]
        assert len(console_findings) > 0, "Expected finding for console.log"

    def test_c_file_with_gets_produces_findings(
        self, engine: UniversalRuleEngine, c_profile: ProjectProfile, tmp_path: Path
    ):
        """C file using gets() should produce a finding."""
        engine.load_rules_for_profile(c_profile)

        c_file = tmp_path / "unsafe.c"
        c_file.write_text(
            '#include <stdio.h>\nint main() {\n  char buf[64];\n  gets(buf);\n  return 0;\n}\n',
            encoding="utf-8",
        )

        findings = asyncio.run(engine.analyze_file(c_file, "c"))
        gets_findings = [f for f in findings if "gets" in f.rule_name.lower()]
        assert len(gets_findings) > 0, "Expected finding for gets() usage"

    def test_c_file_with_strcpy_produces_findings(
        self, engine: UniversalRuleEngine, c_profile: ProjectProfile, tmp_path: Path
    ):
        """C file using strcpy() should produce a finding."""
        engine.load_rules_for_profile(c_profile)

        c_file = tmp_path / "buffer.c"
        c_file.write_text(
            '#include <string.h>\nvoid copy(char *dst, char *src) {\n  strcpy(dst, src);\n}\n',
            encoding="utf-8",
        )

        findings = asyncio.run(engine.analyze_file(c_file, "c"))
        strcpy_findings = [f for f in findings if "strcpy" in f.rule_name.lower()]
        assert len(strcpy_findings) > 0, "Expected finding for strcpy() usage"

    def test_finding_has_all_required_fields(
        self, engine: UniversalRuleEngine, js_profile: ProjectProfile, tmp_path: Path
    ):
        """Each finding must include file, line, column, severity, rule_id, message."""
        engine.load_rules_for_profile(js_profile)

        js_file = tmp_path / "check_fields.js"
        js_file.write_text('var x = eval("code");\n', encoding="utf-8")

        findings = asyncio.run(engine.analyze_file(js_file, "javascript"))
        assert len(findings) > 0, "Expected at least one finding"

        for finding in findings:
            # file_path (stored as 'file' in the Finding dataclass)
            assert finding.file, "Finding must have a file path"
            assert str(tmp_path) in finding.file or "check_fields.js" in finding.file

            # line number (1-based)
            assert isinstance(finding.line, int)
            assert finding.line >= 1, "Line must be >= 1"

            # column (0-based)
            assert isinstance(finding.column, int)
            assert finding.column >= 0, "Column must be >= 0"

            # severity
            assert isinstance(finding.severity, RuleSeverity)

            # rule_id
            assert finding.rule_id, "Finding must have a rule_id"
            assert len(finding.rule_id) > 0

            # message (stored in rule_name or message)
            assert finding.rule_name or finding.message, (
                "Finding must have rule_name or message"
            )

    def test_clean_js_code_fewer_findings(
        self, engine: UniversalRuleEngine, js_profile: ProjectProfile, tmp_path: Path
    ):
        """Clean JS code should produce fewer findings than problematic code."""
        engine.load_rules_for_profile(js_profile)

        # Bad code with many issues
        bad_file = tmp_path / "bad.js"
        bad_file.write_text(
            'var x = eval("test");\n'
            'console.log(x);\n'
            'document.write("<h1>XSS</h1>");\n'
            'debugger;\n',
            encoding="utf-8",
        )

        # Clean code
        clean_file = tmp_path / "clean.js"
        clean_file.write_text(
            'const add = (a, b) => a + b;\n'
            'const result = add(1, 2);\n'
            'export default add;\n',
            encoding="utf-8",
        )

        bad_findings = asyncio.run(engine.analyze_file(bad_file, "javascript"))
        clean_findings = asyncio.run(engine.analyze_file(clean_file, "javascript"))

        assert len(bad_findings) > len(clean_findings), (
            f"Bad code ({len(bad_findings)} findings) should have more findings "
            f"than clean code ({len(clean_findings)} findings)"
        )

    def test_analyze_nonexistent_file_returns_empty(
        self, engine: UniversalRuleEngine, js_profile: ProjectProfile
    ):
        """Analyzing a file that doesn't exist should return empty list."""
        engine.load_rules_for_profile(js_profile)

        findings = asyncio.run(
            engine.analyze_file(Path("/nonexistent/path/file.js"), "javascript")
        )
        assert findings == []


# ─── analyze_project Tests ───────────────────────────────────────────────────


class TestAnalyzeProject:
    """Validates: Requirement 3.7 — analyze_project iterates all project files."""

    def test_multi_file_repo_produces_findings_from_multiple_files(
        self, engine: UniversalRuleEngine, multi_lang_profile: ProjectProfile, tmp_path: Path
    ):
        """analyze_project should find issues across multiple files."""
        # Create JS file with issues
        js_file = tmp_path / "app.js"
        js_file.write_text('eval("hack");\nconsole.log("debug");\n', encoding="utf-8")

        # Create C file with issues
        c_file = tmp_path / "main.c"
        c_file.write_text(
            '#include <stdio.h>\nvoid f() {\n  char buf[64];\n  gets(buf);\n}\n',
            encoding="utf-8",
        )

        # Update profile to point to tmp_path
        multi_lang_profile.repo_path = tmp_path

        findings = asyncio.run(
            engine.analyze_project(tmp_path, multi_lang_profile)
        )

        assert len(findings) > 0, "Expected findings from multi-file project"

        # Findings should come from at least 2 different files
        files_with_findings = {f.file for f in findings}
        assert len(files_with_findings) >= 2, (
            f"Expected findings from >= 2 files, got findings from: {files_with_findings}"
        )

    def test_analyze_project_with_subdirectories(
        self, engine: UniversalRuleEngine, js_profile: ProjectProfile, tmp_path: Path
    ):
        """analyze_project should scan files in subdirectories."""
        sub_dir = tmp_path / "src"
        sub_dir.mkdir()

        js_file = sub_dir / "index.js"
        js_file.write_text('eval("danger");\n', encoding="utf-8")

        js_profile.repo_path = tmp_path

        findings = asyncio.run(engine.analyze_project(tmp_path, js_profile))
        assert len(findings) > 0, "Expected findings from files in subdirectories"

    def test_analyze_project_progress_callback_is_called(
        self, engine: UniversalRuleEngine, tmp_path: Path
    ):
        """Progress streaming callback must be invoked during analyze_project."""
        # Create enough files to trigger progress emission (PROGRESS_EMIT_INTERVAL = 10)
        for i in range(12):
            f = tmp_path / f"file_{i}.js"
            f.write_text(f'eval("code_{i}");\n', encoding="utf-8")

        profile = ProjectProfile(
            repo_path=tmp_path,
            languages=LanguageDistribution(
                primary_language="javascript",
                languages={
                    "javascript": LanguageStats(
                        file_count=12, lines_of_code=12,
                        percentage_files=100.0, percentage_loc=100.0,
                    ),
                },
            ),
            frameworks=[],
            build_tools=[],
            entry_points=[],
            dependency_manifests=[],
            confidence=0.9,
            detected_at=datetime.now(),
            file_tree_hash="progress_test",
        )

        # Collect emitted progress events
        emitted_events: list[PipelineProgressEvent] = []

        class MockSink:
            async def emit(self, event: PipelineProgressEvent) -> None:
                emitted_events.append(event)

        sink = MockSink()

        findings = asyncio.run(engine.analyze_project(tmp_path, profile, progress_sink=sink))

        # With 12 files and PROGRESS_EMIT_INTERVAL=10, we expect at least
        # one progress event (at file 10) plus a completion event
        assert len(emitted_events) >= 1, (
            f"Expected progress events, got {len(emitted_events)}"
        )

        # Completion event should have 100% progress
        completion_events = [e for e in emitted_events if e.progress_percent == 100.0]
        assert len(completion_events) >= 1, "Expected a completion event at 100%"

    def test_analyze_project_empty_repo(
        self, engine: UniversalRuleEngine, js_profile: ProjectProfile, tmp_path: Path
    ):
        """Empty repo should return no findings."""
        js_profile.repo_path = tmp_path
        findings = asyncio.run(engine.analyze_project(tmp_path, js_profile))
        assert findings == []
