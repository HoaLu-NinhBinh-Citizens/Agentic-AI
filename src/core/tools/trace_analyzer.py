"""Trace Analyzer - Distinguishes signal from noise in logs.

PROBLEM:
AI bị confuse bởi misleading logs như:
- Error message trỏ sai chỗ
- Stack trace không liên quan
- Warning không phải root cause
- Symptom nhìn như cause

SOLUTION:
┌─────────────────────────────────────────────────────────────────┐
│                      TraceAnalyzer                                 │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Log Parser                                               │  │
│  │  - Parse structured logs (timestamp, level, source)      │  │
│  │  - Extract error/warning patterns                         │  │
│  │  - Group related entries                                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Signal Detector                                          │  │
│  │  - Correlation analysis                                    │  │
│  │  - Temporal proximity (error sau khi action X)           │  │
│  │  - Call stack correlation                                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Red Herring Detector                                     │  │
│  │  - Temporal distance (> 1s thường không liên quan)      │  │
│  │  - Source isolation (error in unrelated module)           │  │
│  │  - Pattern matching (known misleading patterns)          │  │
│  └───────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Root Cause Estimator                                     │  │
│  │  - Trace backwards from symptom                            │  │
│  │  - Find first deviation from normal                        │  │
│  │  - Rank candidates by evidence                              │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘

KEY FEATURES:
1. Temporal correlation - events close in time are related
2. Call stack analysis - trace actual execution path
3. Pattern library - known misleading patterns
4. Evidence scoring - rank causes by evidence strength
5. Confidence estimation - how sure is the analysis
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class LogLevel(Enum):
    """Log severity levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EventType(Enum):
    """Types of events in trace."""
    FUNCTION_CALL = "function_call"
    FUNCTION_RETURN = "function_return"
    ERROR = "error"
    WARNING = "warning"
    STATE_CHANGE = "state_change"
    INTERRUPT = "interrupt"
    EXCEPTION = "exception"
    MEMORY_ACCESS = "memory_access"
    TIMEOUT = "timeout"


@dataclass
class LogEntry:
    """Single log entry."""
    timestamp: float
    level: LogLevel
    source: str
    message: str
    raw: str
    line_number: Optional[int] = None
    thread_id: Optional[str] = None
    call_stack: Optional[list[str]] = None


@dataclass
class TraceEvent:
    """Event in execution trace."""
    event_id: str
    event_type: EventType
    timestamp: float
    source: str
    description: str
    duration_us: Optional[float] = None
    parent_id: Optional[str] = None
    children_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RootCauseCandidate:
    """Candidate for root cause."""
    event: TraceEvent
    score: float  # 0-1, higher = more likely root cause
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    distance_from_symptom: float = 0.0  # seconds


@dataclass
class TraceAnalysisResult:
    """Result of trace analysis."""
    root_cause: Optional[RootCauseCandidate]
    candidates: list[RootCauseCandidate]
    red_herring_events: list[TraceEvent]
    timeline: list[TraceEvent]
    summary: str
    confidence: float = 0.0


# Known misleading patterns
RED_HERRING_PATTERNS = [
    {
        "pattern": r"error.*timeout.*uart",
        "actual_cause": "clock not enabled",
        "reason": "UART timeout often secondary to clock issue",
    },
    {
        "pattern": r"error.*null.*pointer.*sensor",
        "actual_cause": "peripheral not initialized",
        "reason": "Null pointer in sensor code usually from uninitialized handle",
    },
    {
        "pattern": r"warning.*dma.*not.*ready",
        "actual_cause": "DMA not clocked",
        "reason": "DMA not ready is symptom, clock is cause",
    },
    {
        "pattern": r"error.*spi.*busy",
        "actual_cause": "previous transaction not completed",
        "reason": "SPI busy flag set by incomplete previous operation",
    },
    {
        "pattern": r"error.*i2c.*nak",
        "actual_cause": "device not responding or wrong address",
        "reason": "NAK can be slave not powered or wrong address",
    },
    {
        "pattern": r"guru.*meditation.*pc.*0x080",
        "actual_cause": "stack overflow or null pointer",
        "reason": "PC in flash region during fault usually overflow",
    },
]


class TraceAnalyzer:
    """
    Analyzes execution traces to find root causes.

    Distinguishes:
    - Signal (actual root cause) vs Noise (symptoms)
    - Related events vs Isolated events
    - Primary errors vs Secondary errors
    """

    def __init__(self, time_window_seconds: float = 5.0) -> None:
        self._time_window = time_window_seconds
        self._red_herring_patterns = RED_HERRING_PATTERNS
        self._events: list[TraceEvent] = []
        self._log_entries: list[LogEntry] = []

    def parse_log_line(self, line: str) -> Optional[LogEntry]:
        """Parse a single log line."""
        # Common log format: [TIMESTAMP] [LEVEL] [SOURCE] message
        patterns = [
            r'\[(\d+\.\d+)\]\s*\[(\w+)\]\s*\[([^\]]+)\]\s*(.+)',
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\w+)\s+(.+)',
            r'<(\w+)>\s*(.+)',
        ]

        for pattern in patterns:
            match = re.match(pattern, line)
            if match:
                groups = match.groups()
                if len(groups) >= 4:
                    try:
                        timestamp = float(groups[0])
                    except (ValueError, TypeError):
                        timestamp = datetime.now().timestamp()

                    try:
                        level = LogLevel(groups[1].lower())
                    except ValueError:
                        level = LogLevel.INFO

                    return LogEntry(
                        timestamp=timestamp,
                        level=level,
                        source=groups[2],
                        message=groups[3],
                        raw=line,
                    )

        # Fallback: treat as info
        return LogEntry(
            timestamp=datetime.now().timestamp(),
            level=LogLevel.INFO,
            source="unknown",
            message=line,
            raw=line,
        )

    def parse_log_entries(self, log_text: str) -> list[LogEntry]:
        """Parse multiple log lines."""
        entries = []
        for line in log_text.strip().split('\n'):
            line = line.strip()
            if line:
                entry = self.parse_log_line(line)
                if entry:
                    entries.append(entry)
                    self._log_entries.append(entry)
        return entries

    def add_trace_event(self, event: TraceEvent) -> None:
        """Add event to trace."""
        self._events.append(event)

    def analyze(
        self,
        symptom_event: Optional[TraceEvent] = None,
        symptom_time: Optional[float] = None,
    ) -> TraceAnalysisResult:
        """
        Analyze trace to find root cause.

        Args:
            symptom_event: The event that represents the symptom/failure
            symptom_time: Time of the symptom (if event not available)

        Returns:
            TraceAnalysisResult with root cause and analysis
        """
        if not self._events and not self._log_entries:
            return TraceAnalysisResult(
                root_cause=None,
                candidates=[],
                red_herring_events=[],
                timeline=[],
                summary="No trace data available",
                confidence=0.0,
            )

        # Find symptom time
        if symptom_time is None and symptom_event:
            symptom_time = symptom_event.timestamp
        elif symptom_time is None and self._log_entries:
            # Find last error as symptom
            errors = [e for e in self._log_entries if e.level in (LogLevel.ERROR, LogLevel.CRITICAL)]
            if errors:
                symptom_time = errors[-1].timestamp

        # Analyze log entries
        if self._log_entries:
            return self._analyze_logs(symptom_time)

        # Analyze trace events
        return self._analyze_events(symptom_event, symptom_time)

    def _analyze_logs(self, symptom_time: Optional[float]) -> TraceAnalysisResult:
        """Analyze log entries."""
        candidates: list[RootCauseCandidate] = []
        red_herrings: list[TraceEvent] = []

        # Find all errors and warnings
        errors = [e for e in self._log_entries if e.level == LogLevel.ERROR]

        for error in errors:
            score = 0.0
            evidence = []

            # Check temporal proximity to symptom
            if symptom_time:
                distance = abs(error.timestamp - symptom_time)
                if distance < 1.0:  # Within 1 second
                    score += 0.4 * (1.0 - distance)
                    evidence.append(f"Within {distance:.2f}s of symptom")
                elif distance < self._time_window:
                    score += 0.2
                    evidence.append(f"Within time window ({distance:.2f}s)")
                else:
                    evidence.append(f"Too far from symptom ({distance:.2f}s)")
                    red_herrings.append(TraceEvent(
                        event_id=f"rh_{len(red_herrings)}",
                        event_type=EventType.ERROR,
                        timestamp=error.timestamp,
                        source=error.source,
                        description=error.message,
                        distance_from_symptom=distance,
                    ))

            # Check for red herring patterns
            is_red_herring = False
            for pattern in self._red_herring_patterns:
                if re.search(pattern["pattern"], error.message, re.IGNORECASE):
                    is_red_herring = True
                    evidence.append(f"Known red herring: {pattern['reason']}")
                    score *= 0.5  # Reduce score
                    break

            # Check for correlation with other events
            correlated = self._find_correlated_events(error)
            if correlated:
                score += 0.3
                evidence.append(f"Correlated with {len(correlated)} events")

            candidate = RootCauseCandidate(
                event=TraceEvent(
                    event_id=f"cand_{len(candidates)}",
                    event_type=EventType.ERROR,
                    timestamp=error.timestamp,
                    source=error.source,
                    description=error.message,
                ),
                score=min(score, 1.0),
                evidence=evidence,
                confidence=score,
            )
            candidates.append(candidate)

        # Sort by score
        candidates.sort(key=lambda x: -x.score)

        # Mark red herrings
        red_herring_events = []
        for rh in red_herrings:
            rh.metadata["is_red_herring"] = True
            rh.metadata["reason"] = "Too far from symptom or known misleading pattern"
            red_herring_events.append(rh)

        # Get root cause
        root_cause = candidates[0] if candidates else None

        summary = self._generate_summary(candidates, root_cause)

        return TraceAnalysisResult(
            root_cause=root_cause,
            candidates=candidates,
            red_herring_events=red_herring_events,
            timeline=self._events.copy(),
            summary=summary,
            confidence=root_cause.confidence if root_cause else 0.0,
        )

    def _analyze_events(
        self,
        symptom_event: Optional[TraceEvent],
        symptom_time: Optional[float],
    ) -> TraceAnalysisResult:
        """Analyze trace events."""
        candidates: list[RootCauseCandidate] = []

        # If we have a symptom event, find events leading to it
        if symptom_event and symptom_time:
            for event in self._events:
                if event.timestamp < symptom_time:
                    distance = symptom_time - event.timestamp
                    score = self._calculate_event_score(event, distance, symptom_event)

                    if score > 0.3:  # Only significant events
                        candidate = RootCauseCandidate(
                            event=event,
                            score=score,
                            evidence=[f"{distance:.2f}s before symptom"],
                            distance_from_symptom=distance,
                        )
                        candidates.append(candidate)

        candidates.sort(key=lambda x: -x.score)

        return TraceAnalysisResult(
            root_cause=candidates[0] if candidates else None,
            candidates=candidates,
            red_herring_events=[],
            timeline=self._events.copy(),
            summary=self._generate_summary(candidates, candidates[0] if candidates else None),
            confidence=candidates[0].confidence if candidates else 0.0,
        )

    def _find_correlated_events(self, error: LogEntry) -> list[LogEntry]:
        """Find events correlated with error (same source, close in time)."""
        correlated = []

        for other in self._log_entries:
            if other is error:
                continue

            # Same source?
            same_source = other.source == error.source

            # Close in time?
            time_diff = abs(other.timestamp - error.timestamp)
            close_in_time = time_diff < 0.5  # Within 500ms

            if same_source and close_in_time:
                correlated.append(other)

        return correlated

    def _calculate_event_score(
        self,
        event: TraceEvent,
        distance: float,
        symptom: TraceEvent,
    ) -> float:
        """Calculate likelihood that event is root cause."""
        score = 0.0

        # Closer events more likely
        if distance < 1.0:
            score += 0.5 * (1.0 - distance)
        elif distance < 5.0:
            score += 0.2

        # Error events more likely
        if event.event_type in (EventType.ERROR, EventType.EXCEPTION):
            score += 0.3

        # Function call that precedes symptom
        if event.event_type == EventType.FUNCTION_CALL:
            score += 0.2

        # Duration anomalies (very long calls)
        if event.duration_us and event.duration_us > 100000:  # > 100ms
            score += 0.2

        return min(score, 1.0)

    def _generate_summary(
        self,
        candidates: list[RootCauseCandidate],
        root_cause: Optional[RootCauseCandidate],
    ) -> str:
        """Generate analysis summary."""
        if not candidates:
            return "No root cause identified"

        if root_cause:
            summary = f"Most likely root cause: {root_cause.event.description[:100]}"

            if root_cause.evidence:
                summary += "\nEvidence: " + "; ".join(root_cause.evidence[:3])

            summary += f"\nConfidence: {root_cause.confidence:.0%}"

            if len(candidates) > 1:
                summary += f"\n\nAlternative causes ({len(candidates)-1}):"
                for c in candidates[1:4]:
                    summary += f"\n- {c.event.description[:60]} (score: {c.score:.0%})"
        else:
            summary = "No clear root cause identified"

        return summary

    def is_red_herring(self, message: str) -> tuple[bool, Optional[str]]:
        """
        Check if message matches known red herring pattern.

        Returns:
            (is_red_herring, explanation)
        """
        for pattern in self._red_herring_patterns:
            if re.search(pattern["pattern"], message, re.IGNORECASE):
                return True, pattern["reason"]

        return False, None

    def explain_misleading_logs(self, log_text: str) -> dict[str, Any]:
        """Explain which logs are misleading and why."""
        entries = self.parse_log_entries(log_text)

        analysis = {
            "total_entries": len(entries),
            "errors": len([e for e in entries if e.level == LogLevel.ERROR]),
            "warnings": len([e for e in entries if e.level == LogLevel.WARNING]),
            "red_herrings": [],
            "likely_cause": None,
        }

        for entry in entries:
            is_rh, reason = self.is_red_herring(entry.message)
            if is_rh:
                analysis["red_herrings"].append({
                    "message": entry.message[:100],
                    "actual_cause": reason,
                })

        # Find most likely cause (error closest to symptom that isn't red herring)
        errors = [e for e in entries if e.level == LogLevel.ERROR]
        for error in errors:
            is_rh, _ = self.is_red_herring(error.message)
            if not is_rh:
                analysis["likely_cause"] = error.message[:100]
                break

        return analysis


class MisleadingLogDetector:
    """Detects and explains misleading log patterns."""

    # Patterns that often point to wrong cause
    MISLEADING_PATTERNS = {
        "UART timeout": {
            "red_herring": "UART hardware issue",
            "actual_causes": ["Clock not enabled", "GPIO misconfigured", "TX/RX swapped"],
            "investigation": "Check RCC clock enable and GPIO alternate function",
        },
        "SPI busy": {
            "red_herring": "SPI peripheral stuck",
            "actual_causes": ["Previous transaction not completed", "DMA not finished", "BSY bit latched"],
            "investigation": "Check DMA transfer complete flag and OVR error",
        },
        "I2C NAK": {
            "red_herring": "I2C slave not responding",
            "actual_causes": ["Wrong slave address", "Slave not powered", "Pull-ups missing"],
            "investigation": "Verify address with I2C scanner, check power and pull-ups",
        },
        "DMA not ready": {
            "red_herring": "DMA configuration wrong",
            "actual_causes": ["DMA clock not enabled", "Channel already in use", "Stream disabled"],
            "investigation": "Check RCC DMA clock enable and DMA stream status",
        },
        "Null pointer": {
            "red_herring": "Logic error - null dereference",
            "actual_causes": ["Handle not initialized", "Failed initialization", "Memory corruption"],
            "investigation": "Check init sequence and handle validity before use",
        },
    }

    @classmethod
    def detect(cls, error_message: str) -> Optional[dict[str, Any]]:
        """Detect if error message is misleading."""
        for pattern, info in cls.MISLEADING_PATTERNS.items():
            if pattern.lower() in error_message.lower():
                return {
                    "is_misleading": True,
                    "apparent_cause": info["red_herring"],
                    "actual_causes": info["actual_causes"],
                    "investigation_hint": info["investigation"],
                }
        return None

    @classmethod
    def get_investigation_guide(cls, error_type: str) -> str:
        """Get investigation guide for error type."""
        info = cls.MISLEADING_PATTERNS.get(error_type)
        if info:
            return f"""
Investigation Guide for '{error_type}':
------------------------------------------
Apparent Cause: {info['red_herring']}

Actual Causes to Check:
""" + "\n".join(f"  - {c}" for c in info["actual_causes"]) + f"""

What to Investigate:
{info['investigation']}
"""
        return f"No specific guide for '{error_type}'"
