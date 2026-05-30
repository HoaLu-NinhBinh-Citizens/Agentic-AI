"""Patch infrastructure module."""

from .diff_parser import (
    UnifiedDiffParser,
    DiffHunk,
    ParsedFileDiff,
    ParseResult,
    ApplyResult,
    create_parser,
)
from .patch_sandbox import (
    PatchSandbox,
    Patch,
    PatchRisk,
    PatchStatus,
    RiskLevel,
    ValidationResult,
    SandboxConfig,
    get_patch_sandbox,
)
from .approval_workflow import (
    ApprovalWorkflow,
    ApprovalRequest,
    ApprovalAction,
    ApprovalConfig,
    get_approval_workflow,
)
from .ast_patch_engine import (
    ASTPatchEngine,
    ASTNodeInfo,
    Patch as ASTPatch,
    PatchResult,
    create_engine as create_patch_engine,
)

__all__ = [
    # Diff parser
    "UnifiedDiffParser",
    "DiffHunk",
    "ParsedFileDiff",
    "ParseResult",
    "ApplyResult",
    "create_parser",
    # Patch sandbox
    "PatchSandbox",
    "Patch",
    "PatchRisk",
    "PatchStatus",
    "RiskLevel",
    "ValidationResult",
    "SandboxConfig",
    "get_patch_sandbox",
    # Approval workflow
    "ApprovalWorkflow",
    "ApprovalRequest",
    "ApprovalAction",
    "ApprovalConfig",
    "get_approval_workflow",
    # AST patch engine
    "ASTPatchEngine",
    "ASTNodeInfo",
    "ASTPatch",
    "PatchResult",
    "create_patch_engine",
]
