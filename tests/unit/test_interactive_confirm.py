"""Tests for interactive confirmation flow."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.interfaces.cli.commands.interactive_confirm import (
    ConfirmAction,
    ConfirmationPrompt,
    BatchResult,
    InteractiveConfirmationFlow,
    ConsolePromptProvider,
    Severity,
)
from src.domain.models.review_issue import ReviewIssue, CodeEvidence, FixOption


class MockPromptProvider:
    """Mock prompt provider for testing."""

    def __init__(self, responses: list[str]):
        self.responses = responses
        self.call_count = 0

    async def get_confirmation(self, prompt: ConfirmationPrompt, choices: list[str]) -> str:
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        return "n"


@pytest.fixture
def sample_issues():
    """Create sample ReviewIssue objects for testing."""
    return [
        ReviewIssue(
            id="issue-1",
            rule_id="QUAL006",
            severity=Severity.MEDIUM,
            file="src/test.py",
            line=10,
            end_line=10,
            title="Use logging instead of print",
            message="Use logging instead of print for better observability",
            explanation="Using print() makes debugging harder",
            evidence=CodeEvidence(
                file="src/test.py",
                line_start=10,
                line_end=10,
                old_code="print('hello')",
                new_code="logger.info('hello')",
            ),
            fixes=[
                FixOption(
                    id="fix-1",
                    title="Use logger",
                    description="Replace print with logger.info",
                    old_code="print('hello')",
                    new_code="logger.info('hello')",
                    risk=Severity.LOW,
                    confidence=0.9,
                )
            ],
            confidence=0.9,
            tags=["quality"],
            detector="quality",
        ),
        ReviewIssue(
            id="issue-2",
            rule_id="SEC001",
            severity=Severity.CRITICAL,
            file="src/test.py",
            line=20,
            end_line=20,
            title="Hardcoded API key",
            message="Hardcoded API key detected - use environment variable",
            explanation="Hardcoded secrets are security risks",
            evidence=CodeEvidence(
                file="src/test.py",
                line_start=20,
                line_end=20,
                old_code="API_KEY = 'secret123'",
                new_code="API_KEY = os.getenv('API_KEY')",
            ),
            fixes=[
                FixOption(
                    id="fix-2",
                    title="Use env var",
                    description="Replace hardcoded key with env var",
                    old_code="API_KEY = 'secret123'",
                    new_code="API_KEY = os.getenv('API_KEY')",
                    risk=Severity.LOW,
                    confidence=0.95,
                )
            ],
            confidence=0.95,
            tags=["security"],
            detector="security",
        ),
        ReviewIssue(
            id="issue-3",
            rule_id="LOW001",
            severity=Severity.LOW,
            file="src/test.py",
            line=30,
            end_line=30,
            title="Missing docstring",
            message="Function lacks docstring",
            explanation="Docstrings improve code readability",
            evidence=CodeEvidence(
                file="src/test.py",
                line_start=30,
                line_end=30,
                old_code="def foo(): pass",
                new_code="def foo(): pass  # TODO: add docstring",
            ),
            fixes=[
                FixOption(
                    id="fix-3",
                    title="Add docstring",
                    description="Add a docstring to the function",
                    old_code="def foo(): pass",
                    new_code="def foo(): pass  # TODO: add docstring",
                    risk=Severity.LOW,
                    confidence=0.7,
                )
            ],
            confidence=0.7,
            tags=["style"],
            detector="style",
        ),
    ]


class TestConfirmAction:
    """Tests for ConfirmAction enum."""

    def test_action_values(self):
        """Test that all expected actions are defined."""
        assert ConfirmAction.YES.value == "y"
        assert ConfirmAction.NO.value == "n"
        assert ConfirmAction.YES_TO_ALL.value == "a"
        assert ConfirmAction.NO_TO_ALL.value == "q"
        assert ConfirmAction.EDIT.value == "e"
        assert ConfirmAction.HELP.value == "h"
        assert ConfirmAction.SKIP.value == "s"


class TestConfirmationPrompt:
    """Tests for ConfirmationPrompt dataclass."""

    def test_to_display_string(self):
        """Test prompt display formatting."""
        prompt = ConfirmationPrompt(
            index=1,
            total=5,
            severity_icon="[X]",
            rule_id="SEC001",
            file_path="src/test.py",
            line=10,
            message="Test message",
            old_code_preview="old_code",
            new_code_preview="new_code",
            risk_level="Low",
        )

        display = prompt.to_display_string()

        assert "[1/5]" in display
        assert "[X]" in display
        assert "SEC001" in display
        assert "src/test.py:10" in display
        assert "Test message" in display
        assert "old_code" in display
        assert "new_code" in display
        assert "Low" in display


class TestBatchResult:
    """Tests for BatchResult dataclass."""

    def test_default_values(self):
        """Test default values for batch result."""
        result = BatchResult()

        assert result.applied_count == 0
        assert result.skipped_count == 0
        assert result.failed_count == 0
        assert result.total_processed == 0
        assert result.was_aborted is False
        assert result.applied_fix_ids == []
        assert result.skipped_fix_ids == []

    def test_with_values(self):
        """Test batch result with values."""
        result = BatchResult(
            applied_count=3,
            skipped_count=2,
            failed_count=1,
            total_processed=6,
            was_aborted=True,
            applied_fix_ids=["fix-1", "fix-2", "fix-3"],
            skipped_fix_ids=["fix-4", "fix-5"],
        )

        assert result.applied_count == 3
        assert result.skipped_count == 2
        assert result.failed_count == 1
        assert result.total_processed == 6
        assert result.was_aborted is True
        assert len(result.applied_fix_ids) == 3


class TestConsolePromptProvider:
    """Tests for ConsolePromptProvider."""

    @pytest.mark.asyncio
    async def test_get_confirmation(self):
        """Test getting confirmation from console."""
        output_lines = []

        def mock_write(msg):
            output_lines.append(msg)

        def mock_read(_):
            return "y"

        provider = ConsolePromptProvider(
            output_writer=mock_write,
            input_reader=mock_read,
        )

        prompt = ConfirmationPrompt(
            index=1,
            total=1,
            severity_icon="[!]",
            rule_id="TEST",
            file_path="test.py",
            line=1,
            message="Test",
            old_code_preview="old",
            new_code_preview="new",
            risk_level="Low",
        )

        response = await provider.get_confirmation(prompt, ["y", "n"])

        assert response == "y"
        assert len(output_lines) > 0

    @pytest.mark.asyncio
    async def test_default_to_no(self):
        """Test that empty input defaults to no."""
        output_lines = []

        def mock_write(msg):
            output_lines.append(msg)

        def mock_read(_):
            return ""

        provider = ConsolePromptProvider(
            output_writer=mock_write,
            input_reader=mock_read,
        )

        prompt = ConfirmationPrompt(
            index=1,
            total=1,
            severity_icon="[!]",
            rule_id="TEST",
            file_path="test.py",
            line=1,
            message="Test",
            old_code_preview="old",
            new_code_preview="new",
            risk_level="Low",
        )

        response = await provider.get_confirmation(prompt, ["y", "n"])

        assert response == "n"


class TestInteractiveConfirmationFlow:
    """Tests for InteractiveConfirmationFlow."""

    @pytest.mark.asyncio
    async def test_yes_response(self, sample_issues):
        """Test yes response applies fix."""
        provider = MockPromptProvider(["y"])
        flow = InteractiveConfirmationFlow(prompt_provider=provider)

        apply_calls = []

        async def mock_apply(issue):
            apply_calls.append(issue.id)
            return True

        result = await flow.confirm_and_apply(
            sample_issues[0], 1, 1, mock_apply
        )

        assert result is True
        assert flow.applied_count == 1
        assert len(apply_calls) == 1
        assert "issue-1" in apply_calls

    @pytest.mark.asyncio
    async def test_no_response(self, sample_issues):
        """Test no response skips fix."""
        provider = MockPromptProvider(["n"])
        flow = InteractiveConfirmationFlow(prompt_provider=provider)

        async def mock_apply(issue):
            return True

        result = await flow.confirm_and_apply(
            sample_issues[0], 1, 1, mock_apply
        )

        assert result is False
        assert flow.skipped_count == 1
        assert flow.applied_count == 0

    @pytest.mark.asyncio
    async def test_yes_to_all(self, sample_issues):
        """Test yes to all applies remaining fixes."""
        provider = MockPromptProvider(["a"])
        flow = InteractiveConfirmationFlow(prompt_provider=provider)

        apply_calls = []

        async def mock_apply(issue):
            apply_calls.append(issue.id)
            return True

        result = await flow.confirm_and_apply(
            sample_issues[0], 1, 2, mock_apply
        )

        assert result is True
        assert flow._yes_to_all is True

    @pytest.mark.asyncio
    async def test_no_to_all(self, sample_issues):
        """Test no to all skips remaining fixes."""
        provider = MockPromptProvider(["q"])
        flow = InteractiveConfirmationFlow(prompt_provider=provider)

        async def mock_apply(issue):
            return True

        result = await flow.confirm_and_apply(
            sample_issues[0], 1, 2, mock_apply
        )

        assert result is False
        assert flow._no_to_all is True

    @pytest.mark.asyncio
    async def test_auto_apply_critical(self, sample_issues):
        """Test that critical fixes are auto-applied."""
        provider = MockPromptProvider([])
        flow = InteractiveConfirmationFlow(prompt_provider=provider)

        apply_calls = []

        async def mock_apply(issue):
            apply_calls.append(issue.id)
            return True

        # Critical issue should auto-apply
        result = await flow.confirm_and_apply(
            sample_issues[1], 1, 1, mock_apply
        )

        assert result is True
        assert flow.applied_count == 1
        assert len(apply_calls) == 1
        # Critical issues should auto-apply without prompting
        assert provider.call_count == 0

    @pytest.mark.asyncio
    async def test_edit_response(self, sample_issues):
        """Test edit response skips fix."""
        provider = MockPromptProvider(["e"])
        flow = InteractiveConfirmationFlow(prompt_provider=provider)

        async def mock_apply(issue):
            return True

        result = await flow.confirm_and_apply(
            sample_issues[0], 1, 1, mock_apply
        )

        assert result is False
        assert flow.skipped_count == 1

    @pytest.mark.asyncio
    async def test_help_shows_help(self, sample_issues):
        """Test help response shows help and re-prompts."""
        provider = MockPromptProvider(["h", "y"])
        flow = InteractiveConfirmationFlow(prompt_provider=provider)

        output_lines = []

        async def mock_apply(issue):
            return True

        result = await flow.confirm_and_apply(
            sample_issues[0], 1, 1, mock_apply
        )

        # Help should trigger re-prompt with 'y'
        assert result is True
        assert provider.call_count == 2

    @pytest.mark.asyncio
    async def test_run_batch_empty(self, sample_issues):
        """Test run_batch with empty list."""
        provider = MockPromptProvider([])
        flow = InteractiveConfirmationFlow(prompt_provider=provider)

        async def mock_apply(issue):
            return True

        result = await flow.run_batch([], mock_apply)

        assert result.total_processed == 0
        assert result.applied_count == 0

    @pytest.mark.asyncio
    async def test_run_batch_multiple(self, sample_issues):
        """Test run_batch with multiple fixes."""
        provider = MockPromptProvider(["y", "n", "a"])
        flow = InteractiveConfirmationFlow(prompt_provider=provider)

        apply_calls = []

        async def mock_apply(issue):
            apply_calls.append(issue.id)
            return True

        result = await flow.run_batch(sample_issues[:3], mock_apply)

        assert result.total_processed == 3
        assert result.applied_count >= 1
        assert len(apply_calls) == result.applied_count

    @pytest.mark.asyncio
    async def test_run_batch_with_abort(self, sample_issues):
        """Test run_batch aborts remaining fixes after quit."""
        provider = MockPromptProvider(["y", "q"])
        flow = InteractiveConfirmationFlow(prompt_provider=provider)

        async def mock_apply(issue):
            return True

        result = await flow.run_batch(sample_issues[:3], mock_apply)

        assert result.was_aborted is True
        # First should be applied, second skipped with quit, third auto-skipped
        assert result.applied_count >= 1
        # At least one should be skipped (the quit response)
        assert result.skipped_count >= 1

    def test_should_apply_auto_yes_to_all(self, sample_issues):
        """Test auto-apply when yes_to_all is set."""
        flow = InteractiveConfirmationFlow()
        flow._yes_to_all = True

        result = flow._should_apply(sample_issues[0])
        assert result is True

    def test_should_apply_auto_no_to_all(self, sample_issues):
        """Test auto-skip when no_to_all is set."""
        flow = InteractiveConfirmationFlow()
        flow._no_to_all = True

        result = flow._should_apply(sample_issues[0])
        assert result is False

    def test_should_apply_critical_auto(self, sample_issues):
        """Test critical severity auto-applies."""
        flow = InteractiveConfirmationFlow()

        result = flow._should_apply(sample_issues[1])  # CRITICAL severity
        assert result is True

    def test_should_apply_needs_prompt(self, sample_issues):
        """Test medium severity needs prompt."""
        flow = InteractiveConfirmationFlow()

        result = flow._should_apply(sample_issues[0])  # MEDIUM severity
        assert result is None  # None means prompt needed

    def test_parse_response(self):
        """Test response parsing."""
        flow = InteractiveConfirmationFlow()

        assert flow._parse_response("y") == ConfirmAction.YES
        assert flow._parse_response("n") == ConfirmAction.NO
        assert flow._parse_response("a") == ConfirmAction.YES_TO_ALL
        assert flow._parse_response("q") == ConfirmAction.NO_TO_ALL
        assert flow._parse_response("e") == ConfirmAction.EDIT
        assert flow._parse_response("h") == ConfirmAction.HELP
        assert flow._parse_response("s") == ConfirmAction.SKIP
        assert flow._parse_response("x") == ConfirmAction.NO  # Unknown defaults to NO

    def test_get_severity_icon(self):
        """Test severity icon mapping."""
        flow = InteractiveConfirmationFlow()

        assert flow._get_severity_icon(Severity.CRITICAL) == "[X]"
        assert flow._get_severity_icon(Severity.HIGH) == "[!]"
        assert flow._get_severity_icon(Severity.MEDIUM) == "[@]"
        assert flow._get_severity_icon(Severity.LOW) == "[i]"
        assert flow._get_severity_icon(Severity.INFO) == "[i]"

    def test_truncate_code(self):
        """Test code truncation."""
        flow = InteractiveConfirmationFlow()

        # Short code
        short_code = "x = 1"
        assert flow._truncate_code(short_code, 50) == short_code

        # Empty code
        assert flow._truncate_code("") == "(none)"
        assert flow._truncate_code(None) == "(none)"

        # Long code truncation
        long_code = "x = 1\ny = 2\nz = 3"
        result = flow._truncate_code(long_code, 10)
        assert "..." in result or len(result) <= 10

    def test_print_summary(self):
        """Test summary printing."""
        flow = InteractiveConfirmationFlow()
        flow._applied_count = 2
        flow._skipped_count = 1
        flow._failed_count = 0
        flow._applied_ids = ["fix-1", "fix-2"]
        flow._skipped_ids = ["fix-3"]

        output_lines = []

        def mock_write(msg):
            output_lines.append(msg)

        flow._write = mock_write

        summary = flow.print_summary()

        assert "Applied:  2" in summary
        assert "Skipped:  1" in summary
        assert "Failed:   0" in summary
        assert "fix-1" in summary
        assert "fix-2" in summary

    def test_build_prompt(self, sample_issues):
        """Test prompt building from issue."""
        flow = InteractiveConfirmationFlow()

        prompt = flow._build_prompt(sample_issues[0], 1, 5)

        assert prompt.index == 1
        assert prompt.total == 5
        assert prompt.rule_id == "QUAL006"
        assert prompt.file_path == "src/test.py"
        assert prompt.line == 10
        assert "print" in prompt.old_code_preview
        assert "logger" in prompt.new_code_preview

    def test_show_code_diff(self):
        """Test code diff formatting."""
        flow = InteractiveConfirmationFlow()

        old_code = "print('hello')"
        new_code = "logger.info('hello')"

        diff = flow._show_code_diff(old_code, new_code)

        assert "--- Current" in diff
        assert "+++ Proposed" in diff
        assert "print('hello')" in diff
        assert "logger.info('hello')" in diff
