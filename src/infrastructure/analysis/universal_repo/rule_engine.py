"""Universal Rule Engine — multi-language static analysis with tree-sitter AST.

Extends the base RuleEngine with per-language rule set loading, tree-sitter
grammar integration, and project-wide analysis with progress streaming.

Requirements: 3.1, 3.6
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from src.infrastructure.analysis.rule_engine import (
    Finding,
    Rule,
    RuleEngine,
    RuleSeverity,
)

from .models import ProjectProfile

if TYPE_CHECKING:
    from . import StreamSink

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
}

SKIP_DIRECTORIES: frozenset[str] = frozenset({
    "node_modules", "__pycache__", ".git", "venv", ".venv",
    "dist", "build", "target", ".tox", ".mypy_cache",
    ".pytest_cache", "vendor", "third_party", ".cargo",
})

PROGRESS_EMIT_INTERVAL: int = 10

# Tree-sitter language name mapping
_TS_LANGUAGE_MAP: dict[str, str] = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "c": "c",
    "cpp": "cpp",
    "rust": "rust",
    "go": "go",
    "java": "java",
}


# ─── Rule Protocol ────────────────────────────────────────────────────────────


@runtime_checkable
class LanguageRule(Protocol):
    """Protocol for language-specific analysis rules."""

    @property
    def id(self) -> str: ...

    @property
    def language(self) -> str: ...

    @property
    def severity(self) -> str: ...

    def check(self, source: str, file_path: Path) -> list[Finding]: ...


# ─── Rule Dataclass ──────────────────────────────────────────────────────────


@dataclass
class UniversalRule:
    """A language-specific analysis rule supporting regex and AST queries."""

    id: str
    language: str
    severity: str
    name: str = ""
    description: str = ""
    patterns: list[str] = field(default_factory=list)
    ast_query: str = ""

    def check(self, source: str, file_path: Path) -> list[Finding]:
        """Run regex-based pattern matching against source code."""
        import re

        findings: list[Finding] = []
        rule_severity = _severity_from_str(self.severity)

        for pattern in self.patterns:
            try:
                compiled = re.compile(pattern, re.MULTILINE)
            except re.error:
                logger.debug("Invalid regex in rule %s: %s", self.id, pattern)
                continue

            for match in compiled.finditer(source):
                line_num = source[:match.start()].count("\n") + 1
                line_start = source.rfind("\n", 0, match.start()) + 1
                column = match.start() - line_start

                findings.append(Finding(
                    rule_id=self.id,
                    rule_name=self.name or self.id,
                    severity=rule_severity,
                    file=str(file_path),
                    line=line_num,
                    end_line=line_num,
                    column=column,
                    message=self.description or f"Rule {self.id} violation",
                ))

        return findings


# ─── Helpers ──────────────────────────────────────────────────────────────────

_SEVERITY_MAP: dict[str, RuleSeverity] = {
    "error": RuleSeverity.ERROR,
    "warning": RuleSeverity.WARNING,
    "info": RuleSeverity.INFO,
    "hint": RuleSeverity.HINT,
}


def _severity_from_str(s: str) -> RuleSeverity:
    return _SEVERITY_MAP.get(s, RuleSeverity.WARNING)


# ─── Tree-Sitter Integration ─────────────────────────────────────────────────


def _get_tree_sitter_parser(language: str):
    """Get a tree-sitter parser. Returns None if unavailable."""
    try:
        from tree_sitter_languages import get_parser
        ts_lang = _TS_LANGUAGE_MAP.get(language)
        if ts_lang is None:
            return None
        return get_parser(ts_lang)
    except (ImportError, Exception) as exc:
        logger.debug("tree-sitter unavailable for %s: %s", language, exc)
        return None


def _parse_source_with_tree_sitter(source: str, language: str):
    """Parse source into a tree-sitter AST root node, or None on failure."""
    parser = _get_tree_sitter_parser(language)
    if parser is None:
        return None
    try:
        tree = parser.parse(source.encode("utf-8"))
        return tree.root_node
    except Exception as exc:
        logger.debug("tree-sitter parse failed for %s: %s", language, exc)
        return None


# ─── Universal Rule Engine ───────────────────────────────────────────────────


class UniversalRuleEngine(RuleEngine):
    """Multi-language rule engine extending RuleEngine with tree-sitter AST.

    Adds per-language rule loading, async file/project analysis,
    and progress streaming support.
    """

    def __init__(self, indexer=None) -> None:
        super().__init__(indexer=indexer)
        self._language_rules: dict[str, list[UniversalRule]] = {}
        self._loaded_languages: set[str] = set()

    # ─── Rule Loading ─────────────────────────────────────────────────────────

    def load_rules_for_profile(self, profile: ProjectProfile) -> None:
        """Load language-specific rule sets for each detected language."""
        detected_languages = list(profile.languages.languages.keys())

        for language in detected_languages:
            if language not in self._loaded_languages:
                self._load_language_rules(language)
                self._loaded_languages.add(language)

        logger.info(
            "Loaded rules for %d languages: %s",
            len(detected_languages),
            ", ".join(detected_languages),
        )

    def _load_language_rules(self, language: str) -> None:
        """Load rules from language-specific module under rules/ directory."""
        if language in self._language_rules:
            return

        rules: list[UniversalRule] = []

        try:
            import importlib
            module_name = (
                f"src.infrastructure.analysis.universal_repo.rules.{language}_rules"
            )
            module = importlib.import_module(module_name)
            if hasattr(module, "get_rules"):
                loaded = module.get_rules()
                if isinstance(loaded, list):
                    rules.extend(loaded)
                    logger.info(
                        "Loaded %d rules for %s", len(loaded), language
                    )
        except ImportError:
            logger.debug("No rule module for %s, empty rule set", language)
        except Exception as exc:
            logger.warning("Error loading rules for %s: %s", language, exc)

        self._language_rules[language] = rules

    def register_language_rule(self, rule: UniversalRule) -> None:
        """Register a single rule for a language."""
        language = rule.language
        if language not in self._language_rules:
            self._language_rules[language] = []
        self._language_rules[language].append(rule)

    def get_language_rules(self, language: str) -> list[UniversalRule]:
        """Get all loaded rules for a language."""
        return self._language_rules.get(language, [])

    # ─── Analysis Methods ─────────────────────────────────────────────────────

    async def analyze_file(
        self, file_path: Path, language: str
    ) -> list[Finding]:
        """Analyze a single file with base + language-specific rules."""
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Cannot read file %s: %s", file_path, exc)
            return []

        findings: list[Finding] = []

        # Base RuleEngine detection (synchronous)
        base_findings = self.detect(str(file_path), language)
        findings.extend(base_findings)

        # Language-specific universal rules
        language_rules = self._language_rules.get(language, [])
        ast_root = None  # Lazy-load AST only when needed

        for rule in language_rules:
            if rule.ast_query:
                if ast_root is None:
                    ast_root = _parse_source_with_tree_sitter(source, language)
                if ast_root is not None:
                    findings.extend(
                        self._run_ast_rule(rule, ast_root, source, file_path)
                    )
                else:
                    # Fallback to regex when tree-sitter unavailable
                    findings.extend(rule.check(source, file_path))
            else:
                findings.extend(rule.check(source, file_path))

        return self._deduplicate_findings(findings)

    async def analyze_project(
        self,
        repo_path: Path,
        profile: ProjectProfile,
        progress_sink: "StreamSink | None" = None,
    ) -> list[Finding]:
        """Analyze all project files with progress streaming.

        Uses PipelineProgressEmitter to emit analysis progress including
        files analyzed count, findings count, and current file being analyzed.

        Args:
            repo_path: Root path of the repository.
            profile: Detected project profile.
            progress_sink: Optional sink for streaming progress events.

        Requirements: 3.1, 3.6, 10.2
        """
        from .progress_emitter import PipelineProgressEmitter

        emitter = PipelineProgressEmitter(sink=progress_sink)
        emitter.start_phase("analysis")

        self.load_rules_for_profile(profile)

        files_to_analyze = self._collect_files(repo_path)
        total_files = len(files_to_analyze)
        all_findings: list[Finding] = []

        for idx, file_path in enumerate(files_to_analyze):
            language = self._resolve_language(file_path)
            if not language or language not in profile.languages.languages:
                continue

            file_findings = await self.analyze_file(file_path, language)
            all_findings.extend(file_findings)

            # Emit progress periodically with current file info
            if emitter.has_sink and (idx + 1) % PROGRESS_EMIT_INTERVAL == 0:
                await emitter.emit_analysis_progress(
                    files_analyzed=idx + 1,
                    findings_count=len(all_findings),
                    current_file=str(file_path.relative_to(repo_path)),
                )

        # Emit phase completion
        duration_ms = emitter.get_phase_duration_ms("analysis")
        await emitter.emit_phase_complete(
            phase="analysis",
            summary={
                "files_analyzed": total_files,
                "findings_count": len(all_findings),
            },
            duration_ms=duration_ms,
        )

        return self._deduplicate_findings(all_findings)

    # ─── AST Rule Execution ───────────────────────────────────────────────────

    def _run_ast_rule(
        self,
        rule: UniversalRule,
        ast_root,
        source: str,
        file_path: Path,
    ) -> list[Finding]:
        """Execute an AST-based rule against a parsed tree."""
        findings: list[Finding] = []
        rule_severity = _severity_from_str(rule.severity)

        try:
            from tree_sitter_languages import get_language

            ts_lang_name = _TS_LANGUAGE_MAP.get(rule.language)
            if ts_lang_name is None:
                return findings

            lang = get_language(ts_lang_name)
            query = lang.query(rule.ast_query)
            captures = query.captures(ast_root)

            for node, _capture_name in captures:
                findings.append(Finding(
                    rule_id=rule.id,
                    rule_name=rule.name or rule.id,
                    severity=rule_severity,
                    file=str(file_path),
                    line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    column=node.start_point[1],
                    message=rule.description or f"Rule {rule.id} violation",
                ))
        except ImportError:
            logger.debug("tree-sitter not available for AST rule %s", rule.id)
        except Exception as exc:
            logger.debug("AST rule %s failed: %s", rule.id, exc)

        return findings

    # ─── File Collection ──────────────────────────────────────────────────────

    def _collect_files(self, repo_path: Path) -> list[Path]:
        """Collect all analyzable source files from a repository."""
        files: list[Path] = []
        if not repo_path.exists():
            return files

        for ext in EXTENSION_TO_LANGUAGE:
            for file_path in repo_path.rglob(f"*{ext}"):
                if not self._should_skip_file(file_path):
                    files.append(file_path)

        return sorted(files)

    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if a file is in a directory that should be skipped."""
        return any(part in SKIP_DIRECTORIES for part in file_path.parts)

    def _resolve_language(self, file_path: Path) -> str:
        """Resolve language identifier from file extension."""
        return EXTENSION_TO_LANGUAGE.get(file_path.suffix.lower(), "")
