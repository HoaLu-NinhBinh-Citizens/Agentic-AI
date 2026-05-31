"""Tests for InlineCodeGenerator - 6.2.UTXX.

Tests inline code generation for common patterns like error handling, logging, etc.
"""

import pytest

from src.infrastructure.codegen.inline_generator import (
    InlineCodeGenerator,
    CodeGenerationRequest,
    CodeGenerationResult,
)


class TestCodeGenerationRequest:
    """Test CodeGenerationRequest dataclass."""
    
    def test_create_request(self):
        """Test creating a generation request."""
        request = CodeGenerationRequest(
            file_path="test.py",
            cursor_line=10,
            cursor_col=4,
            context_before="def process():",
            context_after="    pass",
            instruction="add error handling",
            language="python",
        )
        
        assert request.file_path == "test.py"
        assert request.cursor_line == 10
        assert request.cursor_col == 4
        assert request.context_before == "def process():"
        assert request.context_after == "    pass"
        assert request.instruction == "add error handling"
        assert request.language == "python"


class TestCodeGenerationResult:
    """Test CodeGenerationResult dataclass."""
    
    def test_create_result(self):
        """Test creating a generation result."""
        result = CodeGenerationResult(
            generated_code="try:\n    pass\nexcept Exception:\n    pass",
            inserted_lines=3,
            confidence=0.95,
            alternatives=["alt1", "alt2"],
        )
        
        assert result.generated_code == "try:\n    pass\nexcept Exception:\n    pass"
        assert result.inserted_lines == 3
        assert result.confidence == 0.95
        assert result.alternatives == ["alt1", "alt2"]
        assert result.error is None
    
    def test_result_with_error(self):
        """Test result with error."""
        result = CodeGenerationResult(
            generated_code="",
            inserted_lines=0,
            confidence=0.0,
            error="Cannot handle instruction",
        )
        
        assert result.error == "Cannot handle instruction"
        assert result.generated_code == ""


class TestInlineCodeGenerator:
    """Test InlineCodeGenerator class."""
    
    @pytest.fixture
    def generator(self):
        """Create an InlineCodeGenerator instance."""
        return InlineCodeGenerator()
    
    def test_init(self):
        """Test generator initialization."""
        gen = InlineCodeGenerator()
        
        assert gen.llm_provider is None
        assert "python" in gen._templates
        assert "javascript" in gen._templates
        assert "typescript" in gen._templates
    
    def test_init_with_llm_provider(self):
        """Test initialization with LLM provider."""
        mock_provider = object()
        gen = InlineCodeGenerator(llm_provider=mock_provider)
        
        assert gen.llm_provider is mock_provider
    
    def test_templates_contain_error_handling(self, generator):
        """Test that templates include error handling."""
        assert "error_handling" in generator._templates["python"]
        assert "error_handling" in generator._templates["javascript"]
        assert "error_handling" in generator._templates["typescript"]
    
    def test_templates_contain_logging(self, generator):
        """Test that templates include logging."""
        assert "logging" in generator._templates["python"]
        assert "logging" in generator._templates["javascript"]
        assert "logging" in generator._templates["c"]


class TestGenerateErrorHandling:
    """Test error handling code generation."""
    
    @pytest.fixture
    def generator(self):
        return InlineCodeGenerator()
    
    @pytest.fixture
    def python_request(self):
        """Create a Python error handling request."""
        return CodeGenerationRequest(
            file_path="test.py",
            cursor_line=10,
            cursor_col=4,
            context_before="def process():",
            context_after="    pass",
            instruction="add error handling",
            language="python",
        )
    
    @pytest.fixture
    def typescript_request(self):
        """Create a TypeScript error handling request."""
        return CodeGenerationRequest(
            file_path="test.ts",
            cursor_line=10,
            cursor_col=4,
            context_before="function process() {",
            context_after="}",
            instruction="add error handling",
            language="typescript",
        )
    
    def test_error_handling_python(self, generator, python_request):
        """Test error handling generation for Python."""
        result = generator._generate_error_handling(python_request)
        
        assert isinstance(result, CodeGenerationResult)
        assert "try:" in result.generated_code
        assert "except" in result.generated_code
        assert result.inserted_lines >= 3
        assert result.confidence >= 0.9
    
    def test_error_handling_typescript(self, generator, typescript_request):
        """Test error handling generation for TypeScript."""
        result = generator._generate_error_handling(typescript_request)
        
        assert isinstance(result, CodeGenerationResult)
        assert "try {" in result.generated_code
        assert "catch" in result.generated_code
        assert result.inserted_lines >= 3
    
    def test_error_handling_javascript(self, generator):
        """Test error handling generation for JavaScript."""
        request = CodeGenerationRequest(
            file_path="test.js",
            cursor_line=5,
            cursor_col=0,
            context_before="function doSomething() {",
            context_after="}",
            instruction="add try catch",
            language="javascript",
        )
        
        result = generator._generate_error_handling(request)
        
        assert "try {" in result.generated_code
        assert "catch" in result.generated_code
    
    def test_error_handling_alternatives(self, generator, python_request):
        """Test that error handling alternatives are generated."""
        result = generator._generate_error_handling(python_request)
        
        assert len(result.alternatives) >= 1


class TestGenerateLogging:
    """Test logging code generation."""
    
    @pytest.fixture
    def generator(self):
        return InlineCodeGenerator()
    
    def test_logging_python(self, generator):
        """Test logging generation for Python."""
        request = CodeGenerationRequest(
            file_path="test.py",
            cursor_line=5,
            cursor_col=0,
            context_before="def foo():",
            context_after="    return True",
            instruction="add logging",
            language="python",
        )
        
        result = generator._generate_logging(request)
        
        assert isinstance(result, CodeGenerationResult)
        assert "logger" in result.generated_code or "logging" in result.generated_code
        assert result.inserted_lines >= 1
        assert result.confidence >= 0.9
    
    def test_logging_typescript(self, generator):
        """Test logging generation for TypeScript."""
        request = CodeGenerationRequest(
            file_path="test.ts",
            cursor_line=5,
            cursor_col=0,
            context_before="function foo() {",
            context_after="}",
            instruction="add logging",
            language="typescript",
        )
        
        result = generator._generate_logging(request)
        
        assert "console" in result.generated_code
        assert result.inserted_lines >= 1
    
    def test_logging_c(self, generator):
        """Test logging generation for C."""
        request = CodeGenerationRequest(
            file_path="test.c",
            cursor_line=10,
            cursor_col=0,
            context_before="void process() {",
            context_after="}",
            instruction="add logging",
            language="c",
        )
        
        result = generator._generate_logging(request)
        
        assert "printf" in result.generated_code
        assert result.inserted_lines >= 1


class TestGenerateAsyncFunction:
    """Test async function code generation."""
    
    @pytest.fixture
    def generator(self):
        return InlineCodeGenerator()
    
    def test_async_python(self, generator):
        """Test async function generation for Python."""
        request = CodeGenerationRequest(
            file_path="test.py",
            cursor_line=10,
            cursor_col=4,
            context_before="class MyClass:",
            context_after="",
            instruction="add async function",
            language="python",
        )
        
        result = generator._generate_async_function(request)
        
        assert isinstance(result, CodeGenerationResult)
        assert "async def" in result.generated_code
        assert result.confidence >= 0.9
    
    def test_async_typescript(self, generator):
        """Test async function generation for TypeScript."""
        request = CodeGenerationRequest(
            file_path="test.ts",
            cursor_line=5,
            cursor_col=0,
            context_before="class Service {",
            context_after="}",
            instruction="add async method",
            language="typescript",
        )
        
        result = generator._generate_async_function(request)
        
        assert "async" in result.generated_code
        assert "function" in result.generated_code or "=>" in result.generated_code


class TestGenerateDocstring:
    """Test docstring code generation."""
    
    @pytest.fixture
    def generator(self):
        return InlineCodeGenerator()
    
    def test_docstring_python(self, generator):
        """Test docstring generation for Python."""
        request = CodeGenerationRequest(
            file_path="test.py",
            cursor_line=1,
            cursor_col=0,
            context_before="",
            context_after="def foo():",
            instruction="add docstring",
            language="python",
        )
        
        result = generator._generate_docstring(request)
        
        assert isinstance(result, CodeGenerationResult)
        assert '"""' in result.generated_code
        assert "Args:" in result.generated_code
        assert "Returns:" in result.generated_code
    
    def test_docstring_typescript(self, generator):
        """Test docstring generation for TypeScript."""
        request = CodeGenerationRequest(
            file_path="test.ts",
            cursor_line=1,
            cursor_col=0,
            context_before="",
            context_after="function foo() {}",
            instruction="add documentation",
            language="typescript",
        )
        
        result = generator._generate_docstring(request)
        
        assert "/**" in result.generated_code
        assert "@param" in result.generated_code


class TestGenerateFunction:
    """Test function code generation."""
    
    @pytest.fixture
    def generator(self):
        return InlineCodeGenerator()
    
    def test_function_python(self, generator):
        """Test function generation for Python."""
        request = CodeGenerationRequest(
            file_path="test.py",
            cursor_line=10,
            cursor_col=0,
            context_before="# Utility functions",
            context_after="",
            instruction="add function",
            language="python",
        )
        
        result = generator._generate_function(request)
        
        assert isinstance(result, CodeGenerationResult)
        assert "def " in result.generated_code
        assert result.confidence >= 0.9
    
    def test_function_typescript(self, generator):
        """Test function generation for TypeScript."""
        request = CodeGenerationRequest(
            file_path="test.ts",
            cursor_line=5,
            cursor_col=0,
            context_before="// Helpers",
            context_after="",
            instruction="add function",
            language="typescript",
        )
        
        result = generator._generate_function(request)
        
        assert "function" in result.generated_code
        assert ":" in result.generated_code


class TestGenerateInterface:
    """Test interface/type code generation."""
    
    @pytest.fixture
    def generator(self):
        return InlineCodeGenerator()
    
    def test_interface_typescript(self, generator):
        """Test interface generation for TypeScript."""
        request = CodeGenerationRequest(
            file_path="test.ts",
            cursor_line=1,
            cursor_col=0,
            context_before="",
            context_after="",
            instruction="add interface",
            language="typescript",
        )
        
        result = generator._generate_interface(request)
        
        assert isinstance(result, CodeGenerationResult)
        assert "interface" in result.generated_code or "type" in result.generated_code
    
    def test_interface_python(self, generator):
        """Test interface generation for Python."""
        request = CodeGenerationRequest(
            file_path="test.py",
            cursor_line=1,
            cursor_col=0,
            context_before="",
            context_after="",
            instruction="add interface",
            language="python",
        )
        
        result = generator._generate_interface(request)
        
        assert "ABC" in result.generated_code or "abstractmethod" in result.generated_code


class TestGenerateDecorator:
    """Test decorator code generation."""
    
    @pytest.fixture
    def generator(self):
        return InlineCodeGenerator()
    
    def test_decorator_python(self, generator):
        """Test decorator generation for Python."""
        request = CodeGenerationRequest(
            file_path="test.py",
            cursor_line=1,
            cursor_col=0,
            context_before="import functools",
            context_after="",
            instruction="add decorator",
            language="python",
        )
        
        result = generator._generate_decorator(request)
        
        assert isinstance(result, CodeGenerationResult)
        assert "def " in result.generated_code or "@" in result.generated_code


class TestMainGenerate:
    """Test the main generate method."""
    
    @pytest.fixture
    def generator(self):
        return InlineCodeGenerator()
    
    def test_generate_error_handling_via_main(self, generator):
        """Test error handling generation via main generate method."""
        request = CodeGenerationRequest(
            file_path="test.py",
            cursor_line=10,
            cursor_col=4,
            context_before="def process():",
            context_after="    pass",
            instruction="add error handling",
            language="python",
        )
        
        import asyncio
        result = asyncio.run(generator.generate(request))
        
        assert isinstance(result, CodeGenerationResult)
        assert "try:" in result.generated_code
    
    def test_generate_logging_via_main(self, generator):
        """Test logging generation via main generate method."""
        request = CodeGenerationRequest(
            file_path="test.py",
            cursor_line=5,
            cursor_col=0,
            context_before="def foo():",
            context_after="    return True",
            instruction="add logging",
            language="python",
        )
        
        import asyncio
        result = asyncio.run(generator.generate(request))
        
        assert "logger" in result.generated_code or "logging" in result.generated_code
    
    def test_generate_unknown_instruction(self, generator):
        """Test handling of unknown instruction."""
        request = CodeGenerationRequest(
            file_path="test.py",
            cursor_line=1,
            cursor_col=0,
            context_before="",
            context_after="",
            instruction="do something completely unknown",
            language="python",
        )
        
        import asyncio
        result = asyncio.run(generator.generate(request))
        
        assert result.generated_code == ""
        assert result.confidence == 0.0
        assert result.error is not None


class TestExtractPlaceholder:
    """Test placeholder extraction."""
    
    @pytest.fixture
    def generator(self):
        return InlineCodeGenerator()
    
    def test_extract_from_context(self, generator):
        """Test extracting placeholder from context."""
        request = CodeGenerationRequest(
            file_path="test.py",
            cursor_line=5,
            cursor_col=4,
            context_before="def process():\n    data = fetch_data()",
            context_after="    return result",
            instruction="add error handling",
            language="python",
        )
        
        placeholder = generator._extract_placeholder(request)
        
        assert "data = fetch_data()" in placeholder
    
    def test_extract_fallback(self, generator):
        """Test fallback when no placeholder found."""
        request = CodeGenerationRequest(
            file_path="test.py",
            cursor_line=5,
            cursor_col=4,
            context_before="def process():",
            context_after="    pass",
            instruction="add error handling",
            language="python",
        )
        
        placeholder = generator._extract_placeholder(request)
        
        # Should return a non-empty placeholder
        assert placeholder is not None
        assert len(placeholder) > 0
