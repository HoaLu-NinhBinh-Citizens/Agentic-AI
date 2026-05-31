"""Production-ready tests for LLM integration.

Tests cover:
- Retry logic with exponential backoff
- Cost tracking and estimation
- Error handling and fallback behavior
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.core.fix_engine.llm_suggester import (
    LLMSuggester,
    LLMFixSuggestion,
    LLMSuggestionStats,
    CodeContext,
)
from src.infrastructure.llm.adapters import (
    LLMResponse,
    MockLLMProvider,
    RateLimitError,
    ServiceUnavailableError,
    calculate_cost,
    generate_with_retry,
)


class MockFinding:
    """Mock finding for testing."""
    def __init__(
        self,
        rule_id: str = "TEST001",
        message: str = "Test issue",
        file: str = "test.py",
        line: int = 10
    ):
        self.rule_id = rule_id
        self.message = message
        self.file = file
        self.line = line
        self.severity = "medium"


class MockProviderWithErrors:
    """Mock provider that raises specific errors."""
    def __init__(
        self,
        error_types: list[type[Exception]],
        success_response: str = "Success response"
    ):
        self.error_types = error_types
        self.success_response = success_response
        self.provider_name = "mock_error"
        self.model = "mock-model"
        self._call_count = 0

    def is_available(self) -> bool:
        return True

    async def generate(self, **kwargs):
        if self._call_count < len(self.error_types):
            error_class = self.error_types[self._call_count]
            self._call_count += 1
            raise error_class()
        return LLMResponse(
            content=self.success_response,
            model=self.model,
            tokens_used=50,
            finish_reason="stop",
        )


class TestCostTracking:
    """Tests for cost tracking functionality."""

    def test_stats_initialization(self):
        """Test LLMSuggestionStats initializes with zeros."""
        stats = LLMSuggestionStats()
        assert stats.total_calls == 0
        assert stats.successful_calls == 0
        assert stats.failed_calls == 0
        assert stats.total_tokens == 0
        assert stats.total_cost == 0.0

    def test_record_success(self):
        """Test recording successful calls."""
        stats = LLMSuggestionStats()
        stats.record_success(tokens=100, cost=0.001)
        assert stats.total_calls == 1
        assert stats.successful_calls == 1
        assert stats.total_tokens == 100
        assert stats.total_cost == 0.001

    def test_record_failure(self):
        """Test recording failed calls."""
        stats = LLMSuggestionStats()
        stats.record_failure()
        assert stats.total_calls == 1
        assert stats.failed_calls == 1

    def test_success_rate(self):
        """Test success rate calculation."""
        stats = LLMSuggestionStats()
        stats.record_success(tokens=100, cost=0.001)
        stats.record_success(tokens=100, cost=0.001)
        stats.record_failure()
        assert stats.success_rate == pytest.approx(0.666, rel=0.01)

    def test_success_rate_zero_calls(self):
        """Test success rate with no calls."""
        stats = LLMSuggestionStats()
        assert stats.success_rate == 0.0

    def test_to_dict(self):
        """Test converting stats to dictionary."""
        stats = LLMSuggestionStats()
        stats.record_success(tokens=100, cost=0.001)
        d = stats.to_dict()
        assert "total_calls" in d
        assert "successful_calls" in d
        assert "total_tokens" in d
        assert "total_cost" in d
        assert "success_rate" in d


class TestCostCalculation:
    """Tests for cost calculation utilities."""

    def test_calculate_cost_gpt4o_mini(self):
        """Test cost calculation for gpt-4o-mini."""
        cost = calculate_cost("gpt-4o-mini", 1000, 500, "openai")
        expected = (1000 / 1_000_000) * 0.15 + (500 / 1_000_000) * 0.6
        assert cost == pytest.approx(expected, rel=0.001)

    def test_calculate_cost_gpt4o(self):
        """Test cost calculation for gpt-4o."""
        cost = calculate_cost("gpt-4o", 1000, 500, "openai")
        expected = (1000 / 1_000_000) * 2.5 + (500 / 1_000_000) * 10.0
        assert cost == pytest.approx(expected, rel=0.001)

    def test_calculate_cost_anthropic(self):
        """Test cost calculation for Claude."""
        cost = calculate_cost("claude-sonnet-4-20250514", 1000, 500, "anthropic")
        expected = (1000 / 1_000_000) * 3.0 + (500 / 1_000_000) * 15.0
        assert cost == pytest.approx(expected, rel=0.001)

    def test_calculate_cost_unknown_model(self):
        """Test cost calculation for unknown model returns 0."""
        cost = calculate_cost("unknown-model", 1000, 500, "openai")
        assert cost == 0.0


class TestRetryLogic:
    """Tests for retry logic with exponential backoff."""

    @pytest.mark.asyncio
    async def test_successful_call_no_retry(self):
        """Test successful call doesn't trigger retry."""
        mock_provider = MockLLMProvider(response_text="Success")
        response = await generate_with_retry(mock_provider, "test prompt")
        assert "Success" in response.content
        assert response.model == "mock-model"

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit(self):
        """Test retry on rate limit error."""
        # Pass classes, not instances
        provider = MockProviderWithErrors(
            [RateLimitError, RateLimitError, RateLimitError],
            "Success after retries"
        )
        
        with pytest.raises(RateLimitError):
            await generate_with_retry(provider, "test", max_retries=3, backoff_base=0.01)

    @pytest.mark.asyncio
    async def test_retry_on_service_unavailable(self):
        """Test retry on service unavailable error."""
        # Pass classes, not instances
        provider = MockProviderWithErrors(
            [ServiceUnavailableError, ServiceUnavailableError],
            "Success after retries"
        )
        
        with pytest.raises(ServiceUnavailableError):
            await generate_with_retry(provider, "test", max_retries=2, backoff_base=0.01)

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_third_attempt(self):
        """Test that retry succeeds on third attempt."""
        # First two calls fail with RateLimitError, third succeeds
        provider = MockProviderWithErrors(
            [RateLimitError, RateLimitError],
            "Final success"
        )
        
        response = await generate_with_retry(provider, "test", max_retries=3, backoff_base=0.01)
        assert "Final success" in response.content

    @pytest.mark.asyncio
    async def test_non_retryable_error_breaks_early(self):
        """Test that non-retryable errors break retry loop early."""
        class OtherError(Exception):
            pass
        
        # Non-retryable error breaks immediately
        provider = MockProviderWithErrors([OtherError], "Should not reach")
        
        with pytest.raises(OtherError):
            await generate_with_retry(provider, "test", max_retries=3, backoff_base=0.01)


class TestLLMSuggesterWithRetry:
    """Tests for LLMSuggester retry and cost tracking."""

    @pytest.mark.asyncio
    async def test_suggester_tracks_stats_on_success(self):
        """Test suggester tracks stats on successful call."""
        mock_provider = MockLLMProvider(response_text="Success")
        suggester = LLMSuggester(
            provider=mock_provider,
            enable_llm=True,
            max_retries=1
        )
        
        finding = MockFinding()
        context = CodeContext(
            file_path="test.py",
            surrounding_lines=["def foo():", "    x = 1"],
            language="python",
        )
        
        result = await suggester.suggest_fix(finding, context)
        
        assert result is not None
        stats = suggester.stats_summary
        assert stats.total_calls == 1
        assert stats.successful_calls == 1

    @pytest.mark.asyncio
    async def test_suggester_tracks_stats_on_failure(self):
        """Test suggester tracks stats on failed call."""
        class FailingProvider:
            provider_name = "failing"
            model = "mock"
            
            def is_available(self):
                return True
            
            async def generate(self, **kwargs):
                raise Exception("API error")
        
        suggester = LLMSuggester(
            provider=FailingProvider(),
            enable_llm=True,
            max_retries=1
        )
        
        finding = MockFinding()
        context = CodeContext(
            file_path="test.py",
            surrounding_lines=["def foo():", "    x = 1"],
            language="python",
        )
        
        result = await suggester.suggest_fix(finding, context)
        
        assert result is not None
        stats = suggester.stats_summary
        assert stats.total_calls == 1
        assert stats.failed_calls == 1

    @pytest.mark.asyncio
    async def test_suggester_falls_back_on_rate_limit(self):
        """Test suggester falls back to template on rate limit."""
        provider = MockProviderWithErrors([RateLimitError()], "Success")
        suggester = LLMSuggester(
            provider=provider,
            enable_llm=True,
            max_retries=1
        )
        
        finding = MockFinding()
        context = CodeContext(
            file_path="test.py",
            surrounding_lines=["def foo():", "    x = 1"],
            language="python",
        )
        
        result = await suggester.suggest_fix(finding, context)
        
        assert result is not None
        assert result.confidence == 0.3
        stats = suggester.stats_summary
        assert stats.failed_calls == 1

    @pytest.mark.asyncio
    async def test_suggester_with_custom_retry_settings(self):
        """Test suggester with custom retry settings."""
        suggester = LLMSuggester(
            provider=MockLLMProvider(response_text="Success"),
            enable_llm=True,
            max_retries=5,
            backoff_base=1.5
        )
        
        assert suggester.max_retries == 5
        assert suggester.backoff_base == 1.5


class TestLLMSuggesterIntegration:
    """Integration tests for production-ready LLM suggester."""

    @pytest.mark.asyncio
    async def test_full_success_flow(self):
        """Test complete success flow with stats tracking."""
        # Create a mock provider that returns properly formatted response
        class FormatMockProvider:
            provider_name = "format_mock"
            model = "mock-model"
            
            def is_available(self):
                return True
            
            async def generate(self, **kwargs):
                return LLMResponse(
                    content="""EXPLANATION: Fixed issue
FIX: corrected = True
ALTERNATIVES: None
CONFIDENCE: 0.95""",
                    model="mock-model",
                    tokens_used=100,
                    finish_reason="stop",
                )
        
        suggester = LLMSuggester(provider=FormatMockProvider())
        
        finding = MockFinding()
        context = CodeContext(
            file_path="test.py",
            surrounding_lines=["original_code = False"],
            language="python",
        )
        
        result = await suggester.suggest_fix(finding, context)
        
        assert result is not None
        assert result.explanation == "Fixed issue"
        assert result.confidence == 0.95  # Parse CONFIDENCE from response
        
        stats = suggester.stats_summary
        assert stats.successful_calls == 1
        assert stats.total_tokens > 0
        assert stats.total_cost >= 0

    @pytest.mark.asyncio
    async def test_llm_disabled_tracks_template_call(self):
        """Test that disabled LLM doesn't affect stats."""
        suggester = LLMSuggester(enable_llm=False)
        
        finding = MockFinding()
        context = CodeContext(
            file_path="test.py",
            surrounding_lines=["code"],
            language="python",
        )
        
        result = await suggester.suggest_fix(finding, context)
        
        assert result is not None
        stats = suggester.stats_summary
        assert stats.total_calls == 0

    @pytest.mark.asyncio
    async def test_batch_suggest_tracks_all_stats(self):
        """Test batch suggest tracks stats for all calls."""
        mock_provider = MockLLMProvider(response_text="""EXPLANATION: Fix
FIX: code = True
CONFIDENCE: 0.8""")
        
        suggester = LLMSuggester(provider=mock_provider)
        
        findings = [
            MockFinding(rule_id="R1", line=10),
            MockFinding(rule_id="R2", line=20),
        ]
        contexts = {
            "test.py": CodeContext(
                file_path="test.py",
                surrounding_lines=["code1", "code2"],
                language="python",
            )
        }
        
        results = await suggester.batch_suggest(findings, contexts)
        
        assert len(results) == 2
        stats = suggester.stats_summary
        assert stats.total_calls == 2
        assert stats.successful_calls == 2
