"""Auto-fix from LSP diagnostics.

Provides:
- Automatic code fixes from LSP diagnostics
- Batch fixes application
- Safety checks before applying
- Undo support for auto-fixes
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class FixSeverity(Enum):
    """Severity of a fix."""
    ERROR = "error"  # Must fix
    WARNING = "warning"  # Should fix
    INFO = "info"  # Optional
    HINT = "hint"  # Refactor suggestion


@dataclass
class DiagnosticCode:
    """Diagnostic error code."""
    code: str
    source: str = ""  # e.g., "pylint", "ruff", "pyright"
    
    def __str__(self) -> str:
        return f"{self.source}:{self.code}" if self.source else self.code


@dataclass
class Diagnostic:
    """An LSP diagnostic."""
    message: str
    severity: FixSeverity
    range: dict  # start/end with line/character
    
    code: DiagnosticCode | None = None
    source: str = ""
    tags: list[str] = field(default_factory=list)
    
    # Fix info
    fix_available: bool = False
    suggested_fix: dict | None = None


@dataclass
class CodeFix:
    """A code fix."""
    id: str
    title: str
    description: str = ""
    
    # The fix itself
    edits: list[dict] = field(default_factory=list)  # LSP text edits
    
    # Metadata
    severity: FixSeverity = FixSeverity.WARNING
    is_applicable: bool = True
    needs_confirmation: bool = False
    
    # Diagnostics this fixes
    fixes_diagnostics: list[str] = field(default_factory=list)
    
    # Safety
    is_deterministic: bool = True  # Same result every time
    affects_other_files: bool = False


@dataclass
class FixResult:
    """Result of applying fixes."""
    success: bool
    applied: list[CodeFix] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


class AutoFixRule:
    """A rule for automatic fixing."""
    
    def __init__(
        self,
        code: str,
        fix_fn: callable,
        severity: FixSeverity = FixSeverity.WARNING,
        description: str = "",
    ):
        self.code = code
        self.fix_fn = fix_fn
        self.severity = severity
        self.description = description


class DiagnosticFixer:
    """Fixer that applies fixes based on diagnostics."""
    
    def __init__(self):
        self._rules: list[AutoFixRule] = []
        self._fix_history: list[tuple[Path, list[dict]]] = []  # For undo
        self._setup_default_rules()
    
    def _setup_default_rules(self) -> None:
        """Setup default fix rules."""
        # Python rules
        self.add_rule("E302", self._fix_missing_blank_line)
        self.add_rule("E305", self._fix_missing_blank_lines_after)
        self.add_rule("E501", self._fix_line_too_long)
        self.add_rule("F401", self._fix_unused_import)
        self.add_rule("F841", self._fix_unused_variable)
        
        # TypeScript rules
        self.add_rule("no-unused-vars", self._fix_ts_unused_var)
        self.add_rule("no-undef", self._fix_ts_undef)
        
        # Generic rules
        self.add_rule("trailing-whitespace", self._fix_trailing_whitespace)
        self.add_rule("missing-semicolon", self._fix_missing_semicolon)
    
    def add_rule(self, code: str, fix_fn: callable) -> None:
        """Add a fix rule."""
        rule = AutoFixRule(code=code, fix_fn=fix_fn)
        self._rules.append(rule)
    
    async def fix_diagnostics(
        self,
        path: Path,
        diagnostics: list[Diagnostic],
        auto_apply_safe: bool = True,
    ) -> FixResult:
        """Fix diagnostics for a file."""
        result = FixResult(success=True, applied=[], failed=[], skipped=[])
        
        # Get original content for undo
        original_content = path.read_text() if path.exists() else ""
        
        for diag in diagnostics:
            if not diag.fix_available:
                # Check if we have a rule for this
                code = str(diag.code) if diag.code else ""
                
                rule = self._find_rule(code)
                if rule:
                    try:
                        fix = await rule.fix_fn(path, diag)
                        if fix:
                            result.applied.append(fix)
                    except Exception as e:
                        result.failed.append({
                            "diagnostic": code,
                            "error": str(e),
                        })
                else:
                    result.skipped.append(code)
            else:
                # Use LSP-provided fix
                if diag.suggested_fix:
                    fix = self._create_fix_from_lsp(diag.suggested_fix)
                    if self._is_safe_to_apply(fix, diag.severity, auto_apply_safe):
                        result.applied.append(fix)
                    else:
                        result.skipped.append(str(diag.code))
        
        # Apply all fixes
        if result.applied:
            try:
                await self._apply_fixes(path, result.applied)
                
                # Record for undo
                self._fix_history.append((path, [{
                    "original": original_content,
                    "applied": result.applied,
                }]))
                
            except Exception as e:
                result.success = False
                result.failed.append({
                    "fix": "all",
                    "error": str(e),
                })
        
        return result
    
    def _find_rule(self, code: str) -> AutoFixRule | None:
        """Find a fix rule for code."""
        for rule in self._rules:
            if rule.code in code:
                return rule
        return None
    
    def _is_safe_to_apply(
        self,
        fix: CodeFix,
        severity: FixSeverity,
        auto_apply_safe: bool,
    ) -> bool:
        """Check if fix is safe to apply."""
        # Never auto-apply fixes that need confirmation
        if fix.needs_confirmation:
            return False
        
        # Auto-apply only safe fixes if enabled
        if auto_apply_safe:
            return fix.is_deterministic and not fix.affects_other_files
        
        return severity == FixSeverity.ERROR
    
    def _create_fix_from_lsp(self, fix_data: dict) -> CodeFix:
        """Create CodeFix from LSP fix data."""
        return CodeFix(
            id=fix_data.get("id", ""),
            title=fix_data.get("title", "LSP Fix"),
            description=fix_data.get("description", ""),
            edits=fix_data.get("edits", []),
        )
    
    async def _apply_fixes(self, path: Path, fixes: list[CodeFix]) -> None:
        """Apply fixes to a file."""
        if not path.exists():
            return
        
        content = path.read_text()
        lines = content.split("\n")
        
        # Sort edits by position (reverse order to not shift positions)
        all_edits = []
        for fix in fixes:
            for edit in fix.edits:
                all_edits.append((edit, fix))
        
        # Sort by line/character in reverse
        def get_position(edit):
            start = edit.get("range", {}).get("start", {})
            return (start.get("line", 0), start.get("character", 0))
        
        all_edits.sort(key=lambda x: get_position(x[0]), reverse=True)
        
        # Apply edits
        for edit, fix in all_edits:
            start = edit.get("range", {}).get("start", {})
            end = edit.get("range", {}).get("end", {})
            
            start_line = start.get("line", 0)
            start_char = start.get("character", 0)
            end_line = end.get("line", 0)
            end_char = end.get("character", 0)
            
            new_text = edit.get("newText", "")
            
            # Apply the edit
            if start_line == end_line:
                # Single line edit
                if 0 <= start_line < len(lines):
                    line = lines[start_line]
                    lines[start_line] = line[:start_char] + new_text + line[end_char:]
            else:
                # Multi-line edit
                start_line_content = lines[start_line][:start_char]
                end_line_content = lines[end_line][end_char:]
                
                # Remove lines between
                lines[start_line:end_line + 1] = [
                    start_line_content + new_text + end_line_content
                ]
        
        # Write back
        path.write_text("\n".join(lines))
    
    async def undo_last_fix(self, path: Path) -> bool:
        """Undo the last fix applied to a file."""
        for i in range(len(self._fix_history) - 1, -1, -1):
            history_path, history = self._fix_history[i]
            
            if history_path == path and history:
                original = history[0]["original"]
                path.write_text(original)
                self._fix_history.pop(i)
                return True
        
        return False
    
    # Default fix implementations
    
    async def _fix_missing_blank_line(
        self,
        path: Path,
        diag: Diagnostic,
    ) -> CodeFix | None:
        """Fix missing blank line."""
        line = diag.range["start"]["line"]
        
        return CodeFix(
            id="fix-missing-blank-line",
            title="Add missing blank line",
            edits=[{
                "range": {
                    "start": {"line": line, "character": 0},
                    "end": {"line": line, "character": 0},
                },
                "newText": "\n",
            }],
            severity=diag.severity,
        )
    
    async def _fix_missing_blank_lines_after(
        self,
        path: Path,
        diag: Diagnostic,
    ) -> CodeFix | None:
        """Fix missing blank lines after function."""
        line = diag.range["start"]["line"]
        
        return CodeFix(
            id="fix-missing-blank-lines",
            title="Add missing blank lines",
            edits=[{
                "range": {
                    "start": {"line": line + 1, "character": 0},
                    "end": {"line": line + 1, "character": 0},
                },
                "newText": "\n\n",
            }],
            severity=diag.severity,
        )
    
    async def _fix_line_too_long(
        self,
        path: Path,
        diag: Diagnostic,
    ) -> CodeFix | None:
        """Fix line too long by adding line continuation."""
        line_num = diag.range["start"]["line"]
        lines = path.read_text().split("\n")
        
        if 0 <= line_num < len(lines):
            line = lines[line_num]
            if len(line) > 88:
                # Find split point
                split_at = 88
                while split_at > 0 and not line[split_at].isspace():
                    split_at -= 1
                
                if split_at > 0:
                    first_part = line[:split_at].rstrip()
                    second_part = line[split_at:].lstrip()
                    
                    return CodeFix(
                        id="fix-line-too-long",
                        title="Break long line",
                        edits=[{
                            "range": {
                                "start": {"line": line_num, "character": 0},
                                "end": {"line": line_num, "character": len(line)},
                            },
                            "newText": f"{first_part}\\\n{second_part}",
                        }],
                        severity=diag.severity,
                    )
        
        return None
    
    async def _fix_unused_import(
        self,
        path: Path,
        diag: Diagnostic,
    ) -> CodeFix | None:
        """Fix unused import."""
        message = diag.message
        
        # Extract import name
        match = re.search(r"'(\w+)' imported", message)
        if match:
            import_name = match.group(1)
            
            return CodeFix(
                id="fix-unused-import",
                title=f"Remove unused import '{import_name}'",
                edits=[{
                    "range": diag.range,
                    "newText": "",
                }],
                severity=diag.severity,
            )
        
        return None
    
    async def _fix_unused_variable(
        self,
        path: Path,
        diag: Diagnostic,
    ) -> CodeFix | None:
        """Fix unused variable."""
        message = diag.message
        
        # Extract variable name
        match = re.search(r"local variable '(\w+)'", message)
        if match:
            var_name = match.group(1)
            
            return CodeFix(
                id="fix-unused-variable",
                title=f"Rename or remove unused variable '{var_name}'",
                needs_confirmation=True,
                severity=diag.severity,
            )
        
        return None
    
    # TypeScript fixes
    
    async def _fix_ts_unused_var(
        self,
        path: Path,
        diag: Diagnostic,
    ) -> CodeFix | None:
        """Fix TypeScript unused variable."""
        # Similar to Python unused variable
        return await self._fix_unused_variable(path, diag)
    
    async def _fix_ts_undef(
        self,
        path: Path,
        diag: Diagnostic,
    ) -> CodeFix | None:
        """Fix TypeScript undefined variable."""
        # This requires more context - suggest adding declaration
        return CodeFix(
            id="fix-ts-undef",
            title="Declare or import undefined variable",
            needs_confirmation=True,
            severity=diag.severity,
        )
    
    # Generic fixes
    
    async def _fix_trailing_whitespace(
        self,
        path: Path,
        diag: Diagnostic,
    ) -> CodeFix | None:
        """Fix trailing whitespace."""
        line_num = diag.range["start"]["line"]
        lines = path.read_text().split("\n")
        
        if 0 <= line_num < len(lines):
            line = lines[line_num]
            if line.rstrip() != line:
                lines[line_num] = line.rstrip()
                
                return CodeFix(
                    id="fix-trailing-whitespace",
                    title="Remove trailing whitespace",
                    edits=[{
                        "range": {
                            "start": {"line": line_num, "character": 0},
                            "end": {"line": line_num, "character": len(line)},
                        },
                        "newText": line.rstrip(),
                    }],
                    severity=diag.severity,
                    is_deterministic=True,
                )
        
        return None
    
    async def _fix_missing_semicolon(
        self,
        path: Path,
        diag: Diagnostic,
    ) -> CodeFix | None:
        """Fix missing semicolon."""
        line_num = diag.range["start"]["line"]
        
        return CodeFix(
            id="fix-missing-semicolon",
            title="Add missing semicolon",
            edits=[{
                "range": {
                    "start": {"line": line_num, "character": 0},
                    "end": {"line": line_num, "character": 0},
                },
                "newText": ";",
            }],
            severity=diag.severity,
        )


class BatchFixer:
    """Apply fixes across multiple files."""
    
    def __init__(self, fixer: DiagnosticFixer):
        self.fixer = fixer
    
    async def fix_directory(
        self,
        directory: Path,
        file_patterns: list[str] | None = None,
        extensions: list[str] | None = None,
    ) -> dict[Path, FixResult]:
        """Fix diagnostics in all files in a directory."""
        results = {}
        
        file_patterns = file_patterns or ["*.py", "*.ts", "*.js", "*.tsx", "*.jsx"]
        extensions = extensions or [".py", ".ts", ".js", ".tsx", ".jsx"]
        
        for pattern in file_patterns:
            for path in directory.rglob(pattern):
                if path.is_file():
                    results[path] = await self.fix_file(path)
        
        return results
    
    async def fix_file(self, path: Path) -> FixResult:
        """Fix diagnostics in a single file."""
        # This would integrate with LSP to get diagnostics
        # For now, return empty result
        return FixResult(success=True)
