"""Analysis rules package."""

from .security import (
    SQLInjectionRule,
    HardcodedSecretRule,
    CommandInjectionRule,
    XSSRule,
    PathTraversalRule,
    InsecureHashRule,
    InsecureRandomRule,
)
from .quality import (
    CognitiveComplexityRule,
    EmptyExceptRule,
    BroadExceptRule,
    GlobalVariableRule,
    CommentedCodeRule,
    DeprecatedImportRule,
)
from .imports import (
    UnusedImportRule,
    CircularImportRule,
)
from .types import (
    AnyTypeRule,
)
from .naming import (
    InconsistentNamingRule,
)

__all__ = [
    # Security
    "SQLInjectionRule",
    "HardcodedSecretRule",
    "CommandInjectionRule",
    "XSSRule",
    "PathTraversalRule",
    "InsecureHashRule",
    "InsecureRandomRule",
    # Quality
    "CognitiveComplexityRule",
    "EmptyExceptRule",
    "BroadExceptRule",
    "GlobalVariableRule",
    "CommentedCodeRule",
    "DeprecatedImportRule",
    # Imports
    "UnusedImportRule",
    "CircularImportRule",
    # Types
    "AnyTypeRule",
    # Naming
    "InconsistentNamingRule",
]
