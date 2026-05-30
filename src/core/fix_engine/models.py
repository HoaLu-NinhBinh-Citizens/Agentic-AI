"""Fix engine data models for code review fix management."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FixStatus(Enum):
    """Status of a fix in the lifecycle."""
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    FAILED = "failed"
    SKIPPED = "skipped"


class FixSeverity(Enum):
    """Severity level of a fix."""
    ERROR = "error"       # Must fix
    WARNING = "warning"   # Should fix
    INFO = "info"         # Consider fixing


@dataclass
class Fix:
    """A code fix suggestion with full context."""
    id: str
    file_path: str
    line_start: int
    line_end: int
    old_text: str
    new_text: str
    reason: str
    rule_id: str = ""
    severity: FixSeverity = FixSeverity.WARNING
    confidence: float = 1.0
    status: FixStatus = FixStatus.PENDING
    created_by: str = "rule_engine"  # "rule_engine", "llm_review", "security_scan"
    llm_explanation: str = ""

    @property
    def is_critical(self) -> bool:
        """Check if fix is critical (error severity)."""
        return self.severity == FixSeverity.ERROR

    @property
    def location(self) -> str:
        """Human-readable location string."""
        if self.line_start == self.line_end:
            return f"{self.file_path}:{self.line_start}"
        return f"{self.file_path}:{self.line_start}-{self.line_end}"

    def mark_applied(self) -> None:
        """Mark fix as applied."""
        self.status = FixStatus.APPLIED

    def mark_rejected(self) -> None:
        """Mark fix as rejected."""
        self.status = FixStatus.REJECTED

    def mark_failed(self) -> None:
        """Mark fix as failed."""
        self.status = FixStatus.FAILED


@dataclass
class FixBatch:
    """A batch of fixes for multiple files with tracking."""
    fixes: list[Fix] = field(default_factory=list)
    total_files: int = 0
    total_fixes: int = 0
    applied: int = 0
    rejected: int = 0
    failed: int = 0

    def add(self, fix: Fix) -> None:
        """Add a fix and update counters."""
        self.fixes.append(fix)
        self.total_fixes += 1
        if fix.file_path:
            unique_files = len(set(f.file_path for f in self.fixes))
            self.total_files = unique_files

    def update_counters(self) -> None:
        """Recalculate counters from fixes list."""
        self.applied = sum(1 for f in self.fixes if f.status == FixStatus.APPLIED)
        self.rejected = sum(1 for f in self.fixes if f.status == FixStatus.REJECTED)
        self.failed = sum(1 for f in self.fixes if f.status == FixStatus.FAILED)

    @property
    def pending(self) -> int:
        """Count of pending fixes."""
        return sum(1 for f in self.fixes if f.status == FixStatus.PENDING)

    @property
    def success_rate(self) -> float:
        """Success rate of applied fixes."""
        total = self.applied + self.rejected + self.failed
        if total == 0:
            return 0.0
        return self.applied / total

    def get_by_file(self, file_path: str) -> list[Fix]:
        """Get all fixes for a specific file."""
        return [f for f in self.fixes if f.file_path == file_path]

    def get_by_severity(self, severity: FixSeverity) -> list[Fix]:
        """Get all fixes of a specific severity."""
        return [f for f in self.fixes if f.severity == severity]


@dataclass
class FixResult:
    """Result of applying a single fix with rollback info."""
    fix_id: str
    success: bool
    new_content: str = ""
    error: str = ""
    backup_path: str = ""

    @property
    def has_backup(self) -> bool:
        """Check if backup was created."""
        return bool(self.backup_path)


@dataclass
class ReviewFinding:
    """A finding from code review."""
    file_path: str
    line: int
    rule_id: str
    message: str
    severity: FixSeverity
    suggested_fix: Optional[str] = None
    confidence: float = 1.0

    def to_fix(self, fix_id: str) -> Fix:
        """Convert finding to a Fix object."""
        return Fix(
            id=fix_id,
            file_path=self.file_path,
            line_start=self.line,
            line_end=self.line,
            old_text="",  # Will be filled by fix engine
            new_text=self.suggested_fix or "",
            reason=self.message,
            rule_id=self.rule_id,
            severity=self.severity,
            confidence=self.confidence,
            created_by="review_agent",
        )


# ─── Smart Fix Extractor ─────────────────────────────────────────────────────

import re


def extract_fix_context(
    file_path: str,
    line: int,
    context_lines: int = 3,
) -> tuple[str, str]:
    """Extract surrounding context lines from a file.

    Returns:
        (before_code, target_line) tuple.
    """
    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return "", ""

    start = max(0, line - context_lines - 1)
    end = min(len(lines), line + context_lines)
    before = "".join(lines[start:end])
    target = lines[line - 1] if 0 < line <= len(lines) else ""
    return before, target


def build_old_text(
    file_path: str,
    line: int,
    rule_id: str,
    context_lines: int = 3,
) -> str:
    """Build the exact old_text for a finding by reading the file."""
    _, target = extract_fix_context(file_path, line, context_lines)
    return target.strip() if target else ""


def build_new_text(rule_id: str, old_text: str) -> str:
    """Build the new text for a fix based on the rule ID."""
    replacements = {
        # Naming conventions
        "NAME001": old_text.replace("def CamelCase(", "def snake_case("),
        "NAME002": _fix_class_name(old_text),
        "NAME003": _fix_constant_name(old_text),
        # Code quality
        "QUAL003": _fix_broad_except(old_text),
        "QUAL005": "",  # TODO removal - can't auto-fix
        "QUAL006": _fix_print_to_log(old_text),
        "QUAL007": _fix_magic_number(old_text),
        # Type safety
        "TYPE001": _add_type_hints(old_text),
        # Import
        "IMP001": "",  # Unused import - can't auto-determine
        "IMP003": _fix_wildcard_import(old_text),
        # Security
        "SEC001": _fix_hardcoded_secret(old_text),
        "SEC003": _fix_shell_injection(old_text),
        "SEC005": _fix_eval_usage(old_text),
    }
    return replacements.get(rule_id, old_text)


def _fix_class_name(text: str) -> str:
    """Convert PascalCase class name to snake_case."""
    result = re.sub(r'(?<!^)(?=[A-Z])', '_', text).lower()
    return result


def _fix_constant_name(text: str) -> str:
    """Convert lowercase constant to UPPER_CASE."""
    return re.sub(r'^([a-z][a-z0-9_]*)', lambda m: m.group(1).upper(), text)


def _fix_broad_except(text: str) -> str:
    """Fix bare except to catch specific exceptions."""
    if "except :" in text:
        return text.replace("except :", "except Exception as e:")
    if "except Exception :" in text:
        return text.replace("except Exception :", "except (ValueError, TypeError) as e:")
    return text


def _fix_print_to_log(text: str) -> str:
    """Replace print() with logging calls."""
    m = re.search(r'print\s*\(\s*(.+?)\s*\)', text)
    if m:
        content = m.group(1).strip()
        return text.replace(f"print({m.group(0)})", f"logging.info({content})")
    return text


def _fix_magic_number(text: str) -> str:
    """Suggest constant name for magic number."""
    m = re.search(r'(?<![a-zA-Z_])(0x[0-9A-Fa-f]+|[2-9]\d{1,})(?![xXa-zA-Z0-9_.\-%])', text)
    if m:
        num = m.group(1)
        return text.replace(num, "BUFFER_SIZE  # TODO: define constant")
    return text


def _add_type_hints(text: str) -> str:
    """Add basic type hints to function definition."""
    m = re.match(r'(def \w+\s*\()(.*?)(\)\s*:)', text)
    if m:
        params = m.group(2).strip()
        if params:
            return f"{m.group(1)}{params}: Any{m.group(3)}"
        return f"{m.group(1)}) -> None{m.group(3)}"
    return text


def _fix_wildcard_import(text: str) -> str:
    """Replace wildcard import with explicit imports."""
    m = re.search(r'from\s+(\w+)\s+import\s+\*', text)
    if m:
        return f"# TODO: Replace wildcard import with explicit imports\n# from {m.group(1)} import ..."
    return text


def _fix_hardcoded_secret(text: str) -> str:
    """Replace hardcoded secret with env var."""
    return re.sub(
        r'(["\'])(?:api[_-]?key|secret|password|token)(["\'])\s*[:=]\s*["\'][^"\']+["\']',
        r'\1\2: os.getenv("\1\2")',
        text,
        flags=re.IGNORECASE
    )


def _fix_shell_injection(text: str) -> str:
    """Fix shell=True subprocess calls."""
    if "shell=True" in text:
        return text.replace("shell=True", "shell=False")
    if "eval(" in text:
        return "// " + text + "  # DANGER: eval usage removed"
    return text


def _fix_eval_usage(text: str) -> str:
    """Replace eval/exec with safer alternatives."""
    if "eval(" in text:
        m = re.search(r'(\w+)\s*=\s*eval\s*\((.+?)\)', text)
        if m:
            return f"{m.group(1)} = ast.literal_eval({m.group(2)})  # Safe alternative to eval"
    return "// " + text if "exec(" in text else text
