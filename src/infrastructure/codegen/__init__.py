"""Code generation infrastructure for AI_SUPPORT.

Provides:
- Inline code generation at cursor position
- AI-powered completion engine
"""

from src.infrastructure.codegen.inline_generator import (
    InlineCodeGenerator,
    CodeGenerationRequest,
    CodeGenerationResult,
)
from src.infrastructure.codegen.completion_engine import (
    CompletionEngine,
    Completion,
)

__all__ = [
    "InlineCodeGenerator",
    "CodeGenerationRequest",
    "CodeGenerationResult",
    "CompletionEngine",
    "Completion",
]
