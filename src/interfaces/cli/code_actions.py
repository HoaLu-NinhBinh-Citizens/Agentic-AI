"""Editor-grade code actions and inline diagnostics.

Provides Cursor-like UX features:
- Inline diagnostics (severity, message, range)
- Code actions (quick fix, refactor suggestions)
- Ask-to-apply flow with preview
- Diff preview per file/line before applying

These dataclasses and utilities bridge the analysis engine output
to editor-consumable actions, whether via CLI, LSP, or WebSocket.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class DiagnosticSeverity(Enum):
    """LSP-compatible diagnostic severity levels."""
    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4


class CodeActionKind(Enum):
    """Types of code actions (LSP-compatible)."""
    QUICK_FIX = "quickfix"
    REFACTOR = "refactor"
    REFACTOR_EXTRACT = "refactor.extract"
    REFACTOR_INLINE = "refactor.inline"
    REFACTOR_REWRITE = "refactor.rewrite"
    SOURCE_ORGANIZE_IMPORTS = "source.organizeImports"
    SOURCE_FIX_ALL = "source.fixAll"


@dataclass
class DiagnosticRange:
    """Range within a document (0-indexed)."""
    start_line: int
    start_character: int
    end_line: int
    end_character: int

    def contains_line(self, line: int) -> bool:
        """Check if a line number falls within this range."""
        return self.start_line <= line <= self.end_line


@dataclass
class Diagnostic:
    """An inline diagnostic (error, warning, hint) at a specific location.

    Compatible with LSP TextDocumentDiagnostic and Cursor's inline display.
    """
    file_path: str
    range: DiagnosticRange
    severity: DiagnosticSeverity
    message: str
    rule_id: str = ""
    source: str = "ai-support"
    code: str = ""  # Rule code for filtering
    related_information: list[dict] = field(default_factory=list)

    def to_lsp(self) -> dict[str, Any]:
        """Convert to LSP Diagnostic format."""
        return {
            "range": {
                "start": {"line": self.range.start_line, "character": self.range.start_character},
                "end": {"line": self.range.end_line, "character": self.range.end_character},
            },
            "severity": self.severity.value,
            "code": self.rule_id,
            "source": self.source,
            "message": self.message,
            "relatedInformation": self.related_information,
        }


@dataclass
class TextEdit:
    """A text edit to be applied to a document."""
    range: DiagnosticRange
    new_text: str


@dataclass
class CodeAction:
    """A code action that can be applied to fix or improve code.

    Represents a single actionable fix with:
    - A title for display
    - The kind of action (quickfix, refactor, etc.)
    - Text edits to apply
    - Optional preview diff
    """
    title: str
    kind: CodeActionKind
    diagnostics: list[Diagnostic] = field(default_factory=list)
    edits: list[TextEdit] = field(default_factory=list)
    file_path: str = ""
    is_preferred: bool = False  # Highlighted as the recommended action
    command: str = ""  # CLI command equivalent (e.g., "/fix @file:line")
    preview_diff: str = ""  # Unified diff for preview

    def to_lsp(self) -> dict[str, Any]:
        """Convert to LSP CodeAction format."""
        workspace_edit = {
            "changes": {
                self.file_path: [
                    {
                        "range": {
                            "start": {"line": e.range.start_line, "character": e.range.start_character},
                            "end": {"line": e.range.end_line, "character": e.range.end_character},
                        },
                        "newText": e.new_text,
                    }
                    for e in self.edits
                ]
            }
        }
        return {
            "title": self.title,
            "kind": self.kind.value,
            "diagnostics": [d.to_lsp() for d in self.diagnostics],
            "isPreferred": self.is_preferred,
            "edit": workspace_edit,
        }


@dataclass
class ApplyDecision:
    """User's decision on whether to apply a code action."""
    action: CodeAction
    accepted: bool
    reason: str = ""  # Why user rejected (for learning)


def finding_to_diagnostic(finding: Any) -> Diagnostic:
    """Convert a Finding/MLFinding to an inline Diagnostic.

    Args:
        finding: A Finding object from the analysis engine

    Returns:
        Diagnostic suitable for inline display
    """
    severity_map = {
        "critical": DiagnosticSeverity.ERROR,
        "high": DiagnosticSeverity.ERROR,
        "medium": DiagnosticSeverity.WARNING,
        "low": DiagnosticSeverity.INFORMATION,
        "info": DiagnosticSeverity.HINT,
    }

    sev_value = getattr(finding, "severity", "medium")
    if hasattr(sev_value, "value"):
        sev_value = sev_value.value
    severity = severity_map.get(str(sev_value).lower(), DiagnosticSeverity.WARNING)

    line = getattr(finding, "line", 1)
    end_line = getattr(finding, "end_line", None) or line
    file_path = getattr(finding, "file_path", "") or getattr(finding, "file", "")

    return Diagnostic(
        file_path=file_path,
        range=DiagnosticRange(
            start_line=line - 1,  # Convert to 0-indexed
            start_character=0,
            end_line=end_line - 1,
            end_character=999,  # End of line
        ),
        severity=severity,
        message=getattr(finding, "message", str(finding)),
        rule_id=getattr(finding, "rule_id", ""),
        source="ai-support",
    )


def finding_to_code_action(finding: Any) -> Optional[CodeAction]:
    """Convert a Finding with fix to a CodeAction.

    Args:
        finding: A Finding with old_code/new_code or fix_template

    Returns:
        CodeAction if a fix is available, None otherwise
    """
    old_code = getattr(finding, "old_code", "") or ""
    new_code = getattr(finding, "new_code", "") or ""
    fix = getattr(finding, "fix", "") or getattr(finding, "fix_template", "")

    if not new_code and not fix:
        return None

    replacement = new_code or fix
    line = getattr(finding, "line", 1)
    end_line = getattr(finding, "end_line", None) or line
    file_path = getattr(finding, "file_path", "") or getattr(finding, "file", "")
    rule_id = getattr(finding, "rule_id", "")
    message = getattr(finding, "message", "")

    # Generate preview diff
    preview = ""
    if old_code and new_code:
        diff_lines = difflib.unified_diff(
            old_code.split("\n"),
            new_code.split("\n"),
            fromfile="before",
            tofile="after",
            lineterm="",
        )
        preview = "\n".join(diff_lines)

    diagnostic = finding_to_diagnostic(finding)

    edit = TextEdit(
        range=DiagnosticRange(
            start_line=line - 1,
            start_character=0,
            end_line=end_line - 1,
            end_character=999,
        ),
        new_text=replacement,
    )

    return CodeAction(
        title=f"Fix [{rule_id}]: {message[:50]}",
        kind=CodeActionKind.QUICK_FIX,
        diagnostics=[diagnostic],
        edits=[edit],
        file_path=file_path,
        is_preferred=True,
        command=f"/fix @{file_path}:{line}",
        preview_diff=preview,
    )


def generate_ask_to_apply_prompt(action: CodeAction) -> str:
    """Generate a user-facing prompt for the ask-to-apply flow.

    Args:
        action: The code action to present

    Returns:
        Formatted string for terminal display
    """
    lines = []
    lines.append(f"  ┌─ {action.title}")
    lines.append(f"  │  File: {action.file_path}")
    if action.diagnostics:
        d = action.diagnostics[0]
        lines.append(f"  │  Line: {d.range.start_line + 1}")
        lines.append(f"  │  {d.message}")

    if action.preview_diff:
        lines.append("  │")
        lines.append("  │  Preview:")
        for diff_line in action.preview_diff.split("\n")[:10]:
            if diff_line.startswith("-"):
                lines.append(f"  │  \033[91m{diff_line}\033[0m")
            elif diff_line.startswith("+"):
                lines.append(f"  │  \033[92m{diff_line}\033[0m")
            else:
                lines.append(f"  │  {diff_line}")

    lines.append("  │")
    lines.append("  │  [y] Apply  [n] Skip  [d] Show full diff  [q] Quit")
    lines.append("  └─")
    return "\n".join(lines)
