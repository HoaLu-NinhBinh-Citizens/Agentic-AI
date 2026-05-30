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
