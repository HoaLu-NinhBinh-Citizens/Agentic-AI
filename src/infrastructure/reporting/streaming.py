"""Streaming progressive output for long-running reviews.

Instead of blocking until all analysis completes, this module provides
real-time progressive output as findings are discovered.

Features:
- Async generator for streaming findings
- Progress indicators with file counts
- Partial summary updates
- Compatible with both CLI and WebSocket outputs
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Optional

from src.infrastructure.reporting.markdown_report import Finding, Severity


@dataclass
class StreamEvent:
    """A single event in the streaming output."""

    event_type: str  # "start", "progress", "finding", "summary", "complete", "error"
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class StreamProgress:
    """Progress tracking for streaming analysis."""

    total_files: int = 0
    files_analyzed: int = 0
    findings_count: int = 0
    current_file: str = ""
    start_time: float = field(default_factory=time.time)

    @property
    def elapsed(self) -> float:
        """Elapsed time in seconds."""
        return time.time() - self.start_time

    @property
    def percent_complete(self) -> float:
        """Completion percentage."""
        if self.total_files == 0:
            return 0.0
        return (self.files_analyzed / self.total_files) * 100

    @property
    def files_per_second(self) -> float:
        """Processing speed."""
        elapsed = self.elapsed
        if elapsed == 0:
            return 0.0
        return self.files_analyzed / elapsed


class StreamingReporter:
    """Reports analysis results progressively as they arrive.

    Usage:
        reporter = StreamingReporter()
        reporter.on_event(my_handler)

        async for event in reporter.stream_analysis(files, engine):
            # Events arrive in real-time
            handle(event)
    """

    def __init__(self, use_colors: bool = True):
        self._use_colors = use_colors
        self._handlers: list[Callable[[StreamEvent], None]] = []
        self._progress = StreamProgress()

    def on_event(self, handler: Callable[[StreamEvent], None]) -> None:
        """Register an event handler.

        Args:
            handler: Callback for stream events
        """
        self._handlers.append(handler)

    def _emit(self, event: StreamEvent) -> None:
        """Emit an event to all handlers."""
        for handler in self._handlers:
            try:
                handler(event)
            except Exception:
                pass

    async def stream_findings(
        self,
        findings_generator: AsyncIterator[tuple[str, list[Finding]]],
        total_files: int = 0,
    ) -> AsyncIterator[StreamEvent]:
        """Stream findings as they are discovered.

        Args:
            findings_generator: Async generator yielding (file_path, findings)
            total_files: Total number of files being analyzed

        Yields:
            StreamEvent for each significant event
        """
        self._progress = StreamProgress(total_files=total_files)

        # Start event
        start_event = StreamEvent(
            event_type="start",
            data={"total_files": total_files},
        )
        self._emit(start_event)
        yield start_event

        async for file_path, file_findings in findings_generator:
            self._progress.files_analyzed += 1
            self._progress.current_file = file_path
            self._progress.findings_count += len(file_findings)

            # Progress event
            progress_event = StreamEvent(
                event_type="progress",
                data={
                    "file": file_path,
                    "files_analyzed": self._progress.files_analyzed,
                    "total_files": self._progress.total_files,
                    "percent": round(self._progress.percent_complete, 1),
                    "findings_so_far": self._progress.findings_count,
                    "elapsed": round(self._progress.elapsed, 2),
                },
            )
            self._emit(progress_event)
            yield progress_event

            # Individual finding events
            for finding in file_findings:
                finding_event = StreamEvent(
                    event_type="finding",
                    data={
                        "rule_id": finding.rule_id,
                        "severity": finding.severity.value,
                        "file": finding.file_path,
                        "line": finding.line,
                        "message": finding.message,
                        "title": finding.title,
                    },
                )
                self._emit(finding_event)
                yield finding_event

        # Complete event
        complete_event = StreamEvent(
            event_type="complete",
            data={
                "total_files": self._progress.files_analyzed,
                "total_findings": self._progress.findings_count,
                "duration": round(self._progress.elapsed, 2),
                "speed": round(self._progress.files_per_second, 1),
            },
        )
        self._emit(complete_event)
        yield complete_event

    @property
    def progress(self) -> StreamProgress:
        """Current progress."""
        return self._progress


class CLIStreamRenderer:
    """Renders streaming events to terminal with progress bar."""

    _SEVERITY_ICONS = {
        "critical": "\033[91m[CRIT]\033[0m",
        "high": "\033[93m[HIGH]\033[0m",
        "medium": "\033[33m[MED ]\033[0m",
        "low": "\033[94m[LOW ]\033[0m",
        "info": "\033[90m[INFO]\033[0m",
    }

    def __init__(self, use_colors: bool = True):
        self._use_colors = use_colors

    def render_event(self, event: StreamEvent) -> None:
        """Render a single stream event to terminal.

        Args:
            event: StreamEvent to render
        """
        if event.event_type == "start":
            total = event.data.get("total_files", 0)
            self._write(f"\n🔍 Starting analysis of {total} files...\n")

        elif event.event_type == "progress":
            pct = event.data.get("percent", 0)
            current = event.data.get("files_analyzed", 0)
            total = event.data.get("total_files", 0)
            findings = event.data.get("findings_so_far", 0)
            bar = self._progress_bar(pct)
            self._write_inline(
                f"\r  {bar} {current}/{total} files | {findings} findings"
            )

        elif event.event_type == "finding":
            severity = event.data.get("severity", "info")
            icon = self._SEVERITY_ICONS.get(severity, "[???]")
            if not self._use_colors:
                icon = f"[{severity.upper()[:4]}]"
            file_path = event.data.get("file", "?")
            line = event.data.get("line", 0)
            msg = event.data.get("message", "")[:60]
            self._write(f"\n  {icon} {file_path}:{line} {msg}")

        elif event.event_type == "complete":
            duration = event.data.get("duration", 0)
            total_findings = event.data.get("total_findings", 0)
            speed = event.data.get("speed", 0)
            self._write(
                f"\n\n✓ Complete: {total_findings} findings "
                f"in {duration:.1f}s ({speed:.0f} files/s)\n"
            )

        elif event.event_type == "error":
            msg = event.data.get("message", "Unknown error")
            self._write(f"\n  ✗ Error: {msg}")

    def _progress_bar(self, percent: float, width: int = 20) -> str:
        """Render a progress bar."""
        filled = int(width * percent / 100)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}] {percent:.0f}%"

    def _write(self, text: str) -> None:
        """Write to stdout with newline."""
        sys.stdout.write(text + "\n")
        sys.stdout.flush()

    def _write_inline(self, text: str) -> None:
        """Write to stdout without newline (for progress updates)."""
        sys.stdout.write(text)
        sys.stdout.flush()
