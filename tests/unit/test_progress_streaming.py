"""Unit tests for progress streaming in the Universal Repo Handler pipeline.

Tests verify that PipelineProgressEmitter correctly emits events during
detection, analysis, build, and fix phases via the StreamSink protocol.

Requirements: 10.1, 10.2, 10.3, 10.4
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from infrastructure.analysis.universal_repo.models import PipelineProgressEvent
from infrastructure.analysis.universal_repo.progress_emitter import (
    PipelineProgressEmitter,
)


# ─── Test Fixtures ───────────────────────────────────────────────────────────


class FakeStreamSink:
    """Collects emitted events for test assertions."""

    def __init__(self) -> None:
        self.events: list[PipelineProgressEvent] = []

    async def emit(self, event: PipelineProgressEvent) -> None:
        self.events.append(event)


@pytest.fixture
def sink() -> FakeStreamSink:
    return FakeStreamSink()


@pytest.fixture
def emitter(sink: FakeStreamSink) -> PipelineProgressEmitter:
    return PipelineProgressEmitter(sink=sink)


# ─── Detection Phase Tests (Requirement: 10.1) ──────────────────────────────


class TestDetectionProgressEmission:
    """Tests for progress events emitted during detection phase."""

    @pytest.mark.asyncio
    async def test_emit_detection_progress_basic(
        self, emitter: PipelineProgressEmitter, sink: FakeStreamSink
    ):
        """Test detection progress emits event with files_scanned and total."""
        await emitter.emit_detection_progress(
            files_scanned=50, total_files=200, phase="language"
        )

        assert len(sink.events) == 1
        event = sink.events[0]
        assert event.phase == "detection"
        assert event.progress_percent == 25.0
        assert event.data["files_scanned"] == 50
        assert event.data["total_files"] == 200
        assert event.data["sub_phase"] == "language"

    @pytest.mark.asyncio
    async def test_emit_detection_progress_percentage_calculation(
        self, emitter: PipelineProgressEmitter, sink: FakeStreamSink
    ):
        """Test percentage calculation is correct."""
        await emitter.emit_detection_progress(
            files_scanned=100, total_files=400, phase="framework"
        )

        event = sink.events[0]
        assert event.progress_percent == 25.0

    @pytest.mark.asyncio
    async def test_emit_detection_progress_zero_total(
        self, emitter: PipelineProgressEmitter, sink: FakeStreamSink
    ):
        """Test zero total files produces 0% progress without division error."""
        await emitter.emit_detection_progress(
            files_scanned=0, total_files=0, phase="language"
        )

        event = sink.events[0]
        assert event.progress_percent == 0.0

    @pytest.mark.asyncio
    async def test_emit_detection_progress_caps_at_100(
        self, emitter: PipelineProgressEmitter, sink: FakeStreamSink
    ):
        """Test progress caps at 100% even if files_scanned > total."""
        await emitter.emit_detection_progress(
            files_scanned=250, total_files=200, phase="build_tool"
        )

        event = sink.events[0]
        assert event.progress_percent == 100.0

    @pytest.mark.asyncio
    async def test_emit_detection_no_sink(self):
        """Test no-op when sink is None."""
        emitter = PipelineProgressEmitter(sink=None)
        # Should not raise
        await emitter.emit_detection_progress(
            files_scanned=10, total_files=100, phase="language"
        )

    @pytest.mark.asyncio
    async def test_detection_message_format(
        self, emitter: PipelineProgressEmitter, sink: FakeStreamSink
    ):
        """Test message contains scanning info."""
        await emitter.emit_detection_progress(
            files_scanned=30, total_files=100, phase="language"
        )

        event = sink.events[0]
        assert "30/100" in event.message
        assert "language" in event.message


# ─── Analysis Phase Tests (Requirement: 10.2) ────────────────────────────────


class TestAnalysisProgressEmission:
    """Tests for progress events emitted during analysis phase."""

    @pytest.mark.asyncio
    async def test_emit_analysis_progress_basic(
        self, emitter: PipelineProgressEmitter, sink: FakeStreamSink
    ):
        """Test analysis progress emits event with files_analyzed and findings."""
        await emitter.emit_analysis_progress(
            files_analyzed=5, findings_count=12, current_file="src/main.ts"
        )

        assert len(sink.events) == 1
        event = sink.events[0]
        assert event.phase == "analysis"
        assert event.data["files_analyzed"] == 5
        assert event.data["findings_count"] == 12
        assert event.data["current_file"] == "src/main.ts"

    @pytest.mark.asyncio
    async def test_emit_analysis_progress_message_contains_file(
        self, emitter: PipelineProgressEmitter, sink: FakeStreamSink
    ):
        """Test message includes current file and findings count."""
        await emitter.emit_analysis_progress(
            files_analyzed=3, findings_count=7, current_file="lib/utils.rs"
        )

        event = sink.events[0]
        assert "lib/utils.rs" in event.message
        assert "7" in event.message


# ─── Build Phase Tests (Requirement: 10.3) ───────────────────────────────────


class TestBuildProgressEmission:
    """Tests for progress events emitted during build output streaming."""

    @pytest.mark.asyncio
    async def test_emit_build_progress_basic(
        self, emitter: PipelineProgressEmitter, sink: FakeStreamSink
    ):
        """Test build progress emits output line event."""
        await emitter.emit_build_progress(
            output_line="Compiling main.rs (1/5)", phase="compiling"
        )

        assert len(sink.events) == 1
        event = sink.events[0]
        assert event.phase == "build"
        assert event.data["output_line"] == "Compiling main.rs (1/5)"
        assert event.data["sub_phase"] == "compiling"

    @pytest.mark.asyncio
    async def test_emit_build_progress_multiple_lines(
        self, emitter: PipelineProgressEmitter, sink: FakeStreamSink
    ):
        """Test multiple build output lines are emitted as separate events."""
        lines = [
            "Compiling dep1 v0.1.0",
            "Compiling dep2 v0.2.0",
            "Compiling main v1.0.0",
        ]
        for line in lines:
            await emitter.emit_build_progress(output_line=line, phase="compiling")

        assert len(sink.events) == 3
        for i, event in enumerate(sink.events):
            assert event.data["output_line"] == lines[i]

    @pytest.mark.asyncio
    async def test_emit_build_progress_message_is_output_line(
        self, emitter: PipelineProgressEmitter, sink: FakeStreamSink
    ):
        """Test the message field contains the output line."""
        await emitter.emit_build_progress(
            output_line="error[E0308]: mismatched types", phase="error"
        )

        event = sink.events[0]
        assert event.message == "error[E0308]: mismatched types"


# ─── Phase Completion Tests (Requirement: 10.4) ──────────────────────────────


class TestPhaseCompletionEmission:
    """Tests for completion events with summary and duration."""

    @pytest.mark.asyncio
    async def test_emit_phase_complete_detection(
        self, emitter: PipelineProgressEmitter, sink: FakeStreamSink
    ):
        """Test completion event includes summary and duration for detection."""
        summary = {
            "primary_language": "Python",
            "languages_detected": 3,
            "confidence": 0.95,
        }
        await emitter.emit_phase_complete(
            phase="detection", summary=summary, duration_ms=1250.5
        )

        assert len(sink.events) == 1
        event = sink.events[0]
        assert event.phase == "complete"
        assert event.progress_percent == 100.0
        assert event.data["completed_phase"] == "detection"
        assert event.data["summary"] == summary
        assert event.data["duration_ms"] == 1250.5

    @pytest.mark.asyncio
    async def test_emit_phase_complete_analysis(
        self, emitter: PipelineProgressEmitter, sink: FakeStreamSink
    ):
        """Test completion event for analysis phase."""
        summary = {"files_analyzed": 42, "findings_count": 7}
        await emitter.emit_phase_complete(
            phase="analysis", summary=summary, duration_ms=3200.0
        )

        event = sink.events[0]
        assert event.data["completed_phase"] == "analysis"
        assert event.data["summary"]["files_analyzed"] == 42

    @pytest.mark.asyncio
    async def test_emit_phase_complete_build(
        self, emitter: PipelineProgressEmitter, sink: FakeStreamSink
    ):
        """Test completion event for build phase."""
        summary = {"errors": 2, "warnings": 5, "success": False}
        await emitter.emit_phase_complete(
            phase="build", summary=summary, duration_ms=8500.0
        )

        event = sink.events[0]
        assert event.data["completed_phase"] == "build"
        assert event.data["duration_ms"] == 8500.0

    @pytest.mark.asyncio
    async def test_emit_phase_complete_message_format(
        self, emitter: PipelineProgressEmitter, sink: FakeStreamSink
    ):
        """Test completion message includes phase name and duration."""
        await emitter.emit_phase_complete(
            phase="build", summary={}, duration_ms=2000.0
        )

        event = sink.events[0]
        assert "build" in event.message
        assert "2000" in event.message


# ─── Fix Cycle Status Tests (Requirement: 7.6) ──────────────────────────────


class TestFixCycleStatusEmission:
    """Tests for iterative fix cycle status updates."""

    @pytest.mark.asyncio
    async def test_emit_fix_cycle_status_basic(
        self, emitter: PipelineProgressEmitter, sink: FakeStreamSink
    ):
        """Test fix cycle status emits iteration and error counts."""
        await emitter.emit_fix_cycle_status(
            iteration=1, max_iterations=3, errors_fixed=2, errors_remaining=5
        )

        assert len(sink.events) == 1
        event = sink.events[0]
        assert event.phase == "fix"
        assert event.data["iteration"] == 1
        assert event.data["max_iterations"] == 3
        assert event.data["errors_fixed"] == 2
        assert event.data["errors_remaining"] == 5

    @pytest.mark.asyncio
    async def test_emit_fix_cycle_status_progress_percent(
        self, emitter: PipelineProgressEmitter, sink: FakeStreamSink
    ):
        """Test progress percentage based on iteration/max_iterations."""
        await emitter.emit_fix_cycle_status(
            iteration=2, max_iterations=3, errors_fixed=4, errors_remaining=1
        )

        event = sink.events[0]
        expected_pct = (2 / 3) * 100.0
        assert abs(event.progress_percent - expected_pct) < 0.1

    @pytest.mark.asyncio
    async def test_emit_fix_cycle_status_message_format(
        self, emitter: PipelineProgressEmitter, sink: FakeStreamSink
    ):
        """Test message includes iteration info and error counts."""
        await emitter.emit_fix_cycle_status(
            iteration=3, max_iterations=3, errors_fixed=6, errors_remaining=0
        )

        event = sink.events[0]
        assert "3/3" in event.message
        assert "6 fixed" in event.message
        assert "0 remaining" in event.message


# ─── Phase Timing Tests ──────────────────────────────────────────────────────


class TestPhaseTiming:
    """Tests for phase start/duration tracking."""

    def test_start_phase_and_get_duration(
        self, emitter: PipelineProgressEmitter
    ):
        """Test duration measurement after start_phase."""
        emitter.start_phase("detection")
        # Duration should be > 0 (even if tiny)
        duration = emitter.get_phase_duration_ms("detection")
        assert duration >= 0.0

    def test_get_duration_without_start_returns_zero(
        self, emitter: PipelineProgressEmitter
    ):
        """Test duration returns 0 if start_phase was never called."""
        duration = emitter.get_phase_duration_ms("nonexistent")
        assert duration == 0.0

    def test_has_sink_true(self, emitter: PipelineProgressEmitter):
        """Test has_sink returns True when sink is configured."""
        assert emitter.has_sink is True

    def test_has_sink_false(self):
        """Test has_sink returns False when sink is None."""
        emitter = PipelineProgressEmitter(sink=None)
        assert emitter.has_sink is False
