"""Hardware infrastructure exception hierarchy.

This module defines a comprehensive exception tree for all hardware-related errors
in the AI_SUPPORT embedded debugging system.

Exception Code Convention:
- HARD-XXX: General hardware errors
- TARG-XXX: Target-related errors
- PROBE-XXX: Probe-related errors
- PLUG-XXX: Plugin-related errors
- SNAP-XXX: Snapshot-related errors
- EVNT-XXX: Event bus errors
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class ErrorCode(Enum):
    """Standardized error codes for hardware layer."""

    # General Hardware (HARD-XXX)
    HARD_UNKNOWN = auto()
    HARD_INIT_FAILED = auto()
    HARD_CONFIG_INVALID = auto()
    HARD_TIMEOUT = auto()
    HARD_NOT_SUPPORTED = auto()

    # Target (TARG-XXX)
    TARG_NOT_FOUND = auto()
    TARG_INCOMPATIBLE = auto()
    TARG_CONFIG_INVALID = auto()
    TARG_ALREADY_EXISTS = auto()
    TARG_STATE_INVALID = auto()
    TARG_CONNECTION_FAILED = auto()
    TARG_DISCONNECTED = auto()

    # Probe (PROBE-XXX)
    PROBE_NOT_FOUND = auto()
    PROBE_DISCONNECTED = auto()
    PROBE_TIMEOUT = auto()
    PROBE_INIT_FAILED = auto()
    PROBE_LOCKED = auto()
    PROBE_IN_USE = auto()

    # Plugin (PLUG-XXX)
    PLUG_LOAD_FAILED = auto()
    PLUG_NOT_FOUND = auto()
    PLUG_TIMEOUT = auto()
    PLUG_CRASHED = auto()
    PLUG_SIGNATURE_INVALID = auto()
    PLUG_UNTRUSTED = auto()
    PLUG_VERSION_INCOMPATIBLE = auto()

    # Snapshot (SNAP-XXX)
    SNAP_CAPTURE_FAILED = auto()
    SNAP_RESTORE_FAILED = auto()
    SNAP_NOT_FOUND = auto()
    SNAP_CORRUPTED = auto()
    SNAP_ENCRYPTION_FAILED = auto()
    SNAP_DECRYPTION_FAILED = auto()
    SNAP_STORAGE_FULL = auto()
    SNAP_POLICY_VIOLATED = auto()

    # Event Bus (EVNT-XXX)
    EVNT_SUBSCRIBE_FAILED = auto()
    EVNT_PUBLISH_FAILED = auto()
    EVNT_HANDLER_FAILED = auto()
    EVNT_DLQ_FULL = auto()
    EVNT_SCHEMA_INVALID = auto()


@dataclass
class ExceptionContext:
    """Context information for exceptions."""

    target_name: str | None = None
    probe_serial: str | None = None
    session_id: str | None = None
    correlation_id: str | None = None
    plugin_name: str | None = None
    snapshot_id: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "target_name": self.target_name,
            "probe_serial": self.probe_serial,
            "session_id": self.session_id,
            "correlation_id": self.correlation_id,
            "plugin_name": self.plugin_name,
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp.isoformat(),
            "extra": self.extra,
        }


class HardwareError(Exception):
    """Base exception for all hardware-related errors.

    All hardware exceptions inherit from this class. Each exception
    includes an error code, context, and formatted message.

    Attributes:
        code: ErrorCode enum value
        message: Human-readable error message
        context: Additional context information
    """

    DEFAULT_CODE = ErrorCode.HARD_UNKNOWN
    CODE_PREFIX = "HARD"

    def __init__(
        self,
        message: str,
        code: ErrorCode | None = None,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code or self.DEFAULT_CODE
        self.context = context or ExceptionContext()
        self.cause = cause

    @property
    def error_code_str(self) -> str:
        """Get string representation of error code."""
        return f"{self.CODE_PREFIX}-{self.code.value:03d}"

    def __str__(self) -> str:
        """Format exception as string."""
        parts = [f"[{self.error_code_str}] {self.message}"]
        if self.context.target_name:
            parts.append(f"target={self.context.target_name}")
        if self.context.probe_serial:
            parts.append(f"probe={self.context.probe_serial}")
        if self.context.plugin_name:
            parts.append(f"plugin={self.context.plugin_name}")
        return " | ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for logging."""
        return {
            "type": self.__class__.__name__,
            "code": self.error_code_str,
            "message": self.message,
            "context": self.context.to_dict(),
            "cause": str(self.cause) if self.cause else None,
        }


# ============================================================================
# Target Errors
# ============================================================================


class TargetError(HardwareError):
    """Base exception for target-related errors."""

    DEFAULT_CODE = ErrorCode.TARG_STATE_INVALID
    CODE_PREFIX = "TARG"


class TargetNotFoundError(TargetError):
    """Target not found in registry or connected to probe."""

    DEFAULT_CODE = ErrorCode.TARG_NOT_FOUND

    def __init__(
        self,
        target_id: str,
        message: str | None = None,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = message or f"Target not found: {target_id}"
        super().__init__(msg, cause=cause)
        self.target_id = target_id
        if context:
            context.target_name = target_id
        self.context = context or ExceptionContext(target_name=target_id)


class IncompatibleTargetError(TargetError):
    """Target is incompatible with requested operation."""

    DEFAULT_CODE = ErrorCode.TARG_INCOMPATIBLE

    def __init__(
        self,
        target_id: str,
        reason: str,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Target {target_id} incompatible: {reason}"
        super().__init__(msg, cause=cause)
        self.target_id = target_id
        self.reason = reason
        if context:
            context.target_name = target_id
        self.context = context or ExceptionContext(target_name=target_id)


class TargetConfigurationError(TargetError):
    """Target configuration is invalid."""

    DEFAULT_CODE = ErrorCode.TARG_CONFIG_INVALID

    def __init__(
        self,
        target_id: str,
        field: str,
        reason: str,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Target {target_id} config error in '{field}': {reason}"
        super().__init__(msg, cause=cause)
        self.target_id = target_id
        self.field = field
        self.reason = reason
        self.context = context or ExceptionContext(target_name=target_id)


class TargetConnectionError(TargetError):
    """Failed to connect to target."""

    DEFAULT_CODE = ErrorCode.TARG_CONNECTION_FAILED

    def __init__(
        self,
        target_id: str,
        reason: str,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Failed to connect to target {target_id}: {reason}"
        super().__init__(msg, cause=cause)
        self.target_id = target_id
        self.reason = reason
        self.context = context or ExceptionContext(target_name=target_id)


class TargetStateError(TargetError):
    """Target is in invalid state for operation."""

    DEFAULT_CODE = ErrorCode.TARG_STATE_INVALID

    def __init__(
        self,
        target_id: str,
        current_state: str,
        expected_states: list[str],
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        expected = ", ".join(expected_states)
        msg = f"Target {target_id} in state {current_state}, expected one of [{expected}]"
        super().__init__(msg, cause=cause)
        self.target_id = target_id
        self.current_state = current_state
        self.expected_states = expected_states
        self.context = context or ExceptionContext(target_name=target_id)


# ============================================================================
# Probe Errors
# ============================================================================


class ProbeError(HardwareError):
    """Base exception for probe-related errors."""

    DEFAULT_CODE = ErrorCode.PROBE_INIT_FAILED
    CODE_PREFIX = "PROBE"


class ProbeNotFoundError(ProbeError):
    """Debug probe not found or not connected."""

    DEFAULT_CODE = ErrorCode.PROBE_NOT_FOUND

    def __init__(
        self,
        probe_serial: str | None = None,
        message: str | None = None,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        if probe_serial:
            msg = message or f"Probe not found: {probe_serial}"
        else:
            msg = message or "No probe found"
        super().__init__(msg, cause=cause)
        self.probe_serial = probe_serial
        self.context = context or ExceptionContext(probe_serial=probe_serial)


class ProbeDisconnectedError(ProbeError):
    """Probe disconnected during operation."""

    DEFAULT_CODE = ErrorCode.PROBE_DISCONNECTED

    def __init__(
        self,
        probe_serial: str | None = None,
        message: str | None = None,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = message or f"Probe disconnected: {probe_serial or 'unknown'}"
        super().__init__(msg, cause=cause)
        self.probe_serial = probe_serial
        self.context = context or ExceptionContext(probe_serial=probe_serial)


class ProbeTimeoutError(ProbeError):
    """Probe operation timed out."""

    DEFAULT_CODE = ErrorCode.PROBE_TIMEOUT

    def __init__(
        self,
        operation: str,
        timeout_seconds: float,
        probe_serial: str | None = None,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Probe operation '{operation}' timed out after {timeout_seconds}s"
        super().__init__(msg, cause=cause)
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        self.probe_serial = probe_serial
        self.context = context or ExceptionContext(probe_serial=probe_serial)


class ProbeLockedError(ProbeError):
    """Probe is locked by another session."""

    DEFAULT_CODE = ErrorCode.PROBE_LOCKED

    def __init__(
        self,
        probe_serial: str,
        locked_by: str,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Probe {probe_serial} locked by session {locked_by}"
        super().__init__(msg, cause=cause)
        self.probe_serial = probe_serial
        self.locked_by = locked_by
        self.context = context or ExceptionContext(probe_serial=probe_serial)


# ============================================================================
# Plugin Errors
# ============================================================================


class PluginError(HardwareError):
    """Base exception for plugin-related errors."""

    DEFAULT_CODE = ErrorCode.PLUG_LOAD_FAILED
    CODE_PREFIX = "PLUG"


class PluginLoadError(PluginError):
    """Failed to load plugin."""

    DEFAULT_CODE = ErrorCode.PLUG_LOAD_FAILED

    def __init__(
        self,
        plugin_name: str,
        reason: str,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Failed to load plugin '{plugin_name}': {reason}"
        super().__init__(msg, cause=cause)
        self.plugin_name = plugin_name
        self.reason = reason
        self.context = context or ExceptionContext(plugin_name=plugin_name)


class PluginNotFoundError(PluginError):
    """Plugin not found."""

    DEFAULT_CODE = ErrorCode.PLUG_NOT_FOUND

    def __init__(
        self,
        plugin_name: str,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Plugin not found: {plugin_name}"
        super().__init__(msg, cause=cause)
        self.plugin_name = plugin_name
        self.context = context or ExceptionContext(plugin_name=plugin_name)


class PluginTimeoutError(PluginError):
    """Plugin operation timed out."""

    DEFAULT_CODE = ErrorCode.PLUG_TIMEOUT

    def __init__(
        self,
        plugin_name: str,
        operation: str,
        timeout_seconds: float,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Plugin '{plugin_name}' operation '{operation}' timed out after {timeout_seconds}s"
        super().__init__(msg, cause=cause)
        self.plugin_name = plugin_name
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        self.context = context or ExceptionContext(plugin_name=plugin_name)


class PluginCrashError(PluginError):
    """Plugin crashed during execution."""

    DEFAULT_CODE = ErrorCode.PLUG_CRASHED

    def __init__(
        self,
        plugin_name: str,
        exit_code: int | None = None,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Plugin '{plugin_name}' crashed"
        if exit_code is not None:
            msg += f" (exit code: {exit_code})"
        super().__init__(msg, cause=cause)
        self.plugin_name = plugin_name
        self.exit_code = exit_code
        self.context = context or ExceptionContext(plugin_name=plugin_name)


class PluginSignatureError(PluginError):
    """Plugin signature verification failed."""

    DEFAULT_CODE = ErrorCode.PLUG_SIGNATURE_INVALID

    def __init__(
        self,
        plugin_name: str,
        reason: str,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Plugin '{plugin_name}' signature invalid: {reason}"
        super().__init__(msg, cause=cause)
        self.plugin_name = plugin_name
        self.reason = reason
        self.context = context or ExceptionContext(plugin_name=plugin_name)


class PluginUntrustedError(PluginError):
    """Plugin is not trusted."""

    DEFAULT_CODE = ErrorCode.PLUG_UNTRUSTED

    def __init__(
        self,
        plugin_name: str,
        trust_level: str,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Plugin '{plugin_name}' has trust level '{trust_level}' which is insufficient"
        super().__init__(msg, cause=cause)
        self.plugin_name = plugin_name
        self.trust_level = trust_level
        self.context = context or ExceptionContext(plugin_name=plugin_name)


class PluginVersionError(PluginError):
    """Plugin version incompatible with runtime."""

    DEFAULT_CODE = ErrorCode.PLUG_VERSION_INCOMPATIBLE

    def __init__(
        self,
        plugin_name: str,
        plugin_version: str,
        required_version: str,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Plugin '{plugin_name}' version {plugin_version} incompatible, required: {required_version}"
        super().__init__(msg, cause=cause)
        self.plugin_name = plugin_name
        self.plugin_version = plugin_version
        self.required_version = required_version
        self.context = context or ExceptionContext(plugin_name=plugin_name)


# ============================================================================
# Snapshot Errors
# ============================================================================


class SnapshotError(HardwareError):
    """Base exception for snapshot-related errors."""

    DEFAULT_CODE = ErrorCode.SNAP_CAPTURE_FAILED
    CODE_PREFIX = "SNAP"


class SnapshotCaptureError(SnapshotError):
    """Failed to capture target snapshot."""

    DEFAULT_CODE = ErrorCode.SNAP_CAPTURE_FAILED

    def __init__(
        self,
        target_id: str,
        reason: str,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Failed to capture snapshot for target {target_id}: {reason}"
        super().__init__(msg, cause=cause)
        self.target_id = target_id
        self.reason = reason
        self.context = context or ExceptionContext(target_name=target_id)


class SnapshotRestoreError(SnapshotError):
    """Failed to restore target from snapshot."""

    DEFAULT_CODE = ErrorCode.SNAP_RESTORE_FAILED

    def __init__(
        self,
        snapshot_id: str,
        target_id: str,
        reason: str,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Failed to restore snapshot {snapshot_id} to target {target_id}: {reason}"
        super().__init__(msg, cause=cause)
        self.snapshot_id = snapshot_id
        self.target_id = target_id
        self.reason = reason
        self.context = context or ExceptionContext(
            target_name=target_id,
            snapshot_id=snapshot_id,
        )


class SnapshotNotFoundError(SnapshotError):
    """Snapshot not found."""

    DEFAULT_CODE = ErrorCode.SNAP_NOT_FOUND

    def __init__(
        self,
        snapshot_id: str,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Snapshot not found: {snapshot_id}"
        super().__init__(msg, cause=cause)
        self.snapshot_id = snapshot_id
        self.context = context or ExceptionContext(snapshot_id=snapshot_id)


class SnapshotCorruptedError(SnapshotError):
    """Snapshot data is corrupted."""

    DEFAULT_CODE = ErrorCode.SNAP_CORRUPTED

    def __init__(
        self,
        snapshot_id: str,
        reason: str,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Snapshot {snapshot_id} corrupted: {reason}"
        super().__init__(msg, cause=cause)
        self.snapshot_id = snapshot_id
        self.reason = reason
        self.context = context or ExceptionContext(snapshot_id=snapshot_id)


class SnapshotEncryptionError(SnapshotError):
    """Snapshot encryption/decryption failed."""

    DEFAULT_CODE = ErrorCode.SNAP_ENCRYPTION_FAILED

    def __init__(
        self,
        snapshot_id: str,
        operation: str,
        reason: str,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Snapshot {snapshot_id} encryption {operation} failed: {reason}"
        super().__init__(msg, cause=cause)
        self.snapshot_id = snapshot_id
        self.operation = operation
        self.reason = reason
        self.context = context or ExceptionContext(snapshot_id=snapshot_id)


class SnapshotStorageError(SnapshotError):
    """Snapshot storage operation failed."""

    DEFAULT_CODE = ErrorCode.SNAP_STORAGE_FULL

    def __init__(
        self,
        reason: str,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Snapshot storage error: {reason}"
        super().__init__(msg, cause=cause)
        self.reason = reason
        self.context = context or ExceptionContext()


# ============================================================================
# Event Bus Errors
# ============================================================================


class EventBusError(HardwareError):
    """Base exception for event bus errors."""

    DEFAULT_CODE = ErrorCode.EVNT_PUBLISH_FAILED
    CODE_PREFIX = "EVNT"


class EventSubscriptionError(EventBusError):
    """Failed to subscribe to event."""

    DEFAULT_CODE = ErrorCode.EVNT_SUBSCRIBE_FAILED

    def __init__(
        self,
        event_type: str,
        reason: str,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Failed to subscribe to event '{event_type}': {reason}"
        super().__init__(msg, cause=cause)
        self.event_type = event_type
        self.reason = reason
        self.context = context or ExceptionContext()


class EventPublishError(EventBusError):
    """Failed to publish event."""

    DEFAULT_CODE = ErrorCode.EVNT_PUBLISH_FAILED

    def __init__(
        self,
        event_type: str,
        reason: str,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Failed to publish event '{event_type}': {reason}"
        super().__init__(msg, cause=cause)
        self.event_type = event_type
        self.reason = reason
        self.context = context or ExceptionContext()


class EventHandlerError(EventBusError):
    """Event handler raised an exception."""

    DEFAULT_CODE = ErrorCode.EVNT_HANDLER_FAILED

    def __init__(
        self,
        event_type: str,
        handler_name: str,
        original_error: Exception,
        context: ExceptionContext | None = None,
    ):
        msg = f"Event handler '{handler_name}' failed for '{event_type}': {original_error}"
        super().__init__(msg, cause=original_error)
        self.event_type = event_type
        self.handler_name = handler_name
        self.original_error = original_error
        self.context = context or ExceptionContext()


class EventSchemaError(EventBusError):
    """Event schema validation failed."""

    DEFAULT_CODE = ErrorCode.EVNT_SCHEMA_INVALID

    def __init__(
        self,
        event_type: str,
        version: str,
        reason: str,
        context: ExceptionContext | None = None,
        cause: Exception | None = None,
    ):
        msg = f"Event '{event_type}' schema v{version} invalid: {reason}"
        super().__init__(msg, cause=cause)
        self.event_type = event_type
        self.version = version
        self.reason = reason
        self.context = context or ExceptionContext()


# ============================================================================
# Exception Utilities
# ============================================================================


def is_hardware_error(exc: Exception) -> bool:
    """Check if exception is a hardware error."""
    return isinstance(exc, HardwareError)


def get_error_category(exc: Exception) -> str:
    """Get error category from exception."""
    if isinstance(exc, TargetError):
        return "target"
    if isinstance(exc, ProbeError):
        return "probe"
    if isinstance(exc, PluginError):
        return "plugin"
    if isinstance(exc, SnapshotError):
        return "snapshot"
    if isinstance(exc, EventBusError):
        return "event_bus"
    if isinstance(exc, HardwareError):
        return "hardware"
    return "unknown"


def reraise_with_context(
    exc: Exception,
    context: ExceptionContext,
    new_exc_type: type[HardwareError],
    message: str | None = None,
) -> None:
    """Reraise exception with additional context.

    Args:
        exc: Original exception
        context: New context to attach
        new_exc_type: Type of new exception to raise
        message: Optional custom message
    """
    if issubclass(new_exc_type, TargetError):
        raise new_exc_type(
            target_id=context.target_name or "unknown",
            message=message,
            context=context,
            cause=exc,
        ) from exc
    elif issubclass(new_exc_type, ProbeError):
        raise new_exc_type(
            probe_serial=context.probe_serial,
            message=message,
            context=context,
            cause=exc,
        ) from exc
    elif issubclass(new_exc_type, PluginError):
        raise new_exc_type(
            plugin_name=context.plugin_name or "unknown",
            reason=message or str(exc),
            context=context,
            cause=exc,
        ) from exc
    elif issubclass(new_exc_type, SnapshotError):
        raise new_exc_type(
            snapshot_id=context.snapshot_id or "unknown",
            reason=message or str(exc),
            context=context,
            cause=exc,
        ) from exc
    else:
        raise new_exc_type(
            message=message or str(exc),
            context=context,
            cause=exc,
        ) from exc
