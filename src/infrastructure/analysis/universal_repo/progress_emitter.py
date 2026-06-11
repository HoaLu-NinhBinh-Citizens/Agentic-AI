"""Pipeline Progress Emitter — structured progress events for each pipeline phase.

Provides a high-level emitter that wraps a StreamSink and offers
convenience methods for each pipeline phase (detection, analysis, build,
fix, complete). Extends the core StreamEvent model from
src/core/streaming/stream.py to integrate with the existing WebSocket
streaming infrastructure.

Requirements: 10.1, 10.2, 10.3, 10.4
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from src.core.streaming.stream import StreamEvent, StreamEventType
from .models import PipelineProgressEvent

if TYPE_CHECKING:
    from . import StreamSink


def _to_stream_event(event: PipelineProgressEvent) -> StreamEvent:
    """Bridge a PipelineProgressEvent to the core StreamEvent model.

    Converts pipeline-specific progress events into StreamEvent objects
    compatible with the existing WebSocket/SSE streaming infrastructure.
    Uses METADATA type for progress events and STEP_END for completions.
    """
    event_type = (
        StreamEventType.STEP_END
        if event.phase == "complete"
        else StreamEventType.METADATA
    )
    return StreamEvent(
        type=event_type,
        content=event.message,
        data={
            "pipeline_phase": event.phase,
            "progress_percent": event.progress_percent,
            **event.data,
        },
        timestamp=event.timestamp,
    )


class PipelineProgressEmitter:
    """Emits structured progress events for each pipeline phase.

    Wraps a StreamSink protocol implementation and provides typed methods
    for each pipeline phase. Extends the core StreamEvent model by bridging
    PipelineProgressEvent objects to StreamEvent for compatibility with the
    existing WebSocket/SSE streaming infrastructure.

    If no sink is configured, all emissions are silently discarded
    (null-object pattern).

    Requirements: 10.1, 10.2, 10.3, 10.4
    """

    def __init__(self, sink: StreamSink | None = None) -> None:
        self._sink = sink
        self._phase_start_times: dict[str, float] = {}

    @property
    def has_sink(self) -> bool:
        """Return True if a sink is configured."""
        return self._sink is not None

    @staticmethod
    def to_stream_event(event: PipelineProgressEvent) -> StreamEvent:
        """Convert a PipelineProgressEvent to a core StreamEvent.

        Enables integration with existing WebSocket/SSE infrastructure.
        """
        return _to_stream_event(event)

    # ─── Detection Phase (Requirement: 10.1) ──────────────────────────────────

    async def emit_detection_progress(
        self,
        files_scanned: int,
        total_files: int,
        phase: str,
    ) -> None:
        """Emit progress during project detection file scanning.

        Args:
            files_scanned: Number of files scanned so far.
            total_files: Estimated total number of files to scan.
            phase: Current detection sub-phase (e.g., "language", "framework", "build_tool").
        """
        if self._sink is None:
            return

        progress_pct = (
            (files_scanned / total_files) * 100.0 if total_files > 0 else 0.0
        )
        event = PipelineProgressEvent(
            phase="detection",
            progress_percent=min(progress_pct, 100.0),
            message=f"Scanning files: {files_scanned}/{total_files} ({phase})",
            data={
                "files_scanned": files_scanned,
                "total_files": total_files,
                "sub_phase": phase,
            },
        )
        await self._sink.emit(event)

    # ─── Analysis Phase (Requirement: 10.2) ───────────────────────────────────

    async def emit_analysis_progress(
        self,
        files_analyzed: int,
        findings_count: int,
        current_file: str,
    ) -> None:
        """Emit progress during rule engine analysis.

        Args:
            files_analyzed: Number of files analyzed so far.
            findings_count: Total findings discovered so far.
            current_file: Path of the file currently being analyzed.
        """
        if self._sink is None:
            return

        event = PipelineProgressEvent(
            phase="analysis",
            progress_percent=0.0,  # Caller should compute if total is known
            message=f"Analyzing: {current_file} ({findings_count} findings so far)",
            data={
                "files_analyzed": files_analyzed,
                "findings_count": findings_count,
                "current_file": current_file,
            },
        )
        await self._sink.emit(event)

    # ─── Build Phase (Requirement: 10.3) ──────────────────────────────────────

    async def emit_build_progress(
        self,
        output_line: str,
        phase: str,
    ) -> None:
        """Emit a build output line in real-time.

        Args:
            output_line: A single line of build output to stream.
            phase: Build sub-phase (e.g., "compiling", "linking", "complete").
        """
        if self._sink is None:
            return

        event = PipelineProgressEvent(
            phase="build",
            progress_percent=0.0,
            message=output_line,
            data={
                "output_line": output_line,
                "sub_phase": phase,
            },
        )
        await self._sink.emit(event)

    # ─── Phase Completion (Requirement: 10.4) ─────────────────────────────────

    async def emit_phase_complete(
        self,
        phase: str,
        summary: dict[str, Any],
        duration_ms: float,
    ) -> None:
        """Emit a completion event with phase summary and duration.

        Args:
            phase: The pipeline phase that completed (detection, analysis, build, fix).
            summary: Dictionary with phase-specific summary data.
            duration_ms: Time taken for the phase in milliseconds.
        """
        if self._sink is None:
            return

        event = PipelineProgressEvent(
            phase="complete",
            progress_percent=100.0,
            message=f"Phase '{phase}' complete in {duration_ms:.0f}ms",
            data={
                "completed_phase": phase,
                "summary": summary,
                "duration_ms": duration_ms,
            },
        )
        await self._sink.emit(event)

    # ─── Fix Cycle Status (Requirement: 7.6) ─────────────────────────────────

    async def emit_fix_cycle_status(
        self,
        iteration: int,
        max_iterations: int,
        errors_fixed: int,
        errors_remaining: int,
    ) -> None:
        """Emit status updates during iterative fix cycle.

        Args:
            iteration: Current iteration number.
            max_iterations: Maximum allowed iterations.
            errors_fixed: Number of errors resolved so far.
            errors_remaining: Number of errors still remaining.
        """
        if self._sink is None:
            return

        progress_pct = (iteration / max_iterations) * 100.0 if max_iterations > 0 else 0.0
        event = PipelineProgressEvent(
            phase="fix",
            progress_percent=progress_pct,
            message=(
                f"Fix cycle iteration {iteration}/{max_iterations}: "
                f"{errors_fixed} fixed, {errors_remaining} remaining"
            ),
            data={
                "iteration": iteration,
                "max_iterations": max_iterations,
                "errors_fixed": errors_fixed,
                "errors_remaining": errors_remaining,
            },
        )
        await self._sink.emit(event)

    # ─── Phase Timing Helpers ─────────────────────────────────────────────────

    def start_phase(self, phase: str) -> None:
        """Record the start time of a phase for duration calculation."""
        self._phase_start_times[phase] = time.perf_counter()

    def get_phase_duration_ms(self, phase: str) -> float:
        """Get elapsed milliseconds since phase start.

        Returns 0.0 if start_phase was not called for this phase.
        """
        start = self._phase_start_times.get(phase)
        if start is None:
            return 0.0
        return (time.perf_counter() - start) * 1000.0
