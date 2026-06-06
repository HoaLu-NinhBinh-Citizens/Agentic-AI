"""Compile-error-driven fix suggestions.

Parses real compiler/interpreter error output and generates targeted fixes.
Supports: Python (SyntaxError, ImportError, TypeError, NameError),
ruff/pylint output, and tsc/eslint for TypeScript.

Unlike rule-based detection which finds potential issues,
this module fixes ACTUAL errors reported by the compiler/interpreter.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CompileError:
    """A parsed compiler/interpreter error."""

    file: str
    line: int
    column: int
    error_type: str  # "SyntaxError", "ImportError", "TypeError", etc.
    message: str
    raw_output: str = ""


@dataclass
class CompileFix:
    """A fix suggestion derived from a compile error."""

    error: CompileError
    fix_description: str
    old_code: str = ""
    new_code: str = ""
    confidence: float = 0.9


# ─── Error Parsers ───────────────────────────────────────────────────────────

_PYTHON_ERROR_PATTERN = re.compile(
    r'File "([^"]+)", line (\d+)(?:, in .*?)?\n'
    r'\s*(.*?)\n'
    r'(\w+Error): (.+)',
    re.MULTILINE,
)

_PYTHON_SYNTAX_PATTERN = re.compile(
    r'File "([^"]+)", line (\d+)\n'
    r'(.+)\n'
    r'\s*\^\s*\n'
    r'SyntaxError: (.+)',
    re.MULTILINE,
)

_RUFF_PATTERN = re.compile(
    r'([^:]+):(\d+):(\d+): (\w+) (.+)'
)

_TSC_PATTERN = re.compile(
    r'([^(]+)\((\d+),(\d+)\): error (TS\d+): (.+)'
)


def parse_python_errors(output: str) -> list[CompileError]:
    """Parse Python traceback output into structured errors."""
    errors = []

    # Syntax errors
    for match in _PYTHON_SYNTAX_PATTERN.finditer(output):
        errors.append(CompileError(
            file=match.group(1),
            line=int(match.group(2)),
            column=0,
            error_type="SyntaxError",
            message=match.group(4),
            raw_output=match.group(0),
        ))

    # Runtime errors (ImportError, TypeError, NameError, etc.)
    for match in _PYTHON_ERROR_PATTERN.finditer(output):
        errors.append(CompileError(
            file=match.group(1),
            line=int(match.group(2)),
            column=0,
            error_type=match.group(4),
            message=match.group(5),
            raw_output=match.group(0),
        ))

    return errors


def parse_ruff_output(output: str) -> list[CompileError]:
    """Parse ruff linter output."""
    errors = []
    for match in _RUFF_PATTERN.finditer(output):
        errors.append(CompileError(
            file=match.group(1),
            line=int(match.group(2)),
            column=int(match.group(3)),
            error_type=match.group(4),
            message=match.group(5),
        ))
    return errors


def parse_tsc_output(output: str) -> list[CompileError]:
    """Parse TypeScript compiler output."""
    errors = []
    for match in _TSC_PATTERN.finditer(output):
        errors.append(CompileError(
            file=match.group(1),
            line=int(match.group(2)),
            column=int(match.group(3)),
            error_type=match.group(4),
            message=match.group(5),
        ))
    return errors


# ─── Fix Generators ─────────────────────────────────────────────────────────

def generate_fix(error: CompileError, file_content: str = "") -> Optional[CompileFix]:
    """Generate a fix suggestion for a compile error.

    Args:
        error: The parsed compile error
        file_content: Full file content (for context)

    Returns:
        CompileFix if a fix can be determined, None otherwise
    """
    handler = _FIX_HANDLERS.get(error.error_type)
    if handler:
        return handler(error, file_content)

    # Generic handler based on message patterns
    return _generic_fix(error, file_content)


def _fix_import_error(error: CompileError, content: str) -> Optional[CompileFix]:
    """Fix ImportError / ModuleNotFoundError."""
    msg = error.message

    # "No module named 'X'"
    match = re.search(r"No module named '(\w+)'", msg)
    if match:
        module = match.group(1)
        return CompileFix(
            error=error,
            fix_description=f"Module '{module}' not found. Install it or fix the import.",
            new_code=f"# pip install {module}\n# Or check import path:\n# from correct.path import {module}",
            confidence=0.7,
        )

    # "cannot import name 'X' from 'Y'"
    match = re.search(r"cannot import name '(\w+)' from '([\w.]+)'", msg)
    if match:
        name, module = match.group(1), match.group(2)
        return CompileFix(
            error=error,
            fix_description=f"'{name}' not exported from '{module}'. Check spelling or module version.",
            new_code=f"# Check available exports:\n# from {module} import <tab-complete>\n# Or update: pip install --upgrade {module.split('.')[0]}",
            confidence=0.75,
        )

    return None


def _fix_name_error(error: CompileError, content: str) -> Optional[CompileFix]:
    """Fix NameError (undefined variable)."""
    match = re.search(r"name '(\w+)' is not defined", error.message)
    if not match:
        return None

    name = match.group(1)
    lines = content.split("\n") if content else []

    # Check if it looks like a missing import
    common_imports = {
        "Path": "from pathlib import Path",
        "Optional": "from typing import Optional",
        "List": "from typing import List",
        "Dict": "from typing import Dict",
        "Any": "from typing import Any",
        "dataclass": "from dataclasses import dataclass",
        "field": "from dataclasses import field",
        "asyncio": "import asyncio",
        "json": "import json",
        "os": "import os",
        "re": "import re",
        "sys": "import sys",
        "logging": "import logging",
        "datetime": "from datetime import datetime",
    }

    if name in common_imports:
        return CompileFix(
            error=error,
            fix_description=f"Add missing import for '{name}'",
            new_code=common_imports[name],
            confidence=0.95,
        )

    # Check for typos (similar names in file)
    if lines:
        similar = _find_similar_names(name, lines)
        if similar:
            return CompileFix(
                error=error,
                fix_description=f"Did you mean '{similar[0]}'? ('{name}' is not defined)",
                old_code=name,
                new_code=similar[0],
                confidence=0.8,
            )

    return CompileFix(
        error=error,
        fix_description=f"'{name}' is not defined. Add import or define it.",
        confidence=0.5,
    )


def _fix_type_error(error: CompileError, content: str) -> Optional[CompileFix]:
    """Fix TypeError."""
    msg = error.message

    # "X() takes N positional arguments but M were given"
    match = re.search(r"(\w+)\(\) takes (\d+) .* but (\d+) .* given", msg)
    if match:
        func, expected, got = match.group(1), match.group(2), match.group(3)
        return CompileFix(
            error=error,
            fix_description=f"'{func}()' expects {expected} args but got {got}. Remove extra arguments.",
            confidence=0.85,
        )

    # "'NoneType' object is not subscriptable/iterable/callable"
    if "NoneType" in msg:
        return CompileFix(
            error=error,
            fix_description="Value is None. Add a None check before using it.",
            new_code="if value is not None:\n    # use value here",
            confidence=0.8,
        )

    return None


def _fix_syntax_error(error: CompileError, content: str) -> Optional[CompileFix]:
    """Fix SyntaxError."""
    msg = error.message.lower()

    if "unexpected indent" in msg:
        return CompileFix(
            error=error,
            fix_description="Fix indentation (unexpected indent).",
            confidence=0.9,
        )
    if "expected ':'" in msg or "expected an indented block" in msg:
        return CompileFix(
            error=error,
            fix_description="Missing colon or indented block after statement.",
            confidence=0.85,
        )
    if "unterminated string" in msg:
        return CompileFix(
            error=error,
            fix_description="Close the string literal (missing quote).",
            confidence=0.9,
        )
    if "unmatched" in msg or "unclosed" in msg:
        return CompileFix(
            error=error,
            fix_description="Close the bracket/parenthesis.",
            confidence=0.9,
        )

    return CompileFix(
        error=error,
        fix_description=f"Syntax error: {error.message}",
        confidence=0.6,
    )


def _fix_attribute_error(error: CompileError, content: str) -> Optional[CompileFix]:
    """Fix AttributeError."""
    match = re.search(r"'(\w+)' object has no attribute '(\w+)'", error.message)
    if match:
        obj_type, attr = match.group(1), match.group(2)
        return CompileFix(
            error=error,
            fix_description=f"'{obj_type}' has no attribute '{attr}'. Check spelling or object type.",
            confidence=0.75,
        )
    return None


def _generic_fix(error: CompileError, content: str) -> Optional[CompileFix]:
    """Generic fix attempt based on error message patterns."""
    return CompileFix(
        error=error,
        fix_description=f"{error.error_type}: {error.message}",
        confidence=0.4,
    )


# Handler registry
_FIX_HANDLERS = {
    "ImportError": _fix_import_error,
    "ModuleNotFoundError": _fix_import_error,
    "NameError": _fix_name_error,
    "TypeError": _fix_type_error,
    "SyntaxError": _fix_syntax_error,
    "AttributeError": _fix_attribute_error,
}


# ─── Utility ─────────────────────────────────────────────────────────────────

def _find_similar_names(target: str, lines: list[str]) -> list[str]:
    """Find names in code that are similar to target (possible typos)."""
    import difflib

    # Extract all identifiers from the file
    names: set[str] = set()
    for line in lines:
        for word in re.findall(r'\b([a-zA-Z_]\w*)\b', line):
            if len(word) > 2:
                names.add(word)

    # Find close matches
    matches = difflib.get_close_matches(target, list(names), n=3, cutoff=0.7)
    return matches


def run_python_check(file_path: str | Path) -> list[CompileError]:
    """Run Python syntax check on a file and return errors.

    Args:
        file_path: Path to the Python file

    Returns:
        List of compile errors found
    """
    try:
        result = subprocess.run(
            ["python", "-m", "py_compile", str(file_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return parse_python_errors(result.stderr)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []


# ─── Enhanced Compile-Error-Driven Pipeline ──────────────────────────────────


class CompileErrorPipeline:
    """End-to-end pipeline: run compiler → parse errors → generate fixes.

    Supports multiple tools in sequence:
    1. py_compile (syntax)
    2. ruff (lint + format)
    3. mypy (type checking)
    4. Custom commands

    This enables "compile-error-driven fixing" where real tool output
    drives fix suggestions, not just static rules.
    """

    DEFAULT_TOOLS = {
        ".py": [
            {"name": "py_compile", "cmd": ["python", "-m", "py_compile"], "parser": "python"},
            {"name": "ruff", "cmd": ["ruff", "check", "--output-format=text"], "parser": "ruff"},
        ],
        ".ts": [
            {"name": "tsc", "cmd": ["npx", "tsc", "--noEmit"], "parser": "tsc"},
        ],
    }

    def __init__(self, extra_tools: dict | None = None):
        self._tools = dict(self.DEFAULT_TOOLS)
        if extra_tools:
            for ext, tools in extra_tools.items():
                self._tools.setdefault(ext, []).extend(tools)
        self._fix_cache: dict[str, list[CompileFix]] = {}

    def check_file(self, file_path: Path) -> list[CompileError]:
        """Run all relevant tools on a file and return errors.

        Args:
            file_path: Path to source file

        Returns:
            Combined list of errors from all tools
        """
        ext = file_path.suffix.lower()
        tools = self._tools.get(ext, [])
        all_errors: list[CompileError] = []

        for tool in tools:
            cmd = tool["cmd"] + [str(file_path)]
            parser_name = tool["parser"]

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    output = result.stderr + result.stdout
                    errors = self._parse_output(output, parser_name)
                    all_errors.extend(errors)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

        return all_errors

    def check_and_fix(self, file_path: Path) -> list[CompileFix]:
        """Check file and generate fixes for all errors.

        Args:
            file_path: Path to source file

        Returns:
            List of fix suggestions
        """
        errors = self.check_file(file_path)
        content = ""
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass

        fixes = []
        for error in errors:
            fix = generate_fix(error, content)
            if fix:
                fixes.append(fix)

        # Cache fixes for this file
        self._fix_cache[str(file_path)] = fixes
        return fixes

    def get_cached_fixes(self, file_path: str) -> list[CompileFix]:
        """Get cached fixes for a file (from last check_and_fix call)."""
        return self._fix_cache.get(file_path, [])

    def _parse_output(self, output: str, parser_name: str) -> list[CompileError]:
        """Parse tool output using the specified parser."""
        parsers = {
            "python": parse_python_errors,
            "ruff": parse_ruff_output,
            "tsc": parse_tsc_output,
        }
        parser = parsers.get(parser_name)
        if parser:
            return parser(output)
        return []


def fix_from_compiler_output(
    file_path: Path, compiler_output: str, parser: str = "python"
) -> list[CompileFix]:
    """One-shot: parse compiler output and generate fixes.

    Convenience function for when you already have the compiler output.

    Args:
        file_path: Path to the source file
        compiler_output: Raw output from compiler/linter
        parser: Parser to use ("python", "ruff", "tsc")

    Returns:
        List of fix suggestions
    """
    parsers = {
        "python": parse_python_errors,
        "ruff": parse_ruff_output,
        "tsc": parse_tsc_output,
    }

    parse_fn = parsers.get(parser)
    if not parse_fn:
        return []

    errors = parse_fn(compiler_output)

    content = ""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass

    fixes = []
    for error in errors:
        fix = generate_fix(error, content)
        if fix:
            fixes.append(fix)

    return fixes
