"""Conflict resolution for multiple fixes affecting same code.

This module provides conflict detection and resolution for cases where
multiple fixes target overlapping lines or make conflicting changes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.core.fix_engine.models import Fix, FixBatch, FixStatus

logger = logging.getLogger(__name__)


class ConflictType(Enum):
    """Types of conflicts between fixes."""
    OVERLAPPING_LINES = "overlapping_lines"
    CONFLICTING_CHANGES = "conflicting_changes"
    CONTAINER_CONFLICT = "container_conflict"
    DEPENDENCY_CONFLICT = "dependency_conflict"


class ResolutionStrategy(Enum):
    """Strategy for resolving conflicts."""
    APPLY_A_FIRST = "apply_a_first"
    APPLY_B_FIRST = "apply_b_first"
    SKIP_B = "skip_b"
    SKIP_A = "skip_a"
    MERGE = "merge"
    MANUAL = "manual"
    DEPENDENCY_ORDER = "dependency_order"


@dataclass
class FixConflict:
    """Represents a conflict between fixes.

    Attributes:
        conflict_type: Type of conflict detected
        fix_a: First conflicting fix
        fix_b: Second conflicting fix
        overlap_lines: Tuple of (start_line, end_line) for overlap
        severity: Conflict severity ("high", "medium", "low")
        description: Human-readable conflict description
    """
    conflict_type: ConflictType
    fix_a: Fix
    fix_b: Fix
    overlap_lines: tuple[int, int]
    severity: str
    description: str = ""

    def __post_init__(self) -> None:
        if not self.description:
            self.description = self._generate_description()

    def _generate_description(self) -> str:
        """Generate a human-readable description of the conflict."""
        start, end = self.overlap_lines
        file_a = self.fix_a.file_path.split("/")[-1]
        file_b = self.fix_b.file_path.split("/")[-1]

        if self.conflict_type == ConflictType.OVERLAPPING_LINES:
            return (
                f"Fixes at {self.fix_a.file_path}:{self.fix_a.line_start}-"
                f"{self.fix_a.line_end} and {self.fix_b.file_path}:"
                f"{self.fix_b.line_start}-{self.fix_b.line_end} overlap on "
                f"lines {start}-{end}"
            )
        elif self.conflict_type == ConflictType.CONFLICTING_CHANGES:
            return (
                f"Conflicting changes: '{file_a}' modifies behavior that "
                f"'{file_b}' depends on"
            )
        elif self.conflict_type == ConflictType.CONTAINER_CONFLICT:
            return (
                f"Fix '{file_a}' modifies container that contains "
                f"fix '{file_b}'"
            )
        elif self.conflict_type == ConflictType.DEPENDENCY_CONFLICT:
            return (
                f"Dependency conflict: '{file_a}' and '{file_b}' have "
                f"mutual dependencies"
            )
        return "Unknown conflict type"


@dataclass
class ConflictResolution:
    """Resolution strategy for a conflict.

    Attributes:
        conflict: The conflict being resolved
        strategy: Resolution strategy used
        resolved_fixes: Ordered list of fixes to apply
        explanation: Why this strategy was chosen
    """
    conflict: FixConflict
    strategy: ResolutionStrategy
    resolved_fixes: list[Fix]
    explanation: str


@dataclass
class ConflictReport:
    """Report of all conflicts found and their resolutions.

    Attributes:
        conflicts: List of detected conflicts
        resolutions: List of resolutions for each conflict
        safe_order: Recommended order for applying fixes
        has_unresolved: Whether any conflicts remain unresolved
    """
    conflicts: list[FixConflict] = field(default_factory=list)
    resolutions: list[ConflictResolution] = field(default_factory=list)
    safe_order: list[Fix] = field(default_factory=list)
    has_unresolved: bool = False

    @property
    def high_severity_count(self) -> int:
        """Count of high-severity conflicts."""
        return sum(1 for c in self.conflicts if c.severity == "high")

    @property
    def medium_severity_count(self) -> int:
        """Count of medium-severity conflicts."""
        return sum(1 for c in self.conflicts if c.severity == "medium")

    @property
    def low_severity_count(self) -> int:
        """Count of low-severity conflicts."""
        return sum(1 for c in self.conflicts if c.severity == "low")


class ConflictResolver:
    """Detect and resolve fix conflicts.

    This class analyzes multiple fixes and identifies conflicts based on:
    - Line number overlap
    - Conflicting changes to the same code
    - Container/containee relationships
    - Dependency ordering
    """

    def __init__(self, overlap_window: int = 3) -> None:
        """Initialize the conflict resolver.

        Args:
            overlap_window: Number of lines to consider as overlapping
        """
        self.overlap_window = overlap_window

    def detect_conflicts(self, fixes: list[Fix]) -> list[FixConflict]:
        """Find all conflicting fixes.

        Args:
            fixes: List of fixes to check for conflicts

        Returns:
            List of detected conflicts
        """
        conflicts: list[FixConflict] = []

        for i, fix_a in enumerate(fixes):
            for fix_b in fixes[i + 1:]:
                conflict = self._check_pair_conflict(fix_a, fix_b)
                if conflict:
                    conflicts.append(conflict)

        logger.info("Detected %d conflicts in %d fixes", len(conflicts), len(fixes))
        return conflicts

    def _check_pair_conflict(self, fix_a: Fix, fix_b: Fix) -> Optional[FixConflict]:
        """Check if two fixes conflict.

        Args:
            fix_a: First fix to check
            fix_b: Second fix to check

        Returns:
            FixConflict if they conflict, None otherwise
        """
        if fix_a.file_path != fix_b.file_path:
            return self._check_dependency_conflict(fix_a, fix_b)

        overlap = self._calculate_overlap(fix_a, fix_b)

        if overlap:
            return self._create_overlap_conflict(fix_a, fix_b, overlap)

        if self._check_text_conflict(fix_a, fix_b):
            return self._create_text_conflict(fix_a, fix_b)

        return None

    def _calculate_overlap(
        self, fix_a: Fix, fix_b: Fix
    ) -> Optional[tuple[int, int]]:
        """Calculate overlapping lines between two fixes.

        Args:
            fix_a: First fix
            fix_b: Second fix

        Returns:
            Tuple of (start, end) lines of overlap, or None
        """
        a_start, a_end = fix_a.line_start, fix_a.line_end
        b_start, b_end = fix_b.line_start, fix_b.line_end

        if a_end < b_start - self.overlap_window or b_end < a_start - self.overlap_window:
            return None

        overlap_start = max(a_start, b_start)
        overlap_end = min(a_end, b_end)

        if overlap_start <= overlap_end:
            return (overlap_start, overlap_end)

        return None

    def _check_text_conflict(self, fix_a: Fix, fix_b: Fix) -> bool:
        """Check if two fixes make conflicting text changes.

        Args:
            fix_a: First fix
            fix_b: Second fix

        Returns:
            True if changes conflict
        """
        if not fix_a.old_text or not fix_b.old_text:
            return False

        a_covers_b = fix_a.old_text in fix_b.old_text
        b_covers_a = fix_b.old_text in fix_a.old_text

        if a_covers_b or b_covers_a:
            return True

        common_prefix = self._find_common_prefix(fix_a.old_text, fix_b.old_text)
        if len(common_prefix) > 20:
            return True

        return False

    def _find_common_prefix(self, text_a: str, text_b: str) -> str:
        """Find common prefix between two texts.

        Args:
            text_a: First text
            text_b: Second text

        Returns:
            Common prefix string
        """
        result = []
        for a, b in zip(text_a, text_b):
            if a == b:
                result.append(a)
            else:
                break
        return "".join(result)

    def _check_dependency_conflict(
        self, fix_a: Fix, fix_b: Fix
    ) -> Optional[FixConflict]:
        """Check for dependency-based conflicts between fixes.

        Args:
            fix_a: First fix
            fix_b: Second fix

        Returns:
            FixConflict if dependency conflict exists
        """
        import re

        dependency_patterns = [
            (r"import\s+(\w+)", r"from\s+(\w+)\s+import"),
            (r"def\s+(\w+)", r"class\s+(\w+)"),
            (r"class\s+(\w+)", r"def\s+(\w+)"),
        ]

        for pattern_a, pattern_b in dependency_patterns:
            match_a = re.search(pattern_a, fix_a.new_text)
            match_b = re.search(pattern_b, fix_b.new_text)

            if match_a and match_b:
                if match_a.group(1) == match_b.group(1):
                    return FixConflict(
                        conflict_type=ConflictType.DEPENDENCY_CONFLICT,
                        fix_a=fix_a,
                        fix_b=fix_b,
                        overlap_lines=(0, 0),
                        severity="medium",
                        description=(
                            f"'{fix_a.file_path}' defines '{match_a.group(1)}' "
                            f"that '{fix_b.file_path}' also references"
                        ),
                    )

        return None

    def _create_overlap_conflict(
        self,
        fix_a: Fix,
        fix_b: Fix,
        overlap: tuple[int, int],
    ) -> FixConflict:
        """Create a conflict for overlapping fixes.

        Args:
            fix_a: First fix
            fix_b: Second fix
            overlap: Overlapping lines

        Returns:
            FixConflict for the overlap
        """
        severity = "high" if abs(fix_a.line_start - fix_b.line_start) < 2 else "medium"

        return FixConflict(
            conflict_type=ConflictType.OVERLAPPING_LINES,
            fix_a=fix_a,
            fix_b=fix_b,
            overlap_lines=overlap,
            severity=severity,
        )

    def _create_text_conflict(
        self,
        fix_a: Fix,
        fix_b: Fix,
    ) -> FixConflict:
        """Create a conflict for textually conflicting fixes.

        Args:
            fix_a: First fix
            fix_b: Second fix

        Returns:
            FixConflict for the text conflict
        """
        return FixConflict(
            conflict_type=ConflictType.CONFLICTING_CHANGES,
            fix_a=fix_a,
            fix_b=fix_b,
            overlap_lines=(fix_b.line_start, fix_b.line_end),
            severity="high",
        )

    def resolve_conflicts(
        self,
        conflicts: list[FixConflict],
        strategy: ResolutionStrategy = ResolutionStrategy.APPLY_A_FIRST,
    ) -> list[ConflictResolution]:
        """Resolve conflicts and return ordered fix list.

        Args:
            conflicts: List of conflicts to resolve
            strategy: Default strategy to use

        Returns:
            List of resolutions for each conflict
        """
        resolutions: list[ConflictResolution] = []

        for conflict in conflicts:
            resolution = self._resolve_single_conflict(conflict, strategy)
            resolutions.append(resolution)

        return resolutions

    def _resolve_single_conflict(
        self,
        conflict: FixConflict,
        default_strategy: ResolutionStrategy,
    ) -> ConflictResolution:
        """Resolve a single conflict.

        Args:
            conflict: The conflict to resolve
            default_strategy: Default strategy to use

        Returns:
            ConflictResolution with chosen strategy
        """
        if conflict.conflict_type == ConflictType.OVERLAPPING_LINES:
            return self._resolve_overlap_conflict(conflict)

        if conflict.conflict_type == ConflictType.DEPENDENCY_CONFLICT:
            return self._resolve_dependency_conflict(conflict)

        return self._resolve_by_severity(conflict, default_strategy)

    def _resolve_overlap_conflict(
        self,
        conflict: FixConflict,
    ) -> ConflictResolution:
        """Resolve an overlap conflict by ordering fixes by line number.

        Args:
            conflict: The overlap conflict

        Returns:
            ConflictResolution with ordered fixes
        """
        fixes = sorted(
            [conflict.fix_a, conflict.fix_b],
            key=lambda f: f.line_start,
        )

        if conflict.fix_a.line_start < conflict.fix_b.line_start:
            strategy = ResolutionStrategy.APPLY_A_FIRST
            explanation = (
                f"Applying {conflict.fix_a.rule_id} first as it appears "
                f"earlier in the file"
            )
        else:
            strategy = ResolutionStrategy.APPLY_B_FIRST
            explanation = (
                f"Applying {conflict.fix_b.rule_id} first as it appears "
                f"earlier in the file"
            )

        return ConflictResolution(
            conflict=conflict,
            strategy=strategy,
            resolved_fixes=fixes,
            explanation=explanation,
        )

    def _resolve_dependency_conflict(
        self,
        conflict: FixConflict,
    ) -> ConflictResolution:
        """Resolve a dependency conflict.

        Args:
            conflict: The dependency conflict

        Returns:
            ConflictResolution with dependency-ordered fixes
        """
        return ConflictResolution(
            conflict=conflict,
            strategy=ResolutionStrategy.DEPENDENCY_ORDER,
            resolved_fixes=[conflict.fix_a, conflict.fix_b],
            explanation="Dependency-ordered: definitions before usages",
        )

    def _resolve_by_severity(
        self,
        conflict: FixConflict,
        default_strategy: ResolutionStrategy,
    ) -> ConflictResolution:
        """Resolve conflict based on severity.

        Args:
            conflict: The conflict to resolve
            default_strategy: Default strategy

        Returns:
            ConflictResolution
        """
        if conflict.fix_a.severity.value == "error":
            return ConflictResolution(
                conflict=conflict,
                strategy=ResolutionStrategy.APPLY_A_FIRST,
                resolved_fixes=[conflict.fix_a, conflict.fix_b],
                explanation="Applied higher-severity fix first",
            )

        if conflict.fix_b.severity.value == "error":
            return ConflictResolution(
                conflict=conflict,
                strategy=ResolutionStrategy.APPLY_B_FIRST,
                resolved_fixes=[conflict.fix_b, conflict.fix_a],
                explanation="Applied higher-severity fix first",
            )

        return ConflictResolution(
            conflict=conflict,
            strategy=default_strategy,
            resolved_fixes=[conflict.fix_a, conflict.fix_b],
            explanation=f"Applied default strategy: {default_strategy.value}",
        )

    def get_safe_order(self, fixes: list[Fix]) -> list[Fix]:
        """Return fixes in safe application order.

        This method resolves all conflicts and returns a list of fixes
        ordered for safe application.

        Args:
            fixes: List of fixes to order

        Returns:
            List of fixes in safe application order
        """
        conflicts = self.detect_conflicts(fixes)

        if not conflicts:
            return self._order_by_file_and_line(fixes)

        resolutions = self.resolve_conflicts(conflicts)

        ordered_fixes: list[Fix] = []
        seen: set[str] = set()

        for resolution in sorted(resolutions, key=lambda r: r.conflict.severity):
            for fix in resolution.resolved_fixes:
                if fix.id not in seen:
                    ordered_fixes.append(fix)
                    seen.add(fix.id)

        for fix in fixes:
            if fix.id not in seen:
                ordered_fixes.append(fix)
                seen.add(fix.id)

        return ordered_fixes

    def _order_by_file_and_line(self, fixes: list[Fix]) -> list[Fix]:
        """Order fixes by file path and line number.

        Args:
            fixes: List of fixes to order

        Returns:
            Ordered list of fixes
        """
        return sorted(
            fixes,
            key=lambda f: (f.file_path, f.line_start),
        )

    def generate_report(self, fixes: list[Fix]) -> ConflictReport:
        """Generate a full conflict report for fixes.

        Args:
            fixes: List of fixes to analyze

        Returns:
            ConflictReport with all findings
        """
        conflicts = self.detect_conflicts(fixes)
        resolutions = self.resolve_conflicts(conflicts)
        safe_order = self.get_safe_order(fixes)

        return ConflictReport(
            conflicts=conflicts,
            resolutions=resolutions,
            safe_order=safe_order,
            has_unresolved=len(conflicts) > 0,
        )


def apply_with_conflict_resolution(
    fixes: list[Fix],
    apply_tool,
    resolve_conflicts: bool = True,
) -> FixBatch:
    """Apply fixes with automatic conflict resolution.

    Args:
        fixes: List of fixes to apply
        apply_tool: ApplyFixTool instance
        resolve_conflicts: Whether to detect and resolve conflicts

    Returns:
        FixBatch with results
    """
    if resolve_conflicts:
        resolver = ConflictResolver()
        ordered_fixes = resolver.get_safe_order(fixes)
        return apply_tool.apply_batch(ordered_fixes)

    return apply_tool.apply_batch(fixes)
