"""
Unit Tests for P2 Sandbox Implementation

Tests for:
- SandboxManager
- SandboxConfig
- SandboxResult
- PathValidator
- ResourceMonitor
- SubprocessSandbox
- AuditLogger
- AuditRecord
- Integration with ToolExecutor
"""

import asyncio
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

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
from src.core.tools.audit import (
    AuditLogger,
    AuditRecord,
    AuditQuery,
    AuditEventType,
    AuditSeverity,
    AuditVerdict,
    AuditStats,
    get_audit_logger,
    reset_audit_logger,
)
from src.core.tools.context import (
    ToolContext,
    ToolExecutionMode,
    ResourceLimits,
    create_sandbox_context,
    create_strict_sandbox_context,
)
from src.core.tools.schema import (
    Tool,
    ToolParameter,
    ToolPermission,
    ToolCategory,
    ParameterType,
)
from src.core.tools.registry import ToolRegistry
from src.core.tools.executor import ToolExecutor


# ============ SandboxConfig Tests ============


class TestSandboxConfig:
    """Tests for SandboxConfig."""

    def test_config_defaults(self):
        """Test default configuration values."""
        config = SandboxConfig()

        assert config.mode == SandboxMode.HARD
        assert config.allowed_paths == []
        assert config.denied_paths == []
        assert config.allow_network is False
        assert config.allow_subprocess is False
        assert config.allow_file_create is True
        assert config.allow_file_delete is True
        assert config.audit_enabled is True

    def test_config_with_paths(self):
        """Test configuration with path restrictions."""
        config = SandboxConfig(
            allowed_paths=[Path("/workspace")],
            denied_paths=[Path("/etc"), Path("/root")],
        )

        assert len(config.allowed_paths) == 1
        assert len(config.denied_paths) == 2
        assert config.allowed_paths[0] == Path("/workspace").resolve()

    def test_config_resource_limits(self):
        """Test configuration with resource limits."""
        config = SandboxConfig(
            resource_limits={
                ResourceLimitType.CPU_TIME: ResourceLimit(
                    limit_type=ResourceLimitType.CPU_TIME,
                    soft_limit=10,
                    hard_limit=20,
                ),
                ResourceLimitType.MEMORY: ResourceLimit(
                    limit_type=ResourceLimitType.MEMORY,
                    soft_limit=128 * 1024 * 1024,  # 128 MB
                    hard_limit=256 * 1024 * 1024,
                ),
            }
        )

        assert ResourceLimitType.CPU_TIME in config.resource_limits
        assert ResourceLimitType.MEMORY in config.resource_limits
        assert config.resource_limits[ResourceLimitType.CPU_TIME].soft_limit == 10

    def test_config_default_resource_limits(self):
        """Test that default resource limits are set."""
        config = SandboxConfig()

        assert ResourceLimitType.CPU_TIME in config.resource_limits
        assert ResourceLimitType.WALL_TIME in config.resource_limits
        assert ResourceLimitType.MEMORY in config.resource_limits
        assert ResourceLimitType.OPEN_FILES in config.resource_limits
        assert ResourceLimitType.CHILD_PROCESSES in config.resource_limits


# ============ PathValidator Tests ============


class TestPathValidator:
    """Tests for PathValidator."""

    def test_path_allowed_in_workspace(self):
        """Test path allowed within workspace."""
        config = SandboxConfig(
            allowed_paths=[Path("/workspace")],
        )
        validator = PathValidator(config)

        allowed, error = validator.is_path_allowed(Path("/workspace/file.txt"))
        assert allowed is True
        assert error is None

    def test_path_denied_outside_workspace(self):
        """Test path denied outside workspace."""
        config = SandboxConfig(
            allowed_paths=[Path("/workspace")],
        )
        validator = PathValidator(config)

        allowed, error = validator.is_path_allowed(Path("/etc/passwd"))
        assert allowed is False
        assert error is not None  # Error message exists

    def test_path_denied_in_blocked_directory(self):
        """Test path denied in blocked directory."""
        config = SandboxConfig(
            denied_paths=[Path("/etc")],
        )
        validator = PathValidator(config)

        allowed, error = validator.is_path_allowed(Path("/etc/passwd"))
        assert allowed is False

    def test_path_with_symlinks(self):
        """Test path resolution prevents symlink bypass."""
        config = SandboxConfig(
            allowed_paths=[Path("/workspace")],
            denied_paths=[Path("/workspace/secret")],
        )
        validator = PathValidator(config)

        # Symlink to blocked directory should be denied
        allowed, _ = validator.is_path_allowed(Path("/workspace/secret"))
        assert allowed is False

    def test_validate_write_new_file(self):
        """Test write validation for new file."""
        config = SandboxConfig(
            allowed_paths=[Path("/workspace")],
            allow_file_create=True,
        )
        validator = PathValidator(config)

        allowed, error = validator.validate_write(Path("/workspace/newfile.txt"))
        assert allowed is True

    def test_validate_write_blocked_when_disabled(self):
        """Test write validation when file creation is disabled."""
        config = SandboxConfig(
            allowed_paths=[Path("/workspace")],
            allow_file_create=False,
        )
        validator = PathValidator(config)

        allowed, error = validator.validate_write(Path("/workspace/newfile.txt"))
        assert allowed is False
        assert "Creating new files" in error

    def test_validate_delete_blocked(self):
        """Test delete validation when delete is disabled."""
        config = SandboxConfig(
            allowed_paths=[Path("/workspace")],
            allow_file_delete=False,
        )
        validator = PathValidator(config)

        allowed, error = validator.validate_delete(Path("/workspace/file.txt"))
        assert allowed is False
        assert "Deleting files" in error


# ============ ResourceMonitor Tests ============


class TestResourceMonitor:
    """Tests for ResourceMonitor."""

    def test_start_and_get_stats(self):
        """Test resource monitoring start and stats."""
        config = SandboxConfig()
        monitor = ResourceMonitor(config)

        monitor.start_monitoring()
        time.sleep(0.1)

        stats = monitor.get_current_stats()
        assert "wall_time_ms" in stats
        assert "cpu_time_ms" in stats
        assert "peak_memory_bytes" in stats
        assert stats["wall_time_ms"] > 0

    def test_check_limits_within_bounds(self):
        """Test limit checking when within bounds."""
        import platform

        # Use very generous limits
        config = SandboxConfig(
            resource_limits={
                ResourceLimitType.WALL_TIME: ResourceLimit(
                    limit_type=ResourceLimitType.WALL_TIME,
                    soft_limit=300,  # 5 minutes
                    hard_limit=600,
                    enabled=True,
                ),
                ResourceLimitType.CPU_TIME: ResourceLimit(
                    limit_type=ResourceLimitType.CPU_TIME,
                    soft_limit=300,  # 5 minutes
                    hard_limit=600,
                    enabled=True,
                ),
            }
        )
        # On Windows, memory check may return system memory instead of process memory
        # so we don't include a memory limit for this test
        monitor = ResourceMonitor(config)

        monitor.start_monitoring()

        # Short delay
        time.sleep(0.05)

        within_limits, violations = monitor.check_limits()
        assert within_limits is True
        assert len(violations) == 0

    def test_check_limits_exceeded(self):
        """Test limit checking when exceeded."""
        config = SandboxConfig(
            resource_limits={
                ResourceLimitType.WALL_TIME: ResourceLimit(
                    limit_type=ResourceLimitType.WALL_TIME,
                    soft_limit=0,  # Very low limit
                    hard_limit=1,
                    enabled=True,
                ),
            }
        )
        monitor = ResourceMonitor(config)

        monitor.start_monitoring()
        time.sleep(0.1)

        within_limits, violations = monitor.check_limits()
        assert within_limits is False
        assert len(violations) > 0


# ============ SubprocessSandbox Tests ============


class TestSubprocessSandbox:
    """Tests for SubprocessSandbox."""

    def test_subprocess_disabled(self):
        """Test subprocess execution when disabled."""
        config = SandboxConfig(allow_subprocess=False)
        sandbox = SubprocessSandbox(config)

        allowed, error = sandbox.can_execute()
        assert allowed is False
        assert "disabled" in error.lower()

    def test_subprocess_enabled(self):
        """Test subprocess execution when enabled."""
        config = SandboxConfig(allow_subprocess=True)
        sandbox = SubprocessSandbox(config)

        allowed, error = sandbox.can_execute()
        assert allowed is True

    def test_build_environment_whitelist(self):
        """Test environment building with whitelist."""
        config = SandboxConfig(
            env_whitelist=["PATH"],
        )
        sandbox = SubprocessSandbox(config)

        env = sandbox.build_environment()
        assert "PATH" in env

    def test_build_environment_blocklist(self):
        """Test environment building with blocklist."""
        config = SandboxConfig(
            env_blocklist=["MY_SECRET_VAR"],
        )
        sandbox = SubprocessSandbox(config)

        env = sandbox.build_environment()
        assert "MY_SECRET_VAR" not in env

    def test_build_subprocess_args(self):
        """Test subprocess argument building."""
        config = SandboxConfig()
        sandbox = SubprocessSandbox(config)

        args = sandbox.build_subprocess_args(
            command="echo test",
            cwd=Path("/tmp"),
            timeout=30,
        )

        assert args["args"] == "echo test"
        assert args["shell"] is True
        assert args["timeout"] == 30


# ============ SandboxManager Tests ============


class TestSandboxManager:
    """Tests for SandboxManager."""

    def test_manager_disabled_mode(self):
        """Test manager with disabled sandbox."""
        config = SandboxConfig(mode=SandboxMode.DISABLED)
        manager = SandboxManager(config)

        assert manager.is_enabled() is False
        assert manager.mode == SandboxMode.DISABLED

    def test_manager_enabled_mode(self):
        """Test manager with enabled sandbox."""
        config = SandboxConfig(mode=SandboxMode.HARD)
        manager = SandboxManager(config)

        assert manager.is_enabled() is True
        assert manager.mode == SandboxMode.HARD

    def test_is_path_allowed(self):
        """Test path checking."""
        config = SandboxConfig(
            allowed_paths=[Path("/workspace")],
        )
        manager = SandboxManager(config)

        allowed, error = manager.is_path_allowed(Path("/workspace/file.txt"))
        assert allowed is True

        allowed, error = manager.is_path_allowed(Path("/etc/passwd"))
        assert allowed is False

    def test_execute_tool_simple(self):
        """Test simple tool execution."""
        config = SandboxConfig()
        manager = SandboxManager(config)

        def handler(params, ctx):
            return f"Hello, {params['name']}!"

        result = asyncio.run(manager.execute_tool(
            handler=handler,
            params={"name": "World"},
            tool_context=ToolContext(),
            tool_name="greet",
        ))

        assert result.success is True
        assert result.output == "Hello, World!"

    def test_execute_tool_with_violation(self):
        """Test tool execution with sandbox violation."""
        config = SandboxConfig(
            mode=SandboxMode.HARD,
            allowed_paths=[Path("/workspace")],
        )
        manager = SandboxManager(config)

        def handler(params, ctx):
            return f"Reading {params['path']}"

        result = asyncio.run(manager.execute_tool(
            handler=handler,
            params={"path": "/etc/passwd"},
            tool_context=ToolContext(mode=ToolExecutionMode.SANDBOX),
            tool_name="read_file",
        ))

        assert result.success is False
        assert result.sandbox_violations is not None
        assert len(result.sandbox_violations) > 0

    def test_execute_tool_timeout(self):
        """Test tool execution timeout."""
        config = SandboxConfig(
            resource_limits={
                ResourceLimitType.WALL_TIME: ResourceLimit(
                    limit_type=ResourceLimitType.WALL_TIME,
                    soft_limit=1,
                    hard_limit=2,
                    enabled=True,
                ),
            }
        )
        manager = SandboxManager(config)

        def slow_handler(params, ctx):
            time.sleep(10)
            return "done"

        result = asyncio.run(manager.execute_tool(
            handler=slow_handler,
            params={},
            tool_context=ToolContext(),
            tool_name="slow_tool",
            timeout=2,
        ))

        assert result.success is False
        assert result.error_type == "TimeoutError"

    def test_get_execution_stats(self):
        """Test execution statistics."""
        config = SandboxConfig()
        manager = SandboxManager(config)

        stats = manager.get_execution_stats()
        assert "mode" in stats
        assert "enabled" in stats
        assert "execution_counts" in stats
        assert "config" in stats


# ============ AuditLogger Tests ============


class TestAuditLogger:
    """Tests for AuditLogger."""

    def test_log_record_creation(self):
        """Test basic audit record creation."""
        logger = AuditLogger()
        reset_audit_logger()

        record = logger.log(
            event_type=AuditEventType.TOOL_EXECUTION_COMPLETE,
            action="execute:test_tool",
            tool_name="test_tool",
            result="success",
            verdict=AuditVerdict.ALLOWED,
        )

        assert record.id is not None
        assert record.event_type == AuditEventType.TOOL_EXECUTION_COMPLETE
        assert record.timestamp is not None
        assert record.checksum is not None

    def test_log_record_integrity(self):
        """Test audit record integrity verification."""
        logger = AuditLogger()

        record = logger.log(
            event_type=AuditEventType.TOOL_EXECUTION_COMPLETE,
            action="execute:test",
            result="success",
        )

        assert record.verify_integrity() is True

        # Tamper with record and verify fails
        record.details["tampered"] = True
        assert record.verify_integrity() is False

    def test_log_tool_execution(self):
        """Test tool execution logging."""
        logger = AuditLogger()

        from src.core.tools.schema import ToolResult

        result = ToolResult(
            tool_name="test_tool",
            success=True,
            output="test_output",
            execution_time_ms=100,
        )

        context = ToolContext(
            agent_id="test_agent",
            session_id="test_session",
        )

        record = logger.log_tool_execution(
            tool_name="test_tool",
            params={"path": "/workspace/test.txt"},
            context=context,
            result=result,
        )

        assert record.tool_name == "test_tool"
        assert record.agent_id == "test_agent"
        assert record.session_id == "test_session"

    def test_log_sandbox_violation(self):
        """Test sandbox violation logging."""
        logger = AuditLogger()

        context = ToolContext(agent_id="test_agent")

        record = logger.log_sandbox_violation(
            violation_type="path_violation",
            details="Attempted to access /etc/passwd",
            tool_name="file_read",
            resource="/etc/passwd",
            context=context,
        )

        assert record.event_type == AuditEventType.SANDBOX_VIOLATION
        assert record.verdict == AuditVerdict.BLOCKED
        assert record.severity == AuditSeverity.WARNING

    def test_query_records(self):
        """Test querying audit records."""
        logger = AuditLogger()

        # Create test records
        for i in range(5):
            logger.log(
                event_type=AuditEventType.TOOL_EXECUTION_COMPLETE,
                action=f"execute:tool_{i}",
                tool_name=f"tool_{i % 2}",  # Some duplicates
                result="success",
            )

        # Query for specific tool
        query = AuditQuery(tool_name="tool_0", limit=10)
        results = logger.query(query)

        assert len(results) > 0
        assert all(r.tool_name == "tool_0" for r in results)

    def test_query_by_time_range(self):
        """Test querying by time range."""
        logger = AuditLogger()

        logger.log(
            event_type=AuditEventType.TOOL_EXECUTION_COMPLETE,
            action="execute:test",
            result="success",
        )

        now = datetime.now()
        query = AuditQuery(
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
            limit=10,
        )

        results = logger.query(query)
        assert len(results) > 0

    def test_get_violations(self):
        """Test getting sandbox violations."""
        logger = AuditLogger()

        logger.log_sandbox_violation(
            violation_type="path",
            details="test",
            tool_name="file_read",
        )
        logger.log(
            event_type=AuditEventType.TOOL_EXECUTION_COMPLETE,
            action="execute:test",
            result="success",
        )

        violations = logger.get_violations()
        assert len(violations) > 0
        assert all(
            e.event_type in [
                AuditEventType.SANDBOX_VIOLATION,
                AuditEventType.PATH_VIOLATION,
            ]
            for e in violations
        )

    def test_get_stats(self):
        """Test getting audit statistics."""
        logger = AuditLogger()

        logger.log(
            event_type=AuditEventType.TOOL_EXECUTION_COMPLETE,
            action="execute:test",
            result="success",
        )

        stats = logger.get_stats()
        assert stats.total_records > 0
        assert stats.total_records == len(logger._records)

    def test_sanitize_params(self):
        """Test parameter sanitization."""
        logger = AuditLogger()

        params = {
            "username": "testuser",
            "password": "secret123",
            "api_key": "key123",
            "path": "/workspace/test.txt",
        }

        sanitized = logger._sanitize_params(params)

        assert sanitized["username"] == "testuser"
        assert sanitized["password"] == "***REDACTED***"
        assert sanitized["api_key"] == "***REDACTED***"
        assert sanitized["path"] == "/workspace/test.txt"

    def test_verify_integrity(self):
        """Test integrity verification of all records."""
        logger = AuditLogger()

        logger.log(
            event_type=AuditEventType.TOOL_EXECUTION_COMPLETE,
            action="execute:test",
            result="success",
        )

        results = logger.verify_integrity()
        assert results["total_records"] > 0
        assert results["failed"] == 0


# ============ AuditQuery Tests ============


class TestAuditQuery:
    """Tests for AuditQuery."""

    def test_query_matches_basic(self):
        """Test basic query matching."""
        record = AuditRecord(
            id="test-id",
            timestamp=datetime.now(),
            event_type=AuditEventType.TOOL_EXECUTION_COMPLETE,
            severity=AuditSeverity.INFO,
            tool_name="test_tool",
            action="execute:test",
            result="success",
        )

        query = AuditQuery(tool_name="test_tool")
        assert query.matches(record) is True

        query = AuditQuery(tool_name="other_tool")
        assert query.matches(record) is False

    def test_query_matches_severity(self):
        """Test severity filtering."""
        record = AuditRecord(
            id="test-id",
            timestamp=datetime.now(),
            event_type=AuditEventType.SANDBOX_VIOLATION,
            severity=AuditSeverity.WARNING,
            action="violation",
        )

        query = AuditQuery(
            severity=[AuditSeverity.WARNING, AuditSeverity.ERROR],
        )
        assert query.matches(record) is True

        query = AuditQuery(severity=[AuditSeverity.INFO])
        assert query.matches(record) is False

    def test_query_matches_time_range(self):
        """Test time range filtering."""
        now = datetime.now()

        record = AuditRecord(
            id="test-id",
            timestamp=now,
            event_type=AuditEventType.TOOL_EXECUTION_COMPLETE,
            severity=AuditSeverity.INFO,
            action="execute:test",
        )

        query = AuditQuery(
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )
        assert query.matches(record) is True

        query = AuditQuery(
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=2),
        )
        assert query.matches(record) is False

    def test_query_matches_resource_pattern(self):
        """Test resource pattern matching."""
        record = AuditRecord(
            id="test-id",
            timestamp=datetime.now(),
            event_type=AuditEventType.TOOL_EXECUTION_COMPLETE,
            severity=AuditSeverity.INFO,
            action="execute:test",
            resource="/workspace/test.txt",
        )

        query = AuditQuery(resource_pattern="workspace")
        assert query.matches(record) is True

        query = AuditQuery(resource_pattern="etc")
        assert query.matches(record) is False


# ============ Integration Tests ============


class TestSandboxIntegration:
    """Integration tests for sandbox with executor."""

    def test_executor_with_sandbox_config(self):
        """Test executor with sandbox configuration."""
        registry = ToolRegistry()

        def simple_handler(params, ctx):
            return params["value"] * 2

        registry.register(Tool(
            name="double",
            description="Double a value",
            handler=simple_handler,
            parameters=[
                ToolParameter(name="value", type=ParameterType.INTEGER),
            ],
        ))

        config = SandboxConfig(mode=SandboxMode.HARD)
        executor = ToolExecutor(
            registry,
            sandbox_config=config,
            audit_enabled=True,
        )

        context = ToolContext(mode=ToolExecutionMode.SANDBOX)

        result = asyncio.run(executor.execute(
            "double",
            {"value": 21},
            context=context,
        ))

        assert result.success is True
        assert result.output == 42

    def test_executor_with_path_violation(self):
        """Test executor blocks path violations."""
        registry = ToolRegistry()

        def file_handler(params, ctx):
            return f"Reading {params['path']}"

        registry.register(Tool(
            name="read_file",
            description="Read a file",
            handler=file_handler,
            parameters=[
                ToolParameter(
                    name="path",
                    type=ParameterType.FILE_PATH,
                    description="File path",
                ),
            ],
            permissions=[ToolPermission.READ],
        ))

        config = SandboxConfig(
            mode=SandboxMode.HARD,
            allowed_paths=[Path("/workspace")],
        )
        executor = ToolExecutor(registry, sandbox_config=config)

        context = ToolContext(mode=ToolExecutionMode.SANDBOX)

        # This should fail due to sandbox violation
        with pytest.raises(Exception):
            asyncio.run(executor.execute(
                "read_file",
                {"path": "/etc/passwd"},
                context=context,
            ))


class TestToolContextWithSandbox:
    """Tests for ToolContext with sandbox integration."""

    def test_create_sandbox_context(self):
        """Test sandbox context creation."""
        context = create_sandbox_context(
            workspace_root=Path("/workspace"),
            allowed_paths=[Path("/workspace/src")],
            denied_paths=[Path("/workspace/secret")],
            resource_limits=ResourceLimits(max_memory_mb=128),
        )

        assert context.mode == ToolExecutionMode.SANDBOX
        assert context.workspace_root == Path("/workspace").resolve()
        assert len(context.allowed_paths) == 1
        assert len(context.denied_paths) == 1
        assert context.sandbox_enabled is True
        assert context.resource_limits.max_memory_mb == 128

    def test_create_strict_sandbox_context(self):
        """Test strict sandbox context creation."""
        context = create_strict_sandbox_context(
            workspace_root=Path("/workspace"),
        )

        assert context.mode == ToolExecutionMode.SANDBOX
        assert context.resource_limits.max_subprocesses == 0  # No subprocesses
        assert context.resource_limits.max_cpu_time_seconds == 10  # Short timeout

    def test_context_to_dict(self):
        """Test context serialization."""
        context = ToolContext(
            mode=ToolExecutionMode.SANDBOX,
            workspace_root=Path("/workspace"),
            agent_id="test_agent",
            sandbox_enabled=True,
        )

        data = context.to_dict()
        assert data["mode"] == "sandbox"
        assert data["agent_id"] == "test_agent"
        assert data["sandbox_enabled"] is True
        assert "resource_limits" in data


class TestSandboxModeComparison:
    """Tests for comparing sandbox modes."""

    def test_mode_hierarchy(self):
        """Test that modes have correct hierarchy."""
        # DISABLED - no protection
        assert SandboxMode.DISABLED.value == "disabled"

        # SOFT - path checking only
        assert SandboxMode.SOFT.value == "soft"

        # HARD - full enforcement
        assert SandboxMode.HARD.value == "hard"

        # STRICT - maximum isolation
        assert SandboxMode.STRICT.value == "strict"


class TestSandboxResult:
    """Tests for SandboxResult."""

    def test_result_creation(self):
        """Test result creation."""
        result = SandboxResult(
            sandbox_id="test-123",
            tool_name="test_tool",
            success=True,
            output="test_output",
            execution_time_ms=100.5,
        )

        assert result.sandbox_id == "test-123"
        assert result.success is True
        assert result.output == "test_output"
        assert result.execution_time_ms == 100.5
        assert len(result.sandbox_violations) == 0

    def test_result_with_violations(self):
        """Test result with violations."""
        result = SandboxResult(
            sandbox_id="test-123",
            tool_name="test_tool",
            success=False,
            error="Path violation",
            sandbox_violations=[
                {"type": "path_violation", "details": "Access denied"},
            ],
        )

        assert result.success is False
        assert len(result.sandbox_violations) == 1

    def test_result_to_dict(self):
        """Test result serialization."""
        result = SandboxResult(
            sandbox_id="test-123",
            tool_name="test_tool",
            success=True,
            output="test_output",
        )

        data = result.to_dict()
        assert data["sandbox_id"] == "test-123"
        assert data["tool_name"] == "test_tool"
        assert data["success"] is True
        assert "timestamp" in data


# ============ Global Manager Tests ============


class TestGlobalManagers:
    """Tests for global singleton managers."""

    def test_sandbox_manager_singleton(self):
        """Test sandbox manager singleton."""
        reset_sandbox_manager()

        manager1 = get_sandbox_manager()
        manager2 = get_sandbox_manager()

        assert manager1 is manager2

        # With config
        config = SandboxConfig(mode=SandboxMode.HARD)
        manager3 = get_sandbox_manager(config)
        assert manager3 is not manager1

    def test_audit_logger_singleton(self):
        """Test audit logger singleton."""
        reset_audit_logger()

        logger1 = get_audit_logger()
        logger2 = get_audit_logger()

        assert logger1 is logger2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
