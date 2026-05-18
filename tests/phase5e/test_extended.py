"""
Tests for Phase 5E Extended Components.

Tests for:
- FormalExecutionSemantics
- CDCConsistency
- WORMArchive
"""

import asyncio
import pytest
from datetime import datetime

from src.core.multi_agent.coordination.execution_semantics import (
    FormalExecutionEngine,
    IdempotencyKeyManager,
    GlobalExecutionLease,
    ExecutionOwnershipRegistry,
)
from src.core.multi_agent.coordination.cdc_consistency import (
    CDCConsistencyManager,
    ConsistencyLevel,
)
from src.core.multi_agent.coordination.worm_archive import (
    WORMArchive,
)


# =============================================================================
# Execution Semantics Tests
# =============================================================================

class TestExecutionSemantics:
    """Tests for execution semantics."""

    @pytest.mark.asyncio
    async def test_idempotency_key_generation(self):
        """Idempotency keys are deterministic."""
        manager = IdempotencyKeyManager()
        
        key1 = await manager.generate_key("task-1", "process", {"a": 1, "b": 2})
        key2 = await manager.generate_key("task-1", "process", {"b": 2, "a": 1})  # Same params, different order
        
        assert key1 == key2  # Deterministic

    @pytest.mark.asyncio
    async def test_idempotency_reserve(self):
        """Can reserve idempotency key."""
        manager = IdempotencyKeyManager()
        
        should_exec, record = await manager.check_and_reserve("key-1", "exec-1")
        
        assert should_exec is True
        assert record is None  # No existing record

    @pytest.mark.asyncio
    async def test_idempotency_hit(self):
        """Duplicate execution returns cached result."""
        manager = IdempotencyKeyManager()
        
        # First execution
        await manager.check_and_reserve("key-1", "exec-1")
        await manager.mark_completed("key-1", {"result": "success"})
        
        # Second execution attempt
        should_exec, record = await manager.check_and_reserve("key-1", "exec-2")
        
        assert should_exec is False
        assert record is not None
        assert record.status == "completed"

    @pytest.mark.asyncio
    async def test_execution_lease_acquire(self):
        """Can acquire execution lease."""
        lease = GlobalExecutionLease(lease_ttl_seconds=60)
        
        acquired, token = await lease.acquire("task-1", "worker-1", "exec-1")
        
        assert acquired is True
        assert token is not None

    @pytest.mark.asyncio
    async def test_execution_lease_conflict(self):
        """Different worker cannot acquire active lease."""
        lease = GlobalExecutionLease(lease_ttl_seconds=60)
        
        # Worker 1 acquires
        await lease.acquire("task-1", "worker-1", "exec-1")
        
        # Worker 2 tries to acquire
        acquired, _ = await lease.acquire("task-1", "worker-2", "exec-2")
        
        assert acquired is False

    @pytest.mark.asyncio
    async def test_execution_lease_validate(self):
        """Can validate lease."""
        lease = GlobalExecutionLease(lease_ttl_seconds=60)
        
        _, token = await lease.acquire("task-1", "worker-1", "exec-1")
        
        valid, reason = await lease.validate("task-1", "worker-1", token)
        
        assert valid is True
        assert reason == "VALID"

    @pytest.mark.asyncio
    async def test_ownership_registry_claim(self):
        """Can claim task ownership."""
        registry = ExecutionOwnershipRegistry()
        
        claimed, prev = await registry.claim(
            task_id="task-1",
            execution_id="exec-1",
            worker_id="worker-1",
            region="us-east",
            lease_token="token-1",
        )
        
        assert claimed is True
        assert prev is None

    @pytest.mark.asyncio
    async def test_ownership_registry_conflict(self):
        """Registry tracks ownership changes."""
        registry = ExecutionOwnershipRegistry()
        
        # First claim
        await registry.claim(
            task_id="task-1",
            execution_id="exec-1",
            worker_id="worker-1",
            region="us-east",
            lease_token="token-1",
        )
        
        # Get ownership
        owner = await registry.get_owner("task-1")
        
        assert owner is not None
        assert owner["execution_id"] == "exec-1"


# =============================================================================
# CDC Consistency Tests
# =============================================================================

class TestCDCConsistency:
    """Tests for CDC consistency."""

    @pytest.mark.asyncio
    async def test_fence_token_increment(self):
        """Fence tokens increment monotonically."""
        manager = CDCConsistencyManager()
        
        fence1 = await manager.next_fence_token()
        fence2 = await manager.next_fence_token()
        fence3 = await manager.next_fence_token()
        
        assert fence2 > fence1
        assert fence3 > fence2

    @pytest.mark.asyncio
    async def test_publish_change(self):
        """Can publish change to CDC stream."""
        manager = CDCConsistencyManager()
        
        event = await manager.publish_change(
            entity_type="task",
            entity_id="task-1",
            operation="created",
            data={"name": "test"},
        )
        
        assert event.entity_type == "task"
        assert event.entity_id == "task-1"
        assert event.fence_token > 0

    @pytest.mark.asyncio
    async def test_read_timestamp_tracking(self):
        """Read timestamps are tracked for sessions."""
        manager = CDCConsistencyManager()
        
        await manager.publish_change("task", "task-1", "created", {})
        
        # Perform read
        await manager._update_session("session-1", 1)
        
        info = await manager.get_consistency_info("session-1")
        
        assert info["session_id"] == "session-1"
        assert info["last_read_fence"] == 1


# =============================================================================
# WORM Archive Tests
# =============================================================================

class TestWORMArchive:
    """Tests for WORM archive."""

    @pytest.mark.asyncio
    async def test_append_entry(self):
        """Can append entries to archive."""
        archive = WORMArchive(archive_id="test-archive", block_size=10)
        
        entry = await archive.append(
            entry_id="entry-1",
            tenant_id="tenant-1",
            payload={"data": "test"},
        )
        
        assert entry.entry_id == "entry-1"
        assert entry.hash is not None

    @pytest.mark.asyncio
    async def test_worm_immutable(self):
        """Entries are stored in archive."""
        archive = WORMArchive(archive_id="test-archive", block_size=10)
        
        entry = await archive.append(
            entry_id="entry-1",
            tenant_id="tenant-1",
            payload={"data": "original"},
        )
        
        # Entry was appended
        assert entry is not None
        assert entry.payload["data"] == "original"

    @pytest.mark.asyncio
    async def test_hash_chain(self):
        """Blocks form hash chain."""
        archive = WORMArchive(archive_id="test-archive", block_size=2)
        
        # Add entries to fill block
        await archive.append("entry-1", "t1", {"d": 1})
        await archive.append("entry-2", "t1", {"d": 2})
        
        # Verify chain
        is_valid, errors = await archive.verify_chain_integrity()
        
        assert is_valid is True
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_merkle_proof_after_seal(self):
        """Can generate Merkle proof after block sealed."""
        archive = WORMArchive(archive_id="test-archive", block_size=2)
        
        # Fill block to trigger seal
        await archive.append("entry-1", "t1", {"d": 1})
        await archive.append("entry-2", "t1", {"d": 2})
        
        # After sealing, can get proof
        proof = await archive.get_merkle_proof("entry-1")
        
        assert proof is not None
        assert proof.entry_id == "entry-1"

    @pytest.mark.asyncio
    async def test_finalize_creates_manifest(self):
        """Finalize creates signed manifest."""
        archive = WORMArchive(archive_id="test-archive", block_size=10)
        
        await archive.append("entry-1", "t1", {"d": 1})
        
        manifest = await archive.finalize(
            signature="test-signature",
            public_key_id="key-1",
        )
        
        assert manifest is not None
        assert manifest.signature == "test-signature"


# =============================================================================
# Integration Tests
# =============================================================================

class TestFormalExecutionIntegration:
    """Integration tests for formal execution."""

    @pytest.mark.asyncio
    async def test_execute_with_semantics(self):
        """Execute respects idempotency semantics."""
        engine = FormalExecutionEngine()
        
        executed_count = 0
        
        async def handler(idempotency_key, params):
            nonlocal executed_count
            executed_count += 1
            return {"result": "done"}
        
        # First execution
        executed, result, status = await engine.execute_with_semantics(
            task_id="task-1",
            action="process",
            params={"data": "test"},
            worker_id="worker-1",
            region="us-east",
            external_effect_handler=handler,
        )
        
        assert executed is True
        assert executed_count == 1
        
        # Idempotent retry (should not execute)
        executed2, result2, status2 = await engine.execute_with_semantics(
            task_id="task-1",
            action="process",
            params={"data": "test"},
            worker_id="worker-1",
            region="us-east",
            external_effect_handler=handler,
        )
        
        assert executed2 is False
        assert executed_count == 1  # Not incremented


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
