"""
P2 Audit Trail - Security Audit Logging for Tool Execution

Provides comprehensive, persistent audit logging for all tool operations.
This enables security analysis, replay, and compliance requirements.

Features:
- Immutable audit records
- Structured JSON logging
- Integrity verification (checksums)
- Query and search capabilities
- Retention policy management
- Event correlation
- Violation tracking

Usage:
    from src.core.tools.audit import AuditLogger, AuditQuery

    # Log an event
    audit = AuditLogger()
    audit.log_tool_execution(
        tool_name="file_read",
        params={"path": "/workspace/test.txt"},
        result=tool_result,
        sandbox_result=sandbox_result,
    )

    # Query audit logs
    query = AuditQuery(tool_name="file_read", limit=100)
    results = audit.query(query)
"""

import asyncio
import hashlib
import json
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Types of auditable events."""

    TOOL_EXECUTION_START = "tool_execution_start"
    TOOL_EXECUTION_COMPLETE = "tool_execution_complete"
    TOOL_EXECUTION_ERROR = "tool_execution_error"
    TOOL_EXECUTION_TIMEOUT = "tool_execution_timeout"
    SANDBOX_VIOLATION = "sandbox_violation"
    SANDBOX_VIOLATION_BLOCKED = "sandbox_violation_blocked"
    RESOURCE_LIMIT_EXCEEDED = "resource_limit_exceeded"
    PERMISSION_CHECK = "permission_check"
    PERMISSION_DENIED = "permission_denied"
    PATH_VIOLATION = "path_violation"
    SUBPROCESS_SPAWNED = "subprocess_spawned"
    SUBPROCESS_TERMINATED = "subprocess_terminated"
    NETWORK_REQUEST = "network_request"
    FILE_CREATED = "file_created"
    FILE_DELETED = "file_deleted"
    FILE_MODIFIED = "file_modified"
    FLASH_OPERATION = "flash_operation"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    AGENT_AUTHENTICATED = "agent_authenticated"
    CONFIGURATION_CHANGED = "configuration_changed"


class AuditSeverity(Enum):
    """Severity levels for audit events."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    SECURITY = "security"  # Security-related events


class AuditVerdict(Enum):
    """Verdict for permission checks."""

    ALLOWED = "allowed"
    DENIED = "denied"
    BLOCKED = "blocked"
    WARNED = "warned"


@dataclass
class AuditRecord:
    """
    Immutable audit record for a single event.

    Attributes:
        id: Unique record identifier
        timestamp: When the event occurred
        event_type: Type of event
        severity: Event severity
        agent_id: ID of the agent performing the action
        session_id: Current session identifier
        tool_name: Name of tool involved (if applicable)
        action: Action performed
        resource: Resource accessed (file path, URL, etc.)
        result: Result of the action
        verdict: Permission verdict
        details: Additional event details
        sandbox_id: Associated sandbox execution ID
        correlation_id: Links related events
        checksum: Integrity checksum
        parent_id: ID of parent event (for event chains)
    """

    id: str
    timestamp: datetime
    event_type: AuditEventType
    severity: AuditSeverity
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    tool_name: Optional[str] = None
    action: str = ""
    resource: Optional[str] = None
    result: Optional[str] = None
    verdict: Optional[AuditVerdict] = None
    details: Dict[str, Any] = field(default_factory=dict)
    sandbox_id: Optional[str] = None
    correlation_id: Optional[str] = None
    checksum: Optional[str] = None
    parent_id: Optional[str] = None

    def __post_init__(self):
        """Generate checksum after initialization."""
        if self.checksum is None:
            self.checksum = self._compute_checksum()

    def _compute_checksum(self) -> str:
        """Compute integrity checksum for the record."""
        data = {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "tool_name": self.tool_name,
            "action": self.action,
            "resource": self.resource,
            "result": self.result,
            "verdict": self.verdict.value if self.verdict else None,
            "details": self.details,
            "correlation_id": self.correlation_id,
            "parent_id": self.parent_id,
        }
        content = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def verify_integrity(self) -> bool:
        """
        Verify the record has not been tampered with.

        Returns:
            True if checksum is valid
        """
        return self.checksum == self._compute_checksum()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "tool_name": self.tool_name,
            "action": self.action,
            "resource": self.resource,
            "result": self.result,
            "verdict": self.verdict.value if self.verdict else None,
            "details": self.details,
            "sandbox_id": self.sandbox_id,
            "correlation_id": self.correlation_id,
            "checksum": self.checksum,
            "parent_id": self.parent_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditRecord":
        """Create AuditRecord from dictionary."""
        return cls(
            id=data["id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            event_type=AuditEventType(data["event_type"]),
            severity=AuditSeverity(data["severity"]),
            agent_id=data.get("agent_id"),
            session_id=data.get("session_id"),
            tool_name=data.get("tool_name"),
            action=data.get("action", ""),
            resource=data.get("resource"),
            result=data.get("result"),
            verdict=AuditVerdict(data["verdict"]) if data.get("verdict") else None,
            details=data.get("details", {}),
            sandbox_id=data.get("sandbox_id"),
            correlation_id=data.get("correlation_id"),
            checksum=data.get("checksum"),
            parent_id=data.get("parent_id"),
        )


@dataclass
class AuditQuery:
    """
    Query parameters for searching audit records.

    Attributes:
        start_time: Filter events after this time
        end_time: Filter events before this time
        event_types: Filter by event types
        severity: Filter by severity levels
        agent_id: Filter by agent ID
        session_id: Filter by session ID
        tool_name: Filter by tool name
        resource: Filter by resource (substring match)
        verdict: Filter by verdict
        correlation_id: Filter by correlation ID
        limit: Maximum number of results
        offset: Offset for pagination
        order_by: Field to order by (default: timestamp)
        ascending: Sort order
    """

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    event_types: Optional[List[AuditEventType]] = None
    severity: Optional[List[AuditSeverity]] = None
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    tool_name: Optional[str] = None
    resource_pattern: Optional[str] = None
    verdict: Optional[AuditVerdict] = None
    correlation_id: Optional[str] = None
    limit: int = 100
    offset: int = 0
    order_by: str = "timestamp"
    ascending: bool = False

    def matches(self, record: AuditRecord) -> bool:
        """
        Check if a record matches this query.

        Args:
            record: Audit record to check

        Returns:
            True if record matches all criteria
        """
        # Time filters
        if self.start_time and record.timestamp < self.start_time:
            return False
        if self.end_time and record.timestamp > self.end_time:
            return False

        # Event type filter
        if self.event_types and record.event_type not in self.event_types:
            return False

        # Severity filter
        if self.severity and record.severity not in self.severity:
            return False

        # Agent filter
        if self.agent_id and record.agent_id != self.agent_id:
            return False

        # Session filter
        if self.session_id and record.session_id != self.session_id:
            return False

        # Tool filter
        if self.tool_name and record.tool_name != self.tool_name:
            return False

        # Resource pattern filter
        if self.resource_pattern and record.resource:
            if self.resource_pattern.lower() not in record.resource.lower():
                return False

        # Verdict filter
        if self.verdict and record.verdict != self.verdict:
            return False

        # Correlation filter
        if self.correlation_id and record.correlation_id != self.correlation_id:
            return False

        return True


@dataclass
class AuditStats:
    """Statistics about audit logging."""

    total_records: int = 0
    records_by_type: Dict[str, int] = field(default_factory=dict)
    records_by_severity: Dict[str, int] = field(default_factory=dict)
    records_by_agent: Dict[str, int] = field(default_factory=dict)
    violations_count: int = 0
    denied_count: int = 0
    last_record_time: Optional[datetime] = None
    integrity_failures: int = 0


class AuditLogger:
    """
    Comprehensive audit logging for tool execution.

    Features:
    - Thread-safe logging
    - In-memory storage with optional disk persistence
    - Structured JSON format
    - Integrity verification
    - Query and search
    - Event correlation
    - Retention policies
    - Statistics tracking

    Usage:
        audit = AuditLogger(persist_path=Path("/var/log/ai_support/audit.jsonl"))

        # Log an event
        audit.log_tool_execution(
            tool_name="file_read",
            params={"path": "/workspace/test.txt"},
            result=tool_result,
        )

        # Query logs
        query = AuditQuery(tool_name="file_read", limit=100)
        results = audit.query(query)

        # Get statistics
        stats = audit.get_stats()
    """

    def __init__(
        self,
        persist_path: Optional[Path] = None,
        retention_days: int = 90,
        max_memory_records: int = 10000,
        enable_verification: bool = True,
    ):
        """
        Initialize audit logger.

        Args:
            persist_path: Path for persistent audit log (JSONL format)
            retention_days: Number of days to retain records
            max_memory_records: Maximum records to keep in memory
            enable_verification: Whether to verify record integrity
        """
        self.persist_path = persist_path
        self.retention_days = retention_days
        self.max_memory_records = max_memory_records
        self.enable_verification = enable_verification

        self._records: List[AuditRecord] = []
        self._records_by_session: Dict[str, List[str]] = defaultdict(list)
        self._records_by_correlation: Dict[str, List[str]] = defaultdict(list)
        self._lock = threading.RLock()

        # Statistics
        self._stats = AuditStats()

        # Load existing records if persist path exists
        if persist_path and persist_path.exists():
            self._load_from_disk()

    def log(
        self,
        event_type: AuditEventType,
        action: str,
        severity: AuditSeverity = AuditSeverity.INFO,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        resource: Optional[str] = None,
        result: Optional[str] = None,
        verdict: Optional[AuditVerdict] = None,
        details: Optional[Dict[str, Any]] = None,
        sandbox_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> AuditRecord:
        """
        Log an audit event.

        Args:
            event_type: Type of event
            action: Action performed
            severity: Event severity
            agent_id: ID of agent
            session_id: Session ID
            tool_name: Name of tool
            resource: Resource accessed
            result: Result of action
            verdict: Permission verdict
            details: Additional details
            sandbox_id: Sandbox execution ID
            correlation_id: Correlation ID for linking events
            parent_id: Parent event ID

        Returns:
            Created AuditRecord
        """
        record = AuditRecord(
            id=str(uuid4()),
            timestamp=datetime.now(),
            event_type=event_type,
            severity=severity,
            agent_id=agent_id,
            session_id=session_id,
            tool_name=tool_name,
            action=action,
            resource=resource,
            result=result,
            verdict=verdict,
            details=details or {},
            sandbox_id=sandbox_id,
            correlation_id=correlation_id,
            parent_id=parent_id,
        )

        self._add_record(record)
        return record

    def _add_record(self, record: AuditRecord) -> None:
        """Add record to storage with thread safety."""
        with self._lock:
            # Add to memory
            self._records.append(record)

            # Trim if over limit
            if len(self._records) > self.max_memory_records:
                self._records = self._records[-self.max_memory_records :]

            # Index by session
            if record.session_id:
                self._records_by_session[record.session_id].append(record.id)

            # Index by correlation
            if record.correlation_id:
                self._records_by_correlation[record.correlation_id].append(record.id)

            # Update statistics
            self._update_stats(record)

            # Persist to disk
            if self.persist_path:
                self._persist_record(record)

    def _update_stats(self, record: AuditRecord) -> None:
        """Update audit statistics."""
        self._stats.total_records += 1
        self._stats.last_record_time = record.timestamp

        # Count by type
        event_type_key = record.event_type.value
        self._stats.records_by_type[event_type_key] = (
            self._stats.records_by_type.get(event_type_key, 0) + 1
        )

        # Count by severity
        severity_key = record.severity.value
        self._stats.records_by_severity[severity_key] = (
            self._stats.records_by_severity.get(severity_key, 0) + 1
        )

        # Count by agent
        if record.agent_id:
            self._stats.records_by_agent[record.agent_id] = (
                self._stats.records_by_agent.get(record.agent_id, 0) + 1
            )

        # Count violations and denials
        if record.event_type in (
            AuditEventType.SANDBOX_VIOLATION,
            AuditEventType.PATH_VIOLATION,
            AuditEventType.RESOURCE_LIMIT_EXCEEDED,
        ):
            self._stats.violations_count += 1

        if record.event_type == AuditEventType.PERMISSION_DENIED:
            self._stats.denied_count += 1

    def _persist_record(self, record: AuditRecord) -> None:
        """Write record to persistent storage."""
        if not self.persist_path:
            return

        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.persist_path, "a") as f:
                f.write(json.dumps(record.to_dict()) + "\n")
        except Exception as e:
            logger.warning(f"Failed to persist audit record: {e}")

    def _load_from_disk(self) -> None:
        """Load records from persistent storage."""
        if not self.persist_path or not self.persist_path.exists():
            return

        try:
            with open(self.persist_path, "r") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        record = AuditRecord.from_dict(data)
                        self._records.append(record)
                        self._update_stats(record)

            logger.info(f"Loaded {len(self._records)} audit records from disk")
        except Exception as e:
            logger.warning(f"Failed to load audit records: {e}")

    def query(self, query: AuditQuery) -> List[AuditRecord]:
        """
        Query audit records.

        Args:
            query: Query parameters

        Returns:
            List of matching AuditRecords
        """
        with self._lock:
            # Filter records
            results = [r for r in self._records if query.matches(r)]

            # Sort
            reverse = not query.ascending
            results.sort(key=lambda r: getattr(r, query.order_by), reverse=reverse)

            # Paginate
            return results[query.offset : query.offset + query.limit]

    def get_by_session(self, session_id: str) -> List[AuditRecord]:
        """
        Get all records for a session.

        Args:
            session_id: Session ID

        Returns:
            List of records in session order
        """
        with self._lock:
            record_ids = self._records_by_session.get(session_id, [])
            record_map = {r.id: r for r in self._records}

            # Return in order
            return [record_map[rid] for rid in record_ids if rid in record_map]

    def get_by_correlation(self, correlation_id: str) -> List[AuditRecord]:
        """
        Get all records linked by correlation ID.

        Args:
            correlation_id: Correlation ID

        Returns:
            List of related records
        """
        with self._lock:
            record_ids = self._records_by_correlation.get(correlation_id, [])
            record_map = {r.id: r for r in self._records}

            return [record_map[rid] for rid in record_ids if rid in record_map]

    def get_violations(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditRecord]:
        """
        Get all sandbox violations.

        Args:
            start_time: Filter start time
            end_time: Filter end time
            limit: Maximum results

        Returns:
            List of violation records
        """
        query = AuditQuery(
            start_time=start_time,
            end_time=end_time,
            event_types=[
                AuditEventType.SANDBOX_VIOLATION,
                AuditEventType.SANDBOX_VIOLATION_BLOCKED,
                AuditEventType.PATH_VIOLATION,
                AuditEventType.RESOURCE_LIMIT_EXCEEDED,
                AuditEventType.PERMISSION_DENIED,
            ],
            severity=[AuditSeverity.WARNING, AuditSeverity.ERROR, AuditSeverity.CRITICAL],
            limit=limit,
        )
        return self.query(query)

    def verify_integrity(self) -> Dict[str, Any]:
        """
        Verify integrity of all audit records.

        Returns:
            Dictionary with verification results
        """
        results = {
            "total_records": len(self._records),
            "verified": 0,
            "failed": 0,
            "failed_ids": [],
        }

        with self._lock:
            for record in self._records:
                if record.verify_integrity():
                    results["verified"] += 1
                else:
                    results["failed"] += 1
                    results["failed_ids"].append(record.id)
                    self._stats.integrity_failures += 1

        return results

    def get_stats(self) -> AuditStats:
        """
        Get audit statistics.

        Returns:
            AuditStats object
        """
        with self._lock:
            return AuditStats(
                total_records=self._stats.total_records,
                records_by_type=self._stats.records_by_type.copy(),
                records_by_severity=self._stats.records_by_severity.copy(),
                records_by_agent=self._stats.records_by_agent.copy(),
                violations_count=self._stats.violations_count,
                denied_count=self._stats.denied_count,
                last_record_time=self._stats.last_record_time,
                integrity_failures=self._stats.integrity_failures,
            )

    def cleanup_old_records(self) -> int:
        """
        Remove records older than retention period.

        Returns:
            Number of records removed
        """
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        removed = 0

        with self._lock:
            # Filter out old records
            original_count = len(self._records)
            self._records = [r for r in self._records if r.timestamp >= cutoff]

            # Clean up session index
            for session_id in list(self._records_by_session.keys()):
                self._records_by_session[session_id] = [
                    rid
                    for rid in self._records_by_session[session_id]
                    if rid in {r.id for r in self._records}
                ]
                if not self._records_by_session[session_id]:
                    del self._records_by_session[session_id]

            # Clean up correlation index
            for corr_id in list(self._records_by_correlation.keys()):
                self._records_by_correlation[corr_id] = [
                    rid
                    for rid in self._records_by_correlation[corr_id]
                    if rid in {r.id for r in self._records}
                ]
                if not self._records_by_correlation[corr_id]:
                    del self._records_by_correlation[corr_id]

            removed = original_count - len(self._records)

        if removed > 0:
            logger.info(f"Cleaned up {removed} old audit records")

        return removed

    def clear(self) -> None:
        """Clear all audit records."""
        with self._lock:
            self._records.clear()
            self._records_by_session.clear()
            self._records_by_correlation.clear()
            self._stats = AuditStats()

    def log_tool_execution(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Any,
        result: Any,
        sandbox_result: Optional[Any] = None,
        correlation_id: Optional[str] = None,
    ) -> AuditRecord:
        """
        Convenience method to log a tool execution.

        Args:
            tool_name: Name of executed tool
            params: Tool parameters
            context: Execution context
            result: Execution result
            sandbox_result: Sandbox result if sandboxed
            correlation_id: Correlation ID for linking

        Returns:
            Created AuditRecord
        """
        agent_id = getattr(context, "agent_id", None) or getattr(context, "user_id", None)
        session_id = getattr(context, "session_id", None)

        # Sanitize params for logging (remove sensitive data)
        safe_params = self._sanitize_params(params)

        if result and getattr(result, "success", True):
            event_type = AuditEventType.TOOL_EXECUTION_COMPLETE
            severity = AuditSeverity.INFO
            result_str = "success"
        elif result and hasattr(result, "error"):
            event_type = AuditEventType.TOOL_EXECUTION_ERROR
            severity = AuditSeverity.ERROR
            result_str = getattr(result, "error", "unknown error")
        else:
            event_type = AuditEventType.TOOL_EXECUTION_COMPLETE
            severity = AuditSeverity.INFO
            result_str = "success" if result else "no output"

        details = {
            "params": safe_params,
            "execution_time_ms": getattr(result, "execution_time_ms", 0),
        }

        if sandbox_result:
            details["sandbox_info"] = {
                "violations": getattr(sandbox_result, "sandbox_violations", []),
                "resources_used": getattr(sandbox_result, "resources_used", {}),
            }

        return self.log(
            event_type=event_type,
            action=f"execute:{tool_name}",
            severity=severity,
            agent_id=agent_id,
            session_id=session_id,
            tool_name=tool_name,
            result=result_str,
            verdict=AuditVerdict.ALLOWED,
            details=details,
            sandbox_id=getattr(sandbox_result, "sandbox_id", None),
            correlation_id=correlation_id,
        )

    def log_sandbox_violation(
        self,
        violation_type: str,
        details: str,
        tool_name: Optional[str] = None,
        resource: Optional[str] = None,
        context: Optional[Any] = None,
    ) -> AuditRecord:
        """
        Log a sandbox violation.

        Args:
            violation_type: Type of violation
            details: Violation details
            tool_name: Tool involved
            resource: Resource involved
            context: Execution context

        Returns:
            Created AuditRecord
        """
        agent_id = getattr(context, "agent_id", None) if context else None
        session_id = getattr(context, "session_id", None) if context else None

        return self.log(
            event_type=AuditEventType.SANDBOX_VIOLATION,
            action=f"violation:{violation_type}",
            severity=AuditSeverity.WARNING,
            agent_id=agent_id,
            session_id=session_id,
            tool_name=tool_name,
            resource=resource,
            result="blocked",
            verdict=AuditVerdict.BLOCKED,
            details={"violation_details": details},
        )

    def log_permission_check(
        self,
        tool_name: str,
        permission: str,
        allowed: bool,
        reason: Optional[str] = None,
        context: Optional[Any] = None,
    ) -> AuditRecord:
        """
        Log a permission check.

        Args:
            tool_name: Tool name
            permission: Permission checked
            allowed: Whether permission was granted
            reason: Reason for decision
            context: Execution context

        Returns:
            Created AuditRecord
        """
        agent_id = getattr(context, "agent_id", None) if context else None
        session_id = getattr(context, "session_id", None) if context else None

        return self.log(
            event_type=AuditEventType.PERMISSION_CHECK,
            action=f"permission:{permission}",
            severity=AuditSeverity.INFO,
            agent_id=agent_id,
            session_id=session_id,
            tool_name=tool_name,
            verdict=AuditVerdict.ALLOWED if allowed else AuditVerdict.DENIED,
            result="granted" if allowed else "denied",
            details={"reason": reason} if reason else {},
        )

    def _sanitize_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove sensitive data from parameters for logging.

        Args:
            params: Original parameters

        Returns:
            Sanitized parameters
        """
        sensitive_keys = {
            "password",
            "secret",
            "token",
            "api_key",
            "private_key",
            "credential",
        }

        sanitized = {}
        for key, value in params.items():
            if key.lower() in sensitive_keys:
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_params(value)
            else:
                sanitized[key] = value

        return sanitized

    def export_jsonl(self, output_path: Path) -> int:
        """
        Export all records to JSONL file.

        Args:
            output_path: Output file path

        Returns:
            Number of records exported
        """
        count = 0
        with open(output_path, "w") as f:
            with self._lock:
                for record in self._records:
                    f.write(json.dumps(record.to_dict()) + "\n")
                    count += 1

        logger.info(f"Exported {count} audit records to {output_path}")
        return count

    def import_jsonl(self, input_path: Path) -> int:
        """
        Import records from JSONL file.

        Args:
            input_path: Input file path

        Returns:
            Number of records imported
        """
        count = 0
        with open(input_path, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        record = AuditRecord.from_dict(data)
                        self._add_record(record)
                        count += 1
                    except Exception as e:
                        logger.warning(f"Failed to import audit record: {e}")

        logger.info(f"Imported {count} audit records from {input_path}")
        return count


# Default audit logger instance
_default_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """
    Get the default audit logger instance.

    Returns:
        AuditLogger instance
    """
    global _default_logger

    if _default_logger is None:
        _default_logger = AuditLogger()

    return _default_logger


def reset_audit_logger() -> None:
    """Reset the default audit logger."""
    global _default_logger
    _default_logger = None
