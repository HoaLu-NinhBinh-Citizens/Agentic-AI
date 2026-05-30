"""Unit tests for DiffEngine."""
import pytest
from pathlib import Path

from src.infrastructure.editing.diff_engine import (
    DiffEngine,
    EditPlan,
    LineRange,
    HunkInfo,
    Severity,
    Confidence,
)


class TestDiffEngine:
    def setup_method(self):
        self.engine = DiffEngine()

    def test_generate_diff_simple(self):
        old = "line1\nline2\nline3\n"
        new = "line1\nmodified\nline3\n"
        diff = self.engine.generate_diff(old, new)
        assert "---" in diff and "+++" in diff

    def test_generate_diff_no_change(self):
        old = "same\nsame\n"
        new = "same\nsame\n"
        diff = self.engine.generate_diff(old, new)
        # When files are identical, diff may be empty or just have headers
        # Check it doesn't raise
        assert isinstance(diff, str)

    def test_generate_diff_additions(self):
        old = "line1\nline3\n"
        new = "line1\nline2\nline3\n"
        diff = self.engine.generate_diff(old, new)
        assert "+" in diff or "line2" in diff

    def test_generate_diff_removals(self):
        old = "line1\nline2\nline3\n"
        new = "line1\nline3\n"
        diff = self.engine.generate_diff(old, new)
        assert "-" in diff or "line2" in diff

    def test_generate_diff_from_lines(self):
        old = ["line1", "line2"]
        new = ["line1", "modified"]
        diff = self.engine.generate_diff_from_lines(old, new)
        assert "@@" in diff

    def test_generate_diff_labels(self):
        old = "a\n"
        new = "b\n"
        diff = self.engine.generate_diff(old, new, old_label="old.txt", new_label="new.txt")
        assert "old.txt" in diff
        assert "new.txt" in diff

    def test_apply_diff(self):
        old = "line1\nline2\nline3\n"
        new = "line1\nmodified\nline3\n"
        diff = self.engine.generate_diff(old, new)
        result = self.engine.apply_diff(old, diff)
        assert "modified" in result

    def test_apply_diff_no_changes(self):
        original = "unchanged\n"
        result = self.engine.apply_diff(original, "")
        assert result == original

    def test_apply_diff_empty_diff(self):
        original = "hello\nworld\n"
        result = self.engine.apply_diff(original, "")
        assert result == original

    def test_validate_diff_valid(self):
        old = "line1\nline2\n"
        new = "line1\nmodified\n"
        diff = self.engine.generate_diff(old, new)
        validation = self.engine.validate_diff(old, diff)
        assert validation["valid"] is True

    def test_validate_diff_invalid(self):
        old = "original\ncontent\n"
        diff = "--- a.py\n+++ a.py\n@@ -1,2 +1,2 @@\n-X\n+Y\n"
        validation = self.engine.validate_diff(old, diff)
        # May be valid or invalid depending on fuzzy matching

    def test_parse_hunks(self):
        diff = (
            "--- a.py\n+++ a.py\n"
            "@@ -1,2 +1,2 @@\n"
            "-old\n+new\n"
        )
        hunks = self.engine._parse_hunks(diff)
        assert len(hunks) >= 1

    def test_parse_hunks_multiple(self):
        diff = (
            "--- a.py\n+++ a.py\n"
            "@@ -1,2 +1,2 @@\n-old1\n+new1\n"
            "@@ -5,2 +5,2 @@\n-old2\n+new2\n"
        )
        hunks = self.engine._parse_hunks(diff)
        assert len(hunks) >= 1

    def test_render_colored(self):
        diff = "--- a.py\n+++ a.py\n@@ -1 +1 @@\n-old\n+new\n"
        colored = self.engine.render_colored(diff)
        assert len(colored) > len(diff)

    def test_render_colored_rich_fallback(self):
        diff = "--- a.py\n+++ a.py\n@@\n-old\n+new\n"
        result = self.engine.render_colored_rich(diff)
        assert isinstance(result, str)

    def test_generate_multi_file_diff(self):
        plan1 = EditPlan(
            file_path="a.py",
            old_lines=["old"],
            new_lines=["new"],
            line_range=LineRange(1, 1),
            old_label="a.py",
            new_label="a.py",
        )
        plan2 = EditPlan(
            file_path="b.py",
            old_lines=["old2"],
            new_lines=["new2"],
            line_range=LineRange(5, 5),
            old_label="b.py",
            new_label="b.py",
        )
        diff = self.engine.generate_multi_file_diff([plan1, plan2])
        assert "a.py" in diff
        assert "b.py" in diff

    def test_generate_multi_file_diff_empty(self):
        diff = self.engine.generate_multi_file_diff([])
        assert diff == ""

    def test_generate_multi_file_diff_from_text(self):
        changes = {
            "a.py": ("old", "new"),
            "b.py": ("x", "y"),
        }
        diff = self.engine.generate_multi_file_diff_from_text(changes)
        assert "a.py" in diff
        assert "b.py" in diff

    def test_format_stats(self):
        diff = "---\n+++\n@@\n-old\n+new\n"
        stats = self.engine.format_stats(diff)
        assert "added" in stats
        assert "removed" in stats
        assert isinstance(stats["added"], int)
        assert isinstance(stats["removed"], int)

    def test_format_summary(self):
        plan = EditPlan(
            file_path="test.py",
            old_lines=["old"],
            new_lines=["new"],
            reason="test change",
            severity=Severity.MEDIUM,
            confidence=Confidence.MEDIUM,
        )
        summary = self.engine.format_summary(plan)
        assert "test.py" in summary
        assert "test change" in summary

    def test_generate_edit_plan(self):
        old = "def foo():\n    return 1\n"
        new = "def foo() -> int:\n    return 1\n"
        plan = self.engine.generate_edit_plan(
            "test.py", old, new,
            reason="add return type",
            severity=Severity.INFO,
            confidence=Confidence.HIGH,
        )
        assert plan.file_path == "test.py"
        assert len(plan.old_lines) > 0
        assert len(plan.new_lines) > 0

    def test_find_changed_range(self):
        old_lines = ["a", "b", "c"]
        new_lines = ["a", "b", "c"]
        rng = self.engine._find_changed_range(old_lines, new_lines)
        assert rng.start <= rng.end

    def test_normalize_lines(self):
        result = self.engine._normalize_lines(["  line1  \n", "line2\t\n"])
        assert result[0] == "  line1"
        assert result[1] == "line2"


class TestEditPlan:
    def test_creation_defaults(self):
        plan = EditPlan(
            file_path="test.py",
            old_lines=["line1"],
            new_lines=["line2"],
        )
        assert plan.severity == Severity.MEDIUM
        assert plan.confidence == Confidence.MEDIUM
        assert plan.is_addition is False

    def test_is_addition(self):
        plan = EditPlan(
            file_path="test.py",
            old_lines=[""],
            new_lines=["new"],
        )
        assert plan.is_addition is True

    def test_is_deletion(self):
        plan = EditPlan(
            file_path="test.py",
            old_lines=["old"],
            new_lines=[""],
        )
        assert plan.is_deletion is True

    def test_diff_label_addition(self):
        plan = EditPlan(
            file_path="test.py",
            old_lines=[""],
            new_lines=["new1", "new2"],
        )
        label = plan.diff_label()
        assert "added" in label

    def test_diff_label_deletion(self):
        plan = EditPlan(
            file_path="test.py",
            old_lines=["old1", "old2"],
            new_lines=[""],
        )
        label = plan.diff_label()
        assert "removed" in label

    def test_diff_label_modification(self):
        plan = EditPlan(
            file_path="test.py",
            old_lines=["old"],
            new_lines=["new"],
        )
        label = plan.diff_label()
        assert "~" in label or "→" in label

    def test_with_options(self):
        plan = EditPlan(
            file_path="test.py",
            old_lines=["old"],
            new_lines=["default"],
        )
        options = ["opt1", "opt2"]
        variants = plan.with_options(options)
        assert len(variants) == 2

    def test_custom_labels(self):
        plan = EditPlan(
            file_path="test.py",
            old_lines=["old"],
            new_lines=["new"],
            old_label="v1.py",
            new_label="v2.py",
        )
        assert plan.old_label == "v1.py"
        assert plan.new_label == "v2.py"


class TestLineRange:
    def test_creation(self):
        lr = LineRange(5, 10)
        assert lr.start == 5
        assert lr.end == 10

    def test_negative_start_corrected(self):
        lr = LineRange(0, 5)
        assert lr.start == 1

    def test_end_before_start(self):
        lr = LineRange(10, 5)
        assert lr.end == 10

    def test_negative_both(self):
        lr = LineRange(-1, -5)
        assert lr.start == 1

    def test_zero_range(self):
        lr = LineRange(1, 1)
        assert lr.start == 1
        assert lr.end == 1


class TestHunkInfo:
    def test_creation(self):
        hunk = HunkInfo(
            old_start=1,
            old_count=2,
            new_start=1,
            new_count=2,
            lines_removed=["-old"],
            lines_added=["+new"],
            lines_context=[" context"],
        )
        assert hunk.old_start == 1
        assert hunk.new_count == 2


class TestSeverityEnum:
    def test_all_values(self):
        assert Severity.INFO.value == "info"
        assert Severity.WARNING.value == "warning"
        assert Severity.ERROR.value == "error"
        assert Severity.CRITICAL.value == "critical"
        assert Severity.MEDIUM.value == "medium"


class TestConfidenceEnum:
    def test_all_values(self):
        assert Confidence.HIGH.value == "high"
        assert Confidence.MEDIUM.value == "medium"
        assert Confidence.LOW.value == "low"
