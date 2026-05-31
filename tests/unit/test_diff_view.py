"""Tests for Diff View Component."""

import pytest
from pathlib import Path

from src.interfaces.tui.diff_view import (
    DiffViewRenderer,
    FixPreviewRenderer,
    DiffType,
    DiffLine,
    DiffHunk,
    FileDiff,
)


class TestDiffViewRenderer:
    """Test suite for DiffViewRenderer."""

    @pytest.fixture
    def renderer(self):
        """Create a DiffViewRenderer for testing."""
        return DiffViewRenderer(context_lines=3)

    def test_compute_diff_added_lines(self, renderer):
        """Test diff computation with added lines."""
        old = "line1\nline2\n"
        new = "line1\nline2\nline3\n"

        diff = renderer.compute_diff(old, new)

        assert diff.stats["added"] == 1
        assert diff.stats["removed"] == 0
        assert len(diff.hunks) >= 1

    def test_compute_diff_removed_lines(self, renderer):
        """Test diff computation with removed lines."""
        old = "line1\nline2\nline3\n"
        new = "line1\nline2\n"

        diff = renderer.compute_diff(old, new)

        assert diff.stats["added"] == 0
        assert diff.stats["removed"] == 1

    def test_compute_diff_modified_lines(self, renderer):
        """Test diff computation with modified lines."""
        old = "line1\noriginal\nline3\n"
        new = "line1\nmodified\nline3\n"

        diff = renderer.compute_diff(old, new)

        assert diff.stats["added"] == 1
        assert diff.stats["removed"] == 1

    def test_compute_diff_no_changes(self, renderer):
        """Test diff computation with no changes."""
        content = "line1\nline2\nline3\n"

        diff = renderer.compute_diff(content, content)

        assert diff.stats["added"] == 0
        assert diff.stats["removed"] == 0

    def test_compute_diff_with_paths(self, renderer):
        """Test diff computation with file paths."""
        old = "old content\n"
        new = "new content\n"

        diff = renderer.compute_diff(
            old, new,
            old_path="original.py",
            new_path="modified.py"
        )

        assert diff.old_path == "original.py"
        assert diff.new_path == "modified.py"

    def test_render_unified_output(self, renderer):
        """Test unified diff rendering."""
        old = "line1\nline2\nline3\n"
        new = "line1\nline2\nmodified\n"

        diff = renderer.compute_diff(old, new)
        lines = renderer.render_unified(diff)

        assert len(lines) > 0
        assert any("@@" in line for line in lines)

    def test_render_unified_max_lines(self, renderer):
        """Test unified diff respects max_lines."""
        old = "\n".join([f"line{i}" for i in range(200)])
        new = "\n".join([f"line{i}" for i in range(200)])

        diff = renderer.compute_diff(old, new)
        lines = renderer.render_unified(diff, max_lines=10)

        assert len(lines) <= 20  # Some buffer for context

    def test_render_stats(self, renderer):
        """Test statistics rendering."""
        old = "line1\nline2\nline3\n"
        new = "line1\nline2\nline3\nline4\n"

        diff = renderer.compute_diff(old, new)
        stats = renderer.render_stats(diff)

        # Stats contains colored output with +number
        assert "+" in stats
        assert "1" in stats

    def test_parse_hunk_header(self, renderer):
        """Test hunk header parsing."""
        header = "@@ -10,5 +10,6 @@ context"
        result = renderer._parse_hunk_header(header)

        assert result == (10, 5, 10, 6)

    def test_parse_hunk_header_single_line(self, renderer):
        """Test hunk header with single line count."""
        header = "@@ -10 +10 @@ context"
        result = renderer._parse_hunk_header(header)

        assert result == (10, 1, 10, 1)

    def test_parse_hunk_header_invalid(self, renderer):
        """Test hunk header parsing with invalid input."""
        result = renderer._parse_hunk_header("invalid header")
        assert result is None


class TestDiffLine:
    """Test DiffLine dataclass."""

    def test_diff_line_context(self):
        """Test context diff line."""
        line = DiffLine(
            line_type=DiffType.CONTEXT,
            content="unchanged line",
            old_line_num=5,
            new_line_num=5,
        )

        assert line.line_type == DiffType.CONTEXT
        assert line.content == "unchanged line"

    def test_diff_line_added(self):
        """Test added diff line."""
        line = DiffLine(
            line_type=DiffType.ADDED,
            content="new line",
            old_line_num=None,
            new_line_num=6,
        )

        assert line.line_type == DiffType.ADDED
        assert line.old_line_num is None

    def test_diff_line_removed(self):
        """Test removed diff line."""
        line = DiffLine(
            line_type=DiffType.REMOVED,
            content="removed line",
            old_line_num=5,
            new_line_num=None,
        )

        assert line.line_type == DiffType.REMOVED
        assert line.new_line_num is None


class TestDiffHunk:
    """Test DiffHunk dataclass."""

    def test_diff_hunk_creation(self):
        """Test DiffHunk instantiation."""
        lines = [
            DiffLine(DiffType.CONTEXT, "line", 1, 1),
            DiffLine(DiffType.ADDED, "added", None, 2),
        ]

        hunk = DiffHunk(
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=lines,
        )

        assert hunk.old_start == 1
        assert len(hunk.lines) == 2


class TestFileDiff:
    """Test FileDiff dataclass."""

    def test_file_diff_creation(self):
        """Test FileDiff instantiation."""
        diff = FileDiff(
            old_path="old.py",
            new_path="new.py",
            hunks=[],
            stats={"added": 2, "removed": 1, "hunks": 1},
        )

        assert diff.old_path == "old.py"
        assert diff.new_path == "new.py"
        assert diff.stats["added"] == 2


class TestFixPreviewRenderer:
    """Test suite for FixPreviewRenderer."""

    @pytest.fixture
    def fix_renderer(self):
        """Create a FixPreviewRenderer for testing."""
        return FixPreviewRenderer()

    def test_create_preview(self, fix_renderer):
        """Test fix preview creation."""
        original = "password = 'hardcoded'\n"
        fixed = "password = os.getenv('PASSWORD')\n"

        preview = fix_renderer.create_preview(
            original, fixed, Path("config.py")
        )

        assert "diff" in preview
        assert "stats" in preview
        assert preview["can_apply"] is True

    def test_create_preview_no_changes(self, fix_renderer):
        """Test fix preview with no changes."""
        content = "same content\n"

        preview = fix_renderer.create_preview(
            content, content, Path("file.py")
        )

        assert preview["can_apply"] is False

    def test_format_fix_summary(self, fix_renderer):
        """Test fix summary formatting."""
        preview = {
            "stats": {
                "added": 3,
                "removed": 1,
                "hunks": 2,
            }
        }

        summary = fix_renderer.format_fix_summary(preview)

        assert "2" in summary  # hunks
        assert "3" in summary  # added
        assert "1" in summary  # removed

    def test_preview_stats_calculation(self, fix_renderer):
        """Test that preview stats are calculated correctly."""
        original = "line1\nline2\nline3\n"
        fixed = "line1\nmodified\nline3\nline4\n"

        preview = fix_renderer.create_preview(original, fixed, Path("test.py"))

        stats = preview["stats"]
        assert stats["added"] >= 1
        assert stats["removed"] >= 1


class TestDiffType:
    """Test DiffType enum."""

    def test_diff_type_values(self):
        """Test DiffType enum values."""
        assert DiffType.CONTEXT.value == "context"
        assert DiffType.ADDED.value == "added"
        assert DiffType.REMOVED.value == "removed"
        assert DiffType.HEADER.value == "header"


class TestDiffRendering:
    """Integration tests for diff rendering."""

    @pytest.fixture
    def renderer(self):
        return DiffViewRenderer(context_lines=2)

    def test_complex_diff(self, renderer):
        """Test complex diff with multiple changes."""
        old = """def old_function():
    x = 1
    y = 2
    return x + y
"""

        new = """def new_function():
    x = 1
    y = 2
    z = 3
    return x + y + z
"""

        diff = renderer.compute_diff(old, new)

        # 3 added: z = 3, modified return, function name change
        assert diff.stats["added"] >= 2
        assert diff.stats["removed"] >= 1

        lines = renderer.render_unified(diff)
        assert len(lines) > 0

    def test_multiline_addition(self, renderer):
        """Test adding multiple lines."""
        old = "line1\n"
        new = "line1\nline2\nline3\nline4\n"

        diff = renderer.compute_diff(old, new)

        assert diff.stats["added"] == 3

    def test_multiline_removal(self, renderer):
        """Test removing multiple lines."""
        old = "line1\nline2\nline3\nline4\n"
        new = "line1\n"

        diff = renderer.compute_diff(old, new)

        assert diff.stats["removed"] == 3

    def test_whitespace_changes(self, renderer):
        """Test diff detects whitespace changes."""
        old = "text with spaces"
        new = "text  with  double  spaces"

        diff = renderer.compute_diff(old, new)

        assert diff.stats["added"] > 0 or diff.stats["removed"] > 0
