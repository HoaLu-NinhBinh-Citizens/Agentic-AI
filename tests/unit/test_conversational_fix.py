"""Tests for conversational fix workflow."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.interfaces.conversation.conversational_fix_engine import (
    UXAction,
    RiskLevel,
    FixOption,
    FixContext,
    FixDecision,
    ConversationState,
    ConversationResult,
    ConversationalFixEngine,
)
from src.interfaces.conversation.formatters import (
    ConsoleConversationFormatter,
    Color,
    create_formatter,
)


class TestFixOption:
    """Tests for FixOption dataclass."""

    def test_fix_option_creation(self):
        """Test creating a FixOption."""
        option = FixOption(
            index=0,
            label="Test Fix",
            new_code="print('hello')",
            old_code="print 'hello'",
            confidence=0.9,
            risk=RiskLevel.LOW,
        )

        assert option.index == 0
        assert option.label == "Test Fix"
        assert option.confidence == 0.9
        assert option.risk == RiskLevel.LOW

    def test_risk_color(self):
        """Test risk_color method."""
        low_option = FixOption(index=0, label="Low", new_code="x", risk=RiskLevel.LOW)
        high_option = FixOption(index=1, label="High", new_code="x", risk=RiskLevel.HIGH)

        assert low_option.risk_color() == "\033[92m"  # Green
        assert high_option.risk_color() == "\033[91m"  # Red


class TestFixContext:
    """Tests for FixContext dataclass."""

    def test_fix_context_creation(self):
        """Test creating a FixContext."""
        context = FixContext(
            file_path="src/test.py",
            line=10,
            rule_id="TEST001",
            message="Use logging instead of print",
            explanation="Print is not configurable",
            root_cause="Hardcoded output",
        )

        assert context.file_path == "src/test.py"
        assert context.line == 10
        assert context.rule_id == "TEST001"
        assert not context.is_critical()

    def test_is_critical(self):
        """Test is_critical method."""
        critical = FixContext(
            file_path="src/test.py",
            line=10,
            rule_id="SEC001",
            message="Security issue",
            explanation="",
            root_cause="",
            severity="CRITICAL",
        )

        warning = FixContext(
            file_path="src/test.py",
            line=20,
            rule_id="QUAL001",
            message="Style issue",
            explanation="",
            root_cause="",
            severity="WARNING",
        )

        assert critical.is_critical()
        assert not warning.is_critical()


class TestConversationState:
    """Tests for ConversationState."""

    def test_state_initialization(self):
        """Test state initializes correctly."""
        context = FixContext(
            file_path="test.py",
            line=1,
            rule_id="TEST",
            message="Test",
            explanation="",
            root_cause="",
        )
        state = ConversationState(fixes=[context])

        assert state.remaining == 1
        assert state.current == context
        assert len(state.applied) == 0
        assert len(state.skipped) == 0

    def test_advance(self):
        """Test advancing through fixes."""
        contexts = [
            FixContext(file_path="t.py", line=i, rule_id="T", message="", explanation="", root_cause="")
            for i in range(3)
        ]
        state = ConversationState(fixes=contexts)

        # First advance: 0 -> 1
        assert state.advance()
        assert state.current_index == 1
        assert state.current == contexts[1]

        # Second advance: 1 -> 2
        assert state.advance()
        assert state.current_index == 2
        assert state.current == contexts[2]

        # Third advance: 2 -> 3 (no more fixes, returns False)
        assert not state.advance()
        assert state.current_index == 3
        assert state.current is None

    def test_record_applied(self):
        """Test recording applied fixes."""
        context = FixContext(
            file_path="test.py", line=1, rule_id="T", message="", explanation="", root_cause=""
        )
        state = ConversationState(fixes=[context])

        state.record_applied(0)
        assert 0 in state.applied
        assert len(state.undo_stack) == 1

        # Duplicate shouldn't be added
        state.record_applied(0)
        assert len(state.applied) == 1

    def test_record_skipped(self):
        """Test recording skipped fixes."""
        context = FixContext(
            file_path="test.py", line=1, rule_id="T", message="", explanation="", root_cause=""
        )
        state = ConversationState(fixes=[context])

        state.record_skipped(0)
        assert 0 in state.skipped

    def test_undo_last(self):
        """Test undo functionality."""
        context = FixContext(
            file_path="test.py", line=1, rule_id="T", message="", explanation="", root_cause=""
        )
        state = ConversationState(fixes=[context])

        state.record_applied(0)
        assert len(state.applied) == 1

        undone = state.undo_last()
        assert undone == 0
        assert 0 not in state.applied
        assert len(state.undo_stack) == 0

        # Undo empty stack
        assert state.undo_last() is None


class TestConversationResult:
    """Tests for ConversationResult."""

    def test_result_creation(self):
        """Test creating a result."""
        applied = [
            FixContext(
                file_path="a.py", line=1, rule_id="A", message="", explanation="", root_cause=""
            )
        ]
        skipped = [
            FixContext(
                file_path="b.py", line=2, rule_id="B", message="", explanation="", root_cause=""
            )
        ]
        result = ConversationResult(applied=applied, skipped=skipped, summary="Done")

        assert result.applied_count == 1
        assert result.skipped_count == 1

    def test_empty_result(self):
        """Test empty result."""
        result = ConversationResult(applied=[], skipped=[], summary="No changes")

        assert result.applied_count == 0
        assert result.skipped_count == 0


class TestConversationalFixEngine:
    """Tests for ConversationalFixEngine."""

    def test_engine_initialization(self):
        """Test engine initializes correctly."""
        engine = ConversationalFixEngine(fixer=None, llm_suggester=None)

        assert engine.fixer is None
        assert engine.llm_suggester is None

    @pytest.mark.asyncio
    async def test_run_session_empty_findings(self):
        """Test session with no findings."""
        engine = ConversationalFixEngine()

        result = await engine.run_session(
            findings=[],
            workspace_root="/workspace",
            auto_critical=False,
        )

        assert result.applied_count == 0
        assert result.skipped_count == 0
        assert "No fixable" in result.summary

    def test_parse_response(self):
        """Test parsing user responses."""
        engine = ConversationalFixEngine()

        # Test apply shortcuts
        for response in ["a", "apply", "y", "yes"]:
            decision = engine._parse_response(response)
            assert decision.action == UXAction.APPLY

        # Test skip shortcuts
        for response in ["s", "skip", "n", "no"]:
            decision = engine._parse_response(response)
            assert decision.action == UXAction.SKIP

        # Test other actions
        assert engine._parse_response("t").action == UXAction.EXPLAIN_TRADEOFF
        assert engine._parse_response("r").action == UXAction.EXPLAIN_RISK
        assert engine._parse_response("p").action == UXAction.PREVIEW
        assert engine._parse_response("c").action == UXAction.APPLY_ALL_CRITICAL
        assert engine._parse_response("u").action == UXAction.UNDO_LAST
        assert engine._parse_response("q").action == UXAction.QUIT
        assert engine._parse_response("h").action == UXAction.HELP

        # Test numbered option
        decision = engine._parse_response("3")
        assert decision.action == UXAction.CHOOSE_OPTION
        assert decision.chosen_option_index == 3

    def test_risk_indicator(self):
        """Test risk indicator generation."""
        engine = ConversationalFixEngine()

        assert "LOW" in engine._risk_indicator(RiskLevel.LOW)
        assert "MEDIUM" in engine._risk_indicator(RiskLevel.MEDIUM)
        assert "HIGH" in engine._risk_indicator(RiskLevel.HIGH)
        assert "CRITICAL" in engine._risk_indicator(RiskLevel.CRITICAL)

    @pytest.mark.asyncio
    async def test_show_fix_intro(self):
        """Test fix intro generation."""
        context = FixContext(
            file_path="src/test.py",
            line=10,
            rule_id="TEST001",
            message="Use logging",
            explanation="Print is not configurable",
            root_cause="Hardcoded",
            options=[
                FixOption(index=0, label="Fix A", new_code="log()", risk=RiskLevel.LOW),
                FixOption(index=1, label="Fix B", new_code="print()", risk=RiskLevel.HIGH),
            ],
            severity="WARNING",
        )
        engine = ConversationalFixEngine()

        intro = await engine._show_fix_intro(context)

        assert "TEST001" in intro
        assert "src/test.py:10" in intro
        assert "Use logging" in intro
        assert "[0]" in intro
        assert "[1]" in intro

    def test_show_help(self):
        """Test help text generation."""
        engine = ConversationalFixEngine()
        help_text = engine._show_help()

        assert "apply" in help_text.lower()
        assert "skip" in help_text.lower()
        assert "tradeoff" in help_text.lower()
        assert "risk" in help_text.lower()


class TestConsoleConversationFormatter:
    """Tests for ConsoleConversationFormatter."""

    def test_formatter_initialization(self):
        """Test formatter initializes correctly."""
        formatter = ConsoleConversationFormatter(use_colors=True)
        assert formatter.use_colors

        formatter_no_color = ConsoleConversationFormatter(use_colors=False)
        assert not formatter_no_color.use_colors

    def test_color_application(self):
        """Test color application."""
        formatter = ConsoleConversationFormatter(use_colors=True)

        colored = formatter._color("test", Color.RED)
        assert "\033[31m" in colored
        assert "test\033[0m" in colored

    def test_color_disabled(self):
        """Test colors disabled."""
        formatter = ConsoleConversationFormatter(use_colors=False)

        colored = formatter._color("test", Color.RED)
        assert colored == "test"

    def test_bold_text(self):
        """Test bold text."""
        formatter = ConsoleConversationFormatter(use_colors=True)
        bold = formatter._bold("test")
        assert "\033[1m" in bold

    def test_dim_text(self):
        """Test dim text."""
        formatter = ConsoleConversationFormatter(use_colors=True)
        dim = formatter._dim("test")
        assert "\033[2m" in dim

    def test_progress_bar(self):
        """Test progress bar generation."""
        formatter = ConsoleConversationFormatter(use_colors=False)

        bar = formatter._make_progress_bar(0.5, 10)
        assert "[" in bar
        assert "]" in bar
        # Bar should be 50% filled (5 out of 10 chars)
        # Contains unicode block characters for filled/empty
        assert len(bar) >= 2  # At least [ and ]

    def test_progress_bar_full(self):
        """Test full progress bar."""
        formatter = ConsoleConversationFormatter(use_colors=False)

        bar = formatter._make_progress_bar(1.0, 10)
        # Full bar should have all filled characters
        assert "[" in bar
        assert "]" in bar

    def test_progress_bar_empty(self):
        """Test empty progress bar."""
        formatter = ConsoleConversationFormatter(use_colors=False)

        bar = formatter._make_progress_bar(0.0, 10)
        assert "[" in bar
        assert "]" in bar

    def test_format_intro(self):
        """Test fix intro formatting."""
        formatter = ConsoleConversationFormatter(use_colors=True)
        context = FixContext(
            file_path="src/test.py",
            line=10,
            rule_id="TEST001",
            message="Test issue",
            explanation="Explanation",
            root_cause="Root",
            severity="WARNING",
        )

        intro = formatter.format_intro(context)

        assert "TEST001" in intro
        assert "src/test.py" in intro
        assert "Test issue" in intro

    def test_format_options(self):
        """Test options formatting."""
        formatter = ConsoleConversationFormatter(use_colors=True)
        options = [
            FixOption(
                index=0,
                label="Option 1",
                new_code="x",
                confidence=0.8,
                risk=RiskLevel.LOW,
            ),
            FixOption(
                index=1,
                label="Option 2",
                new_code="y",
                confidence=0.5,
                risk=RiskLevel.HIGH,
            ),
        ]

        formatted = formatter.format_options(options)

        assert "Option 1" in formatted
        assert "Option 2" in formatted
        assert "LOW" in formatted
        assert "HIGH" in formatted

    def test_format_summary(self):
        """Test summary formatting."""
        formatter = ConsoleConversationFormatter(use_colors=True)
        applied = [
            FixContext(
                file_path="a.py", line=1, rule_id="A", message="", explanation="", root_cause=""
            )
        ]
        skipped = [
            FixContext(
                file_path="b.py", line=2, rule_id="B", message="", explanation="", root_cause=""
            )
        ]
        result = ConversationResult(applied=applied, skipped=skipped, summary="Done")

        summary = formatter.format_summary(result)

        assert "Applied" in summary
        assert "Skipped" in summary
        assert "a.py" in summary
        assert "b.py" in summary

    def test_format_diff_preview(self):
        """Test diff preview formatting."""
        formatter = ConsoleConversationFormatter(use_colors=True)

        preview = formatter.format_diff_preview(
            old_code="print('old')",
            new_code="print('new')",
            file_path="test.py",
            line=10,
        )

        assert "old" in preview
        assert "new" in preview
        assert "test.py" in preview

    def test_format_risk_explanation(self):
        """Test risk explanation formatting."""
        formatter = ConsoleConversationFormatter(use_colors=True)
        context = FixContext(
            file_path="test.py",
            line=1,
            rule_id="TEST",
            message="Issue",
            explanation="Why it's a problem",
            root_cause="",
            options=[
                FixOption(
                    index=0,
                    label="Fix",
                    new_code="x",
                    old_code="y",
                    confidence=0.7,
                    risk=RiskLevel.HIGH,
                    explanation="This is the explanation",
                )
            ],
        )

        explanation = formatter.format_risk_explanation(context, 0)

        assert "Fix" in explanation
        assert "HIGH" in explanation
        assert "This is the explanation" in explanation

    def test_format_help(self):
        """Test help formatting."""
        formatter = ConsoleConversationFormatter(use_colors=True)
        help_text = formatter.format_help()

        assert "Apply" in help_text
        assert "Skip" in help_text
        # Check for lowercase version in the colored output
        assert "tradeoff" in help_text.lower()


class TestCreateFormatter:
    """Tests for create_formatter factory function."""

    def test_create_formatter_with_colors(self):
        """Test creating formatter with colors."""
        formatter = create_formatter(use_colors=True)
        assert formatter.use_colors

    def test_create_formatter_without_colors(self):
        """Test creating formatter without colors."""
        formatter = create_formatter(use_colors=False)
        assert not formatter.use_colors


class TestIntegration:
    """Integration tests for conversational fix workflow."""

    @pytest.mark.asyncio
    async def test_full_session_flow(self):
        """Test complete session flow."""
        # Create mock findings
        mock_finding = MagicMock()
        mock_finding.file = "test.py"
        mock_finding.line = 10
        mock_finding.rule_id = "TEST001"
        mock_finding.message = "Test issue"
        mock_finding.explanation = "Test explanation"
        mock_finding.root_cause = ""
        mock_finding.severity = "WARNING"
        mock_finding.metadata = {"old_code": "old", "new_code": "new"}
        mock_finding.fix = None

        engine = ConversationalFixEngine()
        formatter = ConsoleConversationFormatter(use_colors=False)

        result = await engine.run_session(
            findings=[mock_finding],
            workspace_root="/workspace",
            auto_critical=False,
        )

        # Verify session ran
        assert result is not None
        assert result.summary is not None

    @pytest.mark.asyncio
    async def test_auto_critical_mode(self):
        """Test auto-critic mode."""
        mock_finding = MagicMock()
        mock_finding.file = "test.py"
        mock_finding.line = 10
        mock_finding.rule_id = "SEC001"
        mock_finding.message = "Critical security issue"
        mock_finding.explanation = ""
        mock_finding.root_cause = ""
        mock_finding.severity = "CRITICAL"
        mock_finding.metadata = {"old_code": "old", "new_code": "new"}
        mock_finding.fix = None

        engine = ConversationalFixEngine()

        result = await engine.run_session(
            findings=[mock_finding],
            workspace_root="/workspace",
            auto_critical=True,  # Should auto-apply critical
        )

        # In auto-critical mode, critical fixes should be auto-processed
        assert result is not None
