"""Test generation support for AI_SUPPORT.

This module provides test generation capabilities:
- Python AST-aware test generation
- Support for pytest, unittest, and doctest frameworks
- Auto-detection of function parameters
- Basic test case generation
"""

from .test_generator import (
    TestGenerator,
    GeneratedTest,
    TestTemplate,
)

__all__ = [
    "TestGenerator",
    "GeneratedTest",
    "TestTemplate",
]
