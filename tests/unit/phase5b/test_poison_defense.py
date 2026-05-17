"""Unit tests for poison tool defense.

Tests cover:
- Poison tool detection and quarantine
- Trust score management
- Dangerous pattern detection
"""

from __future__ import annotations

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from core.runtime.enterprise.poison_defense import (
    PoisonToolDefense,
    ToolOutputSanitizer,
    TrustScoreManager,
    SanitizationResult,
    SanitizationAction,
    TrustScore,
)


# ============================================================================
# ToolOutputSanitizer Tests
# ============================================================================

class TestToolOutputSanitizer:
    """Test tool output sanitization."""

    @pytest.fixture
    def sanitizer(self):
        """Create sanitizer with default patterns."""
        return ToolOutputSanitizer()

    @pytest.fixture
    def custom_sanitizer(self):
        """Create sanitizer with custom patterns."""
        return ToolOutputSanitizer(
            max_output_size=1024,
            dangerous_patterns=[r"<script", r"eval\(", r"__import__"],
        )

    def test_sanitize_safe_output(self, sanitizer):
        """Test sanitizing safe output."""
        result = sanitizer.sanitize(
            {"status": "success", "data": "hello world"},
            tool_name="test_tool",
        )
        
        assert result.action == SanitizationAction.ALLOW
        assert result.sanitized_output is not None

    def test_sanitize_none_output(self, sanitizer):
        """Test sanitizing None output."""
        result = sanitizer.sanitize(None, tool_name="test_tool")
        
        assert result.action == SanitizationAction.ALLOW
        assert result.sanitized_output is None

    def test_sanitize_string_output(self, sanitizer):
        """Test sanitizing string output."""
        result = sanitizer.sanitize("Hello, World!", tool_name="test_tool")
        
        assert result.action == SanitizationAction.ALLOW
        assert result.sanitized_output == "Hello, World!"

    def test_sanitize_dangerous_script_tag(self, sanitizer):
        """Test detection of script tag injection."""
        result = sanitizer.sanitize(
            "<script>alert('xss')</script>",
            tool_name="test_tool",
        )
        
        assert result.action == SanitizationAction.QUARANTINE
        assert len(result.issues) > 0
        assert any("script" in issue.lower() for issue in result.issues)

    def test_sanitize_dangerous_javascript_protocol(self, sanitizer):
        """Test detection of javascript: protocol."""
        result = sanitizer.sanitize(
            '<a href="javascript:void(0)">click</a>',
            tool_name="test_tool",
        )
        
        assert result.action == SanitizationAction.QUARANTINE

    def test_sanitize_dangerous_event_handler(self, sanitizer):
        """Test detection of inline event handlers."""
        result = sanitizer.sanitize(
            '<img src=x onerror="alert(1)">',
            tool_name="test_tool",
        )
        
        assert result.action == SanitizationAction.QUARANTINE

    def test_sanitize_dangerous_eval(self, sanitizer):
        """Test detection of eval()."""
        result = sanitizer.sanitize(
            'result = eval("1+1")',
            tool_name="test_tool",
        )
        
        assert result.action == SanitizationAction.QUARANTINE

    def test_sanitize_dangerous_import(self, sanitizer):
        """Test detection of __import__()."""
        result = sanitizer.sanitize(
            '__import__("os").system("ls")',
            tool_name="test_tool",
        )
        
        assert result.action == SanitizationAction.QUARANTINE

    def test_sanitize_dangerous_subprocess(self, sanitizer):
        """Test detection of subprocess calls."""
        result = sanitizer.sanitize(
            'subprocess.run(["ls", "-la"])',
            tool_name="test_tool",
        )
        
        assert result.action == SanitizationAction.QUARANTINE

    def test_sanitize_dangerous_os_system(self, sanitizer):
        """Test detection of os.system()."""
        result = sanitizer.sanitize(
            'os.system("rm -rf /")',
            tool_name="test_tool",
        )
        
        assert result.action == SanitizationAction.QUARANTINE

    def test_sanitize_dangerous_exec(self, sanitizer):
        """Test detection of exec()."""
        result = sanitizer.sanitize(
            'exec("malicious_code")',
            tool_name="test_tool",
        )
        
        assert result.action == SanitizationAction.QUARANTINE

    def test_sanitize_output_too_large(self, custom_sanitizer):
        """Test truncation of oversized output."""
        large_output = "x" * 2000
        
        result = custom_sanitizer.sanitize(large_output, tool_name="test_tool")
        
        assert result.action == SanitizationAction.QUARANTINE
        assert len(result.sanitized_output) <= 1024

    def test_sanitize_custom_patterns(self, custom_sanitizer):
        """Test custom dangerous patterns."""
        result = custom_sanitizer.sanitize(
            "<script>alert(1)</script>",
            tool_name="test_tool",
        )
        
        assert result.action == SanitizationAction.QUARANTINE

    def test_sanitize_with_schema_validation(self, sanitizer):
        """Test sanitization with schema validation."""
        schema = {
            "required": ["status", "data"],
        }
        
        # Valid output
        valid_output = {"status": "ok", "data": "result"}
        result = sanitizer.sanitize(valid_output, schema=schema, tool_name="test_tool")
        assert result.action == SanitizationAction.ALLOW
        
        # Invalid output - missing required field
        invalid_output = {"status": "ok"}  # Missing "data"
        result = sanitizer.sanitize(invalid_output, schema=schema, tool_name="test_tool")
        assert result.action == SanitizationAction.QUARANTINE

    def test_sanitize_case_insensitive(self, sanitizer):
        """Test that pattern matching is case-insensitive."""
        result = sanitizer.sanitize(
            "<SCRIPT>alert(1)</SCRIPT>",
            tool_name="test_tool",
        )
        
        assert result.action == SanitizationAction.QUARANTINE


# ============================================================================
# TrustScoreManager Tests
# ============================================================================

class TestTrustScoreManager:
    """Test trust score management."""

    @pytest.fixture
    def manager(self):
        """Create trust score manager."""
        return TrustScoreManager(
            initial_score=0.8,
            quarantine_threshold=0.3,
            reject_threshold=0.1,
        )

    def test_initial_score(self, manager):
        """Test initial trust score."""
        score = manager.get_score("new_tool")
        
        assert score.score == 0.8

    def test_record_success(self, manager):
        """Test recording successful execution."""
        manager.record_success("test_tool")
        manager.record_success("test_tool")
        
        score = manager.get_score("test_tool")
        
        assert score.success_count == 2

    def test_record_failure_normal(self, manager):
        """Test recording normal failure."""
        manager.record_failure("test_tool", "normal")
        
        score = manager.get_score("test_tool")
        
        assert score.failure_count == 1

    def test_record_failure_severe(self, manager):
        """Test recording severe failure."""
        manager.record_failure("test_tool", "severe")
        
        score = manager.get_score("test_tool")
        
        assert score.score < 0.8

    def test_record_failure_critical(self, manager):
        """Test recording critical failure."""
        manager.record_failure("test_tool", "critical")
        
        score = manager.get_score("test_tool")
        
        assert score.score == 0.0

    def test_score_recalculation(self, manager):
        """Test score recalculation based on history."""
        for _ in range(10):
            manager.record_success("test_tool")
        
        score = manager.get_score("test_tool")
        
        # 10 successes, 0 failures = 100% success rate
        assert score.score == 1.0

    def test_quarantine_threshold(self, manager):
        """Test quarantine threshold."""
        # Record many failures to drop score below quarantine threshold
        for _ in range(10):
            manager.record_failure("test_tool", "normal")
        
        is_quarantined = manager.is_quarantined("test_tool")
        
        assert is_quarantined is True

    def test_reject_threshold(self, manager):
        """Test reject threshold."""
        # Record many severe failures
        for _ in range(5):
            manager.record_failure("test_tool", "severe")
        
        is_rejected = manager.is_rejected("test_tool")
        
        assert is_rejected is True

    def test_manual_quarantine(self, manager):
        """Test manual quarantine."""
        manager.quarantine("test_tool", 300)
        
        assert manager.is_quarantined("test_tool") is True

    def test_remove_quarantine(self, manager):
        """Test removing quarantine."""
        manager.quarantine("test_tool", 300)
        manager.remove_quarantine("test_tool")
        
        assert manager.is_quarantined("test_tool") is False

    def test_reset_score(self, manager):
        """Test resetting trust score."""
        manager.record_success("test_tool")
        manager.reset_score("test_tool")
        
        score = manager.get_score("test_tool")
        
        assert score.score == 0.8
        assert score.success_count == 0
        assert score.failure_count == 0


# ============================================================================
# PoisonToolDefense Integration Tests
# ============================================================================

class TestPoisonToolDefense:
    """Test full poison tool defense system."""

    @pytest.fixture
    def defense(self):
        """Create poison tool defense."""
        sanitizer = ToolOutputSanitizer()
        trust_manager = TrustScoreManager()
        return PoisonToolDefense(sanitizer, trust_manager)

    @pytest.mark.asyncio
    async def test_process_safe_output(self, defense):
        """Test processing safe output."""
        allowed, output, issues = await defense.process_output(
            "safe_tool",
            {"status": "success", "data": "result"},
        )
        
        assert allowed is True
        assert output is not None
        assert len(issues) == 0

    @pytest.mark.asyncio
    async def test_process_poisoned_output_quarantine(self, defense):
        """Test that poisoned output is quarantined."""
        allowed, output, issues = await defense.process_output(
            "poison_tool",
            "<script>alert('xss')</script>",
        )
        
        assert allowed is False
        assert len(issues) > 0

    @pytest.mark.asyncio
    async def test_process_output_trust_score_update(self, defense):
        """Test that trust score is updated after processing."""
        await defense.process_output("test_tool", {"status": "ok"})
        
        score = defense.get_trust_score("test_tool")
        
        assert score > 0.8  # Should increase with success

    @pytest.mark.asyncio
    async def test_tool_quarantine_after_poison(self, defense):
        """Test that tool is quarantined after poisoning."""
        # First poisoning
        await defense.process_output("bad_tool", "<script>alert(1)</script>")
        
        # Second attempt should be quarantined
        allowed, output, issues = await defense.process_output(
            "bad_tool",
            {"status": "ok"},
        )
        
        assert allowed is False
        assert any("quarantined" in issue.lower() for issue in issues)

    @pytest.mark.asyncio
    async def test_tool_rejected_at_low_score(self, defense):
        """Test that low-trust tool is rejected."""
        # Manually lower trust score
        defense._trust_manager.record_failure("low_trust_tool", "critical")
        defense._trust_manager.record_failure("low_trust_tool", "critical")
        defense._trust_manager.record_failure("low_trust_tool", "critical")
        
        allowed, output, issues = await defense.process_output(
            "low_trust_tool",
            {"status": "ok"},
        )
        
        assert allowed is False
        assert any("rejected" in issue.lower() for issue in issues)

    @pytest.mark.asyncio
    async def test_is_allowed(self, defense):
        """Test is_allowed check."""
        assert defense.is_allowed("new_tool") is True
        
        defense._trust_manager.quarantine("quarantined_tool", 300)
        assert defense.is_allowed("quarantined_tool") is False
        
        defense._trust_manager.reset_score("low_tool")
        defense._trust_manager.record_failure("low_tool", "critical")
        defense._trust_manager.record_failure("low_tool", "critical")
        assert defense.is_allowed("low_tool") is False

    @pytest.mark.asyncio
    async def test_multiple_tools_independent(self, defense):
        """Test that tool trust scores are independent."""
        await defense.process_output("tool_a", {"status": "ok"})
        await defense.process_output("tool_a", {"status": "ok"})
        await defense.process_output("tool_b", "<script>alert(1)</script>")
        
        score_a = defense.get_trust_score("tool_a")
        score_b = defense.get_trust_score("tool_b")
        
        assert score_a > score_b


# ============================================================================
# Edge Cases
# ============================================================================

class TestPoisonDefenseEdgeCases:
    """Test edge cases in poison defense."""

    @pytest.fixture
    def defense(self):
        """Create defense system."""
        return PoisonToolDefense()

    @pytest.mark.asyncio
    async def test_empty_output(self, defense):
        """Test handling empty output."""
        allowed, output, issues = await defense.process_output("tool", "")
        
        assert allowed is True

    @pytest.mark.asyncio
    async def test_unicode_output(self, defense):
        """Test handling unicode output."""
        allowed, output, issues = await defense.process_output(
            "tool",
            "Hello 世界 🌍",
        )
        
        assert allowed is True

    @pytest.mark.asyncio
    async def test_nested_json_output(self, defense):
        """Test handling nested JSON output."""
        output = {
            "status": "success",
            "data": {
                "nested": {
                    "deep": {
                        "value": 42
                    }
                }
            }
        }
        
        allowed, result, issues = await defense.process_output("tool", output)
        
        assert allowed is True
        assert result["data"]["nested"]["deep"]["value"] == 42

    @pytest.mark.asyncio
    async def test_unicode_xss_attempt(self, defense):
        """Test detection of unicode XSS attempts."""
        # Try various encodings
        result = defense._sanitizer.sanitize(
            '<img src=x onerror=\u0061lert(1)>',
            tool_name="test_tool",
        )
        
        # Should still catch event handlers
        assert result.action == SanitizationAction.QUARANTINE
