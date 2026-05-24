"""
AI_support Tools Module

Tool execution engine for src.

Note: src.core.tools.tool_executor is deprecated. Use this module instead.
"""

from src.core.tools.schema import (
    Tool,
    ToolParameter,
    ToolResult,
    ToolPermission,
    ToolCategory,
    ParameterType,
)
from src.core.tools.registry import ToolRegistry, get_tool_registry
from src.core.tools.executor import ToolExecutor, get_tool_executor
from src.core.tools.file_tools import FileTools
from src.core.tools.build_tools import BuildTools
from src.core.tools.context import (
    ToolContext,
    ToolExecutionMode,
    ToolPermissionContext,
    ResourceLimits,
    create_sandbox_context,
    create_strict_sandbox_context,
    create_dry_run_context,
    create_default_context,
)
from src.core.tools.cache import ToolResultCache

# P2 Sandbox imports
from src.core.tools.sandbox import (
    SandboxManager,
    SandboxConfig,
    SandboxMode,
    SandboxResult,
    SandboxViolation,
    PathValidator,
    ResourceMonitor,
    SubprocessSandbox,
    ResourceLimit,
    ResourceLimitType,
    get_sandbox_manager,
    reset_sandbox_manager,
)

# P2 Audit imports
from src.core.tools.audit import (
    AuditLogger,
    AuditRecord,
    AuditQuery,
    AuditStats,
    AuditEventType,
    AuditSeverity,
    AuditVerdict,
    get_audit_logger,
    reset_audit_logger,
)

from src.core.tools.flash_tools import (
    FlashPermissionGuard,
    FlashConfig,
    FlashProgress,
    FlashResult,
    FlashStatus,
    get_flash_permission_guard,
    get_all_flash_tools,
    FLASH_FIRMWARE_TOOL,
    FLASH_VERIFY_TOOL,
    FLASH_READ_TOOL,
    FLASH_ERASE_TOOL,
    FLASH_INFO_TOOL,
    execute_flash_firmware,
    execute_flash_info,
)

# Codex-style agent improvement tools
from src.core.tools.tool_schema_registry import (
    ToolSchemaRegistry,
    ValidationReport,
    APISchema,
    ValidationResult,
)
from src.core.tools.trace_analyzer import (
    TraceAnalyzer,
    TraceAnalysisResult,
    LogEntry,
    MisleadingLogDetector,
)
from src.core.tools.architecture_preservation import (
    ArchitecturePreservation,
    ChangeImpact,
    PartialFixDetector,
)
from src.core.tools.root_cause_analyzer import (
    RootCauseAnalyzer,
    Symptom,
    AnalysisResult,
    FixValidation,
)

__all__ = [
    # Schema
    "Tool",
    "ToolParameter",
    "ToolResult",
    "ToolPermission",
    "ToolCategory",
    "ParameterType",
    # Registry
    "ToolRegistry",
    "get_tool_registry",
    # Executor
    "ToolExecutor",
    "get_tool_executor",
    # Context
    "ToolContext",
    "ToolExecutionMode",
    "ToolPermissionContext",
    "ResourceLimits",
    "create_sandbox_context",
    "create_strict_sandbox_context",
    "create_dry_run_context",
    "create_default_context",
    # Cache
    "ToolResultCache",
    # P2 Sandbox
    "SandboxManager",
    "SandboxConfig",
    "SandboxMode",
    "SandboxResult",
    "SandboxViolation",
    "PathValidator",
    "ResourceMonitor",
    "SubprocessSandbox",
    "ResourceLimit",
    "ResourceLimitType",
    "get_sandbox_manager",
    "reset_sandbox_manager",
    # P2 Audit
    "AuditLogger",
    "AuditRecord",
    "AuditQuery",
    "AuditStats",
    "AuditEventType",
    "AuditSeverity",
    "AuditVerdict",
    "get_audit_logger",
    "reset_audit_logger",
    # Flash Tools
    "FlashPermissionGuard",
    "FlashConfig",
    "FlashProgress",
    "FlashResult",
    "FlashStatus",
    "get_flash_permission_guard",
    "get_all_flash_tools",
    "FLASH_FIRMWARE_TOOL",
    "FLASH_VERIFY_TOOL",
    "FLASH_READ_TOOL",
    "FLASH_ERASE_TOOL",
    "FLASH_INFO_TOOL",
    "execute_flash_firmware",
    "execute_flash_info",
    # Build Tools
    "BuildTools",
    # Codex-style tools
    "ToolSchemaRegistry",
    "ValidationReport",
    "APISchema",
    "ValidationResult",
    "TraceAnalyzer",
    "TraceAnalysisResult",
    "LogEntry",
    "MisleadingLogDetector",
    "ArchitecturePreservation",
    "ChangeImpact",
    "PartialFixDetector",
    "RootCauseAnalyzer",
    "Symptom",
    "AnalysisResult",
    "FixValidation",
]
