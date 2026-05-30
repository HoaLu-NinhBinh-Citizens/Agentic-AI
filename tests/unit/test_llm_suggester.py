"""Tests for LLMSuggester with real LLM integration."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.core.fix_engine.llm_suggester import (
    LLMSuggester,
    LLMFixSuggestion,
    CodeContext,
    create_llm_suggester,
)
from src.infrastructure.llm.adapters import (
    MockLLMProvider,
    OpenAIAdapter,
    ClaudeAdapter,
)


class MockFinding:
    """Mock finding for testing."""
    def __init__(self, rule_id="TEST001", message="Test issue", file="test.py", line=10):
        self.rule_id = rule_id
        self.message = message
        self.file = file
        self.line = line
        self.severity = "medium"


class TestLLMSuggester:
    """Tests for LLMSuggester class."""

    @pytest.mark.asyncio
    async def test_suggester_without_llm(self):
        """Test suggester falls back to template without LLM."""
        suggester = LLMSuggester(provider=None, enable_llm=False)
        finding = MockFinding()
        context = CodeContext(
            file_path="test.py",
            surrounding_lines=["def foo():", "    x = 1"],
            language="python",
        )

        result = await suggester.suggest_fix(finding, context)

        assert result is not None
        assert result.confidence == 0.3
        assert "not configured" in result.explanation

    @pytest.mark.asyncio
    async def test_suggester_with_mock_provider(self):
        """Test suggester with mock provider."""
        mock_provider = MockLLMProvider(response_text="EXPLANATION: Test fix")
        suggester = LLMSuggester(provider=mock_provider, enable_llm=True)
        finding = MockFinding()
        context = CodeContext(
            file_path="test.py",
            surrounding_lines=["def foo():", "    x = 1"],
            language="python",
        )

        result = await suggester.suggest_fix(finding, context)

        assert result is not None
        assert isinstance(result, LLMFixSuggestion)

    def test_suggester_is_llm_enabled_property(self):
        """Test is_llm_enabled property."""
        suggester_disabled = LLMSuggester(enable_llm=False)
        assert not suggester_disabled.is_llm_enabled

        suggester_no_provider = LLMSuggester(provider=None, enable_llm=True)
        assert not suggester_no_provider.is_llm_enabled

        suggester_mock = LLMSuggester(provider=MockLLMProvider(), enable_llm=True)
        assert suggester_mock.is_llm_enabled

    def test_suggester_provider_property(self):
        """Test provider property access."""
        mock = MockLLMProvider()
        suggester = LLMSuggester(provider=mock)
        assert suggester.provider is mock

        suggester_none = LLMSuggester(provider=None)
        assert suggester_none.provider is None


class TestCreateLLMSuggester:
    """Tests for create_llm_suggester factory function."""

    def test_create_with_auto_provider(self):
        """Test creating suggester with auto provider detection."""
        suggester = create_llm_suggester({"provider": "auto"})
        # Should either get a provider or None based on env
        assert suggester is not None

    def test_create_with_explicit_provider(self):
        """Test creating suggester with explicit provider."""
        suggester = create_llm_suggester({"provider": "openai", "api_key": "test"})
        assert suggester.provider is not None
        assert isinstance(suggester.provider, OpenAIAdapter)

    def test_create_with_llm_disabled(self):
        """Test creating suggester with LLM disabled."""
        suggester = create_llm_suggester({"enable_llm": False})
        assert not suggester.is_llm_enabled

    def test_create_with_config(self):
        """Test creating suggester with full config."""
        suggester = create_llm_suggester({
            "provider": "anthropic",
            "api_key": "test-key",
            "model": "claude-sonnet",
            "enable_llm": True,
        })
        assert suggester.is_llm_enabled


class TestCodeContext:
    """Tests for CodeContext class."""

    def test_context_creation(self):
        """Test basic CodeContext creation."""
        context = CodeContext(
            file_path="test.py",
            function_name="test_func",
            surrounding_lines=["line1", "line2", "line3"],
            language="python",
        )
        assert context.file_path == "test.py"
        assert context.language == "python"

    def test_get_relevant_code(self):
        """Test getting relevant code around a line."""
        context = CodeContext(
            file_path="test.py",
            surrounding_lines=["line0", "line1", "TARGET", "line3", "line4"],
            language="python",
        )
        # Note: line numbers are 1-based
        code = context.get_relevant_code(target_line=3, context_lines=1)
        assert "TARGET" in code

    def test_get_surrounding_code(self):
        """Test getting surrounding code."""
        context = CodeContext(
            file_path="test.py",
            surrounding_lines=[f"line{i}" for i in range(10)],
        )
        code = context.get_surrounding_code(max_lines=5)
        assert len(code.split("\n")) <= 5


class TestLLMFixSuggestion:
    """Tests for LLMFixSuggestion dataclass."""

    def test_suggestion_creation(self):
        """Test LLMFixSuggestion creation."""
        suggestion = LLMFixSuggestion(
            original_code="x = 1",
            suggested_code="x = 2",
            explanation="Changed value",
            confidence=0.9,
            rule_id="TEST001",
        )
        assert suggestion.original_code == "x = 1"
        assert suggestion.suggested_code == "x = 2"
        assert suggestion.confidence == 0.9

    def test_suggestion_to_dict(self):
        """Test converting suggestion to dict."""
        suggestion = LLMFixSuggestion(
            original_code="x = 1",
            suggested_code="x = 2",
            explanation="Changed value",
        )
        d = suggestion.to_dict()
        assert "original_code" in d
        assert "suggested_code" in d
        assert d["confidence"] == 0.8  # default


@pytest.mark.asyncio
class TestLLMSuggesterIntegration:
    """Integration tests for LLMSuggester with real providers."""

    async def test_suggest_fix_with_mock_llm_parses_response(self):
        """Test that suggester correctly parses mock LLM response."""
        # Mock provider that returns a properly formatted response
        class FormatMockProvider:
            provider_name = "format_mock"
            is_available = lambda self: True

            async def generate(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2048):
                from src.infrastructure.llm.adapters import LLMResponse
                return LLMResponse(
                    content="""EXPLANATION: This is a test fix
FIX: corrected_code = True
ALTERNATIVES: None
CONFIDENCE: 0.9""",
                    model="mock",
                    tokens_used=50,
                    finish_reason="stop",
                )

        suggester = LLMSuggester(provider=FormatMockProvider())

        finding = MockFinding(rule_id="TEST001", message="Test issue")
        context = CodeContext(
            file_path="test.py",
            surrounding_lines=["original_code = False"],
            language="python",
        )

        result = await suggester.suggest_fix(finding, context)

        assert result is not None
        assert result.explanation == "This is a test fix"
        assert result.suggested_code == "corrected_code = True"
        assert result.confidence == 0.9

    async def test_suggester_handles_llm_error_gracefully(self):
        """Test that suggester falls back on LLM error."""
        class ErrorProvider:
            provider_name = "error"
            is_available = lambda self: True

            async def generate(self, **kwargs):
                raise Exception("LLM API error")

        suggester = LLMSuggester(provider=ErrorProvider())
        finding = MockFinding()
        context = CodeContext(
            file_path="test.py",
            surrounding_lines=["code"],
        )

        result = await suggester.suggest_fix(finding, context)

        # Should fall back to template
        assert result is not None
        assert result.confidence == 0.3
