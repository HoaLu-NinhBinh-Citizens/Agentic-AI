"""Unit tests for FixCommandParser and FixCommandExecutor."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.interfaces.cli.commands.fix import (
    FixCommandParser,
    FixCommand,
    FixCommandExecutor,
    FixCommandResult,
)


class TestFixCommandParser:
    """Tests for FixCommandParser."""

    def setup_method(self):
        self.parser = FixCommandParser()

    def test_basic_fix(self):
        """Test basic /fix command with file and line."""
        result = self.parser.parse("/fix @src/main.py:42")
        assert result is not None
        assert result.file_path == "src/main.py"
        assert result.line_start == 42
        assert result.line_end is None
        assert result.dry_run is False
        assert result.preview is True

    def test_fix_without_line(self):
        """Test /fix command without line number."""
        result = self.parser.parse("/fix @src/main.py")
        assert result is not None
        assert result.file_path == "src/main.py"
        assert result.line_start is None

    def test_fix_with_range(self):
        """Test /fix command with line range."""
        result = self.parser.parse("/fix @src/main.py:42:50")
        assert result is not None
        assert result.line_start == 42
        assert result.line_end == 50

    def test_fix_with_dry_run(self):
        """Test /fix command with --dry-run flag."""
        result = self.parser.parse("/fix @src/main.py:42 --dry-run")
        assert result is not None
        assert result.dry_run is True
        assert result.preview is True

    def test_fix_with_no_preview(self):
        """Test /fix command with --no-preview flag."""
        result = self.parser.parse("/fix @src/main.py:42 --no-preview")
        assert result is not None
        assert result.preview is False
        assert result.dry_run is False

    def test_fix_with_rule(self):
        """Test /fix command with --rule filter."""
        result = self.parser.parse("/fix @src/main.py:42 --rule=ML001")
        assert result is not None
        assert result.rule_id == "ML001"

    def test_fix_with_multiple_rules(self):
        """Test /fix command with various rule IDs."""
        test_cases = [
            ("/fix @a.py:1 --rule=SEC001", "SEC001"),
            ("/fix @a.py:1 --rule=QUAL001", "QUAL001"),
            ("/fix @a.py:1 --rule=EMB001", "EMB001"),
            ("/fix @a.py:1 --rule=CRASH001", "CRASH001"),
            ("/fix @a.py:1 --rule=ASSERT001", "ASSERT001"),
        ]
        for cmd, expected_rule in test_cases:
            result = self.parser.parse(cmd)
            assert result is not None
            assert result.rule_id == expected_rule, f"Failed for {cmd}"

    def test_fix_with_apply(self):
        """Test /fix command with --apply flag."""
        result = self.parser.parse("/fix @src/main.py:42 --apply")
        assert result is not None
        assert result.apply is True

    def test_fix_with_interactive(self):
        """Test /fix command with --interactive flag."""
        result = self.parser.parse("/fix @src/main.py:42 --interactive")
        assert result is not None
        assert result.interactive is True

    def test_fix_with_i_short_flag(self):
        """Test /fix command with -i short flag."""
        result = self.parser.parse("/fix @src/main.py:42 -i")
        assert result is not None
        assert result.interactive is True

    def test_fix_with_multiple_options(self):
        """Test /fix command with multiple options."""
        result = self.parser.parse("/fix @src/main.py:42 --dry-run --rule=ML001")
        assert result is not None
        assert result.dry_run is True
        assert result.rule_id == "ML001"
        assert result.preview is True

    def test_fix_with_focus(self):
        """Test /fix command with --focus option."""
        result = self.parser.parse("/fix @src/main.py --focus=ml,security")
        assert result is not None
        assert "ml" in result.focus_areas
        assert "security" in result.focus_areas

    def test_fix_invalid_command(self):
        """Test invalid /fix command returns None."""
        assert self.parser.parse("/fix") is None
        assert self.parser.parse("/fix ") is None
        assert self.parser.parse("/fix@src/main.py") is None
        assert self.parser.parse("/review @src/main.py:42") is None
        assert self.parser.parse("/fix @") is None

    def test_fix_with_whitespace(self):
        """Test /fix command with extra whitespace."""
        result = self.parser.parse("  /fix @src/main.py:42  ")
        assert result is not None
        assert result.file_path == "src/main.py"
        assert result.line_start == 42

    def test_fix_with_nested_path(self):
        """Test /fix command with nested file path."""
        result = self.parser.parse("/fix @src/core/agent/state.py:100")
        assert result is not None
        assert result.file_path == "src/core/agent/state.py"
        assert result.line_start == 100

    def test_fix_with_dot_path(self):
        """Test /fix command with relative path."""
        result = self.parser.parse("/fix @./src/main.py:42")
        assert result is not None
        assert result.file_path == "./src/main.py"

    def test_fix_with_different_rule_patterns(self):
        """Test various rule ID patterns."""
        patterns = [
            "/fix @a.py:1 --rule=ML999",
            "/fix @a.py:1 --rule=SEC999",
            "/fix @a.py:1 --rule=QUAL999",
        ]
        for cmd in patterns:
            result = self.parser.parse(cmd)
            assert result is not None, f"Failed for {cmd}"


class TestFixCommand:
    """Tests for FixCommand dataclass."""

    def test_default_values(self):
        """Test FixCommand default values."""
        cmd = FixCommand(file_path="test.py")
        assert cmd.file_path == "test.py"
        assert cmd.line_start is None
        assert cmd.line_end is None
        assert cmd.rule_id is None
        assert cmd.dry_run is False
        assert cmd.preview is True
        assert cmd.interactive is False
        assert cmd.apply is False
        assert cmd.focus_areas == []

    def test_custom_values(self):
        """Test FixCommand with custom values."""
        cmd = FixCommand(
            file_path="src/main.py",
            line_start=42,
            line_end=50,
            rule_id="ML001",
            dry_run=True,
            preview=False,
            interactive=True,
            apply=True,
            focus_areas=["ml", "security"],
        )
        assert cmd.file_path == "src/main.py"
        assert cmd.line_start == 42
        assert cmd.line_end == 50
        assert cmd.rule_id == "ML001"
        assert cmd.dry_run is True
        assert cmd.preview is False
        assert cmd.interactive is True
        assert cmd.apply is True
        assert cmd.focus_areas == ["ml", "security"]


class TestFixCommandResult:
    """Tests for FixCommandResult dataclass."""

    def test_default_values(self):
        """Test FixCommandResult default values."""
        result = FixCommandResult(success=True, output="Test output")
        assert result.success is True
        assert result.output == "Test output"
        assert result.findings_count == 0
        assert result.applied_count == 0
        assert result.failed_count == 0
        assert result.skipped_count == 0
        assert result.errors == []
        assert result.data == {}

    def test_to_command_result(self):
        """Test conversion to CommandResult."""
        result = FixCommandResult(
            success=True,
            output="Test output",
            findings_count=5,
            applied_count=3,
            failed_count=1,
            skipped_count=1,
            errors=["Warning 1"],
            data={"key": "value"},
        )

        cmd_result = result.to_command_result()
        assert cmd_result.success is True
        assert cmd_result.output == "Test output"
        assert cmd_result.errors == ["Warning 1"]
        assert cmd_result.data["findings_count"] == 5
        assert cmd_result.data["applied_count"] == 3
        assert cmd_result.data["key"] == "value"


class TestFixCommandExecutor:
    """Tests for FixCommandExecutor."""

    def setup_method(self):
        self.workspace_root = Path("/tmp/test_workspace")
        self.executor = FixCommandExecutor(self.workspace_root)

    def test_executor_initialization(self):
        """Test executor initializes correctly."""
        assert self.executor.workspace_root == Path("/tmp/test_workspace")
        assert self.executor.fixer is not None
        assert self.executor._parser is not None

    def test_executor_with_pathlib(self):
        """Test executor accepts Path objects."""
        executor = FixCommandExecutor(Path("/tmp/test"))
        assert executor.workspace_root == Path("/tmp/test")

    @pytest.mark.asyncio
    async def test_execute_nonexistent_file(self):
        """Test execution with non-existent file."""
        cmd = FixCommand(file_path="nonexistent.py", line_start=1)
        result = await self.executor.execute(cmd)
        assert result.success is False
        assert "not found" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_no_findings(self, tmp_path):
        """Test execution when no findings are found."""
        # Create empty file
        test_file = tmp_path / "empty.py"
        test_file.write_text("# empty file\n", encoding="utf-8")

        # Use the tmp_path as workspace root and absolute path
        executor = FixCommandExecutor(tmp_path)
        cmd = FixCommand(file_path=str(test_file), line_start=1)
        result = await executor.execute(cmd)
        # Empty file may or may not have findings depending on content
        assert result.success is True


class TestFixCommandParserEdgeCases:
    """Edge case tests for FixCommandParser."""

    def setup_method(self):
        self.parser = FixCommandParser()

    def test_fix_with_special_chars_in_path(self):
        """Test /fix command with special characters in path."""
        result = self.parser.parse("/fix @src/core_v2/api.test.py:42")
        assert result is not None
        assert result.file_path == "src/core_v2/api.test.py"

    def test_fix_line_zero(self):
        """Test /fix command with line 0."""
        result = self.parser.parse("/fix @src/main.py:0")
        assert result is not None
        assert result.line_start == 0

    def test_fix_large_line_number(self):
        """Test /fix command with large line number."""
        result = self.parser.parse("/fix @src/main.py:999999")
        assert result is not None
        assert result.line_start == 999999

    def test_fix_end_before_start(self):
        """Test /fix command where end line < start line."""
        result = self.parser.parse("/fix @src/main.py:50:10")
        assert result is not None
        assert result.line_start == 50
        assert result.line_end == 10

    def test_fix_rule_in_middle_of_options(self):
        """Test rule extraction from middle of options."""
        result = self.parser.parse("/fix @a.py:1 --dry-run --rule=ML001 --apply")
        assert result is not None
        assert result.rule_id == "ML001"
        assert result.dry_run is True
        assert result.apply is True

    def test_fix_focus_with_spaces(self):
        """Test focus extraction."""
        result = self.parser.parse("/fix @a.py --focus=ml, security, quality")
        assert result is not None
        # Note: focus extraction splits on comma without spaces
        assert "ml" in result.focus_areas
