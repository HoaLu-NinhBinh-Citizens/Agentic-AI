"""Unit tests for hardware exceptions."""

import pytest

from src.infrastructure.hardware.exceptions import (
    ErrorCode,
    ExceptionContext,
    EventBusError,
    EventHandlerError,
    EventPublishError,
    EventSchemaError,
    EventSubscriptionError,
    HardwareError,
    IncompatibleTargetError,
    is_hardware_error,
    PluginCrashError,
    PluginError,
    PluginLoadError,
    PluginNotFoundError,
    PluginSignatureError,
    PluginTimeoutError,
    PluginUntrustedError,
    PluginVersionError,
    ProbeDisconnectedError,
    ProbeError,
    ProbeLockedError,
    ProbeNotFoundError,
    ProbeTimeoutError,
    get_error_category,
    SnapshotCaptureError,
    SnapshotCorruptedError,
    SnapshotEncryptionError,
    SnapshotError,
    SnapshotNotFoundError,
    SnapshotRestoreError,
    SnapshotStorageError,
    TargetConfigurationError,
    TargetConnectionError,
    TargetError,
    TargetNotFoundError,
    TargetStateError,
)


class TestExceptionContext:
    """Tests for ExceptionContext."""

    def test_default_context(self):
        """Test default context values."""
        ctx = ExceptionContext()
        assert ctx.target_name is None
        assert ctx.probe_serial is None
        assert ctx.session_id is None
        assert ctx.correlation_id is None
        assert ctx.plugin_name is None
        assert ctx.snapshot_id is None
        assert ctx.extra == {}

    def test_context_with_values(self):
        """Test context with custom values."""
        ctx = ExceptionContext(
            target_name="stm32f4",
            probe_serial="123456",
            session_id="sess-1",
            plugin_name="st_plugin",
        )
        assert ctx.target_name == "stm32f4"
        assert ctx.probe_serial == "123456"
        assert ctx.session_id == "sess-1"
        assert ctx.plugin_name == "st_plugin"

    def test_context_to_dict(self):
        """Test context serialization."""
        ctx = ExceptionContext(target_name="test")
        data = ctx.to_dict()
        assert data["target_name"] == "test"
        assert "timestamp" in data


class TestHardwareError:
    """Tests for base HardwareError."""

    def test_error_code_str_format(self):
        """Test error code string formatting uses 3-digit format."""
        exc = HardwareError("test")
        code_str = exc.error_code_str
        assert code_str.startswith("HARD-")
        # Extract number part and verify 3 digits
        num_part = code_str.split("-")[1]
        assert len(num_part) == 3
        assert num_part.isdigit()

    def test_str_with_context(self):
        """Test string formatting with context."""
        ctx = ExceptionContext(target_name="my_target", probe_serial="ABC")
        exc = HardwareError("connection failed", context=ctx)
        result = str(exc)
        assert "my_target" in result
        assert "ABC" in result
        assert "connection failed" in result

    def test_to_dict(self):
        """Test exception serialization."""
        ctx = ExceptionContext(target_name="test")
        exc = HardwareError("error", context=ctx)
        data = exc.to_dict()
        assert data["type"] == "HardwareError"
        assert data["code"].startswith("HARD-")
        assert data["message"] == "error"
        assert data["context"]["target_name"] == "test"

    def test_cause_chaining(self):
        """Test exception cause chaining."""
        original = ValueError("original")
        exc = HardwareError("wrapper", cause=original)
        assert exc.cause is original
        assert exc.cause.args[0] == "original"


class TestTargetErrors:
    """Tests for TargetError hierarchy."""

    def test_target_not_found(self):
        """Test TargetNotFoundError."""
        exc = TargetNotFoundError("my_target")
        assert exc.target_id == "my_target"
        assert "my_target" in str(exc)
        assert exc.error_code_str.startswith("TARG-")

    def test_incompatible_target(self):
        """Test IncompatibleTargetError."""
        exc = IncompatibleTargetError("chip", "FPU not present")
        assert exc.target_id == "chip"
        assert exc.reason == "FPU not present"
        assert "FPU not present" in str(exc)
        assert exc.error_code_str.startswith("TARG-")

    def test_target_config_error(self):
        """Test TargetConfigurationError."""
        exc = TargetConfigurationError("t1", "probe", "invalid speed")
        assert exc.target_id == "t1"
        assert exc.field == "probe"
        assert "probe" in str(exc)
        assert exc.error_code_str.startswith("TARG-")

    def test_target_connection_error(self):
        """Test TargetConnectionError."""
        exc = TargetConnectionError("target", "timeout")
        assert exc.target_id == "target"
        assert exc.reason == "timeout"
        assert exc.error_code_str.startswith("TARG-")

    def test_target_state_error(self):
        """Test TargetStateError."""
        exc = TargetStateError("t1", "RUNNING", ["HALTED", "CONNECTED"])
        assert exc.target_id == "t1"
        assert exc.current_state == "RUNNING"
        assert exc.error_code_str.startswith("TARG-")

    def test_is_target_error(self):
        """Test is_hardware_error with target errors."""
        exc = TargetNotFoundError("test")
        assert is_hardware_error(exc)
        assert get_error_category(exc) == "target"


class TestProbeErrors:
    """Tests for ProbeError hierarchy."""

    def test_probe_not_found(self):
        """Test ProbeNotFoundError."""
        exc = ProbeNotFoundError("SERIAL123")
        assert exc.probe_serial == "SERIAL123"
        assert "SERIAL123" in str(exc)
        assert exc.error_code_str.startswith("PROBE-")

    def test_probe_not_found_no_serial(self):
        """Test ProbeNotFoundError without serial."""
        exc = ProbeNotFoundError()
        assert exc.probe_serial is None
        assert "No probe found" in str(exc)

    def test_probe_disconnected(self):
        """Test ProbeDisconnectedError."""
        exc = ProbeDisconnectedError("ABC")
        assert exc.probe_serial == "ABC"
        assert exc.error_code_str.startswith("PROBE-")

    def test_probe_timeout(self):
        """Test ProbeTimeoutError."""
        exc = ProbeTimeoutError("read", 5.0, "PROBE1")
        assert exc.operation == "read"
        assert exc.timeout_seconds == 5.0
        assert exc.probe_serial == "PROBE1"
        assert "read" in str(exc)
        assert exc.error_code_str.startswith("PROBE-")

    def test_probe_locked(self):
        """Test ProbeLockedError."""
        exc = ProbeLockedError("P1", "session-2")
        assert exc.probe_serial == "P1"
        assert exc.locked_by == "session-2"
        assert "session-2" in str(exc)
        assert exc.error_code_str.startswith("PROBE-")

    def test_is_probe_error(self):
        """Test is_hardware_error with probe errors."""
        exc = ProbeNotFoundError("test")
        assert is_hardware_error(exc)
        assert get_error_category(exc) == "probe"


class TestPluginErrors:
    """Tests for PluginError hierarchy."""

    def test_plugin_load_error(self):
        """Test PluginLoadError."""
        exc = PluginLoadError("my_plugin", "import failed")
        assert exc.plugin_name == "my_plugin"
        assert exc.reason == "import failed"
        assert exc.error_code_str.startswith("PLUG-")

    def test_plugin_not_found(self):
        """Test PluginNotFoundError."""
        exc = PluginNotFoundError("unknown")
        assert exc.plugin_name == "unknown"
        assert exc.error_code_str.startswith("PLUG-")

    def test_plugin_timeout(self):
        """Test PluginTimeoutError."""
        exc = PluginTimeoutError("plugin", "init", 3.0)
        assert exc.plugin_name == "plugin"
        assert exc.operation == "init"
        assert exc.timeout_seconds == 3.0
        assert exc.error_code_str.startswith("PLUG-")

    def test_plugin_crashed(self):
        """Test PluginCrashError."""
        exc = PluginCrashError("bad_plugin", exit_code=1)
        assert exc.plugin_name == "bad_plugin"
        assert exc.exit_code == 1
        assert exc.error_code_str.startswith("PLUG-")

    def test_plugin_signature_error(self):
        """Test PluginSignatureError."""
        exc = PluginSignatureError("p1", "expired certificate")
        assert exc.plugin_name == "p1"
        assert exc.reason == "expired certificate"
        assert exc.error_code_str.startswith("PLUG-")

    def test_plugin_untrusted(self):
        """Test PluginUntrustedError."""
        exc = PluginUntrustedError("p1", "UNTRUSTED")
        assert exc.plugin_name == "p1"
        assert exc.trust_level == "UNTRUSTED"
        assert exc.error_code_str.startswith("PLUG-")

    def test_plugin_version_error(self):
        """Test PluginVersionError."""
        exc = PluginVersionError("p1", "1.0.0", "2.0.0")
        assert exc.plugin_name == "p1"
        assert exc.plugin_version == "1.0.0"
        assert exc.required_version == "2.0.0"
        assert exc.error_code_str.startswith("PLUG-")

    def test_is_plugin_error(self):
        """Test is_hardware_error with plugin errors."""
        exc = PluginNotFoundError("test")
        assert is_hardware_error(exc)
        assert get_error_category(exc) == "plugin"


class TestSnapshotErrors:
    """Tests for SnapshotError hierarchy."""

    def test_snapshot_capture_error(self):
        """Test SnapshotCaptureError."""
        exc = SnapshotCaptureError("t1", "memory read failed")
        assert exc.target_id == "t1"
        assert exc.reason == "memory read failed"
        assert exc.error_code_str.startswith("SNAP-")

    def test_snapshot_restore_error(self):
        """Test SnapshotRestoreError."""
        exc = SnapshotRestoreError("snap1", "t1", "checksum mismatch")
        assert exc.snapshot_id == "snap1"
        assert exc.target_id == "t1"
        assert exc.reason == "checksum mismatch"
        assert exc.error_code_str.startswith("SNAP-")

    def test_snapshot_not_found(self):
        """Test SnapshotNotFoundError."""
        exc = SnapshotNotFoundError("snap123")
        assert exc.snapshot_id == "snap123"
        assert "snap123" in str(exc)
        assert exc.error_code_str.startswith("SNAP-")

    def test_snapshot_corrupted(self):
        """Test SnapshotCorruptedError."""
        exc = SnapshotCorruptedError("s1", "truncated data")
        assert exc.snapshot_id == "s1"
        assert exc.reason == "truncated data"
        assert exc.error_code_str.startswith("SNAP-")

    def test_snapshot_encryption_error(self):
        """Test SnapshotEncryptionError."""
        exc = SnapshotEncryptionError("s1", "decrypt", "wrong key")
        assert exc.snapshot_id == "s1"
        assert exc.operation == "decrypt"
        assert exc.reason == "wrong key"
        assert exc.error_code_str.startswith("SNAP-")

    def test_snapshot_storage_error(self):
        """Test SnapshotStorageError."""
        exc = SnapshotStorageError("disk full")
        assert exc.reason == "disk full"
        assert exc.error_code_str.startswith("SNAP-")

    def test_is_snapshot_error(self):
        """Test is_hardware_error with snapshot errors."""
        exc = SnapshotNotFoundError("test")
        assert is_hardware_error(exc)
        assert get_error_category(exc) == "snapshot"


class TestEventBusErrors:
    """Tests for EventBusError hierarchy."""

    def test_event_subscription_error(self):
        """Test EventSubscriptionError."""
        exc = EventSubscriptionError("TargetDetected", "handler limit reached")
        assert exc.event_type == "TargetDetected"
        assert exc.reason == "handler limit reached"
        assert exc.error_code_str.startswith("EVNT-")

    def test_event_publish_error(self):
        """Test EventPublishError."""
        exc = EventPublishError("HardFault", "queue full")
        assert exc.event_type == "HardFault"
        assert exc.reason == "queue full"
        assert exc.error_code_str.startswith("EVNT-")

    def test_event_handler_error(self):
        """Test EventHandlerError."""
        original = ValueError("bad data")
        exc = EventHandlerError("TestEvent", "my_handler", original)
        assert exc.event_type == "TestEvent"
        assert exc.handler_name == "my_handler"
        assert exc.original_error is original
        assert exc.error_code_str.startswith("EVNT-")

    def test_event_schema_error(self):
        """Test EventSchemaError."""
        exc = EventSchemaError("Test", "1.0", "missing required field")
        assert exc.event_type == "Test"
        assert exc.version == "1.0"
        assert exc.reason == "missing required field"
        assert exc.error_code_str.startswith("EVNT-")

    def test_is_event_bus_error(self):
        """Test is_hardware_error with event bus errors."""
        exc = EventPublishError("Test", "reason")
        assert is_hardware_error(exc)
        assert get_error_category(exc) == "event_bus"


class TestErrorUtilities:
    """Tests for error utility functions."""

    def test_is_hardware_error_true(self):
        """Test is_hardware_error returns True for hardware errors."""
        assert is_hardware_error(HardwareError("test"))
        assert is_hardware_error(TargetError("test"))
        assert is_hardware_error(ProbeError("test"))
        assert is_hardware_error(PluginError("test"))
        assert is_hardware_error(SnapshotError("test"))
        assert is_hardware_error(EventBusError("test"))

    def test_is_hardware_error_false(self):
        """Test is_hardware_error returns False for non-hardware errors."""
        assert not is_hardware_error(ValueError("test"))
        assert not is_hardware_error(RuntimeError("test"))
        assert not is_hardware_error(IOError("test"))

    def test_get_error_category(self):
        """Test error category detection."""
        assert get_error_category(TargetError("test")) == "target"
        assert get_error_category(ProbeError("test")) == "probe"
        assert get_error_category(PluginError("test")) == "plugin"
        assert get_error_category(SnapshotError("test")) == "snapshot"
        assert get_error_category(EventBusError("test")) == "event_bus"
        assert get_error_category(HardwareError("test")) == "hardware"
        assert get_error_category(ValueError("test")) == "unknown"


class TestExceptionInheritance:
    """Tests for exception inheritance hierarchy."""

    def test_target_inherits_hardware(self):
        """Test TargetError inherits from HardwareError."""
        exc = TargetError("test")
        assert isinstance(exc, HardwareError)
        assert isinstance(exc, Exception)

    def test_probe_inherits_hardware(self):
        """Test ProbeError inherits from HardwareError."""
        exc = ProbeError("test")
        assert isinstance(exc, HardwareError)
        assert isinstance(exc, Exception)

    def test_plugin_inherits_hardware(self):
        """Test PluginError inherits from HardwareError."""
        exc = PluginError("test")
        assert isinstance(exc, HardwareError)
        assert isinstance(exc, Exception)

    def test_snapshot_inherits_hardware(self):
        """Test SnapshotError inherits from HardwareError."""
        exc = SnapshotError("test")
        assert isinstance(exc, HardwareError)
        assert isinstance(exc, Exception)

    def test_event_bus_inherits_hardware(self):
        """Test EventBusError inherits from HardwareError."""
        exc = EventBusError("test")
        assert isinstance(exc, HardwareError)
        assert isinstance(exc, Exception)
