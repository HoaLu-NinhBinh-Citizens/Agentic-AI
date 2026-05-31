"""Test generation for AI_SUPPORT.

Generates pytest/unittest tests from functions and classes using Python AST analysis.

Features:
- AST-aware test generation
- Support for pytest, unittest, doctest frameworks
- Auto-detection of function parameters and return types
- Basic test case generation
- Integration with LLM for enhanced test generation

Usage:
    generator = TestGenerator(project_root)
    result = await generator.generate_tests(
        file_path=Path("src/my_module.py"),
        symbol_name="my_function",
        framework="pytest",
    )
    print(result.content)
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

logger = logging.getLogger(__name__)


@dataclass
class TestTemplate:
    """Template for test generation."""
    framework: Literal["pytest", "unittest", "doctest"]
    imports: list[str] = field(default_factory=list)
    fixtures: list[str] = field(default_factory=list)
    test_functions: list[str] = field(default_factory=list)
    setup_code: Optional[str] = None


@dataclass
class GeneratedTest:
    """Result of test generation."""
    filename: str
    content: str
    framework: str
    test_count: int
    coverage_estimate: float  # 0.0-1.0
    symbol_name: str = ""
    symbol_type: str = ""  # "function" or "class"
    test_cases: list[dict] = field(default_factory=list)


@dataclass
class FunctionInfo:
    """Information about a function extracted from AST."""
    name: str
    args: list[str]
    defaults: list[Any]
    return_type: Optional[str] = None
    decorators: list[str] = field(default_factory=list)
    is_async: bool = False
    docstring: Optional[str] = None
    raises_exceptions: list[str] = field(default_factory=list)


@dataclass
class ClassInfo:
    """Information about a class extracted from AST."""
    name: str
    bases: list[str] = field(default_factory=list)
    methods: list[FunctionInfo] = field(default_factory=list)
    class_variables: list[str] = field(default_factory=list)
    docstring: Optional[str] = None


class TestGenerator:
    """Generate unit tests from functions and classes using AST analysis.

    This class provides comprehensive test generation capabilities:
    - Parses Python source files using AST
    - Extracts function/class metadata
    - Generates framework-appropriate test code
    - Supports pytest, unittest, and doctest
    - Can be extended with LLM for enhanced generation
    """

    def __init__(
        self,
        project_root: Path | str,
        llm_provider: Any = None,
        default_framework: str = "pytest",
    ):
        """Initialize the test generator.

        Args:
            project_root: Root directory of the project
            llm_provider: Optional LLM provider for enhanced generation
            default_framework: Default test framework ("pytest", "unittest", "doctest")
        """
        self.project_root = Path(project_root)
        self.llm_provider = llm_provider
        self.default_framework = default_framework

    async def generate_tests(
        self,
        file_path: Path | str,
        symbol_name: Optional[str] = None,
        framework: Optional[str] = None,
        include_fixtures: bool = True,
        include_edge_cases: bool = True,
    ) -> GeneratedTest:
        """Generate tests for a function or class.

        Args:
            file_path: File containing the code to test
            symbol_name: Function/class name (auto-detect if None)
            framework: Test framework ("pytest", "unittest", "doctest")
            include_fixtures: Include pytest fixtures
            include_edge_cases: Generate edge case tests

        Returns:
            GeneratedTest with filename and content
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        content = file_path.read_text(encoding="utf-8", errors="replace")

        # Parse AST
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            raise ValueError(f"Failed to parse {file_path}: {e}")

        # Find target symbol
        if symbol_name:
            target = self._find_symbol(tree, symbol_name)
        else:
            target = self._find_first_def(tree)

        if not target:
            raise ValueError(f"Could not find symbol in {file_path}")

        # Extract metadata
        if isinstance(target, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_info = self._extract_function_info(target)
            symbol_type = "function"
            test_content = await self._generate_function_test(
                func_info, framework or self.default_framework, include_edge_cases
            )
        elif isinstance(target, ast.ClassDef):
            cls_info = self._extract_class_info(target)
            symbol_type = "class"
            test_content = await self._generate_class_test(
                cls_info, framework or self.default_framework, include_edge_cases
            )
        else:
            raise ValueError(f"Unsupported symbol type: {type(target).__name__}")

        # Build test filename
        test_filename = self._get_test_filename(file_path, symbol_name)

        # Wrap in proper test file
        final_content = self._wrap_in_test_file(
            content=test_content,
            framework=framework or self.default_framework,
            include_fixtures=include_fixtures,
            symbol_name=symbol_name or getattr(target, "name", "unknown"),
        )

        # Detect test cases
        test_cases = self._detect_test_cases(target)

        return GeneratedTest(
            filename=test_filename,
            content=final_content,
            framework=framework or self.default_framework,
            test_count=self._count_tests(final_content),
            coverage_estimate=self._estimate_coverage(target),
            symbol_name=symbol_name or getattr(target, "name", ""),
            symbol_type=symbol_type,
            test_cases=test_cases,
        )

    def _extract_function_info(self, func: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionInfo:
        """Extract function metadata from AST node."""
        args = [arg.arg for arg in func.args.args]

        # Get default values
        defaults = []
        if func.args.defaults:
            defaults = [self._ast_to_value(d) for d in func.args.defaults]

        # Get decorators
        decorators = []
        for dec in func.decorator_list:
            dec_name = self._get_decorator_name(dec)
            if dec_name:
                decorators.append(dec_name)

        # Get docstring
        docstring = ast.get_docstring(func)

        # Detect potential exceptions
        raises = self._detect_raises(func)

        # Get return type annotation
        return_type = None
        if func.returns:
            return_type = self._get_annotation_name(func.returns)

        return FunctionInfo(
            name=func.name,
            args=args,
            defaults=defaults,
            return_type=return_type,
            decorators=decorators,
            is_async=isinstance(func, ast.AsyncFunctionDef),
            docstring=docstring,
            raises_exceptions=raises,
        )

    def _extract_class_info(self, cls: ast.ClassDef) -> ClassInfo:
        """Extract class metadata from AST node."""
        # Get base classes
        bases = []
        for base in cls.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(self._get_attribute_name(base))

        # Get methods
        methods = []
        class_vars = []

        for node in cls.body:
            if isinstance(node, ast.FunctionDef):
                methods.append(self._extract_function_info(node))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                # Class variable with type annotation
                class_vars.append(node.target.id)

        docstring = ast.get_docstring(cls)

        return ClassInfo(
            name=cls.name,
            bases=bases,
            methods=methods,
            class_variables=class_vars,
            docstring=docstring,
        )

    def _get_decorator_name(self, dec: ast.expr) -> Optional[str]:
        """Get the name of a decorator."""
        if isinstance(dec, ast.Name):
            return dec.id
        elif isinstance(dec, ast.Attribute):
            return self._get_attribute_name(dec)
        elif isinstance(dec, ast.Call):
            return self._get_decorator_name(dec.func)
        return None

    def _get_attribute_name(self, attr: ast.Attribute) -> str:
        """Get full name of an attribute expression."""
        parts = []
        node = attr
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return ".".join(reversed(parts))

    def _get_annotation_name(self, ann: ast.expr) -> str:
        """Get the name of a type annotation."""
        if isinstance(ann, ast.Name):
            return ann.id
        elif isinstance(ann, ast.Attribute):
            return self._get_attribute_name(ann)
        elif isinstance(ann, ast.Subscript):
            base = self._get_annotation_name(ann.value)
            if isinstance(ann.slice, ast.Tuple):
                args = ", ".join(self._get_annotation_name(a) for a in ann.slice.elts)
                return f"{base}[{args}]"
            else:
                return f"{base}[{self._get_annotation_name(ann.slice)}]"
        elif isinstance(ann, ast.Constant):
            return str(ann.value)
        return "Any"

    def _ast_to_value(self, node: ast.expr) -> Any:
        """Convert an AST node to a Python value."""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.Str):
            return node.s
        elif isinstance(node, ast.Bytes):
            return node.s
        elif isinstance(node, ast.NameConstant):
            return node.value
        elif isinstance(node, ast.Tuple):
            return tuple(self._ast_to_value(e) for e in node.elts)
        elif isinstance(node, ast.List):
            return [self._ast_to_value(e) for e in node.elts]
        elif isinstance(node, ast.Dict):
            return {
                self._ast_to_value(k): self._ast_to_value(v)
                for k, v in zip(node.keys, node.values)
                if k is not None
            }
        elif isinstance(node, ast.Name):
            if node.id == "None":
                return None
            elif node.id == "True":
                return True
            elif node.id == "False":
                return False
            return node.id
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            operand = self._ast_to_value(node.operand)
            if isinstance(operand, (int, float)):
                return -operand
        return None

    def _detect_raises(self, func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
        """Detect exceptions that the function might raise."""
        raises = set()

        for node in ast.walk(func):
            if isinstance(node, ast.Raise):
                if node.exc:
                    exc_name = self._get_exception_name(node.exc)
                    if exc_name:
                        raises.add(exc_name)

        return list(raises)

    def _get_exception_name(self, exc: ast.expr) -> Optional[str]:
        """Get the name of an exception."""
        if isinstance(exc, ast.Name):
            return exc.id
        elif isinstance(exc, ast.Attribute):
            return self._get_attribute_name(exc)
        elif isinstance(exc, ast.Call):
            return self._get_exception_name(exc.func)
        return None

    def _detect_test_cases(self, target: ast.AST) -> list[dict]:
        """Detect potential test cases based on function signature and behavior."""
        test_cases = []

        if isinstance(target, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [arg.arg for arg in target.args.args]
            func_name = target.name

            # Basic test case
            if len(args) == 0:
                test_cases.append({
                    "name": "test_basic",
                    "args": [],
                    "expected_behavior": "call_function",
                })
            else:
                # Generate test args based on types or generic values
                test_args = []
                for arg in args:
                    test_args.append(self._generate_test_value(arg))

                test_cases.append({
                    "name": "test_basic",
                    "args": test_args,
                    "expected_behavior": "call_function",
                })

            # Edge cases
            if len(args) >= 1:
                test_cases.append({
                    "name": "test_with_none",
                    "args": [None] * len(args),
                    "expected_behavior": "handle_none",
                })

            # Empty string/collection tests
            if len(args) >= 1:
                test_cases.append({
                    "name": "test_with_empty_values",
                    "args": self._generate_empty_values(len(args)),
                    "expected_behavior": "handle_empty",
                })

            # Exception tests
            raises = self._detect_raises(target)
            for exc in raises[:2]:  # Limit to 2 exception tests
                test_cases.append({
                    "name": f"test_raises_{exc.lower()}",
                    "args": self._generate_invalid_args(len(args)),
                    "expected_behavior": "raises",
                    "expected_exception": exc,
                })

        return test_cases

    def _generate_test_value(self, arg_name: str) -> Any:
        """Generate a reasonable test value based on argument name."""
        name_lower = arg_name.lower()

        # Type hints from name
        if "name" in name_lower or "str" in name_lower:
            return "test_value"
        elif "num" in name_lower or "count" in name_lower:
            return 42
        elif "flag" in name_lower or "is_" in name_lower or "enabled" in name_lower:
            return True
        elif "list" in name_lower or "items" in name_lower:
            return []
        elif "dict" in name_lower or "data" in name_lower:
            return {}
        elif "path" in name_lower or "file" in name_lower:
            return "/tmp/test_path"

        # Generic fallback
        return "test_value"

    def _generate_empty_values(self, count: int) -> list[Any]:
        """Generate empty/invalid values for edge case testing."""
        values = []
        for _ in range(count):
            values.append("")
        return values

    def _generate_invalid_args(self, count: int) -> list[Any]:
        """Generate invalid arguments for exception testing."""
        values = []
        for _ in range(count):
            values.append("__INVALID__")
        return values

    async def _generate_function_test(
        self,
        func_info: FunctionInfo,
        framework: str,
        include_edge_cases: bool,
    ) -> str:
        """Generate tests for a function."""
        if framework == "pytest":
            return self._generate_pytest_function(func_info, include_edge_cases)
        elif framework == "unittest":
            return self._generate_unittest_function(func_info, include_edge_cases)
        else:
            return self._generate_doctest_function(func_info)

    async def _generate_class_test(
        self,
        cls_info: ClassInfo,
        framework: str,
        include_edge_cases: bool,
    ) -> str:
        """Generate tests for a class."""
        if framework == "pytest":
            return self._generate_pytest_class(cls_info, include_edge_cases)
        elif framework == "unittest":
            return self._generate_unittest_class(cls_info, include_edge_cases)
        else:
            return self._generate_doctest_class(cls_info)

    def _generate_pytest_function(
        self,
        func_info: FunctionInfo,
        include_edge_cases: bool,
    ) -> str:
        """Generate pytest-style tests for a function."""
        lines = []
        func_name = func_info.name
        args = func_info.args
        is_async = func_info.is_async
        raises = func_info.raises_exceptions

        # Stub function definition
        if is_async:
            lines.append(f"async def {func_name}({', '.join(args)}):")
        else:
            lines.append(f"def {func_name}({', '.join(args)}):")
        lines.append('    """TODO: Implement the actual function."""')
        lines.append("    raise NotImplementedError")
        lines.append("")

        # Test: basic call
        test_args = [self._get_test_value_for_arg(arg) for arg in args]
        prefix = "await " if is_async else ""

        lines.append("def test_basic():")
        if args:
            lines.append(f"    # Arrange")
            for i, (arg, val) in enumerate(zip(args, test_args)):
                lines.append(f"    {arg} = {val}")
            lines.append(f"")
            lines.append(f"    # Act")
            lines.append(f"    result = {prefix}{func_name}({', '.join(args)})")
        else:
            lines.append(f"    result = {prefix}{func_name}()")
        lines.append(f"    # Assert")
        if func_info.return_type and func_info.return_type != "None":
            lines.append(f"    assert result is not None  # TODO: Check specific assertion")
        else:
            lines.append(f"    # No return type specified")
        lines.append("")

        # Edge case tests
        if include_edge_cases and args:
            # Test with None values
            lines.append("def test_with_none():")
            for i, arg in enumerate(args):
                lines.append(f"    {arg} = None")
            lines.append(f"    try:")
            lines.append(f"        result = {prefix}{func_name}({', '.join(args)})")
            lines.append(f"        # Function handles None gracefully")
            lines.append(f"    except Exception:")
            lines.append(f"        # Expected: function may raise on None")
            lines.append("")

            # Test with empty values
            lines.append("def test_with_empty_values():")
            empty_values = ["''", "0", "[]", "{}", "False"]
            for i, arg in enumerate(args):
                val = empty_values[i % len(empty_values)]
                lines.append(f"    {arg} = {val}")
            lines.append(f"    result = {prefix}{func_name}({', '.join(args)})")
            lines.append("    assert result is not None  # TODO: Check expected behavior")
            lines.append("")

        # Exception tests
        for exc in raises[:2]:
            exc_name = exc.split(".")[-1]  # Get simple name
            lines.append(f"def test_raises_{exc_name.lower()}():")
            for i, arg in enumerate(args):
                lines.append(f"    {arg} = 'invalid'  # Trigger {exc_name}")
            lines.append(f"    with pytest.raises({exc}):")
            lines.append(f"        {prefix}{func_name}({', '.join(args)})")
            lines.append("")

        return '\n'.join(lines)

    def _generate_pytest_class(
        self,
        cls_info: ClassInfo,
        include_edge_cases: bool,
    ) -> str:
        """Generate pytest-style tests for a class."""
        lines = []
        cls_name = cls_info.name

        lines.append(f"class Test{cls_name}:")
        lines.append(f'    """Test cases for {cls_name}. """')
        lines.append("")

        # Fixture for class instance
        lines.append("    @pytest.fixture")
        lines.append("    def instance(self):")
        lines.append(f"        return {cls_name}()")
        lines.append("")

        # Test __init__
        init_method = None
        for method in cls_info.methods:
            if method.name == "__init__":
                init_method = method
                break

        lines.append("    def test_init(self):")
        lines.append(f"        instance = {cls_name}()")
        lines.append("        assert instance is not None")
        lines.append("")

        # Test public methods
        for method in cls_info.methods:
            if method.name.startswith("_") and method.name != "__init__":
                continue  # Skip private methods

            if method.name == "__init__":
                continue

            method_name = method.name
            args = [a for a in method.args if a != "self"]
            args_str = ", ".join(args)

            lines.append(f"    def test_{method_name}(self):")
            if args:
                test_args = [self._get_test_value_for_arg(arg) for arg in args]
                for arg, val in zip(args, test_args):
                    lines.append(f"        {arg} = {self._format_value(val)}")
                lines.append(f"        result = self.instance.{method_name}({', '.join(args)})")
            else:
                lines.append(f"        result = self.instance.{method_name}()")
            lines.append("        assert result is not None  # TODO: Check specific assertion")
            lines.append("")

        return '\n'.join(lines)

    def _generate_unittest_function(
        self,
        func_info: FunctionInfo,
        include_edge_cases: bool,
    ) -> str:
        """Generate unittest-style tests for a function."""
        lines = []
        func_name = func_info.name
        args = func_info.args

        test_class_name = f"Test{func_name.capitalize()}"

        lines.append(f"class {test_class_name}(unittest.TestCase):")
        lines.append(f'    """Test cases for {func_name}. """')
        lines.append("")

        # Basic test
        test_args = [self._get_test_value_for_arg(arg) for arg in args]
        args_str = ", ".join(test_args)

        lines.append("    def test_basic(self):")
        if args:
            lines.append(f"        # Arrange")
            for i, (arg, val) in enumerate(zip(args, test_args)):
                lines.append(f"        {arg} = {self._format_value(val)}")
            lines.append(f"        # Act")
            lines.append(f"        result = {func_name}({', '.join(args)})")
        else:
            lines.append(f"        result = {func_name}()")
        lines.append(f"        # Assert")
        lines.append(f"        self.assertIsNotNone(result)")
        lines.append("")

        return '\n'.join(lines)

    def _generate_unittest_class(
        self,
        cls_info: ClassInfo,
        include_edge_cases: bool,
    ) -> str:
        """Generate unittest-style tests for a class."""
        lines = []
        cls_name = cls_info.name

        lines.append(f"class Test{cls_name}(unittest.TestCase):")
        lines.append(f'    """Test cases for {cls_name}. """')
        lines.append("")

        # setUp
        lines.append("    def setUp(self):")
        lines.append(f"        self.instance = {cls_name}()")
        lines.append("")

        # Test init
        lines.append("    def test_init(self):")
        lines.append(f"        instance = {cls_name}()")
        lines.append("        self.assertIsNotNone(instance)")
        lines.append("")

        # Test public methods
        for method in cls_info.methods:
            if method.name.startswith("_") and method.name != "__init__":
                continue

            if method.name == "__init__":
                continue

            method_name = method.name
            args = [a for a in method.args if a != "self"]

            lines.append(f"    def test_{method_name}(self):")
            if args:
                for arg in args:
                    val = self._get_test_value_for_arg(arg)
                    lines.append(f"        {arg} = {self._format_value(val)}")
                lines.append(f"        result = self.instance.{method_name}({', '.join(args)})")
            else:
                lines.append(f"        result = self.instance.{method_name}()")
            lines.append("        self.assertIsNotNone(result)")
            lines.append("")

        return '\n'.join(lines)

    def _generate_doctest_function(self, func_info: FunctionInfo) -> str:
        """Generate doctest-style examples for a function."""
        lines = []
        func_name = func_info.name
        args = func_info.args

        lines.append('"""Doctest examples for the module."""')
        lines.append("")

        # Basic example
        test_args = [self._get_test_value_for_arg(arg) for arg in args]
        args_str = ", ".join(test_args)

        lines.append(f">>> {func_name}({args_str})")
        lines.append("# TODO: Expected output")
        lines.append("")

        return '\n'.join(lines)

    def _generate_doctest_class(self, cls_info: ClassInfo) -> str:
        """Generate doctest-style examples for a class."""
        lines = []
        cls_name = cls_info.name

        lines.append('"""Doctest examples for the module."""')
        lines.append("")

        lines.append(f">>> obj = {cls_name}()")
        lines.append(">>> # TODO: Test method calls")
        lines.append("")

        return '\n'.join(lines)

    def _get_test_value_for_arg(self, arg_name: str) -> str:
        """Get a test value for an argument based on its name."""
        name_lower = arg_name.lower()

        if "name" in name_lower or "str" in name_lower or "title" in name_lower:
            return '"test_string"'
        elif "count" in name_lower or "num" in name_lower or "size" in name_lower:
            return "42"
        elif "flag" in name_lower or "is_" in name_lower or "enabled" in name_lower:
            return "True"
        elif "items" in name_lower or "values" in name_lower:
            return "[1, 2, 3]"
        elif "data" in name_lower or "dict" in name_lower or "config" in name_lower:
            return '{"key": "value"}'
        elif "path" in name_lower or "file" in name_lower or "url" in name_lower:
            return '"/tmp/test_path"'
        elif "id" in name_lower:
            return "123"
        elif "list" in name_lower:
            return "[]"

        return '"test_value"'

    def _format_value(self, value: Any) -> str:
        """Format a Python value for use in test code."""
        if value is None:
            return "None"
        elif isinstance(value, bool):
            return str(value)
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, str):
            # Escape quotes
            escaped = value.replace('"', '\\"')
            return f'"{escaped}"'
        elif isinstance(value, list):
            items = ", ".join(self._format_value(v) for v in value)
            return f"[{items}]"
        elif isinstance(value, dict):
            items = ", ".join(
                f"{self._format_value(k)}: {self._format_value(v)}"
                for k, v in value.items()
            )
            return f"{{{items}}}"
        return "None"

    def _find_symbol(self, tree: ast.AST, name: str) -> Optional[ast.AST]:
        """Find a function or class by name."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == name:
                    return node
        return None

    def _find_first_def(self, tree: ast.AST) -> Optional[ast.AST]:
        """Find first function or class definition."""
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                return node
        return None

    def _get_test_filename(self, file_path: Path, symbol_name: Optional[str]) -> str:
        """Get test filename for a source file."""
        stem = file_path.stem
        return f"test_{stem}.py"

    def _wrap_in_test_file(
        self,
        content: str,
        framework: str,
        include_fixtures: bool,
        symbol_name: str = "",
    ) -> str:
        """Wrap test content in proper test file with imports."""
        lines = []

        # Docstring
        if symbol_name:
            lines.append(f'"""Tests for {symbol_name}."""')
        else:
            lines.append('"""Auto-generated tests."""')
        lines.append("")

        # Imports based on framework
        if framework == "pytest":
            lines.append("import pytest")
            lines.append("import sys")
            lines.append("from pathlib import Path")
            lines.append("")
        elif framework == "unittest":
            lines.append("import unittest")
            lines.append("import sys")
            lines.append("from pathlib import Path")
            lines.append("")
        else:  # doctest
            lines.append('"""Module with doctest examples."""')
            lines.append("")

        lines.append(content)

        return '\n'.join(lines)

    def _count_tests(self, content: str) -> int:
        """Count number of test functions."""
        count = 0
        for line in content.split('\n'):
            stripped = line.strip()
            if stripped.startswith('def test_') or stripped.startswith('async def test_'):
                count += 1
            elif stripped.startswith('def test_') or stripped.startswith('async def test_'):
                count += 1
        return count

    def _estimate_coverage(self, target: ast.AST) -> float:
        """Estimate test coverage for target based on complexity."""
        if isinstance(target, ast.FunctionDef):
            # Count statements in function body
            stmt_count = len([n for n in ast.walk(target) if isinstance(n, ast.stmt)])
            if stmt_count <= 5:
                return 0.4  # Simple function
            elif stmt_count <= 15:
                return 0.3
            else:
                return 0.2

        elif isinstance(target, ast.ClassDef):
            # Count methods
            method_count = len([
                n for n in target.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ])
            if method_count <= 3:
                return 0.3
            elif method_count <= 7:
                return 0.25
            else:
                return 0.2

        return 0.1

    async def generate_with_llm(
        self,
        source_code: str,
        symbol_name: str,
        framework: str = "pytest",
        test_style: str = "comprehensive",
    ) -> str:
        """Generate enhanced tests using LLM.

        Args:
            source_code: The source code to generate tests for
            symbol_name: Name of the function/class
            framework: Test framework
            test_style: Style of tests ("basic", "comprehensive", "edge_cases")

        Returns:
            Generated test code
        """
        if not self.llm_provider:
            raise ValueError("LLM provider not configured")

        prompt = f"""Generate unit tests for the following Python code:

{source_code}

Function/Class: {symbol_name}
Framework: {framework}
Style: {test_style}

Generate comprehensive tests including:
1. Basic functionality tests
2. Edge case tests
3. Error condition tests
4. Type checking tests (if applicable)

Return ONLY the test code, no explanations.
"""

        response = await self.llm_provider.generate(
            prompt=prompt,
            system_prompt="You are an expert Python test engineer. Generate high-quality unit tests.",
            temperature=0.3,
            max_tokens=2048,
        )

        return response.content if hasattr(response, 'content') else str(response)
