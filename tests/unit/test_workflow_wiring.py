"""Wire-in tests: composer and collaborative review reachable as CLI commands.

These previously-orphaned workflows are now registered slash commands.
"""

import asyncio
import tempfile

from src.interfaces.cli.commands.slash import (
    _BUILTIN_COMMANDS,
    cmd_composer,
    cmd_review_session,
    CommandContext,
)


class TestRegistered:
    def test_commands_registered_with_handlers(self):
        for name in ("composer", "review-session"):
            assert name in _BUILTIN_COMMANDS
            assert _BUILTIN_COMMANDS[name].handler is not None


class TestComposer:
    def test_empty_message_shows_usage(self):
        ctx = CommandContext(workspace_root=tempfile.mkdtemp(), raw_args="")
        result = asyncio.run(cmd_composer(ctx))
        assert result.success is False
        assert "Usage" in result.output

    def test_chat_returns_response(self):
        ctx = CommandContext(
            workspace_root=tempfile.mkdtemp(), raw_args="explain the main function"
        )
        result = asyncio.run(cmd_composer(ctx))
        assert result.success is True
        assert "Composer" in result.output
        assert "confidence" in result.data


class TestReviewSession:
    def test_unknown_action_shows_usage(self):
        ctx = CommandContext(workspace_root="/", raw_flags={})
        result = asyncio.run(cmd_review_session(ctx))
        assert result.success is False
        assert "Usage" in result.output

    def test_create_returns_session_id(self):
        ctx = CommandContext(
            workspace_root="/", raw_flags={"action": "create", "title": "T1"}
        )
        result = asyncio.run(cmd_review_session(ctx))
        assert result.success is True
        assert result.data.get("session_id")

    def test_summary_requires_session(self):
        ctx = CommandContext(workspace_root="/", raw_flags={"action": "summary"})
        result = asyncio.run(cmd_review_session(ctx))
        assert result.success is False
        assert "session" in result.output.lower()

    def test_create_then_summary_roundtrip(self):
        created = asyncio.run(
            cmd_review_session(
                CommandContext(
                    workspace_root="/", raw_flags={"action": "create", "title": "RT"}
                )
            )
        )
        sid = created.data["session_id"]
        summary = asyncio.run(
            cmd_review_session(
                CommandContext(
                    workspace_root="/",
                    raw_flags={"action": "summary", "session": sid},
                )
            )
        )
        assert summary.success is True
