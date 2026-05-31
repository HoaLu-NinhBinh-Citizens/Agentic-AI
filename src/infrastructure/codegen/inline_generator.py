"""Inline code generation for AI_SUPPORT.
Generates new code based on context and requirements.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, AsyncIterator

logger = logging.getLogger(__name__)


@dataclass
class CodeGenerationRequest:
    """Request for inline code generation."""
    file_path: str
    cursor_line: int
    cursor_col: int
    context_before: str
    context_after: str
    instruction: str
    language: str


@dataclass
class CodeGenerationResult:
    """Result of inline code generation."""
    generated_code: str
    inserted_lines: int
    confidence: float
    alternatives: list[str] = field(default_factory=list)
    error: Optional[str] = None


class InlineCodeGenerator:
    """Generate code inline at cursor position.
    
    Supports:
    - Pattern-based generation for common cases (error handling, logging, etc.)
    - Template-based generation for language-specific constructs
    - LLM-based generation for complex requests
    
    Usage:
        generator = InlineCodeGenerator(llm_provider=llm)
        result = await generator.generate(request)
    """
    
    def __init__(self, llm_provider=None):
        self.llm_provider = llm_provider
        self._templates = self._load_templates()
    
    def _load_templates(self) -> dict[str, dict[str, str]]:
        """Load code templates for each language."""
        return {
            "python": {
                "error_handling": '''try:
    {placeholder}
except {exception_type} as exc:
    logger.error(f"Error: {{exc}}")
    raise''',
                "logging": 'logger.info("{message}")',
                "type_hint": "# TODO: Add type hints",
                "docstring": '"""\n{doc}\n"""',
                "test": '''def test_{name}():
    # TODO: Add test assertions
    pass''',
                "context_manager": '''with {context} as {var}:
    {body}''',
                "property": '''@property
def {name}(self) -> {type_}:
    return self._{name}

@{name}.setter
def {name}(self, value: {type_}):
    self._{name} = value''',
                "dataclass": '''@dataclass
class {name}:
    {fields}''',
                "async_function": '''async def {name}({params}) -> {return_type}:
    """TODO: Add docstring."""
    pass''',
                "decorator": '''def {name}(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # TODO: Add decorator logic
        return func(*args, **kwargs)
    return wrapper''',
            },
            "javascript": {
                "error_handling": '''try {{
    {placeholder}
}} catch (error) {{
    console.error('Error:', error);
    throw error;
}}''',
                "logging": 'console.log("{message}");',
                "async_function": '''async function {name}({params}) {{
    // TODO: Add implementation
}}=''',
                "arrow_function": 'const {name} = ({params}) => {{}};',
                "class": '''class {name} {{
    constructor({params}) {{
        // TODO: Initialize
    }}
}}''',
                "promise": '''return new Promise((resolve, reject) => {{
    // TODO: Implement
}});''',
            },
            "typescript": {
                "error_handling": '''try {{
    {placeholder}
}} catch (error) {{
    console.error('Error:', error);
    throw error;
}}''',
                "interface": '''interface {name} {{
    {fields}
}}''',
                "type": '''type {name} = {{
    {fields}
}};''',
                "async_function": '''async function {name}({params}): Promise<{return_type}> {{
    // TODO: Add implementation
}}''',
                "generic": '''function <T>(arg: T): T {{
    return arg;
}}''',
            },
            "c": {
                "error_handling": '''if (result != SUCCESS) {{
    // TODO: Handle error
    goto cleanup;
}}''',
                "logging": 'printf("[DEBUG] {message}\\n");',
                "function": '''{return_type} {name}({params}) {{
    // TODO: Add implementation
    return {return_value};
}}''',
            },
        }
    
    async def generate(self, request: CodeGenerationRequest) -> CodeGenerationResult:
        """Generate code at cursor position based on instruction.
        
        Args:
            request: Code generation request with context and instruction
            
        Returns:
            CodeGenerationResult with generated code and metadata
        """
        instruction_lower = request.instruction.lower()
        
        # Try pattern-based generation first
        if "error handling" in instruction_lower or "try" in instruction_lower:
            return self._generate_error_handling(request)
        elif "logging" in instruction_lower or "log" in instruction_lower:
            return self._generate_logging(request)
        elif "type hint" in instruction_lower or "type annotation" in instruction_lower:
            return self._generate_type_hints(request)
        elif "docstring" in instruction_lower or "documentation" in instruction_lower:
            return self._generate_docstring(request)
        elif "test" in instruction_lower:
            return self._generate_test(request)
        elif "async" in instruction_lower or "await" in instruction_lower:
            return self._generate_async_function(request)
        elif "property" in instruction_lower:
            return self._generate_property(request)
        elif "decorator" in instruction_lower:
            return self._generate_decorator(request)
        elif "interface" in instruction_lower:
            return self._generate_interface(request)
        elif "class" in instruction_lower:
            return self._generate_class(request)
        elif "function" in instruction_lower or "def " in instruction_lower:
            return self._generate_function(request)
        
        # Fall back to LLM-based generation
        if self.llm_provider:
            return await self._llm_generate(request)
        
        # Last resort: return empty with error
        return CodeGenerationResult(
            generated_code="",
            inserted_lines=0,
            confidence=0.0,
            error=f"Cannot handle instruction: {request.instruction}"
        )
    
    def _generate_error_handling(self, request: CodeGenerationRequest) -> CodeGenerationResult:
        """Generate try/except block."""
        lang = request.language.lower()
        templates = self._templates.get(lang, self._templates.get("python", {}))
        
        template = templates.get(
            "error_handling",
            self._templates["python"]["error_handling"]
        )
        
        code = template.format(
            placeholder=self._extract_placeholder(request),
            exception_type="Exception"
        )
        
        return CodeGenerationResult(
            generated_code=code,
            inserted_lines=len(code.split('\n')),
            confidence=0.95,
            alternatives=self._generate_error_alternatives(lang),
        )
    
    def _generate_error_alternatives(self, lang: str) -> list[str]:
        """Generate alternative error handling patterns."""
        alternatives = []
        
        if lang in ("python", "python3"):
            alternatives.extend([
                '''try:
    pass
except ValueError as e:
    logger.warning(f"Value error: {e}")
except TypeError as e:
    logger.warning(f"Type error: {e}")''',
                '''try:
    pass
finally:
    # Cleanup code
    pass''',
            ])
        elif lang in ("javascript", "typescript"):
            alternatives.extend([
                '''try {
    // code
} catch (e) {
    if (e instanceof TypeError) {
        console.error('Type error:', e);
    } else if (e instanceof RangeError) {
        console.error('Range error:', e);
    }
    throw e;
}''',
                '''try {
    // code
} finally {
    // cleanup
}''',
            ])
        
        return alternatives
    
    def _generate_logging(self, request: CodeGenerationRequest) -> CodeGenerationResult:
        """Generate logging statement."""
        lang = request.language.lower()
        
        if lang in ("python", "python3"):
            code = 'logger.info("TODO: Add log message")'
        elif lang in ("javascript", "typescript"):
            code = 'console.log("TODO: Add log message");'
        elif lang in ("c", "cpp"):
            code = 'printf("[INFO] TODO: Add log message\\n");'
        else:
            code = f"// TODO: Add logging for {lang}"
        
        return CodeGenerationResult(
            generated_code=code,
            inserted_lines=1,
            confidence=0.9,
        )
    
    def _generate_type_hints(self, request: CodeGenerationRequest) -> CodeGenerationResult:
        """Generate type hints for function."""
        lang = request.language.lower()
        
        if lang in ("python", "python3"):
            code = '''# Type hints for function parameters and return value
from typing import Optional, List, Dict, Any, Callable

def function_name(
    param1: str,
    param2: int,
    optional_param: Optional[str] = None,
) -> bool:
    """Function with type hints."""
    return True'''
        elif lang in ("typescript",):
            code = '''// TypeScript type annotations
function functionName(
    param1: string,
    param2: number,
    optionalParam?: string
): boolean {
    return true;
}'''
        else:
            code = f"// TODO: Add type hints for {lang}"
        
        return CodeGenerationResult(
            generated_code=code,
            inserted_lines=len(code.split('\n')),
            confidence=0.85,
        )
    
    def _generate_docstring(self, request: CodeGenerationRequest) -> CodeGenerationResult:
        """Generate docstring."""
        lang = request.language.lower()
        
        if lang in ("python", "python3"):
            code = '''"""Function description.

Args:
    param1: Description of param1
    param2: Description of param2

Returns:
    Description of return value

Raises:
    ValueError: When something is invalid
"""'''
        elif lang in ("javascript", "typescript"):
            code = '''/**
 * Function description.
 * @param {string} param1 - Description of param1
 * @param {number} param2 - Description of param2
 * @returns {boolean} Description of return value
 */'''
        elif lang == "c":
            code = '''/**
 * @brief Brief description
 *
 * Detailed description
 *
 * @param param1 Description of param1
 * @param param2 Description of param2
 * @return Description of return value
 */'''
        else:
            code = f"// TODO: Add docstring for {lang}"
        
        return CodeGenerationResult(
            generated_code=code,
            inserted_lines=len(code.split('\n')),
            confidence=0.9,
        )
    
    def _generate_test(self, request: CodeGenerationRequest) -> CodeGenerationResult:
        """Generate test code."""
        lang = request.language.lower()
        
        if lang in ("python", "python3"):
            code = '''import pytest

class TestClassName:
    """Tests for ClassName."""
    
    def setup_method(self):
        """Set up test fixtures."""
        pass
    
    def teardown_method(self):
        """Tear down test fixtures."""
        pass
    
    def test_basic_case(self):
        """Test basic functionality."""
        # Arrange
        pass
        
        # Act
        pass
        
        # Assert
        assert True'''
        elif lang in ("javascript", "typescript"):
            code = '''describe('ClassName', () => {
    beforeEach(() => {
        // Setup
    });
    
    afterEach(() => {
        // Teardown
    });
    
    it('should handle basic case', () => {
        // Arrange
        // Act
        // Assert
        expect(true).toBe(true);
    });
});'''
        else:
            code = f"// TODO: Add test for {lang}"
        
        return CodeGenerationResult(
            generated_code=code,
            inserted_lines=len(code.split('\n')),
            confidence=0.85,
        )
    
    def _generate_async_function(self, request: CodeGenerationRequest) -> CodeGenerationResult:
        """Generate async function."""
        lang = request.language.lower()
        
        if lang in ("python", "python3"):
            code = '''async def function_name(param1: str, param2: int) -> bool:
    """Async function with type hints.
    
    Args:
        param1: Description of param1
        param2: Description of param2
    
    Returns:
        True if successful
    """
    # TODO: Add implementation
    return True'''
        elif lang in ("javascript", "typescript"):
            code = '''async function functionName(
    param1: string,
    param2: number
): Promise<boolean> {
    // TODO: Add implementation
    return true;
}'''
        else:
            code = f"// TODO: Add async function for {lang}"
        
        return CodeGenerationResult(
            generated_code=code,
            inserted_lines=len(code.split('\n')),
            confidence=0.9,
        )
    
    def _generate_property(self, request: CodeGenerationRequest) -> CodeGenerationResult:
        """Generate property getter/setter."""
        lang = request.language.lower()
        
        if lang in ("python", "python3"):
            code = '''@property
def value(self) -> str:
    """Get the value."""
    return self._value

@value.setter
def value(self, new_value: str) -> None:
    """Set the value."""
    self._value = new_value'''
        elif lang in ("typescript",):
            code = '''get value(): string {
    return this._value;
}

set value(newValue: string) {
    this._value = newValue;
}'''
        else:
            code = f"// TODO: Add property for {lang}"
        
        return CodeGenerationResult(
            generated_code=code,
            inserted_lines=len(code.split('\n')),
            confidence=0.9,
        )
    
    def _generate_decorator(self, request: CodeGenerationResult) -> CodeGenerationResult:
        """Generate decorator function."""
        lang = request.language.lower()
        
        if lang in ("python", "python3"):
            code = '''from functools import wraps

def decorator_name(func: Callable) -> Callable:
    """Decorator that does something.
    
    Args:
        func: Function to wrap
    
    Returns:
        Wrapped function
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # TODO: Add decorator logic
        result = func(*args, **kwargs)
        # TODO: Add post-processing
        return result
    return wrapper'''
        else:
            code = f"// TODO: Add decorator for {lang}"
        
        return CodeGenerationResult(
            generated_code=code,
            inserted_lines=len(code.split('\n')),
            confidence=0.85,
        )
    
    def _generate_interface(self, request: CodeGenerationRequest) -> CodeGenerationResult:
        """Generate interface/type definition."""
        lang = request.language.lower()
        
        if lang in ("typescript",):
            code = '''interface IName {
    readonly id: string;
    name: string;
    
    // Methods
    doSomething(): void;
    doSomethingElse(param: string): boolean;
}'''
        elif lang in ("python", "python3"):
            code = '''from abc import ABC, abstractmethod

class IName(ABC):
    """Interface for something."""
    
    @abstractmethod
    def do_something(self) -> None:
        """Do something."""
        pass
    
    @abstractmethod
    def do_something_else(self, param: str) -> bool:
        """Do something else.
        
        Args:
            param: The parameter
            
        Returns:
            True if successful
        """
        pass'''
        else:
            code = f"// TODO: Add interface for {lang}"
        
        return CodeGenerationResult(
            generated_code=code,
            inserted_lines=len(code.split('\n')),
            confidence=0.85,
        )
    
    def _generate_class(self, request: CodeGenerationRequest) -> CodeGenerationResult:
        """Generate class definition."""
        lang = request.language.lower()
        
        if lang in ("python", "python3"):
            code = '''class ClassName:
    """Description of the class."""
    
    def __init__(self, param1: str, param2: int):
        """Initialize the class.
        
        Args:
            param1: Description of param1
            param2: Description of param2
        """
        self._param1 = param1
        self._param2 = param2
    
    def __repr__(self) -> str:
        return f"ClassName(param1={self._param1!r}, param2={self._param2!r})"
    
    def __str__(self) -> str:
        return f"ClassName: {self._param1}"'''
        elif lang in ("javascript", "typescript"):
            code = '''class ClassName {
    private param1: string;
    private param2: number;
    
    constructor(param1: string, param2: number) {
        this.param1 = param1;
        this.param2 = param2;
    }
    
    public toString(): string {
        return `ClassName: ${this.param1}`;
    }
}'''
        else:
            code = f"// TODO: Add class for {lang}"
        
        return CodeGenerationResult(
            generated_code=code,
            inserted_lines=len(code.split('\n')),
            confidence=0.9,
        )
    
    def _generate_function(self, request: CodeGenerationRequest) -> CodeGenerationResult:
        """Generate function definition."""
        lang = request.language.lower()
        
        if lang in ("python", "python3"):
            code = '''def function_name(param1: str, param2: int = 0) -> bool:
    """Function description.
    
    Args:
        param1: Description of param1
        param2: Description of param2 (default: 0)
    
    Returns:
        True if successful
    """
    # TODO: Add implementation
    return True'''
        elif lang in ("javascript", "typescript"):
            code = '''function functionName(
    param1: string,
    param2: number = 0
): boolean {
    // TODO: Add implementation
    return true;
}'''
        elif lang in ("c",):
            code = '''/**
 * @brief Brief description
 * @param param1 Description of param1
 * @param param2 Description of param2 (default: 0)
 * @return True if successful
 */
bool function_name(const char* param1, int param2) {
    // TODO: Add implementation
    return true;
}'''
        else:
            code = f"// TODO: Add function for {lang}"
        
        return CodeGenerationResult(
            generated_code=code,
            inserted_lines=len(code.split('\n')),
            confidence=0.9,
        )
    
    async def _llm_generate(self, request: CodeGenerationRequest) -> CodeGenerationResult:
        """Use LLM for complex code generation."""
        prompt = f"""Generate code for this file at line {request.cursor_line}.

File: {request.file_path}
Language: {request.language}
Instruction: {request.instruction}

Context before:
{request.context_before}

Context after:
{request.context_after}

Generate ONLY the code to insert at the cursor position. No explanation.
The code should be appropriate for the language ({request.language}) and fit naturally
with the surrounding context."""

        try:
            response = await self.llm_provider.generate(prompt)
            
            if not response or not response.strip():
                return CodeGenerationResult(
                    generated_code="",
                    inserted_lines=0,
                    confidence=0.0,
                    error="LLM returned empty response"
                )
            
            return CodeGenerationResult(
                generated_code=response.strip(),
                inserted_lines=len(response.strip().split('\n')),
                confidence=0.85,
                alternatives=[],
            )
        except Exception as e:
            logger.error("LLM generation failed: %s", e)
            return CodeGenerationResult(
                generated_code="",
                inserted_lines=0,
                confidence=0.0,
                error=str(e)
            )
    
    def _extract_placeholder(self, request: CodeGenerationRequest) -> str:
        """Extract placeholder text from context."""
        # Try to find what code is likely to be inside the try block
        lines = request.context_before.strip().split('\n')
        if lines:
            last_line = lines[-1].strip()
            if last_line and last_line != "#":
                return f"    {last_line}"
        return "    # TODO: Add code here"
