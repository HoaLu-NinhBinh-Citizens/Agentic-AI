"""Unit tests for slash command parser."""
import pytest
from src.interfaces.cli.commands.slash import (
    parse_and_execute,
    _parse_ref,
    _parse_flags,
    CommandContext,
    _BUILTIN_COMMANDS,
)


class TestParseRef:
    def test_file_only(self):
        f, ln = _parse_ref("@src/main.py")
        assert f == "src/main.py"
        assert ln is None

    def test_file_with_line(self):
        f, ln = _parse_ref("@src/main.py:42")
        assert f == "src/main.py"
        assert ln == 42

    def test_plain_path(self):
        f, ln = _parse_ref("src/main.py")
        assert f == "src/main.py"
        assert ln is None


class TestParseFlags:
    def test_positional_args(self):
        args, flags = _parse_flags("file1 file2")
        assert args == ["file1", "file2"]
        assert flags == {}

    def test_single_flag(self):
        args, flags = _parse_flags("--focus=security")
        assert args == []
        assert flags["focus"] == "security"

    def test_multiple_flags(self):
        args, flags = _parse_flags("--focus=ml --auto --dry-run")
        assert flags["focus"] == "ml"
        assert flags["auto"] == "true"
        assert flags["dry_run"] == "true"

    def test_mixed_args_and_flags(self):
        args, flags = _parse_flags("@file.py:42 --auto")
        assert args == ["@file.py:42"]
        assert flags["auto"] == "true"

    def test_shlex_split_preserves_quotes(self):
        args, flags = _parse_flags('--files="a.py, b.py" --flag=value')
        assert flags["files"] == "a.py, b.py"


class TestCommandRegistry:
    def test_all_commands_registered(self):
        expected = {"review", "fix", "explain", "stats", "rules", "help"}
        assert set(_BUILTIN_COMMANDS.keys()) == expected

    def test_review_has_alias(self):
        cmd = _BUILTIN_COMMANDS["review"]
        assert "r" in cmd.aliases

    def test_fix_has_alias(self):
        cmd = _BUILTIN_COMMANDS["fix"]
        assert "f" in cmd.aliases

    def test_all_commands_have_handlers(self):
        for name, cmd in _BUILTIN_COMMANDS.items():
            assert cmd.handler is not None, f"Command {name} has no handler"


class TestCommandContext:
    def test_primary_file(self):
        ctx = CommandContext(workspace_root="/", files=["a.py", "b.py"])
        assert ctx.primary_file == "a.py"

    def test_primary_file_empty(self):
        ctx = CommandContext(workspace_root="/", files=[])
        assert ctx.primary_file is None

    def test_primary_line(self):
        ctx = CommandContext(workspace_root="/", lines=[42, 100])
        assert ctx.primary_line == 42

    def test_primary_line_empty(self):
        ctx = CommandContext(workspace_root="/", lines=[])
        assert ctx.primary_line is None


class TestParseAndExecute:
    def test_unknown_command(self):
        import asyncio
        result = asyncio.run(
            parse_and_execute("/unknowncommand", "/workspace")
        )
        assert result.success is False

    def test_help_command(self):
        import asyncio
        result = asyncio.run(parse_and_execute("/help", "/workspace"))
        assert result.success is True
        assert "review" in result.output.lower()

    def test_stats_command(self):
        import asyncio
        result = asyncio.run(parse_and_execute("/stats", "/workspace"))
        assert result.success is True
        assert "Statistics" in result.output or "statistics" in result.output

    def test_rules_command(self):
        import asyncio
        result = asyncio.run(parse_and_execute("/rules", "/workspace"))
        assert result.success is True
        assert "SEC" in result.output or "Total:" in result.output

    def test_fix_without_file_shows_usage(self):
        import asyncio
        result = asyncio.run(parse_and_execute("/fix", "/workspace"))
        assert result.success is False
        assert "Usage" in result.output

    def test_explain_without_symbol_shows_usage(self):
        import asyncio
        result = asyncio.run(parse_and_execute("/explain", "/workspace"))
        assert result.success is False
        assert "Usage" in result.output

    def test_review_command_parsed(self):
        import asyncio
        result = asyncio.run(
            parse_and_execute("/review @src/ --focus=security --auto", "/workspace")
        )
        # Should either succeed or fail gracefully (no crash)
        assert isinstance(result.success, bool)
