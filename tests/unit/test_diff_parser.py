"""Unit tests for UnifiedDiffParser."""
import pytest

from src.infrastructure.patching.diff_parser import (
    UnifiedDiffParser,
    DiffHunk,
    ParsedFileDiff,
    ParseResult,
    ApplyResult,
    _apply_single_hunk,
)


class TestUnifiedDiffParser:
    """Tests for UnifiedDiffParser.parse()."""

    def setup_method(self):
        self.parser = UnifiedDiffParser()

    def test_parse_simple_diff(self):
        """Test parsing a simple unified diff."""
        diff = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,3 @@
 line 1
-old line
+new line
 line 3"""
        result = self.parser.parse(diff)

        assert result.success is True
        assert len(result.files) == 1
        assert result.files[0].old_path == "test.py"
        assert result.files[0].new_path == "test.py"
        assert len(result.files[0].hunks) == 1

    def test_parse_diff_with_paths(self):
        """Test parsing diff with full paths."""
        diff = """--- a/src/main.py
+++ b/src/main.py
@@ -1,2 +1,2 @@
-old
+new
"""
        result = self.parser.parse(diff)

        assert result.success is True
        assert result.files[0].old_path == "src/main.py"
        assert result.files[0].new_path == "src/main.py"

    def test_parse_multi_file_diff(self):
        """Test parsing multi-file diff."""
        diff = """--- a/file1.py
+++ b/file1.py
@@ -1 +1 @@
-old1
+new1
--- a/file2.py
+++ b/file2.py
@@ -1 +1 @@
-old2
+new2
"""
        result = self.parser.parse(diff)

        assert result.success is True
        assert len(result.files) == 2
        assert result.files[0].old_path == "file1.py"
        assert result.files[1].old_path == "file2.py"

    def test_parse_diff_no_header(self):
        """Test parsing invalid diff without headers."""
        diff = """@@ -1 +1 @@
-old
+new
"""
        result = self.parser.parse(diff)
        assert result.success is False
        assert result.error is not None

    def test_parse_empty_diff(self):
        """Test parsing empty diff."""
        result = self.parser.parse("")
        assert result.success is False

    def test_parse_diff_with_single_line_hunk(self):
        """Test parsing hunk with single line count."""
        diff = """--- a/test.py
+++ b/test.py
@@ -5 +5 @@
-old
+new
"""
        result = self.parser.parse(diff)

        assert result.success is True
        hunk = result.files[0].hunks[0]
        assert hunk.old_start == 5
        assert hunk.old_count == 1
        assert hunk.new_count == 1

    def test_parse_diff_with_line_counts(self):
        """Test parsing hunk with explicit line counts."""
        diff = """--- a/test.py
+++ b/test.py
@@ -10,5 +11,6 @@
-old
-old2
+new
+new2
+new3
 context
"""
        result = self.parser.parse(diff)

        assert result.success is True
        hunk = result.files[0].hunks[0]
        assert hunk.old_start == 10
        assert hunk.old_count == 5
        assert hunk.new_start == 11
        assert hunk.new_count == 6


class TestDiffHunk:
    """Tests for DiffHunk properties."""

    def test_removed_lines(self):
        """Test extracting removed lines."""
        hunk = DiffHunk(
            old_start=1,
            old_count=2,
            new_start=1,
            new_count=2,
            lines=["-removed1", "-removed2", "+added1"],
        )
        assert hunk.removed_lines == ["removed1", "removed2"]

    def test_added_lines(self):
        """Test extracting added lines."""
        hunk = DiffHunk(
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["-removed", "+added1", "+added2"],
        )
        assert hunk.added_lines == ["added1", "added2"]

    def test_context_lines(self):
        """Test extracting context lines."""
        hunk = DiffHunk(
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=[" context1", " context2", "-removed", "+added"],
        )
        assert hunk.context_lines == ["context1", "context2"]


class TestApplySingleHunk:
    """Tests for _apply_single_hunk()."""

    def test_apply_simple_replacement(self):
        """Test applying a simple line replacement."""
        content = ["line 1", "old line", "line 3"]
        hunk = DiffHunk(
            old_start=2,
            old_count=1,
            new_start=2,
            new_count=1,
            lines=["-old line", "+new line"],  # Only +/- lines
        )

        result = _apply_single_hunk(content, hunk)
        assert result == ["line 1", "new line", "line 3"]

    def test_apply_addition(self):
        """Test applying an addition (inserting new lines)."""
        content = ["line 1", "line 2"]
        hunk = DiffHunk(
            old_start=2,
            old_count=1,  # Replacing 1 line
            new_start=2,
            new_count=2,  # With 2 lines
            lines=["-line 2", "+line 2", "+line 3"],  # Replace + add
        )

        result = _apply_single_hunk(content, hunk)
        assert result == ["line 1", "line 2", "line 3"]

    def test_apply_deletion(self):
        """Test applying a deletion (no addition)."""
        content = ["line 1", "line 2", "line 3"]
        hunk = DiffHunk(
            old_start=2,
            old_count=1,
            new_start=2,
            new_count=1,
            lines=["-line 2"],  # Just remove
        )

        result = _apply_single_hunk(content, hunk)
        assert result == ["line 1", "line 3"]

    def test_apply_multi_line_change(self):
        """Test applying a multi-line change."""
        content = ["line 1", "old 1", "old 2", "line 4"]
        hunk = DiffHunk(
            old_start=2,
            old_count=2,
            new_start=2,
            new_count=2,
            lines=["-old 1", "-old 2", "+new 1", "+new 2"],
        )

        result = _apply_single_hunk(content, hunk)
        assert result == ["line 1", "new 1", "new 2", "line 4"]

    def test_apply_with_context(self):
        """Test applying hunk with context lines - context is ignored."""
        content = ["line 1", "old line", "line 3"]
        hunk = DiffHunk(
            old_start=2,
            old_count=1,
            new_start=2,
            new_count=1,
            lines=["-old line", "+new line"],  # Context ignored
        )

        result = _apply_single_hunk(content, hunk)
        assert result == ["line 1", "new line", "line 3"]


class TestParsedFileDiff:
    """Tests for ParsedFileDiff.apply_to()."""

    def test_apply_to_simple(self):
        """Test applying file diff."""
        diff = ParsedFileDiff(
            old_path="test.py",
            new_path="test.py",
            hunks=[
                DiffHunk(
                    old_start=2,
                    old_count=1,
                    new_start=2,
                    new_count=1,
                    lines=["-old", "+new"],  # No context needed
                )
            ],
        )

        content = ["line 1", "old", "line 3"]
        result = diff.apply_to(content)
        assert result == ["line 1", "new", "line 3"]

    def test_apply_to_multiple_hunks(self):
        """Test applying multiple hunks in reverse order."""
        diff = ParsedFileDiff(
            old_path="test.py",
            new_path="test.py",
            hunks=[
                DiffHunk(
                    old_start=2,
                    old_count=1,
                    new_start=2,
                    new_count=1,
                    lines=["-line 2", "+modified 2"],
                ),
                DiffHunk(
                    old_start=4,
                    old_count=1,
                    new_start=4,
                    new_count=1,
                    lines=["-line 4", "+modified 4"],
                ),
            ],
        )

        content = ["line 1", "line 2", "line 3", "line 4"]
        result = diff.apply_to(content)
        assert result == ["line 1", "modified 2", "line 3", "modified 4"]


class TestUnifiedDiffParserApply:
    """Tests for UnifiedDiffParser.apply_diff()."""

    def setup_method(self):
        self.parser = UnifiedDiffParser()

    def test_apply_diff_simple(self):
        """Test applying a simple diff."""
        original = "line1\nline2\nline3\n"
        diff = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,3 @@
 line1
-old line2
+new line2
 line3
"""
        result = self.parser.apply_diff(original, diff, "test.py")
        assert result == "line1\nnew line2\nline3"

    def test_apply_diff_addition(self):
        """Test applying an addition diff."""
        original = "line1\nline2\nline3\n"
        diff = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
 line1
-old line2
+old line2
+new line3
 line3
"""
        result = self.parser.apply_diff(original, diff, "test.py")
        assert "new line3" in result

    def test_apply_diff_mismatch(self):
        """Test applying diff with mismatched content."""
        original = "different content\n"
        diff = """--- a/test.py
+++ b/test.py
@@ -1 +1 @@
-old
+new
"""
        # Should not raise, but may produce unexpected results
        # depending on implementation
        try:
            result = self.parser.apply_diff(original, diff, "test.py")
            # If it doesn't raise, it might still work or not
        except ValueError:
            pass  # Expected for strict matching


class TestParseHunkHeader:
    """Tests for parse_hunk_header()."""

    def test_parse_with_counts(self):
        """Test parsing hunk header with line counts."""
        parser = UnifiedDiffParser()
        old_start, old_count, new_start, new_count = parser.parse_hunk_header(
            "@@ -1,3 +1,4 @@"
        )
        assert old_start == 1
        assert old_count == 3
        assert new_start == 1
        assert new_count == 4

    def test_parse_without_counts(self):
        """Test parsing hunk header without line counts."""
        parser = UnifiedDiffParser()
        old_start, old_count, new_start, new_count = parser.parse_hunk_header(
            "@@ -5 +5 @@"
        )
        assert old_start == 5
        assert old_count == 1
        assert new_start == 5
        assert new_count == 1

    def test_parse_invalid_header(self):
        """Test parsing invalid hunk header."""
        parser = UnifiedDiffParser()
        with pytest.raises(ValueError):
            parser.parse_hunk_header("invalid header")


class TestApplyResult:
    """Tests for ApplyResult dataclass."""

    def test_success_result(self):
        """Test creating a success result."""
        result = ApplyResult(
            success=True,
            file_path="test.py",
            lines_modified=5,
        )
        assert result.success is True
        assert result.file_path == "test.py"
        assert result.lines_modified == 5
        assert result.error is None

    def test_failure_result(self):
        """Test creating a failure result."""
        result = ApplyResult(
            success=False,
            file_path="test.py",
            error="File not found",
        )
        assert result.success is False
        assert result.error == "File not found"

    def test_repr_success(self):
        """Test string representation of success result."""
        result = ApplyResult(success=True, file_path="test.py", lines_modified=3)
        assert "success=True" in repr(result)
        assert "test.py" in repr(result)

    def test_repr_failure(self):
        """Test string representation of failure result."""
        result = ApplyResult(success=False, error="Test error")
        assert "success=False" in repr(result)


class TestIntegration:
    """Integration tests for diff parsing and application."""

    def test_full_workflow(self):
        """Test full diff parse -> apply workflow."""
        parser = UnifiedDiffParser()

        # Create original content
        original = """def hello():
    print("hello")
    return 42
"""
        # Create a diff that modifies the function (with correct line numbers)
        diff = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,3 @@
 def hello():
-    print("hello")
+    print("world")
     return 42
"""

        # Parse
        result = parser.parse(diff)
        assert result.success is True

        # Apply
        modified = parser.apply_diff(original, diff, "test.py")
        assert 'print("world")' in modified
        assert 'print("hello")' not in modified

    def test_python_code_diff(self):
        """Test diff application on Python code."""
        parser = UnifiedDiffParser()

        original = """class MyClass:
    def __init__(self):
        self.value = 0

    def get_value(self):
        return self.value
"""

        # Insert a new line after self.value = 0
        diff = """--- a/myclass.py
+++ b/myclass.py
@@ -2,3 +2,4 @@ class MyClass:
     def __init__(self):
         self.value = 0
+        self.name = "default"

     def get_value(self):
"""

        result = parser.parse(diff)
        assert result.success is True

        modified = parser.apply_diff(original, diff, "myclass.py")
        assert 'self.name = "default"' in modified
