"""Tests for LLM-assisted fix suggestions."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.core.fix_engine.llm_suggester import (
    LLMFixSuggestion,
    CodeContext,
    LLMSuggester,
    FIX_PROMPT_TEMPLATE,
    create_llm_suggester,
)


class TestCodeContext:
    """Tests for CodeContext dataclass."""

    def test_from_file_detection(self, tmp_path):
        """Test language detection from file extension."""
        # Create test files
        py_file = tmp_path / "test.py"
        py_file.write_text("import os\nprint('test')\n")

        ctx = CodeContext.from_file(py_file)
        assert ctx.language == "python"

        js_file = tmp_path / "test.js"
        js_file.write_text("const x = 1;\n")
        ctx = CodeContext.from_file(js_file)
        assert ctx.language == "javascript"

        c_file = tmp_path / "test.c"
        c_file.write_text("#include <stdio.h>\n")
        ctx = CodeContext.from_file(c_file)
        assert ctx.language == "c"

    def test_from_file_extracts_imports(self, tmp_path):
        """Test import extraction from file."""
        py_file = tmp_path / "test.py"
        content = """import os
import sys
from pathlib import Path
import json

def main():
    pass
"""
        py_file.write_text(content)

        ctx = CodeContext.from_file(py_file)
        assert "import os" in ctx.imports
        assert "import sys" in ctx.imports
        assert "from pathlib import Path" in ctx.imports

    def test_get_relevant_code(self, tmp_path):
        """Test getting relevant code around a line."""
        py_file = tmp_path / "test.py"
        py_file.write_text("line1\nline2\nline3\nline4\nline5\nline6\nline7\n")

        ctx = CodeContext.from_file(py_file, target_line=4, context_lines=2)

        relevant = ctx.get_relevant_code(4, context_lines=2)
        # Should include lines around line 4 (1-indexed)
        assert "line3" in relevant or "line4" in relevant or "line5" in relevant

    def test_get_surrounding_code(self, tmp_path):
        """Test getting surrounding code."""
        py_file = tmp_path / "test.py"
        content = "\n".join([f"line{i}" for i in range(30)])
        py_file.write_text(content)

        ctx = CodeContext.from_file(py_file)
        surrounding = ctx.get_surrounding_code(max_lines=10)

        assert len(surrounding.split("\n")) <= 10

    def test_function_name_extraction(self, tmp_path):
        """Test function name extraction."""
        py_file = tmp_path / "test.py"
        content = """
def main():
    pass

class TestClass:
    def method(self):
        pass
"""
        py_file.write_text(content)

        ctx = CodeContext.from_file(py_file, target_line=6)

        # Should find the method at line 6
        assert ctx.function_name is not None


class TestLLMFixSuggestion:
    """Tests for LLMFixSuggestion dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        suggestion = LLMFixSuggestion(
            original_code="old = 100",
            suggested_code="old = MAX_VALUE",
            explanation="Use named constant",
            confidence=0.9,
            alternative_suggestions=["Use enum", "Use config"],
            rule_id="QUAL007",
        )

        data = suggestion.to_dict()

        assert data["original_code"] == "old = 100"
        assert data["suggested_code"] == "old = MAX_VALUE"
        assert data["explanation"] == "Use named constant"
        assert data["confidence"] == 0.9
        assert len(data["alternatives"]) == 2
        assert data["rule_id"] == "QUAL007"

    def test_default_values(self):
        """Test default values for optional fields."""
        suggestion = LLMFixSuggestion(
            original_code="old",
            suggested_code="new",
            explanation="Test",
        )

        assert suggestion.confidence == 0.8
        assert suggestion.alternative_suggestions == []
        assert suggestion.rule_id == ""


class TestLLMSuggester:
    """Tests for LLMSuggester class."""

    def test_initialization(self):
        """Test initialization with defaults."""
        suggester = LLMSuggester()

        assert suggester.llm_provider is None
        assert suggester.max_context_lines == 20

    def test_initialization_with_config(self):
        """Test initialization with custom config."""
        suggester = LLMSuggester(
            llm_provider=MagicMock(),
            max_context_lines=30,
        )

        assert suggester.llm_provider is not None
        assert suggester.max_context_lines == 30

    @pytest.mark.asyncio
    async def test_suggest_fix_without_llm(self, tmp_path):
        """Test fix suggestion when LLM is not available."""
        py_file = tmp_path / "test.py"
        py_file.write_text("print('hello')\n")

        suggester = LLMSuggester()

        class MockFinding:
            rule_id = "QUAL006"
            message = "Use logging instead of print"
            severity = MagicMock(value="warning")
            file = str(py_file)
            line = 1

        finding = MockFinding()
        suggestion = await suggester.suggest_fix(finding)

        assert suggestion is not None
        assert suggestion.rule_id == "QUAL006"
        assert suggestion.confidence == 0.0  # Mock mode
        assert "not configured" in suggestion.explanation

    @pytest.mark.asyncio
    async def test_batch_suggest(self, tmp_path):
        """Test batch suggestion generation."""
        # Create test files
        file1 = tmp_path / "test1.py"
        file1.write_text("print('a')\n")

        file2 = tmp_path / "test2.py"
        file2.write_text("except:\n")

        suggester = LLMSuggester()

        class MockFinding:
            def __init__(self, rule_id, file_path, line):
                self.rule_id = rule_id
                self.message = "Test"
                self.severity = MagicMock(value="warning")
                self.file = file_path
                self.line = line

        findings = [
            MockFinding("QUAL006", str(file1), 1),
            MockFinding("QUAL003", str(file2), 1),
        ]

        contexts = {
            str(file1): CodeContext.from_file(file1),
            str(file2): CodeContext.from_file(file2),
        }

        suggestions = await suggester.batch_suggest(findings, contexts)

        assert len(suggestions) == 2

    def test_build_prompt(self, tmp_path):
        """Test prompt building."""
        py_file = tmp_path / "test.py"
        content = "import os\nimport sys\nprint('test')\n"
        py_file.write_text(content)

        suggester = LLMSuggester(max_context_lines=20)

        class MockSeverity:
            value = "warning"

        class MockFinding:
            rule_id = "QUAL006"
            message = "Use logging"
            severity = MockSeverity()
            file = str(py_file)
            line = 3

        finding = MockFinding()
        context = CodeContext.from_file(py_file, target_line=3)

        prompt = suggester._build_prompt(finding, context)

        assert "QUAL006" in prompt
        assert "Use logging" in prompt
        assert "python" in prompt.lower()


class TestPromptTemplate:
    """Tests for FIX_PROMPT_TEMPLATE."""

    def test_template_format(self):
        """Test that template can be formatted."""
        formatted = FIX_PROMPT_TEMPLATE.format(
            rule_id="TEST001",
            severity="warning",
            message="Test message",
            file_path="src/test.py",
            line=10,
            original_code="old_code",
            surrounding_code="surrounding",
            language="python",
        )

        assert "TEST001" in formatted
        assert "warning" in formatted
        assert "Test message" in formatted
        assert "src/test.py" in formatted
        assert "10" in formatted
        assert "old_code" in formatted


class TestCreateLLMSuggester:
    """Tests for create_llm_suggester factory function."""

    def test_create_without_config(self):
        """Test creating suggester without config."""
        suggester = create_llm_suggester()
        assert suggester is not None
        assert suggester.llm_provider is None

    def test_create_with_config(self):
        """Test creating suggester with config."""
        config = {"model": "gpt-4"}
        suggester = create_llm_suggester(config)
        # May be None if gateway not available
        assert suggester is not None


class TestLLMSuggesterResponseParsing:
    """Tests for LLM response parsing."""

    def test_parse_full_response(self):
        """Test parsing a complete LLM response."""
        suggester = LLMSuggester()

        response = """EXPLANATION: This is the explanation
FIX: new_code = fixed_value
ALTERNATIVES: option1; option2; option3
CONFIDENCE: 0.85"""

        class MockFinding:
            rule_id = "TEST001"
            message = "Test"
            severity = MagicMock(value="warning")
            file = "test.py"
            line = 1

        class MockContext:
            def get_relevant_code(self, line, context=0):
                return "old_code"

        suggestion = suggester._parse_llm_response(
            response,
            MockFinding(),
            MockContext(),
        )

        assert suggestion.explanation == "This is the explanation"
        assert suggestion.suggested_code == "new_code = fixed_value"
        assert len(suggestion.alternative_suggestions) == 3
        assert suggestion.confidence == 0.85

    def test_parse_partial_response(self):
        """Test parsing incomplete LLM response."""
        suggester = LLMSuggester()

        response = """EXPLANATION: Brief explanation
FIX: fixed_code"""

        class MockFinding:
            rule_id = "TEST001"
            message = "Test"
            severity = MagicMock(value="warning")
            file = "test.py"
            line = 1

        class MockContext:
            def get_relevant_code(self, line, context=0):
                return "old_code"

        suggestion = suggester._parse_llm_response(
            response,
            MockFinding(),
            MockContext(),
        )

        assert suggestion.explanation == "Brief explanation"
        assert suggestion.suggested_code == "fixed_code"
        assert suggestion.confidence == 0.8  # Default

    def test_parse_invalid_confidence(self):
        """Test parsing with invalid confidence value."""
        suggester = LLMSuggester()

        response = """CONFIDENCE: not_a_number"""

        class MockFinding:
            rule_id = "TEST001"
            message = "Test"
            severity = MagicMock(value="warning")
            file = "test.py"
            line = 1

        class MockContext:
            def get_relevant_code(self, line, context=0):
                return "old_code"

        suggestion = suggester._parse_llm_response(
            response,
            MockFinding(),
            MockContext(),
        )

        assert suggestion.confidence == 0.8  # Falls back to default


class TestLLMSuggesterEdgeCases:
    """Edge case tests for LLMSuggester."""

    @pytest.mark.asyncio
    async def test_suggest_fix_with_none_context(self, tmp_path):
        """Test fix suggestion when context creation fails."""
        suggester = LLMSuggester()

        class MockFinding:
            rule_id = "TEST001"
            message = "Test"
            severity = MagicMock(value="warning")
            file = "/nonexistent/file.py"
            line = 1

        # Should fall back to mock suggestion
        suggestion = await suggester.suggest_fix(MockFinding())
        assert suggestion is not None

    @pytest.mark.asyncio
    async def test_suggest_fix_handles_llm_error(self, tmp_path):
        """Test that LLM errors are handled gracefully."""
        py_file = tmp_path / "test.py"
        py_file.write_text("print('test')\n")

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(side_effect=Exception("LLM Error"))

        suggester = LLMSuggester(llm_provider=mock_llm)

        class MockFinding:
            rule_id = "TEST001"
            message = "Test"
            severity = MagicMock(value="warning")
            file = str(py_file)
            line = 1

        # Should fall back to mock suggestion
        suggestion = await suggester.suggest_fix(MockFinding())
        assert suggestion is not None
        assert suggestion.confidence == 0.0  # Fallback mode
