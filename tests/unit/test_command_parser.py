"""Tests for CommandParser.

Tests cover:
- Full command parsing
- Shorthand command parsing
- Flag parsing
- Command help generation
- Alias handling

Usage:
    python -m pytest tests/unit/test_command_parser.py -v
"""

from __future__ import annotations

import pytest

from src.interfaces.cli.commands.command_parser import (
    CommandParser,
    ParsedCommand,
    CommandType,
    parse_virtual_command,
)


# ─── CommandParser Tests ──────────────────────────────────────────────────────


class TestCommandParser:
    """Tests for CommandParser class."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return CommandParser()

    def test_parse_fix_command(self, parser):
        """Test parsing /fix command."""
        result = parser.parse("/fix @src/main.py:42 --dry-run")
        
        assert result is not None
        assert result.command_type == CommandType.FIX
        assert result.file_path == "src/main.py"
        assert result.line_start == 42
        assert result.has_line_spec is True

    def test_parse_explain_command(self, parser):
        """Test parsing /explain command."""
        result = parser.parse("/explain @src/utils.py")
        
        assert result is not None
        assert result.command_type == CommandType.EXPLAIN
        assert result.file_path == "src/utils.py"
        assert result.line_start is None

    def test_parse_refactor_command(self, parser):
        """Test parsing /refactor command."""
        result = parser.parse("/refactor @lib/helper.ts:10:50")
        
        assert result is not None
        assert result.command_type == CommandType.REFACTOR
        assert result.file_path == "lib/helper.ts"
        assert result.line_start == 10
        assert result.line_end == 50

    def test_parse_search_command(self, parser):
        """Test parsing /search command."""
        result = parser.parse("/search @src/main.py:20 --scope=global")
        
        assert result is not None
        assert result.command_type == CommandType.SEARCH
        assert result.file_path == "src/main.py"
        assert result.line_start == 20
        assert result.flags.get("scope") == "global"

    def test_parse_test_command(self, parser):
        """Test parsing /test command."""
        result = parser.parse("/test @tests/test_main.py --generate")
        
        assert result is not None
        assert result.command_type == CommandType.TEST
        assert result.file_path == "tests/test_main.py"
        assert result.flags.get("generate") == "true"

    def test_parse_docs_command(self, parser):
        """Test parsing /docs command."""
        result = parser.parse("/docs @README.md")
        
        assert result is not None
        assert result.command_type == CommandType.DOCS
        assert result.file_path == "README.md"

    def test_parse_command_without_file(self, parser):
        """Test parsing command without file."""
        result = parser.parse("/fix --dry-run")
        
        assert result is not None
        assert result.command_type == CommandType.FIX
        assert result.file_path == ""

    def test_parse_command_aliases(self, parser):
        """Test command aliases."""
        # 'doc' should map to DOCS
        result = parser.parse("/doc @src/main.py")
        assert result is not None
        assert result.command_type == CommandType.DOCS
        
        # 'goto' should map to SEARCH
        result = parser.parse("/goto @src/main.py:10")
        assert result is not None
        assert result.command_type == CommandType.SEARCH
        
        # 'find' should map to SEARCH
        result = parser.parse("/find @src/main.py pattern")
        assert result is not None
        assert result.command_type == CommandType.SEARCH

    def test_parse_unknown_command(self, parser):
        """Test parsing unknown command type."""
        result = parser.parse("/unknown @src/main.py")
        
        assert result is not None
        assert result.command_type == CommandType.UNKNOWN

    def test_parse_non_command_returns_none(self, parser):
        """Test that non-command strings return None."""
        result = parser.parse("not a command")
        assert result is None

    def test_parse_empty_string_returns_none(self, parser):
        """Test that empty string returns None."""
        result = parser.parse("")
        assert result is None

    def test_parse_whitespace_only_returns_none(self, parser):
        """Test that whitespace-only string returns None."""
        result = parser.parse("   ")
        assert result is None


# ─── Flag Parsing Tests ────────────────────────────────────────────────────────


class TestFlagParsing:
    """Tests for flag parsing."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return CommandParser()

    def test_parse_dry_run_flag(self, parser):
        """Test parsing --dry-run flag."""
        result = parser.parse("/fix @test.py --dry-run")
        
        assert result is not None
        assert result.flags.get("dry_run") == "true"

    def test_parse_apply_flag(self, parser):
        """Test parsing --apply flag."""
        result = parser.parse("/fix @test.py --apply")
        
        assert result is not None
        assert result.flags.get("apply") == "true"

    def test_parse_interactive_flag(self, parser):
        """Test parsing --interactive and --i flags."""
        result1 = parser.parse("/fix @test.py --interactive")
        assert result1.flags.get("interactive") == "true"
        
        result2 = parser.parse("/fix @test.py --i")
        assert result2.flags.get("interactive") == "true"

    def test_parse_focus_flag(self, parser):
        """Test parsing --focus flag."""
        result = parser.parse("/fix @test.py --focus=security")
        
        assert result is not None
        assert result.flags.get("focus") == "security"

    def test_parse_focus_multiple_areas(self, parser):
        """Test parsing --focus with multiple areas."""
        result = parser.parse("/fix @test.py --focus=security,ml")
        
        assert result.flags.get("focus") == "security,ml"

    def test_parse_rule_flag(self, parser):
        """Test parsing --rule flag."""
        result = parser.parse("/fix @test.py --rule=ML001")
        
        assert result is not None
        assert result.flags.get("rule") == "ML001"

    def test_parse_scope_flag(self, parser):
        """Test parsing --scope flag."""
        result = parser.parse("/search @test.py pattern --scope=global")
        
        assert result.flags.get("scope") == "global"

    def test_parse_auto_fix_flag(self, parser):
        """Test parsing --auto-fix flag."""
        result = parser.parse("/fix @test.py --auto-fix")
        
        assert result is not None
        assert result.flags.get("auto_fix") == "true"

    def test_parse_auto_fix_with_value(self, parser):
        """Test parsing --auto-fix=value flag."""
        result = parser.parse("/fix @test.py --auto-fix=medium")
        
        assert result.flags.get("auto_fix") == "medium"

    def test_parse_severity_flag(self, parser):
        """Test parsing --severity flag."""
        result = parser.parse("/fix @test.py --severity=high")
        
        assert result is not None
        assert result.flags.get("severity") == "high"

    def test_parse_multiple_flags(self, parser):
        """Test parsing multiple flags."""
        result = parser.parse(
            "/fix @test.py:42 --dry-run --focus=security --rule=SEC001"
        )
        
        assert result is not None
        assert result.flags.get("dry_run") == "true"
        assert result.flags.get("focus") == "security"
        assert result.flags.get("rule") == "SEC001"


# ─── Shorthand Parsing Tests ──────────────────────────────────────────────────


class TestShorthandParsing:
    """Tests for shorthand command parsing."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return CommandParser()

    def test_parse_shorthand_with_line(self, parser):
        """Test parsing @file:line shorthand."""
        result = parser.parse_shorthand("@src/main.py:42")
        
        assert result is not None
        assert result.command_type == CommandType.UNKNOWN
        assert result.file_path == "src/main.py"
        assert result.line_start == 42
        assert result.has_line_spec is True

    def test_parse_shorthand_without_line(self, parser):
        """Test parsing @file shorthand."""
        result = parser.parse_shorthand("@src/main.py")
        
        assert result is not None
        assert result.file_path == "src/main.py"
        assert result.line_start is None

    def test_parse_shorthand_with_range(self, parser):
        """Test parsing @file:start:end shorthand."""
        result = parser.parse_shorthand("@src/main.py:10:50")
        
        assert result is not None
        assert result.line_start == 10
        assert result.line_end == 50

    def test_parse_invalid_shorthand_returns_none(self, parser):
        """Test that invalid shorthand returns None."""
        result = parser.parse_shorthand("not shorthand")
        assert result is None
        
        result = parser.parse_shorthand("")
        assert result is None


# ─── ParsedCommand Tests ────────────────────────────────────────────────────────


class TestParsedCommand:
    """Tests for ParsedCommand dataclass."""

    def test_has_line_spec_with_line(self):
        """Test has_line_spec with line number."""
        cmd = ParsedCommand(
            command_type=CommandType.FIX,
            file_path="test.py",
            line_start=42,
        )
        
        assert cmd.has_line_spec is True

    def test_has_line_spec_without_line(self):
        """Test has_line_spec without line number."""
        cmd = ParsedCommand(
            command_type=CommandType.FIX,
            file_path="test.py",
        )
        
        assert cmd.has_line_spec is False

    def test_raw_command_preserved(self):
        """Test that raw command is preserved."""
        raw = "/fix @test.py:42 --dry-run"
        
        parser = CommandParser()
        result = parser.parse(raw)
        
        assert result.raw_command == raw


# ─── Command Help Tests ────────────────────────────────────────────────────────


class TestCommandHelp:
    """Tests for command help generation."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return CommandParser()

    def test_get_fix_help(self, parser):
        """Test getting help for /fix command."""
        help_text = parser.get_command_help(CommandType.FIX)
        
        assert "/fix" in help_text
        assert "--dry-run" in help_text
        assert "--apply" in help_text
        assert "--interactive" in help_text
        assert "--rule" in help_text
        assert "--focus" in help_text

    def test_get_explain_help(self, parser):
        """Test getting help for /explain command."""
        help_text = parser.get_command_help(CommandType.EXPLAIN)
        
        assert "/explain" in help_text
        assert "--context" in help_text

    def test_get_refactor_help(self, parser):
        """Test getting help for /refactor command."""
        help_text = parser.get_command_help(CommandType.REFACTOR)
        
        assert "/refactor" in help_text
        assert "--mode" in help_text

    def test_get_search_help(self, parser):
        """Test getting help for /search command."""
        help_text = parser.get_command_help(CommandType.SEARCH)
        
        assert "/search" in help_text

    def test_get_test_help(self, parser):
        """Test getting help for /test command."""
        help_text = parser.get_command_help(CommandType.TEST)
        
        assert "/test" in help_text
        assert "--generate" in help_text
        assert "--run" in help_text

    def test_get_docs_help(self, parser):
        """Test getting help for /docs command."""
        help_text = parser.get_command_help(CommandType.DOCS)
        
        assert "/docs" in help_text

    def test_get_unknown_help(self, parser):
        """Test getting help for unknown command."""
        help_text = parser.get_command_help(CommandType.UNKNOWN)
        
        assert "Unknown" in help_text


# ─── Convenience Function Tests ────────────────────────────────────────────────


class TestParseVirtualCommand:
    """Tests for parse_virtual_command convenience function."""

    def test_full_command_parsing(self):
        """Test full command parsing via convenience function."""
        result = parse_virtual_command("/fix @src/main.py:42 --dry-run")
        
        assert result is not None
        assert result.command_type == CommandType.FIX
        assert result.file_path == "src/main.py"
        assert result.line_start == 42

    def test_shorthand_parsing(self):
        """Test shorthand parsing via convenience function."""
        result = parse_virtual_command("@src/main.py:42")
        
        assert result is not None
        assert result.file_path == "src/main.py"
        assert result.line_start == 42

    def test_invalid_input_returns_none(self):
        """Test that invalid input returns None."""
        result = parse_virtual_command("")
        assert result is None
        
        result = parse_virtual_command("not a command")
        assert result is None


# ─── Integration Tests ────────────────────────────────────────────────────────


class TestCommandParserIntegration:
    """Integration tests for command parser."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return CommandParser()

    def test_complex_fix_command(self, parser):
        """Test complex /fix command with multiple options."""
        result = parser.parse(
            "/fix @src/main.py:100:150 "
            "--focus=security,ml "
            "--rule=SEC001 "
            "--interactive"
        )
        
        assert result is not None
        assert result.command_type == CommandType.FIX
        assert result.file_path == "src/main.py"
        assert result.line_start == 100
        assert result.line_end == 150
        assert result.flags.get("focus") == "security,ml"
        assert result.flags.get("rule") == "SEC001"
        assert result.flags.get("interactive") == "true"

    def test_case_insensitive_commands(self, parser):
        """Test that commands are case-insensitive."""
        result1 = parser.parse("/FIX @test.py")
        result2 = parser.parse("/Fix @test.py")
        result3 = parser.parse("/fix @test.py")
        
        assert result1.command_type == CommandType.FIX
        assert result2.command_type == CommandType.FIX
        assert result3.command_type == CommandType.FIX

    def test_whitespace_handling(self, parser):
        """Test handling of extra whitespace."""
        result = parser.parse("  /fix   @test.py:42   --dry-run  ")
        
        assert result is not None
        assert result.command_type == CommandType.FIX
        assert result.file_path == "test.py"
        assert result.line_start == 42

    def test_multiple_commands_in_string(self, parser):
        """Test parsing first command when multiple present."""
        # Note: parser only parses the first command
        result = parser.parse("/fix @test.py /explain @other.py")
        
        assert result is not None
        assert result.command_type == CommandType.FIX
        assert result.file_path == "test.py"
