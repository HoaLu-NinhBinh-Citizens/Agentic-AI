"""Tests for interactive fix workflow."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.interfaces.cli.commands.fix_interactive import (
    FixResponse,
    FixDecision,
    InteractiveFixSession,
    InteractiveFixResult,
    UserPromptProvider,
    ConsolePromptProvider,
    run_interactive_fix,
    prompt_user,
    should_auto_apply,
    format_fix_preview,
)


class MockPromptProvider(UserPromptProvider):
    """Mock prompt provider for testing."""

    def __init__(self, responses: list[str]):
        self.responses = responses
        self.call_count = 0

    async def prompt(
        self,
        message: str,
        choices: list[str],
        default: str,
    ) -> str:
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        return default


@pytest.fixture
def sample_fixes():
    """Create sample fixes for testing."""
    from src.core.fix_engine.models import Fix, FixSeverity

    return [
        Fix(
            id="fix_1",
            file_path="src/test.py",
            line_start=10,
            line_end=10,
            old_text="print('hello')",
            new_text="logger.info('hello')",
            reason="Use logging instead of print",
            rule_id="QUAL006",
            severity=FixSeverity.WARNING,
        ),
        Fix(
            id="fix_2",
            file_path="src/test.py",
            line_start=20,
            line_end=20,
            old_text="except:",
            new_text="except Exception as e:",
            reason="Catch specific exceptions",
            rule_id="QUAL003",
            severity=FixSeverity.WARNING,
        ),
        Fix(
            id="fix_3",
            file_path="src/test.py",
            line_start=30,
            line_end=30,
            old_text="API_KEY = 'secret'",
            new_text="API_KEY = os.getenv('API_KEY')",
            reason="Use environment variable",
            rule_id="SEC001",
            severity=FixSeverity.ERROR,
        ),
    ]


class TestInteractiveFixSession:
    """Tests for InteractiveFixSession."""

    def test_session_initialization(self, sample_fixes):
        """Test session initializes correctly."""
        session = InteractiveFixSession(
            workspace_root="/workspace",
            fixes=sample_fixes,
        )

        assert session.workspace_root == "/workspace"
        assert session.total_fixes == 3
        assert session.current_index == 0
        assert session.current_fix == sample_fixes[0]
        assert not session.skip_remaining
        assert not session.yes_to_all

    def test_session_advance(self, sample_fixes):
        """Test session advances through fixes."""
        session = InteractiveFixSession(
            workspace_root="/workspace",
            fixes=sample_fixes,
        )

        assert session.current_fix == sample_fixes[0]
        session.advance()
        assert session.current_fix == sample_fixes[1]
        session.advance()
        assert session.current_fix == sample_fixes[2]
        session.advance()
        assert session.current_fix is None

    def test_mark_applied(self, sample_fixes):
        """Test marking fixes as applied."""
        session = InteractiveFixSession(
            workspace_root="/workspace",
            fixes=sample_fixes,
        )

        session.mark_applied(sample_fixes[0])
        assert len(session.applied_fixes) == 1
        assert sample_fixes[0].status.value == "applied"

    def test_mark_skipped(self, sample_fixes):
        """Test marking fixes as skipped."""
        session = InteractiveFixSession(
            workspace_root="/workspace",
            fixes=sample_fixes,
        )

        session.mark_skipped(sample_fixes[1])
        assert len(session.skipped_fixes) == 1
        assert sample_fixes[1].status.value == "skipped"

    def test_auto_approved_rules(self, sample_fixes):
        """Test auto-approved rules."""
        session = InteractiveFixSession(
            workspace_root="/workspace",
            fixes=sample_fixes,
            auto_approved={"QUAL006"},
        )

        assert should_auto_apply("QUAL006", session)
        assert not should_auto_apply("QUAL003", session)

    def test_yes_to_all(self, sample_fixes):
        """Test yes_to_all mode."""
        session = InteractiveFixSession(
            workspace_root="/workspace",
            fixes=sample_fixes,
        )
        session.yes_to_all = True

        assert should_auto_apply("QUAL006", session)
        assert should_auto_apply("QUAL003", session)


class TestPromptUser:
    """Tests for prompt_user function."""

    @pytest.mark.asyncio
    async def test_prompt_yes(self, sample_fixes):
        """Test yes response."""
        provider = MockPromptProvider(["y"])
        fix = sample_fixes[0]

        decision = await prompt_user(fix, provider)
        assert decision == FixDecision.APPLY

    @pytest.mark.asyncio
    async def test_prompt_no(self, sample_fixes):
        """Test no response."""
        provider = MockPromptProvider(["n"])
        fix = sample_fixes[0]

        decision = await prompt_user(fix, provider)
        assert decision == FixDecision.SKIP

    @pytest.mark.asyncio
    async def test_prompt_yes_to_all(self, sample_fixes):
        """Test yes to all response."""
        provider = MockPromptProvider(["a"])
        fix = sample_fixes[0]

        decision = await prompt_user(fix, provider)
        assert decision == FixDecision.APPLY

    @pytest.mark.asyncio
    async def test_prompt_quit(self, sample_fixes):
        """Test quit response."""
        provider = MockPromptProvider(["q"])
        fix = sample_fixes[0]

        decision = await prompt_user(fix, provider)
        assert decision == FixDecision.ABORT

    @pytest.mark.asyncio
    async def test_prompt_edit(self, sample_fixes):
        """Test edit response."""
        provider = MockPromptProvider(["e"])
        fix = sample_fixes[0]

        decision = await prompt_user(fix, provider)
        assert decision == FixDecision.EDIT

    @pytest.mark.asyncio
    async def test_prompt_skip(self, sample_fixes):
        """Test skip response."""
        provider = MockPromptProvider(["s"])
        fix = sample_fixes[0]

        decision = await prompt_user(fix, provider)
        assert decision == FixDecision.SKIP

    @pytest.mark.asyncio
    async def test_prompt_help(self, sample_fixes):
        """Test help response."""
        provider = MockPromptProvider(["h"])
        fix = sample_fixes[0]

        decision = await prompt_user(fix, provider)
        assert decision == FixDecision.SKIP


class TestRunInteractiveFix:
    """Tests for run_interactive_fix function."""

    @pytest.mark.asyncio
    async def test_apply_all_fixes(self, sample_fixes):
        """Test applying all fixes with yes responses."""
        provider = MockPromptProvider(["y", "y", "y"])
        session = sample_fixes[0:2]  # Just 2 fixes for simpler test

        result = await run_interactive_fix(
            fixes=session,
            workspace_root="/workspace",
            prompt_provider=provider,
        )

        assert result.applied_count == 2
        assert result.skipped_count == 0
        assert result.total_processed == 2

    @pytest.mark.asyncio
    async def test_skip_all_fixes(self, sample_fixes):
        """Test skipping all fixes with no responses."""
        provider = MockPromptProvider(["n", "n", "n"])
        session = sample_fixes[0:2]

        result = await run_interactive_fix(
            fixes=session,
            workspace_root="/workspace",
            prompt_provider=provider,
        )

        assert result.applied_count == 0
        assert result.skipped_count == 2
        assert result.total_processed == 2

    @pytest.mark.asyncio
    async def test_mixed_responses(self, sample_fixes):
        """Test mixed yes/no responses."""
        provider = MockPromptProvider(["y", "n", "y"])
        session = sample_fixes[0:3]

        result = await run_interactive_fix(
            fixes=session,
            workspace_root="/workspace",
            prompt_provider=provider,
        )

        assert result.applied_count == 2
        assert result.skipped_count == 1
        assert result.total_processed == 3

    @pytest.mark.asyncio
    async def test_quit_aborts_session(self, sample_fixes):
        """Test that quit aborts remaining fixes."""
        provider = MockPromptProvider(["y", "q"])
        session = sample_fixes[0:3]

        result = await run_interactive_fix(
            fixes=session,
            workspace_root="/workspace",
            prompt_provider=provider,
        )

        assert result.applied_count == 1
        assert result.was_aborted
        # Remaining should be marked as skipped
        assert result.skipped_count == 2

    @pytest.mark.asyncio
    async def test_auto_approved_bypass_prompt(self, sample_fixes):
        """Test that auto-approved rules bypass prompt."""
        provider = MockPromptProvider([])  # No responses needed
        session = sample_fixes[0:2]

        result = await run_interactive_fix(
            fixes=session,
            workspace_root="/workspace",
            prompt_provider=provider,
            auto_approved_rules={"QUAL006", "QUAL003"},
        )

        # All fixes should be auto-applied
        assert result.applied_count == 2
        assert provider.call_count == 0  # No prompts needed

    @pytest.mark.asyncio
    async def test_empty_fixes_list(self):
        """Test with empty fixes list."""
        provider = MockPromptProvider([])

        result = await run_interactive_fix(
            fixes=[],
            workspace_root="/workspace",
            prompt_provider=provider,
        )

        assert result.applied_count == 0
        assert result.skipped_count == 0
        assert result.total_processed == 0


class TestFormatFixPreview:
    """Tests for format_fix_preview function."""

    def test_format_with_old_and_new_text(self, sample_fixes):
        """Test formatting with both old and new text."""
        fix = sample_fixes[0]
        preview = format_fix_preview(fix)

        assert "QUAL006" in preview
        assert "src/test.py" in preview
        assert "print('hello')" in preview
        assert "logger.info('hello')" in preview

    def test_format_with_empty_old_text(self):
        """Test formatting with empty old text."""
        from src.core.fix_engine.models import Fix, FixSeverity

        fix = Fix(
            id="fix_1",
            file_path="src/test.py",
            line_start=10,
            line_end=10,
            old_text="",
            new_text="new_code",
            reason="Add new code",
            rule_id="TEST001",
            severity=FixSeverity.INFO,
        )

        preview = format_fix_preview(fix)
        assert "TEST001" in preview
        assert "(auto-generated)" in preview


class TestInteractiveFixResult:
    """Tests for InteractiveFixResult."""

    def test_to_dict(self, sample_fixes):
        """Test result serialization."""
        session = InteractiveFixSession(
            workspace_root="/workspace",
            fixes=sample_fixes,
        )
        session.mark_applied(sample_fixes[0])
        session.mark_skipped(sample_fixes[1])

        result = InteractiveFixResult(
            session=session,
            applied_count=1,
            skipped_count=1,
            total_processed=2,
        )

        data = result.to_dict()

        assert data["applied_count"] == 1
        assert data["skipped_count"] == 1
        assert data["total_processed"] == 2
        assert not data["was_aborted"]
        assert len(data["applied_fixes"]) == 1
        assert len(data["skipped_fixes"]) == 1
