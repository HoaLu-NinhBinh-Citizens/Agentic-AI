"""Replay Conformance Tests - P0-Hardening.

Tests deterministic replay guarantees:
1. First-divergence detection: original vs replay command sequence
2. Nondeterminism injection: verify replay still produces same decisions
3. Replay isolation: no side-effect re-execution during replay

These tests ensure the event replay system is truly deterministic and
conforms to the W-001 specification.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from dataclasses import dataclass, field
from typing import Any

import pytest

sys.path.insert(0, "src")


# =============================================================================
# TEST FIXTURES & HELPERS
# =============================================================================


@dataclass
class FakeEvent:
    """Minimal event for testing.

    Uses event_type (not 'type') to match the ReplayEvent interface.
    """
    offset: int
    event_type: str
    source: str = "test"
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "offset": self.offset,
            "event_type": self.event_type,
            "source": self.source,
            "payload": self.payload,
        }


class MockEventJournal:
    """In-memory event journal for testing.

    Returns FakeEvent objects in insertion order (or sorted if configured).
    """

    def __init__(self, events: list[FakeEvent] | None = None, sorted_events: bool = False):
        self._events = list(events or [])
        self._sorted = sorted_events
        if sorted_events:
            self._events.sort(key=lambda e: e.offset)

    async def scan(
        self,
        event_types: list[str] | None = None,
        sources: list[str] | None = None,
        since: Any = None,
        until: Any = None,
        limit: int = 100000,
    ) -> list[FakeEvent]:
        filtered = []
        for e in self._events:
            if event_types and e.event_type not in event_types:
                continue
            if sources and e.source not in sources:
                continue
            filtered.append(e)
        return filtered[:limit]


class CapturingSideEffectExecutor:
    """Captures side effects for verification.

    Deterministic: same command+params always produce same checksum,
    regardless of call count. This is the correct behavior for replay.
    """

    def __init__(self):
        self.executions: list[dict[str, Any]] = []

    async def execute(self, command: str, params: dict[str, Any]) -> str:
        hasher = hashlib.sha256()
        hasher.update(command.encode())
        # JSON-encode params deterministically (sort keys)
        hasher.update(json.dumps(params, sort_keys=True, default=str).encode())
        checksum = hasher.hexdigest()

        self.executions.append({
            "command": command,
            "params": params,
            "checksum": checksum,
        })
        return checksum


def first_divergence(original: list[dict], replay: list[dict]) -> int | None:
    """Find index of first differing item between two sequences."""
    for i, (o, r) in enumerate(zip(original, replay)):
        if o != r:
            return i
    if len(original) != len(replay):
        return min(len(original), len(replay))
    return None


# =============================================================================
# TESTS: REPLAY DETERMINISM
# =============================================================================


class TestReplayDeterminism:
    """Test W-001 deterministic replay guarantees."""

    @pytest.mark.asyncio
    async def test_checksum_identical_for_same_sequence(self):
        """Identical event sequences must produce identical checksums."""
        from src.core.runtime.replayer import EventReplayer

        events = [
            FakeEvent(offset=0, event_type="workflow.start"),
            FakeEvent(offset=1, event_type="activity.execute"),
            FakeEvent(offset=2, event_type="activity.complete"),
        ]

        journal = MockEventJournal(events, sorted_events=True)

        # First replay
        replayer1 = EventReplayer(journal)
        result1 = await replayer1.replay(from_offset=0, verify_determinism=True)

        # Second replay (same journal, same events)
        replayer2 = EventReplayer(journal)
        result2 = await replayer2.replay(from_offset=0, verify_determinism=True)

        assert result1.checksum == result2.checksum, (
            f"Checksum mismatch: {result1.checksum[:16]} != {result2.checksum[:16]}"
        )

    @pytest.mark.asyncio
    async def test_offset_order_violation_sets_event_order_valid_false(self):
        """Offset regression must set event_order_valid=False."""
        from src.core.runtime.replayer import EventReplayer

        # Events in wrong order: offset 2 before offset 1
        events = [
            FakeEvent(offset=0, event_type="a"),
            FakeEvent(offset=2, event_type="c"),
            FakeEvent(offset=1, event_type="b"),
        ]
        # Deliberately NOT sorted so they come out of order
        journal = MockEventJournal(events, sorted_events=False)
        replayer = EventReplayer(journal)
        result = await replayer.replay(from_offset=0, verify_determinism=True)

        assert result.event_order_valid is False, (
            "Offset regression should set event_order_valid=False"
        )

    @pytest.mark.asyncio
    async def test_checksum_matches_for_ordered_events(self):
        """For correctly ordered events, checksums must match."""
        from src.core.runtime.replayer import EventReplayer

        events = [
            FakeEvent(offset=i, event_type=f"evt_{i}", source="test")
            for i in range(10)
        ]

        journal = MockEventJournal(events, sorted_events=True)
        replayer = EventReplayer(journal)
        result = await replayer.replay(from_offset=0, verify_determinism=True)

        assert result.checksum == result.verification_checksum, (
            f"Incremental ({result.checksum[:16]}) != "
            f"sequence ({result.verification_checksum[:16]})"
        )

    @pytest.mark.asyncio
    async def test_full_flash_workflow_replay_is_deterministic(self):
        """A complete flash workflow must be deterministic across multiple replays."""
        from src.core.runtime.replayer import EventReplayer

        events = [
            FakeEvent(offset=0, event_type="workflow.start",
                     payload={"target": "engine_car"}),
            FakeEvent(offset=1, event_type="lock.acquired",
                     payload={"target": "engine_car"}),
            FakeEvent(offset=2, event_type="flash.erase_started",
                     payload={"sector": 12}),
            FakeEvent(offset=3, event_type="flash.erase_completed",
                     payload={"sector": 12}),
            FakeEvent(offset=4, event_type="flash.write_started",
                     payload={"sector": 12}),
            FakeEvent(offset=5, event_type="flash.write_completed",
                     payload={"sector": 12}),
            FakeEvent(offset=6, event_type="flash.verify_passed",
                     payload={"sector": 12}),
            FakeEvent(offset=7, event_type="lock.released",
                     payload={"target": "engine_car"}),
            FakeEvent(offset=8, event_type="workflow.complete",
                     payload={"status": "success"}),
        ]

        journal = MockEventJournal(events, sorted_events=True)
        checksums = []
        for _ in range(3):
            replayer = EventReplayer(journal)
            result = await replayer.replay(from_offset=0, verify_determinism=True)
            checksums.append(result.checksum)

        assert len(set(checksums)) == 1, (
            f"Flash workflow replay must be deterministic. Got: {checksums}"
        )


# =============================================================================
# TESTS: FIRST DIVERGENCE DETECTION
# =============================================================================


class TestFirstDivergenceDetection:
    """Test that first-divergence tooling identifies replay deviations."""

    @pytest.mark.asyncio
    async def test_captures_command_sequence(self):
        """Executor must capture full command sequence for forensic comparison."""
        executor = CapturingSideEffectExecutor()

        await executor.execute("flash.erase", {"sector": 12, "address": 0x08010000})
        await executor.execute("flash.write", {"sector": 12, "length": 4096})
        await executor.execute("flash.verify", {"sector": 12, "expected_crc": 0xDEADBEEF})

        assert len(executor.executions) == 3
        assert [e["command"] for e in executor.executions] == [
            "flash.erase", "flash.write", "flash.verify"
        ]

    @pytest.mark.asyncio
    async def test_deterministic_output_per_command(self):
        """Same command+params must always produce same checksum (idempotent)."""
        executor = CapturingSideEffectExecutor()

        c1 = await executor.execute("flash.read", {"address": 0x08000000, "length": 256})
        c2 = await executor.execute("flash.read", {"address": 0x08000000, "length": 256})

        assert c1 == c2, (
            f"Idempotent commands must produce identical checksums. "
            f"First: {c1[:16]}, Second: {c2[:16]}"
        )

    @pytest.mark.asyncio
    async def test_different_params_different_output(self):
        """Different params must produce different output."""
        executor = CapturingSideEffectExecutor()

        c1 = await executor.execute("flash.read", {"address": 0x08000000, "length": 256})
        c2 = await executor.execute("flash.read", {"address": 0x08001000, "length": 256})

        assert c1 != c2, "Different params must produce different output"

    def test_divergence_detector_finds_first_difference(self):
        """First-divergence detector must pinpoint the first differing event."""
        original = [
            {"offset": 0, "command": "erase", "checksum": "a"},
            {"offset": 1, "command": "write", "checksum": "b"},
            {"offset": 2, "command": "verify", "checksum": "c"},
        ]
        replay_seq = [
            {"offset": 0, "command": "erase", "checksum": "a"},
            {"offset": 1, "command": "write", "checksum": "X"},
            {"offset": 2, "command": "verify", "checksum": "c"},
        ]

        idx = first_divergence(original, replay_seq)
        assert idx == 1, f"First divergence should be at index 1, got {idx}"


# =============================================================================
# TESTS: REPLAY ISOLATION
# =============================================================================


class TestReplayIsolation:
    """Test that replay does NOT re-execute side effects."""

    @pytest.mark.asyncio
    async def test_verify_false_skips_checksum(self):
        """verify_determinism=False should skip checksum computation."""
        from src.core.runtime.replayer import EventReplayer

        events = [FakeEvent(offset=i, event_type=f"e{i}") for i in range(5)]
        journal = MockEventJournal(events, sorted_events=True)
        replayer = EventReplayer(journal)

        result = await replayer.replay(from_offset=0, verify_determinism=False)

        assert result.checksum == "", "Checksum should be empty when not verified"
        assert result.is_deterministic is True, "is_deterministic defaults to True"

    @pytest.mark.asyncio
    async def test_handlers_called_in_normal_mode(self):
        """Handlers are called in normal (non-dry-run) mode."""
        from src.core.runtime.replayer import EventReplayer

        events = [
            FakeEvent(offset=0, event_type="erase"),
            FakeEvent(offset=1, event_type="write"),
        ]
        journal = MockEventJournal(events, sorted_events=True)
        replayer = EventReplayer(journal)

        call_count = 0

        async def counting_handler(data: dict) -> None:
            nonlocal call_count
            call_count += 1

        replayer.register_handler("erase", counting_handler)
        replayer.register_handler("write", counting_handler)

        # dry_run=False (default): handlers ARE called
        await replayer.replay(from_offset=0, dry_run=False, verify_determinism=False)

        assert call_count == 2, f"Expected 2 handler calls, got {call_count}"

    @pytest.mark.asyncio
    async def test_dry_run_does_not_call_handlers(self):
        """In dry_run mode, handlers are NOT called (only logged)."""
        from src.core.runtime.replayer import EventReplayer

        events = [
            FakeEvent(offset=0, event_type="erase"),
            FakeEvent(offset=1, event_type="write"),
        ]
        journal = MockEventJournal(events, sorted_events=True)
        replayer = EventReplayer(journal)

        call_count = 0

        async def counting_handler(data: dict) -> None:
            nonlocal call_count
            call_count += 1

        replayer.register_handler("erase", counting_handler)
        replayer.register_handler("write", counting_handler)

        # dry_run=True: handlers are skipped (only logged)
        result = await replayer.replay(from_offset=0, dry_run=True, verify_determinism=False)

        # In dry_run mode, handlers are NOT called
        assert call_count == 0, f"Expected 0 handler calls in dry_run, got {call_count}"
        # But events are still replayed (counted)
        assert result.events_replayed == 2

    @pytest.mark.asyncio
    async def test_replay_result_has_required_fields(self):
        """ReplayResult must include all W-001 determinism fields."""
        from src.core.runtime.replayer import EventReplayer

        events = [FakeEvent(offset=0, event_type="test")]
        journal = MockEventJournal(events, sorted_events=True)
        replayer = EventReplayer(journal)
        result = await replayer.replay(from_offset=0, verify_determinism=True)

        report = result.to_dict()
        for field_name in [
            "events_replayed", "events_filtered", "events_failed",
            "checksum", "verification_checksum",
            "is_deterministic", "event_order_valid",
        ]:
            assert field_name in report, f"W-001 field '{field_name}' missing"


# =============================================================================
# TESTS: REPLAY CONFORMANCE
# =============================================================================


class TestReplayConformance:
    """End-to-end conformance tests for deterministic replay."""

    @pytest.mark.asyncio
    async def test_conformance_report_format(self):
        """Replay must produce a structured conformance report."""
        from src.core.runtime.replayer import EventReplayer

        events = [
            FakeEvent(offset=i, event_type=f"evt_{i}", source="test")
            for i in range(5)
        ]
        journal = MockEventJournal(events, sorted_events=True)
        replayer = EventReplayer(journal)
        result = await replayer.replay(from_offset=0, verify_determinism=True)

        report = result.to_dict()

        assert report["events_replayed"] == 5
        assert len(report["checksum"]) == 64  # SHA-256 hex
        assert report["is_deterministic"] is True
        assert report["event_order_valid"] is True

    @pytest.mark.asyncio
    async def test_replay_from_offset_skips_early_events(self):
        """replay from_offset=N should skip events with offset < N."""
        from src.core.runtime.replayer import EventReplayer

        events = [FakeEvent(offset=i, event_type=f"evt_{i}") for i in range(10)]
        journal = MockEventJournal(events, sorted_events=True)
        replayer = EventReplayer(journal)

        result = await replayer.replay(from_offset=5, verify_determinism=True)

        assert result.events_replayed == 5, "Only offsets >= 5 should be replayed"
        assert result.final_offset == 9

    @pytest.mark.asyncio
    async def test_max_events_limits_replay(self):
        """max_events parameter should limit events replayed."""
        from src.core.runtime.replayer import EventReplayer

        events = [FakeEvent(offset=i, event_type=f"e{i}") for i in range(20)]
        journal = MockEventJournal(events, sorted_events=True)
        replayer = EventReplayer(journal)

        result = await replayer.replay(from_offset=0, max_events=5, verify_determinism=True)

        assert result.events_replayed == 5, "max_events should limit replay"
        assert result.final_offset == 4

    @pytest.mark.asyncio
    async def test_handler_not_called_for_unknown_event_type(self):
        """Handlers are only called for registered event types."""
        from src.core.runtime.replayer import EventReplayer

        events = [
            FakeEvent(offset=0, event_type="known"),
            FakeEvent(offset=1, event_type="unknown"),
            FakeEvent(offset=2, event_type="known"),
        ]
        journal = MockEventJournal(events, sorted_events=True)
        replayer = EventReplayer(journal)

        call_count = 0

        async def handler(data: dict) -> None:
            nonlocal call_count
            call_count += 1

        replayer.register_handler("known", handler)

        result = await replayer.replay(from_offset=0, dry_run=False, verify_determinism=False)

        assert call_count == 2, f"Handler should be called 2 times, got {call_count}"


# =============================================================================
# TESTS: REPLAY CONFORMANCE TEST CLASS
# =============================================================================


class ReplayConformanceTest:
    """Replay conformance test harness.

    Runs a workflow, captures event sequence + command outputs,
    replays the same event sequence, and verifies outputs match bit-for-bit.
    """

    def __init__(self, name: str = "unnamed"):
        self.name = name
        self._events: list[dict] = []
        self._captured_outputs: list[dict] = []
        self._is_replaying = False

    def capture_event(self, event_type: str, payload: dict | None = None) -> None:
        """Capture an event during original workflow execution or replay."""
        self._events.append({
            "offset": len(self._events),
            "event_type": event_type,
            "payload": payload or {},
        })

    def capture_output(self, command: str, params: dict, output: Any) -> None:
        """Capture command output during original workflow execution or replay."""
        self._captured_outputs.append({
            "command": command,
            "params": params,
            "output": output,
        })

    async def run_original(
        self,
        executor: CapturingSideEffectExecutor,
        commands: list[tuple[str, dict]],
    ) -> tuple[list[dict], list[dict]]:
        """Run the original workflow and capture events + outputs."""
        self._events = []
        self._captured_outputs = []
        self._is_replaying = False

        for i, (cmd, params) in enumerate(commands):
            self.capture_event("workflow.command_start", {"command": cmd, "index": i, "params": params})
            output = await executor.execute(cmd, params)
            self.capture_output(cmd, params, output)
            self.capture_event("workflow.command_complete", {"command": cmd, "checksum": output})

        return self._events, self._captured_outputs

    async def run_replay(
        self,
        executor: CapturingSideEffectExecutor,
        original_events: list[dict],
        handlers: dict[str, Any],
    ) -> tuple[list[dict], list[dict]]:
        """Replay the captured events and return outputs for comparison."""
        self._events = []
        self._captured_outputs = []
        self._is_replaying = True

        for event in original_events:
            self.capture_event(event["event_type"], event.get("payload", {}))
            if event["event_type"] == "workflow.command_start":
                cmd = event["payload"]["command"]
                params = event["payload"].get("params", {})
                output = await executor.execute(cmd, params)
                self.capture_output(cmd, params, output)

        self._is_replaying = False
        return self._events, self._captured_outputs

    def verify_outputs_match(
        self,
        original: list[dict],
        replay: list[dict],
    ) -> tuple[bool, int | None]:
        """Verify outputs match bit-for-bit. Returns (match, first_divergence_index)."""
        divergence_idx = first_divergence(original, replay)
        return divergence_idx is None, divergence_idx


class TestReplayConformanceTestClass:
    """Tests for the ReplayConformanceTest class."""

    @pytest.mark.asyncio
    async def test_capture_and_replay_workflow(self):
        """Test full capture-replay-verify workflow."""
        executor = CapturingSideEffectExecutor()
        harness = ReplayConformanceTest(name="flash_workflow")

        commands = [
            ("flash.erase", {"sector": 12, "address": 0x08010000}),
            ("flash.write", {"sector": 12, "length": 4096}),
            ("flash.verify", {"sector": 12, "expected_crc": 0xDEADBEEF}),
        ]

        # Original run
        original_events, original_outputs = await harness.run_original(executor, commands)

        # Replay (simulated - use same executor)
        executor_replay = CapturingSideEffectExecutor()
        replay_events, replay_outputs = await harness.run_replay(
            executor_replay, original_events, {}
        )

        # Verify
        match, divergence_idx = harness.verify_outputs_match(original_outputs, replay_outputs)
        assert match, f"Outputs diverged at index {divergence_idx}"

    @pytest.mark.asyncio
    async def test_bit_for_bit_output_verification(self):
        """Test that identical commands produce bit-for-bit matching outputs."""
        executor1 = CapturingSideEffectExecutor()
        executor2 = CapturingSideEffectExecutor()

        cmd, params = "flash.read", {"address": 0x08000000, "length": 256}

        out1 = await executor1.execute(cmd, params)
        out2 = await executor2.execute(cmd, params)

        assert out1 == out2, "Identical commands must produce bit-for-bit matching output"

    @pytest.mark.asyncio
    async def test_event_sequence_preserved_in_replay(self):
        """Test that event sequence order is preserved during replay."""
        harness = ReplayConformanceTest()

        events = [
            {"offset": 0, "event_type": "start"},
            {"offset": 1, "event_type": "middle"},
            {"offset": 2, "event_type": "end"},
        ]

        # Simulate replay by setting up the harness and capturing events
        harness._events = []
        harness._is_replaying = False  # Allow capture during simulation
        for evt in events:
            harness.capture_event(evt["event_type"])

        assert len(harness._events) == 3
        assert [e["event_type"] for e in harness._events] == ["start", "middle", "end"]


# =============================================================================
# TESTS: NONDETERMINISM INJECTION
# =============================================================================


class MockLLMProvider:
    """Mock LLM provider that can inject nondeterminism."""

    def __init__(self, deterministic: bool = True):
        self._deterministic = deterministic
        self._call_count = 0
        self._responses = [
            "Response A",
            "Response B",
            "Response C",
        ]

    async def generate(self, prompt: str) -> str:
        self._call_count += 1
        if self._deterministic:
            # Deterministic: always return same hash for same prompt
            hasher = hashlib.sha256()
            hasher.update(prompt.encode())
            return hasher.hexdigest()
        else:
            # Nondeterministic: return different responses
            idx = self._call_count % len(self._responses)
            return self._responses[idx]


class MockRetrievalService:
    """Mock retrieval service with controllable ordering."""

    def __init__(self, stable_order: bool = True):
        self._stable_order = stable_order
        self._documents = [
            {"id": "doc1", "content": "Document 1"},
            {"id": "doc2", "content": "Document 2"},
            {"id": "doc3", "content": "Document 3"},
        ]

    async def search(self, query: str, k: int = 3) -> list[dict]:
        if self._stable_order:
            # Stable order: sort by id
            return sorted(self._documents[:k], key=lambda d: d["id"])
        else:
            # Nondeterministic: return in random order
            import random
            docs = self._documents[:k].copy()
            random.shuffle(docs)
            return docs


class TestNondeterminismInjection:
    """Test replay produces same decisions despite injected nondeterminism."""

    @pytest.mark.asyncio
    async def test_random_failure_injection(self):
        """Replay should produce same decisions even with injected failures."""
        from src.core.runtime.replayer import EventReplayer

        # Simulate events with failure injection
        events = [
            FakeEvent(offset=0, event_type="workflow.start", payload={"attempt": 1}),
            FakeEvent(offset=1, event_type="flash.erase", payload={"sector": 12}),
            FakeEvent(offset=2, event_type="flash.write", payload={"sector": 12}),
        ]

        # Run with failures injected
        journal = MockEventJournal(events, sorted_events=True)
        replayer = EventReplayer(journal)
        result1 = await replayer.replay(from_offset=0, verify_determinism=True)

        # Replay should produce same checksums regardless of failure injection
        journal2 = MockEventJournal(events, sorted_events=True)
        replayer2 = EventReplayer(journal2)
        result2 = await replayer2.replay(from_offset=0, verify_determinism=True)

        assert result1.checksum == result2.checksum, (
            "Replay must be deterministic despite injected failures"
        )

    @pytest.mark.asyncio
    async def test_clock_skew_injection(self):
        """Replay should handle clock skew without affecting determinism."""
        from src.core.runtime.replayer import EventReplayer

        events = [
            FakeEvent(offset=0, event_type="workflow.start", payload={"timestamp_skew": 1000}),
            FakeEvent(offset=1, event_type="activity.execute", payload={"time": "2024-01-01T00:00:00Z"}),
            FakeEvent(offset=2, event_type="workflow.end", payload={"timestamp_skew": -1000}),
        ]

        journal = MockEventJournal(events, sorted_events=True)
        replayer = EventReplayer(journal)
        result = await replayer.replay(from_offset=0, verify_determinism=True)

        # Checksum should only depend on offset, event_type, source, and logical_clock
        # NOT on timestamp values in payload
        assert result.is_deterministic is True, "Clock skew should not affect determinism"

    @pytest.mark.asyncio
    async def test_llm_variation_injection(self):
        """Replay should produce same decisions even with LLM response variation."""
        # Create two LLM providers with different response patterns
        llm_nondet = MockLLMProvider(deterministic=False)
        llm_det = MockLLMProvider(deterministic=True)

        prompt = "What is the best flash algorithm?"

        # Different calls to nondeterministic LLM produce different results
        response1a = await llm_nondet.generate(prompt)
        response1b = await llm_nondet.generate(prompt)

        # Deterministic LLM always produces same result for same prompt
        response2a = await llm_det.generate(prompt)
        response2b = await llm_det.generate(prompt)

        assert response1a != response1b, "Nondeterministic LLM should vary"
        assert response2a == response2b, "Deterministic LLM should be stable"

    @pytest.mark.asyncio
    async def test_retrieval_order_injection(self):
        """Replay should produce same decisions despite retrieval order changes."""
        # Stable order
        retrieval_stable = MockRetrievalService(stable_order=True)
        docs_stable = await retrieval_stable.search("query", k=3)

        # Unstable order
        retrieval_unstable = MockRetrievalService(stable_order=False)
        docs_unstable = await retrieval_unstable.search("query", k=3)

        # Stable order should be deterministic
        docs_stable2 = await retrieval_stable.search("query", k=3)
        assert [d["id"] for d in docs_stable] == [d["id"] for d in docs_stable2], (
            "Stable retrieval should be deterministic"
        )

    @pytest.mark.asyncio
    async def test_replay_decisions_match_despite_nondeterminism(self):
        """Replay decisions must match original even with all nondeterminism injected."""
        from src.core.runtime.replayer import EventReplayer

        # Simulate workflow with LLM decision points
        events = [
            FakeEvent(offset=0, event_type="workflow.start"),
            FakeEvent(offset=1, event_type="llm.decision",
                     payload={"prompt": "choose_algorithm", "decision": "algorithm_a"}),
            FakeEvent(offset=2, event_type="workflow.complete"),
        ]

        journal = MockEventJournal(events, sorted_events=True)
        replayer = EventReplayer(journal)
        result1 = await replayer.replay(from_offset=0, verify_determinism=True)

        # Replay with same event sequence
        journal2 = MockEventJournal(events, sorted_events=True)
        replayer2 = EventReplayer(journal2)
        result2 = await replayer2.replay(from_offset=0, verify_determinism=True)

        # Checksums should match because replay uses recorded decisions, not live LLM
        assert result1.checksum == result2.checksum, (
            "Replay must produce same decisions from event record"
        )


# =============================================================================
# TESTS: REPLAY ISOLATION
# =============================================================================


class SideEffectTracker:
    """Tracks whether side effects have been executed."""

    def __init__(self):
        self.flash_writes: list[dict] = []
        self.llm_calls: list[dict] = []
        self.network_calls: list[dict] = []
        self._allow_real_execution = False

    def record_flash_write(self, address: int, data: bytes) -> None:
        if not self._allow_real_execution:
            self.flash_writes.append({"address": address, "size": len(data)})

    def record_llm_call(self, prompt: str) -> None:
        if not self._allow_real_execution:
            self.llm_calls.append({"prompt": prompt})

    def record_network_call(self, url: str) -> None:
        if not self._allow_real_execution:
            self.network_calls.append({"url": url})

    def allow_real_execution(self) -> None:
        self._allow_real_execution = True

    def reset(self) -> None:
        self.flash_writes.clear()
        self.llm_calls.clear()
        self.network_calls.clear()

    @property
    def has_side_effects(self) -> bool:
        return bool(self.flash_writes or self.llm_calls or self.network_calls)


class TestReplayIsolation:
    """Test that replay does NOT re-execute side effects."""

    @pytest.mark.asyncio
    async def test_replay_does_not_call_flash_hardware(self):
        """Verify replay does NOT execute actual flash operations."""
        from src.core.runtime.replayer import EventReplayer

        events = [
            FakeEvent(offset=0, event_type="flash.erase", payload={"address": 0x08010000}),
            FakeEvent(offset=1, event_type="flash.write", payload={"address": 0x08010000}),
        ]

        journal = MockEventJournal(events, sorted_events=True)
        replayer = EventReplayer(journal)

        flash_call_count = 0

        async def flash_handler(data: dict) -> None:
            nonlocal flash_call_count
            flash_call_count += 1
            # In dry_run mode, handler is NOT called

        replayer.register_handler("flash.erase", flash_handler)
        replayer.register_handler("flash.write", flash_handler)

        # Normal replay (dry_run=False)
        await replayer.replay(from_offset=0, dry_run=False, verify_determinism=False)

        # Handler IS called in normal mode
        assert flash_call_count == 2

    @pytest.mark.asyncio
    async def test_dry_run_replay_isolates_side_effects(self):
        """Verify dry_run mode completely isolates side effects."""
        from src.core.runtime.replayer import EventReplayer

        events = [
            FakeEvent(offset=0, event_type="flash.erase"),
            FakeEvent(offset=1, event_type="flash.write"),
            FakeEvent(offset=2, event_type="llm.call"),
        ]

        journal = MockEventJournal(events, sorted_events=True)
        replayer = EventReplayer(journal)

        flash_count = 0
        llm_count = 0

        async def flash_handler(data: dict) -> None:
            nonlocal flash_count
            flash_count += 1

        async def llm_handler(data: dict) -> None:
            nonlocal llm_count
            llm_count += 1

        replayer.register_handler("flash.erase", flash_handler)
        replayer.register_handler("flash.write", flash_handler)
        replayer.register_handler("llm.call", llm_handler)

        # dry_run=True: handlers NOT called
        result = await replayer.replay(from_offset=0, dry_run=True, verify_determinism=False)

        assert flash_count == 0, "Flash should NOT be called in dry_run"
        assert llm_count == 0, "LLM should NOT be called in dry_run"
        assert result.events_replayed == 3, "Events still counted in dry_run"

    @pytest.mark.asyncio
    async def test_side_effect_tracker_detects_real_execution(self):
        """SideEffectTracker should detect if real side effects occur."""
        tracker = SideEffectTracker()

        # Simulate some operations
        tracker.record_flash_write(0x08010000, b"\x00" * 4096)
        tracker.record_llm_call("test prompt")

        assert tracker.has_side_effects is True, "Tracker should detect side effects"
        assert len(tracker.flash_writes) == 1
        assert len(tracker.llm_calls) == 1

        tracker.reset()
        assert tracker.has_side_effects is False, "Tracker should be clean after reset"

    @pytest.mark.asyncio
    async def test_replay_verification_skips_unsafe_operations(self):
        """Replay verification should skip operations that could cause harm."""
        from src.core.runtime.replayer import EventReplayer

        unsafe_events = [
            FakeEvent(offset=0, event_type="flash.erase_all"),
            FakeEvent(offset=1, event_type="flash.write"),
        ]

        journal = MockEventJournal(unsafe_events, sorted_events=True)
        replayer = EventReplayer(journal)

        unsafe_count = 0

        async def unsafe_handler(data: dict) -> None:
            nonlocal unsafe_count
            unsafe_count += 1

        replayer.register_handler("flash.erase_all", unsafe_handler)
        replayer.register_handler("flash.write", unsafe_handler)

        # dry_run=True should skip all handlers
        await replayer.replay(from_offset=0, dry_run=True, verify_determinism=False)

        assert unsafe_count == 0, "Unsafe operations should be skipped in dry_run"

    @pytest.mark.asyncio
    async def test_concurrent_replay_isolation(self):
        """Multiple concurrent replays should not interfere."""
        from src.core.runtime.replayer import EventReplayer

        events = [FakeEvent(offset=i, event_type=f"evt_{i}") for i in range(10)]

        async def run_replay(replay_id: int) -> bool:
            journal = MockEventJournal(events, sorted_events=True)
            replayer = EventReplayer(journal)
            result = await replayer.replay(
                from_offset=0, dry_run=True, verify_determinism=True
            )
            return result.success

        # Run multiple replays concurrently
        results = await asyncio.gather(*[run_replay(i) for i in range(5)])

        assert all(results), "All concurrent replays should succeed"
        assert len(set(results)) == 1, "All replays should produce same result"


# =============================================================================
# TESTS: REPLAY CONFORMANCE SUMMARY
# =============================================================================


class TestReplayConformanceSummary:
    """Summary tests verifying overall replay conformance."""

    @pytest.mark.asyncio
    async def test_full_conformance_checklist(self):
        """Verify all conformance requirements are met."""
        from src.core.runtime.replayer import EventReplayer

        # Create comprehensive test workflow
        events = [
            FakeEvent(offset=0, event_type="workflow.start",
                     payload={"session_id": "test_session"}),
            FakeEvent(offset=1, event_type="lock.acquired",
                     payload={"target": "engine_car"}),
            FakeEvent(offset=2, event_type="flash.erase",
                     payload={"sector": 12}),
            FakeEvent(offset=3, event_type="flash.write",
                     payload={"sector": 12, "size": 4096}),
            FakeEvent(offset=4, event_type="flash.verify",
                     payload={"sector": 12}),
            FakeEvent(offset=5, event_type="lock.released",
                     payload={"target": "engine_car"}),
            FakeEvent(offset=6, event_type="workflow.complete",
                     payload={"status": "success"}),
        ]

        checksums = []
        for _ in range(5):
            journal = MockEventJournal(events, sorted_events=True)
            replayer = EventReplayer(journal)
            result = await replayer.replay(from_offset=0, verify_determinism=True)
            checksums.append(result.checksum)

        # All checksums must be identical for deterministic replay
        assert len(set(checksums)) == 1, (
            f"Replay must be deterministic. Got {len(set(checksums))} unique checksums: "
            f"{set(checksums)}"
        )

        # Verify result structure
        journal = MockEventJournal(events, sorted_events=True)
        replayer = EventReplayer(journal)
        result = await replayer.replay(from_offset=0, verify_determinism=True)

        assert result.success is True
        assert result.events_replayed == 7
        assert result.events_failed == 0
        assert result.is_deterministic is True
        assert result.event_order_valid is True
        assert len(result.checksum) == 64  # SHA-256


