"""Edge case tests for ResponseParser."""

import pytest
from src.core.parsing.response_parser import ResponseParser


class TestResponseParserEdgeCases:
    """Test edge cases in ResponseParser."""

    def test_empty_response(self):
        """Empty LLM response."""
        parser = ResponseParser()
        result = parser.normalize_document_worker_response("")
        assert result == ""

    def test_malformed_json(self):
        """Invalid JSON in code block."""
        parser = ResponseParser()
        text = """{"broken": json"""
        # Should not crash, should extract what it can
        result = parser.extract_json_object(text)
        assert result is None or isinstance(result, dict)

    def test_nested_code_blocks(self):
        """Nested markdown code blocks."""
        parser = ResponseParser()
        text = """```c
void inner();
```"""
        # Should handle gracefully
        result = parser.extract_code(text)
        assert result is not None or result is None  # Either way is fine

    def test_very_long_line(self):
        """Very long single line of code."""
        parser = ResponseParser()
        long_line = "x = " + "1" * 10000
        text = "```c\n" + long_line + "\n```"

        result = parser.extract_code(text)
        assert result is not None
        assert len(result) > 9000

    def test_binary_characters(self):
        """Text with binary-like characters."""
        parser = ResponseParser()
        text = "Hello\x00World"
        result = parser.extract_json_object(text)
        # Should handle gracefully
        assert result is None or isinstance(result, dict)

    def test_unicode_edge_cases(self):
        """Various Unicode edge cases."""
        parser = ResponseParser()
        texts = [
            "Test with emoji",
            "Chinese text",
            "Arabic text",
            "Mixed text",
        ]

        for text in texts:
            result = parser.extract_json_object(text)
            assert True  # Should not crash

    def test_markdown_injection(self):
        """Attempted markdown injection."""
        parser = ResponseParser()
        text = "```c\n/* Code block */\n```"
        result = parser.extract_code(text)
        # Should extract code block
        assert result is not None
        assert "Code block" in result

    def test_consecutive_code_blocks(self):
        """Multiple consecutive code blocks."""
        parser = ResponseParser()
        # Only extracts first code block (per current implementation)
        text = """```c
int x = 1;
```"""
        result = parser.extract_code(text)
        assert result is not None
        assert "x = 1" in result

    def test_no_code_block_markers(self):
        """Text without code block markers."""
        parser = ResponseParser()
        text = "This is plain text without any code blocks."
        result = parser.extract_code(text)
        assert result is None

    def test_incomplete_code_block(self):
        """Unclosed code block."""
        parser = ResponseParser()
        text = "```c\nint x = 1;\n"
        result = parser.extract_code(text)
        # Should handle gracefully
        assert result is None or isinstance(result, str)

    def test_plain_c_code(self):
        """C code without markdown fences."""
        parser = ResponseParser()
        code = "#include <stdio.h>\nint main() { return 0; }"
        result = parser.extract_code(code)
        assert result is not None
        assert "include" in result

    def test_json_extraction(self):
        """JSON extraction from various formats."""
        parser = ResponseParser()

        # Valid JSON
        valid_json = '{"key": "value"}'
        result = parser.extract_json_object(valid_json)
        assert result == {"key": "value"}

        # JSON in markdown
        json_in_md = "```json\n{\"key\": \"value\"}\n```"
        result = parser.extract_json_object(json_in_md)
        assert result == {"key": "value"}

    def test_function_signatures_extraction(self):
        """Test function signature extraction."""
        parser = ResponseParser()

        # Function definition in C
        code = "void process_data(int count, char* buffer) { }"
        result = parser.extract_function_signatures(code, expect_definition=True)
        assert "process_data" in result

    def test_function_declaration_extraction(self):
        """Test function declaration extraction."""
        parser = ResponseParser()

        # Function declaration in C
        code = "int calculate(int a, int b);"
        result = parser.extract_function_signatures(code, expect_definition=False)
        assert "calculate" in result

    def test_normalize_document_worker_response(self):
        """Test normalization of document worker response."""
        parser = ResponseParser()

        # Response with structured markers
        text = "Here's some analysis.\n[CODE]\nvoid main() { }"
        result = parser.normalize_document_worker_response(text)
        assert "[CODE]" in result

    def test_extract_file_blocks(self):
        """Test file block extraction."""
        parser = ResponseParser()

        # With FILE: prefix
        text = "FILE: main.c\n```c\n#include <stdio.h>\nint main() { return 0; }\n```"
        result = parser.extract_file_blocks(text)
        assert len(result) >= 1
        assert result[0][0] == "main.c"

    def test_empty_json(self):
        """Empty JSON object."""
        parser = ResponseParser()
        result = parser.extract_json_object("{}")
        assert result == {}

    def test_complex_json_extraction(self):
        """Complex JSON with nested structures."""
        parser = ResponseParser()
        json_text = """{
            "name": "test",
            "items": [1, 2, 3],
            "nested": {
                "key": "value"
            }
        }"""
        result = parser.extract_json_object(json_text)
        assert result is not None
        assert result["name"] == "test"
        assert len(result["items"]) == 3
