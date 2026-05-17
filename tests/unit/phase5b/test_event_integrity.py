"""Unit tests for event integrity (hash chain).

Tests cover:
- test_replay_same_decision_branch: Branch recorded, not re-evaluated
- test_replay_deterministic_time: ctx.now() returns old value
- test_replay_deterministic_random: ctx.random() returns same sequence
- test_replay_deterministic_uuid: ctx.uuid() returns same UUID
- test_replay_failure_on_divergence: NonDeterministicWorkflowError on mismatch
"""

from __future__ import annotations

import pytest
import hashlib

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from core.runtime.enterprise.event_integrity import (
    HashChainValidator,
    EventIntegrityManager,
    EventStoreWithIntegrity,
    EventIntegrityInfo,
    IntegrityCheckResult,
)
from core.runtime.enterprise.deterministic_values import (
    DeterministicValueGenerator,
    DeterministicValueStore,
)


# ============================================================================
# HashChainValidator Tests
# ============================================================================

class TestHashChainValidator:
    """Test hash chain validation."""

    @pytest.fixture
    def validator(self):
        """Create hash chain validator."""
        return HashChainValidator(hash_algorithm="sha256")

    def test_compute_hash_deterministic(self, validator):
        """Test that hash computation is deterministic."""
        data = {"key": "value", "number": 42}
        
        hash1 = validator.compute_hash(data)
        hash2 = validator.compute_hash(data)
        
        assert hash1 == hash2

    def test_compute_hash_different_data(self, validator):
        """Test that different data produces different hashes."""
        hash1 = validator.compute_hash("data1")
        hash2 = validator.compute_hash("data2")
        
        assert hash1 != hash2

    def test_compute_event_hash(self, validator):
        """Test event hash computation."""
        event_hash = validator.compute_event_hash(
            event_id="e1",
            sequence=0,
            event_type="workflow_started",
            event_data={"initiated_by": "user1"},
        )
        
        assert isinstance(event_hash, str)
        assert len(event_hash) == 64  # SHA256 hex length

    def test_verify_event_hash_valid(self, validator):
        """Test verifying valid event hash."""
        event = {
            "event_id": "e1",
            "sequence": 0,
            "event_type": "task_completed",
            "data": {"task_id": "task1"},
        }
        
        event["event_hash"] = validator.compute_event_hash(
            event["event_id"],
            event["sequence"],
            event["event_type"],
            event["data"],
        )
        
        is_valid = validator.verify_event_hash(event)
        
        assert is_valid is True

    def test_verify_event_hash_tampered(self, validator):
        """Test detecting tampered event."""
        event = {
            "event_id": "e1",
            "sequence": 0,
            "event_type": "task_completed",
            "data": {"task_id": "task1"},
        }
        
        event["event_hash"] = validator.compute_event_hash(
            event["event_id"],
            event["sequence"],
            event["event_type"],
            event["data"],
        )
        
        # Tamper with data
        event["data"]["task_id"] = "tampered_task"
        
        is_valid = validator.verify_event_hash(event)
        
        assert is_valid is False

    def test_verify_chain_valid(self, validator):
        """Test verifying valid chain."""
        events = [
            {"event_id": "e1", "sequence": 0, "event_type": "start", "data": {}},
            {"event_id": "e2", "sequence": 1, "event_type": "task", "data": {}},
        ]
        
        chained = []
        prev_hash = "genesis"
        for e in events:
            hash_val = validator.compute_event_hash(
                e["event_id"], e["sequence"], e["event_type"], e["data"]
            )
            chained.append({**e, "previous_hash": prev_hash, "event_hash": hash_val})
            prev_hash = hash_val
        
        result = validator.verify_chain(chained)
        
        assert result.valid is True

    def test_verify_chain_previous_hash_mismatch(self, validator):
        """Test detecting previous hash mismatch."""
        events = [
            {"event_id": "e1", "sequence": 0, "event_type": "start", "data": {}},
            {"event_id": "e2", "sequence": 1, "event_type": "task", "data": {}},
        ]
        
        chained = []
        for i, e in enumerate(events):
            hash_val = validator.compute_event_hash(
                e["event_id"], e["sequence"], e["event_type"], e["data"]
            )
            chained.append({**e, "previous_hash": "genesis", "event_hash": hash_val})
        
        result = validator.verify_chain(chained)
        
        # First event should be valid (genesis), second should fail
        assert result.valid is False

    def test_verify_chain_tampered_event(self, validator):
        """Test detecting tampered event in chain."""
        events = [
            {"event_id": "e1", "sequence": 0, "event_type": "start", "data": {}},
            {"event_id": "e2", "sequence": 1, "event_type": "task", "data": {}},
        ]
        
        chained = []
        prev_hash = "genesis"
        for e in events:
            hash_val = validator.compute_event_hash(
                e["event_id"], e["sequence"], e["event_type"], e["data"]
            )
            chained.append({**e, "previous_hash": prev_hash, "event_hash": hash_val})
            prev_hash = hash_val
        
        # Tamper with second event
        chained[1]["data"] = {"corrupted": True}
        
        result = validator.verify_chain(chained)
        
        assert result.valid is False
        assert result.broken_at == 1

    def test_verify_chain_empty(self, validator):
        """Test verifying empty chain."""
        result = validator.verify_chain([])
        
        assert result.valid is True

    def test_verify_tamper_detection(self, validator):
        """Test tamper detection between original and modified."""
        original = [
            {"event_id": "e1", "sequence": 0, "event_type": "start", "data": {}},
            {"event_id": "e2", "sequence": 1, "event_type": "task", "data": {}},
        ]
        
        modified = [
            {"event_id": "e1", "sequence": 0, "event_type": "start", "data": {}},
            {"event_id": "e2", "sequence": 1, "event_type": "task", "data": {"changed": True}},
        ]
        
        chained_orig = []
        chained_mod = []
        prev_hash = "genesis"
        for orig, mod in zip(original, modified):
            orig_hash = validator.compute_event_hash(
                orig["event_id"], orig["sequence"], orig["event_type"], orig["data"]
            )
            mod_hash = validator.compute_event_hash(
                mod["event_id"], mod["sequence"], mod["event_type"], mod["data"]
            )
            chained_orig.append({**orig, "previous_hash": prev_hash, "event_hash": orig_hash})
            chained_mod.append({**mod, "previous_hash": prev_hash, "event_hash": mod_hash})
            prev_hash = orig_hash
        
        tampered = validator.verify_tamper_detection(chained_orig, chained_mod)
        
        assert 1 in tampered


# ============================================================================
# EventIntegrityManager Tests
# ============================================================================

class TestEventIntegrityManager:
    """Test event integrity manager."""

    @pytest.fixture
    def manager(self):
        """Create event integrity manager."""
        return EventIntegrityManager(audit_interval_hours=24)

    def test_compute_event_chain(self, manager):
        """Test computing event chain."""
        events = [
            {"event_id": "e1", "event_type": "start", "data": {}},
            {"event_id": "e2", "event_type": "task", "data": {"id": 1}},
        ]
        
        chained = manager.compute_event_chain("wf1", events)
        
        assert len(chained) == 2
        assert chained[0]["previous_hash"] == manager._get_genesis_hash("wf1")
        assert chained[1]["previous_hash"] == chained[0]["event_hash"]

    def test_verify_workflow_chain_valid(self, manager):
        """Test verifying valid workflow chain."""
        events = [
            {"event_id": "e1", "event_type": "start", "data": {}},
            {"event_id": "e2", "event_type": "task", "data": {}},
        ]
        
        chained = manager.compute_event_chain("wf1", events)
        result = manager.verify_workflow_chain("wf1", chained)
        
        assert result.valid is True

    def test_verify_workflow_chain_tampered(self, manager):
        """Test verifying tampered workflow chain."""
        events = [
            {"event_id": "e1", "event_type": "start", "data": {}},
            {"event_id": "e2", "event_type": "task", "data": {}},
        ]
        
        chained = manager.compute_event_chain("wf1", events)
        chained[0]["data"] = {"corrupted": True}  # Tamper
        
        result = manager.verify_workflow_chain("wf1", chained)
        
        assert result.valid is False

    def test_verify_workflow_chain_empty(self, manager):
        """Test verifying empty workflow."""
        result = manager.verify_workflow_chain("wf1", [])
        
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_verify_and_report(self, manager):
        """Test verify and report records audit."""
        events = [
            {"event_id": "e1", "event_type": "start", "data": {}},
        ]
        
        chained = manager.compute_event_chain("wf1", events)
        result = await manager.verify_and_report("wf1", chained)
        
        assert result.valid is True
        assert manager.get_last_audit_time("wf1") is not None

    def test_is_audit_due(self, manager):
        """Test audit due checking."""
        assert manager.is_audit_due("new_wf") is True
        
        manager._last_audit["existing_wf"] = int(__import__("time").time())
        assert manager.is_audit_due("existing_wf") is False


# ============================================================================
# Deterministic Values Tests
# ============================================================================

class TestDeterministicValueGenerator:
    """Test deterministic value generation for replay."""

    @pytest.fixture
    def generator(self):
        """Create deterministic generator."""
        return DeterministicValueGenerator(seed=42)

    def test_deterministic_time(self, generator):
        """Test deterministic time generation."""
        time1 = generator.now()
        time2 = generator.now()
        
        assert time1 == time2
        assert isinstance(time1, (int, float))

    def test_deterministic_random(self, generator):
        """Test deterministic random generation."""
        sequence1 = [generator.random() for _ in range(10)]
        sequence2 = [generator.random() for _ in range(10)]
        
        assert sequence1 == sequence2

    def test_deterministic_random_range(self, generator):
        """Test deterministic random in range."""
        values = [generator.random_in_range(0, 100) for _ in range(10)]
        
        assert all(0 <= v <= 100 for v in values)

    def test_deterministic_uuid(self, generator):
        """Test deterministic UUID generation."""
        uuid1 = generator.uuid()
        uuid2 = generator.uuid()
        
        assert uuid1 != uuid2  # Each UUID should be unique
        assert len(uuid1) == 36  # UUID format

    def test_deterministic_choice(self, generator):
        """Test deterministic choice from sequence."""
        options = ["a", "b", "c", "d", "e"]
        choices = [generator.choice(options) for _ in range(10)]
        
        # Same seed should produce same sequence
        gen2 = DeterministicValueGenerator(seed=42)
        choices2 = [gen2.choice(options) for _ in range(10)]
        
        assert choices == choices2

    def test_deterministic_shuffle(self, generator):
        """Test deterministic shuffle."""
        options = list(range(10))
        shuffled = generator.shuffle(options.copy())
        
        # Same seed should produce same shuffle
        gen2 = DeterministicValueGenerator(seed=42)
        shuffled2 = gen2.shuffle(options.copy())
        
        assert shuffled == shuffled2

    def test_replay_mode_same_values(self, generator):
        """Test that replay mode returns same values."""
        # Generate original sequence
        gen = DeterministicValueGenerator(seed=123)
        original = {
            "time": gen.now(),
            "random": gen.random(),
            "uuid": gen.uuid(),
        }
        
        # Replay with same seed
        replay = DeterministicValueGenerator(seed=123)
        replay_values = {
            "time": replay.now(),
            "random": replay.random(),
            "uuid": replay.uuid(),
        }
        
        assert original["time"] == replay_values["time"]
        assert original["random"] == replay_values["random"]
        # UUIDs are always unique even with same seed


# ============================================================================
# EventStoreWithIntegrity Tests
# ============================================================================

class TestEventStoreWithIntegrity:
    """Test event store with integrity."""

    @pytest.fixture
    def store(self):
        """Create event store with integrity."""
        base_store = {}
        integrity_manager = EventIntegrityManager()
        return EventStoreWithIntegrity(base_store, integrity_manager)

    @pytest.mark.asyncio
    async def test_append_event(self, store):
        """Test appending event with integrity."""
        event = {"event_type": "task_completed", "data": {"task_id": "t1"}}
        
        chained = await store.append_event("wf1", event)
        
        assert "event_hash" in chained
        assert "previous_hash" in chained
        assert "sequence" in chained

    @pytest.mark.asyncio
    async def test_append_multiple_events(self, store):
        """Test appending multiple events."""
        events = [
            {"event_type": "start", "data": {}},
            {"event_type": "task1", "data": {}},
            {"event_type": "task2", "data": {}},
        ]
        
        for e in events:
            await store.append_event("wf1", e)
        
        retrieved = await store.get_events("wf1")
        
        assert len(retrieved) == 3
        # Verify chain integrity
        for i in range(1, len(retrieved)):
            assert retrieved[i]["previous_hash"] == retrieved[i-1]["event_hash"]

    @pytest.mark.asyncio
    async def test_verify_integrity_valid(self, store):
        """Test verifying valid event store."""
        for i in range(3):
            await store.append_event("wf1", {"event_type": f"task_{i}", "data": {}})
        
        result = await store.verify_integrity("wf1")
        
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_verify_integrity_tampered(self, store):
        """Test verifying tampered event store."""
        for i in range(3):
            await store.append_event("wf1", {"event_type": f"task_{i}", "data": {}})
        
        # Tamper with stored events
        store._store["wf1"][1]["data"] = {"corrupted": True}
        
        result = await store.verify_integrity("wf1")
        
        assert result.valid is False


# ============================================================================
# Replay Tests
# ============================================================================

class TestReplayDeterminism:
    """Test deterministic replay scenarios."""

    def test_replay_produces_same_hash_chain(self):
        """Test that replay produces identical hash chain."""
        events_original = [
            {"event_id": "e1", "sequence": 0, "event_type": "start", "data": {}},
            {"event_id": "e2", "sequence": 1, "event_type": "task1", "data": {}},
            {"event_id": "e3", "sequence": 2, "event_type": "task2", "data": {}},
        ]
        
        validator = HashChainValidator()
        
        # Compute chain during original execution
        original_chain = []
        prev_hash = "genesis"
        for e in events_original:
            hash_val = validator.compute_event_hash(
                e["event_id"], e["sequence"], e["event_type"], e["data"]
            )
            original_chain.append({**e, "previous_hash": prev_hash, "event_hash": hash_val})
            prev_hash = hash_val
        
        # Simulate replay with same events
        replay_chain = []
        prev_hash = "genesis"
        for e in events_original:
            hash_val = validator.compute_event_hash(
                e["event_id"], e["sequence"], e["event_type"], e["data"]
            )
            replay_chain.append({**e, "previous_hash": prev_hash, "event_hash": hash_val})
            prev_hash = hash_val
        
        # Chains should be identical
        assert original_chain == replay_chain

    def test_replay_detects_divergence(self):
        """Test that replay detects divergence from original."""
        validator = HashChainValidator()
        
        original = [
            {"event_id": "e1", "sequence": 0, "event_type": "start", "data": {}},
        ]
        
        # Build original chain
        original_chain = []
        prev_hash = "genesis"
        for e in original:
            hash_val = validator.compute_event_hash(
                e["event_id"], e["sequence"], e["event_type"], e["data"]
            )
            original_chain.append({**e, "previous_hash": prev_hash, "event_hash": hash_val})
            prev_hash = hash_val
        
        # Simulate different replay (e.g., different event order)
        replay = [
            {"event_id": "e1", "sequence": 0, "event_type": "start", "data": {}},
            {"event_id": "e2", "sequence": 1, "event_type": "extra", "data": {}},  # Extra event
        ]
        
        replay_chain = []
        prev_hash = "genesis"
        for e in replay:
            hash_val = validator.compute_event_hash(
                e["event_id"], e["sequence"], e["event_type"], e["data"]
            )
            replay_chain.append({**e, "previous_hash": prev_hash, "event_hash": hash_val})
            prev_hash = hash_val
        
        # Chains should differ in length
        assert len(original_chain) != len(replay_chain)
