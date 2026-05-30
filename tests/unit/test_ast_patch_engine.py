"""Unit tests for AST Patch Engine."""

import pytest
from pathlib import Path

from src.infrastructure.patching.ast_patch_engine import (
    ASTPatchEngine,
    ASTNodeInfo,
    Patch as ASTPatch,
    PatchResult,
    create_engine,
)


class TestASTPatchEngine:
    """Tests for ASTPatchEngine."""

    def setup_method(self):
        self.engine = create_engine()

    def test_create_engine(self):
        """Test engine creation via factory."""
        engine = create_engine()
        assert engine is not None
        assert isinstance(engine, ASTPatchEngine)

    def test_patch_dataclass(self):
        """Test Patch dataclass creation."""
        patch = ASTPatch(
            file_path=Path("test.py"),
            start_line=5,
            end_line=10,
            old_code="old code",
            new_code="new code",
        )
        assert patch.start_line == 5
        assert patch.end_line == 10
        assert patch.old_code == "old code"
        assert patch.new_code == "new code"

    def test_patch_to_diff(self):
        """Test patch diff generation."""
        patch = ASTPatch(
            file_path=Path("test.py"),
            start_line=1,
            end_line=1,
            old_code="x = 1",
            new_code="x = 2",
        )
        diff = patch.to_diff()
        assert "--- test.py" in diff
        assert "+++ test.py" in diff
        assert "- x = 1" in diff
        assert "+ x = 2" in diff

    def test_patch_result_dataclass(self):
        """Test PatchResult dataclass."""
        result = PatchResult(
            success=True,
            patched_content="new content",
            validation_passed=True,
        )
        assert result.success is True
        assert result.validation_passed is True
        assert result.patched_content == "new content"

    def test_patch_result_with_error(self):
        """Test PatchResult with error."""
        result = PatchResult(
            success=False,
            patched_content="original",
            validation_passed=False,
            error="Syntax error",
        )
        assert result.success is False
        assert result.error == "Syntax error"

    def test_ast_node_info(self):
        """Test ASTNodeInfo dataclass."""
        node_info = ASTNodeInfo(
            type="function_definition",
            start_byte=0,
            end_byte=100,
            start_point=(0, 0),
            end_point=(5, 0),
            text="def foo(): pass",
        )
        assert node_info.type == "function_definition"
        assert node_info.text == "def foo(): pass"


class TestPatchApplication:
    """Tests for patch application."""

    def setup_method(self):
        self.engine = create_engine()

    def test_apply_patch_simple(self):
        """Test applying a simple patch."""
        content = "line1\nline2\nline3\nline4\n"
        patch = ASTPatch(
            file_path=Path("test.py"),
            start_line=2,
            end_line=2,
            old_code="line2",
            new_code="modified_line2",
        )
        result = self.engine.apply_patch(content, patch)
        assert "line1" in result
        assert "modified_line2" in result
        assert "line3" in result
        assert "line4" in result

    def test_apply_patch_preserve_indentation(self):
        """Test that indentation is preserved."""
        content = """def foo():
    if True:
        x = 1  # comment
    return x
"""
        patch = ASTPatch(
            file_path=Path("test.py"),
            start_line=3,
            end_line=3,
            old_code="        x = 1  # comment",
            new_code="        x = 2  # updated",
        )
        result = self.engine.apply_patch(content, patch)
        assert "x = 2  # updated" in result
        assert "    if True:" in result

    def test_apply_patch_multiline(self):
        """Test applying a multi-line patch."""
        content = """def foo():
    a = 1
    b = 2
    return a + b
"""
        patch = ASTPatch(
            file_path=Path("test.py"),
            start_line=2,
            end_line=3,
            old_code="    a = 1\n    b = 2",
            new_code="    a = 10\n    b = 20\n    c = 30",
        )
        result = self.engine.apply_patch(content, patch)
        assert "a = 10" in result
        assert "b = 20" in result
        assert "c = 30" in result

    def test_apply_patch_empty_replacement(self):
        """Test replacing with empty string (deletion)."""
        content = "keep\nremove\nkeep\n"
        patch = ASTPatch(
            file_path=Path("test.py"),
            start_line=2,
            end_line=2,
            old_code="remove",
            new_code="",
        )
        result = self.engine.apply_patch(content, patch)
        assert "keep" in result
        assert "remove" not in result

    def test_apply_patch_addition(self):
        """Test adding new lines (empty old_code)."""
        content = "line1\nline3\n"
        patch = ASTPatch(
            file_path=Path("test.py"),
            start_line=2,
            end_line=1,
            old_code="",
            new_code="line2",
        )
        result = self.engine.apply_patch(content, patch)
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result


class TestSyntaxValidation:
    """Tests for syntax validation."""

    def setup_method(self):
        self.engine = create_engine()

    def test_validate_syntax_python_valid(self):
        """Test validating valid Python code."""
        content = "x = 1\ny = 2\nprint(x + y)\n"
        result = self.engine.validate_syntax(content, "python")
        assert result is True

    def test_validate_syntax_python_invalid(self):
        """Test validating invalid Python code."""
        content = "def foo(\n"  # Missing closing parenthesis
        result = self.engine.validate_syntax(content, "python")
        assert result is False

    def test_validate_syntax_unclosed_bracket(self):
        """Test detecting unclosed brackets."""
        content = "data = {\n    'key': 'value',\n"  # Missing closing }
        result = self.engine.validate_syntax(content, "python")
        assert result is False


class TestGeneratePatch:
    """Tests for patch generation."""

    def setup_method(self):
        self.engine = create_engine()

    def test_generate_patch_from_byte_positions(self):
        """Test generating patch from byte positions."""
        content = "line1\nline2\nline3\n"
        # line1\n = 6 bytes, line2 starts at byte 6
        patch = self.engine.generate_patch(
            file_path=Path("test.py"),
            content=content,
            node_start=(6, 0),  # Start of "line2" (0-indexed)
            node_end=(11, 5),   # End of "line2" - byte 11, col 5 (inclusive)
            new_code="modified_line2",
        )
        assert patch.start_line == 2
        assert patch.end_line == 2
        assert "line2" in patch.old_code

    def test_generate_patch_multiline(self):
        """Test generating patch for multi-line selection."""
        content = "line1\nline2\nline3\n"
        # line1\n = 6, line2 = 5 chars, line3 = 5 chars
        patch = self.engine.generate_patch(
            file_path=Path("test.py"),
            content=content,
            node_start=(6, 0),  # Start of line2
            node_end=(16, 0),   # Start of next line (after line3)
            new_code="new content\nwith multiple\nlines",
        )
        assert patch.start_line == 2
        assert patch.end_line == 3

    def test_generate_patch_to_diff(self):
        """Test that generated patch has proper diff."""
        content = "line1\nline2\nline3\n"
        patch = self.engine.generate_patch(
            file_path=Path("test.py"),
            content=content,
            node_start=(6, 0),
            node_end=(11, 5),
            new_code="modified_line2",
        )
        diff = patch.to_diff()
        assert "--- test.py" in diff
        assert "+++ test.py" in diff


class TestApplyAndValidate:
    """Tests for combined apply and validate."""

    def setup_method(self):
        self.engine = create_engine()

    def test_apply_and_validate_success(self):
        """Test apply and validate with valid result."""
        content = "x = 1\ny = 2\n"
        patch = ASTPatch(
            file_path=Path("test.py"),
            start_line=2,
            end_line=2,
            old_code="y = 2",
            new_code="y = 3",
        )
        result = self.engine.apply_and_validate(content, patch, "python")
        assert result.success is True
        assert "y = 3" in result.patched_content
        assert result.validation_passed is True

    def test_apply_and_validate_invalidates_syntax(self):
        """Test that invalid syntax is detected."""
        content = "x = 1\n"
        patch = ASTPatch(
            file_path=Path("test.py"),
            start_line=2,
            end_line=2,
            old_code="",
            new_code="def foo(\n",  # Invalid syntax
        )
        result = self.engine.apply_and_validate(content, patch, "python")
        assert result.success is True  # Patch applied
        assert result.validation_passed is False  # But syntax is broken

    def test_apply_and_validate_counts_modified_lines(self):
        """Test that modified line count is tracked."""
        content = "a\nb\nc\nd\n"
        patch = ASTPatch(
            file_path=Path("test.py"),
            start_line=2,
            end_line=3,
            old_code="b\nc",
            new_code="x",
        )
        result = self.engine.apply_and_validate(content, patch, "python")
        assert result.success is True
        assert result.modified_lines == 2  # max(2, 1) = 2


class TestSafeApply:
    """Tests for safe patch application."""

    def setup_method(self):
        self.engine = create_engine()

    def test_apply_safely_with_validation(self):
        """Test safe apply requires valid syntax."""
        content = "x = 1\n"
        patch = ASTPatch(
            file_path=Path("test.py"),
            start_line=2,
            end_line=2,
            old_code="",
            new_code="def foo(\n",  # Invalid
        )
        success, result_content = self.engine.apply_safely(
            content, patch, "python", require_valid_syntax=True
        )
        assert success is False
        assert result_content == content  # Unchanged

    def test_apply_safely_without_validation(self):
        """Test safe apply without syntax check."""
        content = "x = 1\n"
        patch = ASTPatch(
            file_path=Path("test.py"),
            start_line=2,
            end_line=2,
            old_code="",
            new_code="def foo(\n",  # Invalid
        )
        success, result_content = self.engine.apply_safely(
            content, patch, "python", require_valid_syntax=False
        )
        assert success is True  # Applied even with invalid syntax
        assert "def foo(" in result_content


class TestExtractWithContext:
    """Tests for context extraction."""

    def setup_method(self):
        self.engine = create_engine()

    def test_extract_with_context_basic(self):
        """Test basic context extraction."""
        content = "l1\nl2\nl3\nl4\nl5\nl6\nl7\nl8\nl9\n"
        before, target, after = self.engine.extract_with_context(
            content, start_line=4, end_line=6, context_lines=2
        )
        # start_line=4, end_line=6, context=2
        # target = lines 4-6 (l4, l5, l6)
        # before = lines 2-3 (l2, l3) - 2 lines before
        # after = lines 7-8 (l7, l8) - 2 lines after
        assert "l2" in before
        assert "l3" in before
        assert "l4" in target
        assert "l5" in target
        assert "l6" in target
        assert "l7" in after
        assert "l8" in after

    def test_extract_with_context_edge_cases(self):
        """Test context extraction at file boundaries."""
        content = "first\nsecond\nthird\n"
        before, target, after = self.engine.extract_with_context(
            content, start_line=1, end_line=1, context_lines=2
        )
        assert before == ""  # No lines before first
        assert "first" in target
        # third is at line 3, context end = 1 + 2 = 3, so l3 should be included
        assert "third" in after


class TestDiffGeneration:
    """Tests for diff generation."""

    def setup_method(self):
        self.engine = create_engine()

    def test_generate_diff(self):
        """Test unified diff generation."""
        old = "line1\nline2\nline3\n"
        new = "line1\nmodified\nline3\n"
        diff = self.engine.generate_diff(old, new)
        assert "---" in diff
        assert "+++" in diff
        assert "-line2" in diff
        assert "+modified" in diff

    def test_generate_diff_no_changes(self):
        """Test diff with no changes."""
        content = "same\nsame\n"
        diff = self.engine.generate_diff(content, content)
        assert isinstance(diff, str)


class TestFindNodes:
    """Tests for AST node finding."""

    def setup_method(self):
        self.engine = create_engine()

    def test_find_node_at_position(self):
        """Test finding node at specific position."""
        content = """
def foo():
    return 1
"""
        node_info = self.engine.find_node_at_position(
            content, line=2, column=0, language="python"
        )
        # Should find some node (function definition or statement)
        assert node_info is not None

    def test_find_nodes_by_type(self):
        """Test finding nodes by type."""
        content = """
def foo():
    pass

def bar():
    pass
"""
        nodes = self.engine.find_nodes_by_type(content, "function_definition", "python")
        # Should find 2 function definitions
        assert len(nodes) >= 1  # At least one function

    def test_find_nodes_no_match(self):
        """Test finding nodes with no matches."""
        content = "x = 1\n"
        nodes = self.engine.find_nodes_by_type(content, "class_definition", "python")
        assert len(nodes) == 0


class TestNodeRange:
    """Tests for node range utilities."""

    def setup_method(self):
        self.engine = create_engine()

    def test_get_node_range(self):
        """Test getting line range from node."""
        content = "line1\nline2\nline3\n"
        # "line1\n" = 6 bytes, "line2" = 5 bytes
        node = ASTNodeInfo(
            type="test",
            start_byte=6,   # Start of line2 (after \n)
            end_byte=11,    # End of line2 (5 bytes: l,i,n,e,2)
            start_point=(1, 0),
            end_point=(1, 5),
            text="line2",
        )
        start, end = self.engine.get_node_range(content, node)
        assert start == 2
        assert end == 2


class TestPatternSearch:
    """Tests for pattern search."""

    def setup_method(self):
        self.engine = create_engine()

    def test_find_similar_code_pattern(self):
        """Test finding code patterns."""
        content = "x = 1\ny = 2\nz = 3\n"
        results = self.engine.find_similar_code_pattern(
            content, "=", language="python"
        )
        # Should find multiple lines with assignment
        assert len(results) >= 3

    def test_find_similar_pattern_no_match(self):
        """Test pattern with no matches."""
        content = "x = 1\n"
        results = self.engine.find_similar_code_pattern(
            content, "nonexistent", language="python"
        )
        assert len(results) == 0


class TestPreserveFormatting:
    """Tests for formatting preservation."""

    def setup_method(self):
        self.engine = create_engine()

    def test_preserve_leading_whitespace(self):
        """Test that leading whitespace is preserved."""
        content = "class MyClass:\n    def method(self):\n        pass\n"
        patch = ASTPatch(
            file_path=Path("test.py"),
            start_line=3,
            end_line=3,
            old_code="        pass",
            new_code="        return None",
        )
        result = self.engine.apply_patch(content, patch)
        # Should preserve 8 spaces indentation
        assert "        return None" in result

    def test_preserve_trailing_whitespace(self):
        """Test that trailing content is preserved."""
        content = "line1\nline2   \nline3\n"
        patch = ASTPatch(
            file_path=Path("test.py"),
            start_line=2,
            end_line=2,
            old_code="line2   ",
            new_code="modified   ",
        )
        result = self.engine.apply_patch(content, patch)
        assert "modified   " in result

    def test_preserve_comments(self):
        """Test that comments are preserved when replacing adjacent code."""
        content = """def foo():
    x = 1  # inline comment
    return x
"""
        patch = ASTPatch(
            file_path=Path("test.py"),
            start_line=2,
            end_line=2,
            old_code="    x = 1  # inline comment",
            new_code="    x = 2  # updated comment",
        )
        result = self.engine.apply_patch(content, patch)
        assert "x = 2  # updated comment" in result


class TestRealWorldScenarios:
    """Tests for real-world patching scenarios."""

    def setup_method(self):
        self.engine = create_engine()

    def test_fix_function_return_type(self):
        """Test fixing a function return type annotation."""
        content = """def get_value():
    return 42
"""
        patch = ASTPatch(
            file_path=Path("test.py"),
            start_line=1,
            end_line=1,
            old_code="def get_value():",
            new_code="def get_value() -> int:",
        )
        result = self.engine.apply_patch(content, patch)
        assert "def get_value() -> int:" in result

    def test_replace_magic_number(self):
        """Test replacing a magic number with constant."""
        content = """TIMEOUT = 1000

def connect():
    return connect_with_timeout(timeout=500)
"""
        patch = ASTPatch(
            file_path=Path("test.py"),
            start_line=4,
            end_line=4,
            old_code="    return connect_with_timeout(timeout=500)",
            new_code="    return connect_with_timeout(timeout=TIMEOUT)",
        )
        result = self.engine.apply_patch(content, patch)
        assert "timeout=TIMEOUT" in result

    def test_add_import(self):
        """Test adding an import statement."""
        content = """def main():
    pass
"""
        patch = ASTPatch(
            file_path=Path("test.py"),
            start_line=1,
            end_line=0,
            old_code="",
            new_code="import sys\n",
        )
        result = self.engine.apply_patch(content, patch)
        assert "import sys" in result
        assert "def main():" in result
