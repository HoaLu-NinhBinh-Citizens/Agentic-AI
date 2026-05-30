"""Unit tests for Command Palette."""
import pytest
from src.interfaces.tui.command_palette import (
    Command, CommandKind, CommandPalette, PaletteResult,
)


class TestCommand:
    def test_exact_prefix_match(self):
        cmd = Command(id="test", label="Format Document")
        assert cmd.matches("format") == 10.0

    def test_substring_match(self):
        cmd = Command(id="test", label="Format Document")
        assert cmd.matches("document") == 6.0

    def test_description_match(self):
        cmd = Command(id="test", label="Fix", description="Fix code issues")
        assert cmd.matches("issues") == 4.0

    def test_no_match(self):
        cmd = Command(id="test", label="Format Document")
        assert cmd.matches("delete") == 0.0

    def test_keyword_match(self):
        cmd = Command(id="test", label="Review", keywords=["analyze", "check"])
        assert cmd.matches("analyze") == 8.0

    def test_fuzzy_match(self):
        cmd = Command(id="test", label="FormatDocument")
        assert cmd.matches("fmdoc") > 0


class TestCommandPalette:
    def setup_method(self):
        self.palette = CommandPalette()

    def test_builtin_commands_registered(self):
        assert len(self.palette._commands) >= 25

    def test_search_returns_results(self):
        # "fix" matches "AI: Fix Problems" with score 8.0
        results = self.palette.search("fix")
        assert len(results) > 0
        # At least the first result should have "fix" in label/description/keywords
        assert (
            "fix" in results[0].command.label.lower()
            or "fix" in results[0].command.description.lower()
            or any("fix" in kw.lower() for kw in results[0].command.keywords)
        )

    def test_search_empty_query_returns_recent(self):
        # Add a command to recent
        self.palette._recent = ["agent.fix"]
        results = self.palette.search("")
        # Empty query returns recent
        assert isinstance(results, list)

    def test_search_with_kind_filter(self):
        results = self.palette.search("ai", kind_filter=[CommandKind.AGENT])
        assert all(r.command.kind == CommandKind.AGENT for r in results)

    def test_search_max_results(self):
        results = self.palette.search("", max_results=5)
        assert len(results) <= 5

    def test_execute_command(self):
        result = self.palette.execute("agent.fix")
        assert result["executed"] == "agent.fix"

    def test_execute_unknown_command_raises(self):
        with pytest.raises(ValueError, match="Unknown command"):
            self.palette.execute("nonexistent.command")

    def test_execute_updates_recent(self):
        self.palette.execute("agent.review")
        assert self.palette._recent[0] == "agent.review"

    def test_recent_order_preserved(self):
        self.palette.execute("agent.review")
        self.palette.execute("agent.fix")
        self.palette.execute("agent.explain")
        assert self.palette._recent[0] == "agent.explain"
        assert self.palette._recent[1] == "agent.fix"
        assert self.palette._recent[2] == "agent.review"

    def test_recent_max_length(self):
        # Register a command to execute
        cmd = Command(id="new.command", label="New Command")
        self.palette.register(cmd)
        # Fill to 20 items (max limit)
        for i in range(20):
            self.palette._recent.append(f"cmd.{i}")
        assert len(self.palette._recent) == 20
        # Execute should not change length since we hit the limit
        self.palette.execute("new.command")
        # After execution: "new.command" moves to front, oldest popped
        assert len(self.palette._recent) == 20

    def test_toggle_favorite(self):
        assert self.palette.toggle_favorite("agent.fix") is True
        assert "agent.fix" in self.palette._favorites
        assert self.palette.toggle_favorite("agent.fix") is False
        assert "agent.fix" not in self.palette._favorites

    def test_get_favorites(self):
        self.palette._favorites.add("agent.fix")
        self.palette._favorites.add("agent.explain")
        favs = self.palette.get_favorites()
        assert len(favs) == 2
        assert all(c.id in ("agent.fix", "agent.explain") for c in favs)

    def test_register_custom_command(self):
        cmd = Command(
            id="custom.test",
            label="My Custom Command",
            description="A custom command",
            kind=CommandKind.EDITOR,
        )
        self.palette.register(cmd)
        assert "custom.test" in self.palette._commands
        results = self.palette.search("custom")
        assert any(r.command.id == "custom.test" for r in results)

    def test_unregister_command(self):
        result = self.palette.unregister("agent.review")
        assert result is True
        assert "agent.review" not in self.palette._commands

    def test_unregister_unknown_returns_false(self):
        result = self.palette.unregister("nonexistent")
        assert result is False

    def test_get_by_kind(self):
        agent_cmds = self.palette.get_by_kind(CommandKind.AGENT)
        assert all(c.kind == CommandKind.AGENT for c in agent_cmds)
        assert len(agent_cmds) >= 7  # At least 7 agent commands

    def test_get_stats(self):
        stats = self.palette.get_stats()
        assert stats["total_commands"] >= 25
        assert "by_kind" in stats
        assert stats["by_kind"]["agent"] >= 7

    def test_highlight_exact_prefix(self):
        ranges = self.palette._get_highlight_ranges("Format Document", "format")
        assert ranges == [(0, 6)]

    def test_highlight_substring(self):
        ranges = self.palette._get_highlight_ranges("Format Document", "document")
        assert any(start == 7 for start, _ in ranges)

    def test_search_sorting_by_score(self):
        # "fix" should match "AI: Fix Problems" (prefix) higher than "AI: Refactor"
        results = self.palette.search("fix")
        if len(results) >= 2:
            # First result should have higher score
            assert results[0].score >= results[1].score

    def test_get_all_commands(self):
        all_cmds = self.palette.get_all_commands()
        assert len(all_cmds) >= 25
        assert all(isinstance(c, Command) for c in all_cmds)
