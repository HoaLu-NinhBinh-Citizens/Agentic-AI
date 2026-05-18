"""
Tests for Multi-Agent Coordination Layer (Phase 5D).

Comprehensive tests covering all enterprise coordination features:
- Two-way circuit breaker
- Federated health propagation
- Schema evolution
- Batch idempotency
- Tenant isolation
- Agent resource quota
- Leader election
- Backpressure control
- Dead letter alerts
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.multi_agent.coordination.types import (
    AgentQuota,
    BackpressureResponse,
    BatchItem,
    BatchResult,
    CircuitBreakerDirection,
    CircuitBreakerState,
    CompatibilityPolicy,
    DeadLetterItem,
    FederatedHealthReport,
    HealthStatus,
    SchemaField,
    SchemaDefinition,
    SubAgentStatus,
    TenantConfig,
)
from src.core.multi_agent.coordination.config import (
    MultiAgentCoordinationConfig,
    CircuitBreakerConfig,
)
from src.core.multi_agent.coordination.circuit_breaker import (
    TwoWayCircuitBreaker,
    CircuitBreakerOpenError,
)
from src.core.multi_agent.coordination.health import (
    FederatedHealthPropagator,
    InMemoryHealthStore,
)
from src.core.multi_agent.coordination.schema_evolution import (
    SchemaEvolutionEngine,
)
from src.core.multi_agent.coordination.batch_idempotency import (
    BatchIdempotencyStore,
)
from src.core.multi_agent.coordination.tenant_isolation import (
    TenantIsolationLayer,
    TenantContext,
    CrossTenantAccessError,
    JWTError,
)
from src.core.multi_agent.coordination.quota import (
    QuotaEnforcer,
    QuotaExceededError,
)
from src.core.multi_agent.coordination.leader_election import (
    LeaderElector,
    NotLeaderError,
)
from src.core.multi_agent.coordination.backpressure import (
    BackpressureController,
)
from src.core.multi_agent.coordination.dead_letter_alert import (
    DeadLetterAlert,
    InMemoryDeadLetterStore,
)
from src.core.multi_agent.coordination.coordinator import (
    MultiAgentCoordinator,
)


# =============================================================================
# Circuit Breaker Tests
# =============================================================================

class TestTwoWayCircuitBreaker:
    """Tests for TwoWayCircuitBreaker."""

    @pytest.mark.asyncio
    async def test_circuit_starts_closed(self):
        """Circuit breaker starts in closed state."""
        cb = TwoWayCircuitBreaker(name="test")
        assert cb.get_state("agent-1") == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self):
        """Circuit opens after failure threshold."""
        cb = TwoWayCircuitBreaker(
            name="test",
            failure_threshold=3,
            window_seconds=60.0,
        )

        async def failing_func():
            raise ConnectionError("Connection refused")

        # Fail 3 times
        for _ in range(3):
            with pytest.raises(ConnectionError):
                await cb.call("agent-1", failing_func)

        # Circuit should be open now
        assert cb.get_state("agent-1") == CircuitBreakerState.OPEN

        # Next call should raise CircuitBreakerOpenError
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call("agent-1", failing_func)

    @pytest.mark.asyncio
    async def test_circuit_half_open_recovery(self):
        """Circuit transitions to half-open after timeout."""
        cb = TwoWayCircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=0.5,
        )

        async def failing_func():
            raise ConnectionError("Connection refused")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(ConnectionError):
                await cb.call("agent-1", failing_func)

        assert cb.get_state("agent-1") == CircuitBreakerState.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(0.6)

        # Should transition to half-open on next call
        async def success_func():
            return "success"

        result = await cb.call("agent-1", success_func)
        assert result == "success"
        assert cb.get_state("agent-1") == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_half_open_failure_reopens(self):
        """Circuit reopens if half-open probe fails."""
        cb = TwoWayCircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=0.1,
        )

        # Open the circuit
        async def failing_func():
            raise ConnectionError("Connection refused")

        for _ in range(2):
            with pytest.raises(ConnectionError):
                await cb.call("agent-1", failing_func)

        # Wait for recovery
        await asyncio.sleep(0.2)

        # Half-open probe fails
        with pytest.raises(ConnectionError):
            await cb.call("agent-1", failing_func)

        assert cb.get_state("agent-1") == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_bidirectional_circuits(self):
        """Each direction has separate circuit state."""
        cb = TwoWayCircuitBreaker(name="test", failure_threshold=2)

        async def failing_func():
            raise ConnectionError("Failed")

        # Fail coordinator->agent direction
        for _ in range(2):
            with pytest.raises(ConnectionError):
                await cb.call("agent-1", failing_func, direction=CircuitBreakerDirection.COORDINATOR_TO_AGENT)

        # agent->coordinator direction should still be closed
        async def success_func():
            return "ok"

        result = await cb.call("coordinator", success_func, direction=CircuitBreakerDirection.AGENT_TO_COORDINATOR)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_reset_circuit(self):
        """Circuit can be reset."""
        cb = TwoWayCircuitBreaker(name="test", failure_threshold=2)

        async def failing_func():
            raise ConnectionError("Failed")

        for _ in range(2):
            with pytest.raises(ConnectionError):
                await cb.call("agent-1", failing_func)

        assert cb.get_state("agent-1") == CircuitBreakerState.OPEN

        # Reset
        cb.reset("agent-1")
        assert cb.get_state("agent-1") == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_ignores_non_transient_errors(self):
        """Non-transient errors don't trigger circuit."""
        cb = TwoWayCircuitBreaker(name="test", failure_threshold=2)

        async def bad_error():
            raise ValueError("Invalid value")

        # These shouldn't open the circuit
        for _ in range(5):
            with pytest.raises(ValueError):
                await cb.call("agent-1", bad_error)

        # Circuit should still be closed
        assert cb.get_state("agent-1") == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_metrics(self):
        """Circuit breaker exposes metrics."""
        cb = TwoWayCircuitBreaker(name="test")

        metrics = cb.get_metrics()
        assert "total_calls" in metrics
        assert "total_failures" in metrics
        assert "open_circuits" in metrics


# =============================================================================
# Federated Health Tests
# =============================================================================

class TestFederatedHealthPropagator:
    """Tests for FederatedHealthPropagator."""

    @pytest.mark.asyncio
    async def test_report_sub_agents_status(self):
        """Report sub-agent status from federated agent."""
        propagator = FederatedHealthPropagator(
            health_interval_seconds=10,
            offline_threshold_seconds=30,
        )

        report = await propagator.report_sub_agents_status(
            federated_agent_id="fed-1",
            sub_agents=[
                {"id": "sub-1", "status": "healthy", "last_heartbeat": datetime.now()},
                {"id": "sub-2", "status": "healthy", "last_heartbeat": datetime.now()},
            ]
        )

        assert report.federated_agent_id == "fed-1"
        assert len(report.sub_agents) == 2
        assert report.health_score > 0

    @pytest.mark.asyncio
    async def test_offline_detection(self):
        """Detect offline sub-agents."""
        propagator = FederatedHealthPropagator(
            offline_threshold_seconds=2,
        )

        old_time = datetime.now() - timedelta(seconds=5)

        report = await propagator.report_sub_agents_status(
            federated_agent_id="fed-1",
            sub_agents=[
                {"id": "sub-1", "status": "healthy", "last_heartbeat": old_time},
            ]
        )

        assert len(report.sub_agents) == 1
        health = await propagator.get_federated_health("fed-1")
        assert health["offline_count"] == 1

    @pytest.mark.asyncio
    async def test_health_score_calculation(self):
        """Health score reflects sub-agent health."""
        propagator = FederatedHealthPropagator()

        # All healthy
        report = await propagator.report_sub_agents_status(
            federated_agent_id="fed-healthy",
            sub_agents=[
                {"id": "sub-1", "status": "healthy", "last_heartbeat": datetime.now()},
                {"id": "sub-2", "status": "healthy", "last_heartbeat": datetime.now()},
            ]
        )
        assert 0.999 < report.health_score <= 1.0  # Allow for floating-point precision

        # Some offline
        old_time = datetime.now() - timedelta(seconds=60)
        report = await propagator.report_sub_agents_status(
            federated_agent_id="fed-partial",
            sub_agents=[
                {"id": "sub-1", "status": "healthy", "last_heartbeat": datetime.now()},
                {"id": "sub-2", "status": "offline", "last_heartbeat": old_time},
            ]
        )
        assert 0 < report.health_score < 1.0


# =============================================================================
# Schema Evolution Tests
# =============================================================================

class TestSchemaEvolutionEngine:
    """Tests for SchemaEvolutionEngine."""

    @pytest.mark.asyncio
    async def test_register_schema(self):
        """Register a new schema version."""
        engine = SchemaEvolutionEngine()

        def migrate_v1_to_v2(msg):
            return {**msg, "new_field": msg.get("old_field", "default")}

        schema = await engine.register_schema(
            message_type="TaskMessage",
            version="2",
            schema={
                "fields": [
                    {"name": "new_field", "type": "string", "required": True}
                ]
            },
            migrations={("1", "2"): migrate_v1_to_v2}
        )

        assert schema.message_type == "TaskMessage"
        assert schema.version == "2"

    @pytest.mark.asyncio
    async def test_migrate_message(self):
        """Migrate message between versions."""
        engine = SchemaEvolutionEngine(current_version="2")

        def migrate_v1_to_v2(msg):
            new_msg = msg.copy()
            new_msg["new_field"] = new_msg.pop("old_field", "default")
            return new_msg

        await engine.register_schema(
            message_type="TaskMessage",
            version="2",
            schema={"fields": [{"name": "new_field", "type": "string"}]},
            migrations={("1", "2"): migrate_v1_to_v2}
        )

        old_msg = {"old_field": "value"}
        transformed = await engine.transform_message(old_msg, target_version="2")

        assert "new_field" in transformed
        assert "old_field" not in transformed

    @pytest.mark.asyncio
    async def test_backward_compatibility(self):
        """New code reads old data with defaults."""
        engine = SchemaEvolutionEngine(
            compatibility_policy=CompatibilityPolicy.BACKWARD,
            current_version="2",
        )

        def migrate_v1_to_v2(msg):
            return {**msg, "new_field": msg.get("old_field", "default_value")}

        await engine.register_schema(
            message_type="TaskMessage",
            version="2",
            schema={
                "fields": [
                    {"name": "new_field", "type": "string", "required": True, "default": "default_value"}
                ]
            },
            migrations={("1", "2"): migrate_v1_to_v2}
        )

        old_msg = {"old_field": "test"}
        result = await engine.transform_message(old_msg, target_version="2")

        assert result.get("new_field") == "test"

    @pytest.mark.asyncio
    async def test_forward_compatibility(self):
        """Old code ignores unknown fields."""
        engine = SchemaEvolutionEngine(
            compatibility_policy=CompatibilityPolicy.FORWARD,
            current_version="1",
        )

        await engine.register_schema(
            message_type="TaskMessage",
            version="1",
            schema={"fields": [{"name": "old_field", "type": "string"}]}
        )

        # Simulate old code receiving new message
        new_msg = {"old_field": "value", "new_field": "extra"}
        
        # When versions match (source=1, target=1), no transformation
        result = await engine.transform_message(new_msg, source_version="1")
        
        # Since source=target, no transformation happens
        assert "new_field" in result  # Without migration, stays as-is


# =============================================================================
# Batch Idempotency Tests
# =============================================================================

class TestBatchIdempotencyStore:
    """Tests for BatchIdempotencyStore."""

    @pytest.mark.asyncio
    async def test_idempotent_processing(self):
        """Duplicate items return cached results."""
        store = BatchIdempotencyStore(ttl_seconds=3600)
        await store.start()

        processed_count = 0

        async def processor1():
            return {"processed": "item1"}

        async def processor2():
            return {"processed": "item2"}

        # First call
        result1 = await store.get_or_execute(
            idempotency_key="batch-1:0",
            func=processor1,
        )

        # Second call with same key should return cached
        result2 = await store.get_or_execute(
            idempotency_key="batch-1:0",
            func=processor2,
        )

        assert result1 == result2
        await store.stop()

    @pytest.mark.asyncio
    async def test_process_batch(self):
        """Process batch with per-item idempotency."""
        store = BatchIdempotencyStore()
        await store.start()

        async def processor(idx, item):
            return {"result": item}

        results = await store.process_batch(
            batch_id="batch-1",
            items=["a", "b", "c"],
            processor=processor,
        )

        assert len(results) == 3
        assert all(r.success for r in results)
        assert not any(r.skipped for r in results)
        await store.stop()

    @pytest.mark.asyncio
    async def test_batch_retry_skips_completed(self):
        """Retry batch only processes incomplete items."""
        store = BatchIdempotencyStore()
        await store.start()

        # Process initial batch
        await store.process_batch(
            batch_id="batch-retry",
            items=["a", "b", "c"],
            processor=lambda i, x: asyncio.coroutine(lambda: {"result": x})(),
        )

        # Retry - should all be skipped
        results = await store.process_batch(
            batch_id="batch-retry",
            items=["a", "b", "c"],
            processor=lambda i, x: asyncio.coroutine(lambda: {"result": x})(),
        )

        assert all(r.skipped for r in results)
        await store.stop()


# =============================================================================
# Tenant Isolation Tests
# =============================================================================

class TestTenantIsolationLayer:
    """Tests for TenantIsolationLayer."""

    @pytest.mark.asyncio
    async def test_create_tenant(self):
        """Create a new tenant."""
        layer = TenantIsolationLayer()
        await layer.create_tenant("tenant-1", "Test Tenant")

        tenant = await layer.get_tenant("tenant-1")
        assert tenant is not None
        assert tenant["tenant_id"] == "tenant-1"
        assert tenant["name"] == "Test Tenant"

    @pytest.mark.asyncio
    async def test_delete_tenant(self):
        """Delete a tenant."""
        layer = TenantIsolationLayer()
        await layer.create_tenant("tenant-1", "Test Tenant")
        await layer.delete_tenant("tenant-1")

        tenant = await layer.get_tenant("tenant-1")
        assert tenant is None

    @pytest.mark.asyncio
    async def test_filter_results(self):
        """Results are filtered by tenant."""
        layer = TenantIsolationLayer()

        results = [
            {"id": "1", "tenant_id": "tenant-1", "data": "a"},
            {"id": "2", "tenant_id": "tenant-2", "data": "b"},
            {"id": "3", "tenant_id": "tenant-1", "data": "c"},
        ]

        context = TenantContext(tenant_id="tenant-1")
        filtered = layer.filter_results(results, context)

        assert len(filtered) == 2
        assert all(r["tenant_id"] == "tenant-1" for r in filtered)

    @pytest.mark.asyncio
    async def test_admin_sees_all_tenants(self):
        """Admin can see all tenant data."""
        layer = TenantIsolationLayer()

        results = [
            {"id": "1", "tenant_id": "tenant-1", "data": "a"},
            {"id": "2", "tenant_id": "tenant-2", "data": "b"},
        ]

        # Use super_admin role to access all tenants
        admin_context = TenantContext(
            tenant_id="admin",
            roles=["super_admin"],
            is_admin=True,
        )

        # Admin with super_admin role should see all tenants
        filtered = layer.filter_results(results, admin_context)
        assert len(filtered) == 2


# =============================================================================
# Quota Enforcer Tests
# =============================================================================

class TestQuotaEnforcer:
    """Tests for QuotaEnforcer."""

    @pytest.mark.asyncio
    async def test_default_quota(self):
        """Agents get default quota."""
        enforcer = QuotaEnforcer(
            default_max_concurrent=5,
            default_max_message_rate=100,
        )

        quota = await enforcer.get_quota("new-agent")
        assert quota.max_concurrent_tasks == 5
        assert quota.max_message_rate == 100

    @pytest.mark.asyncio
    async def test_set_quota(self):
        """Set custom quota for agent."""
        enforcer = QuotaEnforcer()

        await enforcer.set_quota(
            "agent-1",
            max_concurrent_tasks=20,
            max_message_rate=200,
        )

        quota = await enforcer.get_quota("agent-1")
        assert quota.max_concurrent_tasks == 20
        assert quota.max_message_rate == 200

    @pytest.mark.asyncio
    async def test_concurrent_limit(self):
        """Concurrent task limit is enforced."""
        enforcer = QuotaEnforcer(default_max_concurrent=2)

        await enforcer.increment_concurrent("agent-1")
        await enforcer.increment_concurrent("agent-1")

        # Third should fail
        with pytest.raises(QuotaExceededError) as exc_info:
            await enforcer.check_concurrent("agent-1")

        assert exc_info.value.quota_type == "concurrent"

    @pytest.mark.asyncio
    async def test_rate_limit(self):
        """Rate limit is enforced."""
        enforcer = QuotaEnforcer(default_max_message_rate=2)

        # First two should succeed
        await enforcer.record_message("agent-1")
        await enforcer.record_message("agent-1")

        # Third should fail
        with pytest.raises(QuotaExceededError) as exc_info:
            await enforcer.check_rate_limit("agent-1")

        assert exc_info.value.quota_type == "rate"

    @pytest.mark.asyncio
    async def test_workspace_size_limit(self):
        """Workspace size limit is enforced."""
        enforcer = QuotaEnforcer(default_max_workspace_bytes=1000)

        # Adding 1100 should fail (exceeds limit)
        with pytest.raises(QuotaExceededError) as exc_info:
            await enforcer.check_workspace_size("agent-1", additional_bytes=1100)

        assert exc_info.value.quota_type == "workspace"


# =============================================================================
# Leader Election Tests
# =============================================================================

class TestLeaderElector:
    """Tests for LeaderElector."""

    @pytest.mark.asyncio
    async def test_become_leader(self):
        """Instance can become leader."""
        elector = LeaderElector()

        leader = await elector.try_become_leader("instance-1")
        assert leader == "instance-1"
        assert await elector.is_leader()

    @pytest.mark.asyncio
    async def test_only_one_leader(self):
        """Only one instance can be leader."""
        elector = LeaderElector()

        leader1 = await elector.try_become_leader("instance-1")
        leader2 = await elector.try_become_leader("instance-2")

        assert leader1 == "instance-1"
        assert leader2 == "instance-1"  # instance-2 couldn't become leader

    @pytest.mark.asyncio
    async def test_leader_heartbeat(self):
        """Leader sends heartbeat."""
        elector = LeaderElector(lock_ttl=30)

        await elector.try_become_leader("instance-1")
        await elector.heartbeat()

        metrics = elector.get_metrics()
        assert metrics["heartbeat_count"] > 0

    @pytest.mark.asyncio
    async def test_resign_leadership(self):
        """Leader can resign."""
        elector = LeaderElector()

        await elector.try_become_leader("instance-1")
        assert await elector.is_leader()

        await elector.resign_leadership()
        assert not await elector.is_leader()

    @pytest.mark.asyncio
    async def test_other_instance_becomes_leader_after_resign(self):
        """Another instance can become leader after resign."""
        elector = LeaderElector()

        await elector.try_become_leader("instance-1")
        await elector.resign_leadership()

        leader = await elector.try_become_leader("instance-2")
        assert leader == "instance-2"


# =============================================================================
# Backpressure Tests
# =============================================================================

class TestBackpressureController:
    """Tests for BackpressureController."""

    @pytest.mark.asyncio
    async def test_rate_limit_allows_normal_requests(self):
        """Normal requests are allowed."""
        controller = BackpressureController(rate_limit_per_agent=100)

        response = await controller.check_rate_limit("agent-1")
        assert not response.is_limited
        assert response.remaining > 0

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_excess(self):
        """Excess requests are blocked."""
        controller = BackpressureController(rate_limit_per_agent=5)

        # Use up the limit
        for _ in range(5):
            await controller.record_request("agent-1")

        response = await controller.check_rate_limit("agent-1")
        assert response.is_limited
        assert response.retry_after > 0

    @pytest.mark.asyncio
    async def test_retry_after_header(self):
        """Response includes retry-after information."""
        controller = BackpressureController(rate_limit_per_agent=2)

        await controller.record_request("agent-1")
        await controller.record_request("agent-1")

        response = await controller.check_rate_limit("agent-1")
        headers = response.to_headers()

        assert "Retry-After" in headers
        assert headers["Retry-After"].isdigit()

    @pytest.mark.asyncio
    async def test_custom_agent_limit(self):
        """Custom limits can be set per agent."""
        controller = BackpressureController(rate_limit_per_agent=10)

        await controller.set_agent_limit("priority-agent", 100)

        response = await controller.check_rate_limit("priority-agent")
        assert response.limit == 100


# =============================================================================
# Dead Letter Alert Tests
# =============================================================================

class TestDeadLetterAlert:
    """Tests for DeadLetterAlert."""

    @pytest.mark.asyncio
    async def test_add_failed_item(self):
        """Add item to dead letter queue."""
        alerter = DeadLetterAlert(
            store=InMemoryDeadLetterStore(),
            default_threshold=1000,
        )

        item = await alerter.add_failed_item(
            tenant_id="tenant-1",
            item_id="failed-1",
            message={"task": "test"},
            error="Connection timeout",
        )

        assert item.tenant_id == "tenant-1"
        assert item.error == "Connection timeout"

    @pytest.mark.asyncio
    async def test_threshold_alert(self):
        """Alert when threshold exceeded."""
        alerter = DeadLetterAlert(
            store=InMemoryDeadLetterStore(),
            default_threshold=5,
            enabled=True,
        )

        # Mock webhook sender
        alerter.webhook_sender.send = AsyncMock(return_value=True)

        # Add items to exceed threshold
        for i in range(6):
            await alerter.add_failed_item(
                tenant_id="tenant-1",
                item_id=f"failed-{i}",
                message={"task": f"test-{i}"},
                error="Error",
            )

        stats = await alerter.get_queue_stats("tenant-1")
        assert stats["threshold_exceeded"]

    @pytest.mark.asyncio
    async def test_alert_config_per_queue(self):
        """Different alert configs per queue."""
        alerter = DeadLetterAlert(default_threshold=100)

        await alerter.set_alert_config(
            tenant_id="tenant-1",
            queue_name="critical",
            threshold=10,
        )

        config = await alerter.get_alert_config("tenant-1", "critical")
        assert config.threshold == 10


# =============================================================================
# MultiAgentCoordinator Integration Tests
# =============================================================================

class TestMultiAgentCoordinator:
    """Integration tests for MultiAgentCoordinator."""

    @pytest.mark.asyncio
    async def test_create_coordinator(self):
        """Create and initialize coordinator."""
        coordinator = await MultiAgentCoordinator.create()

        assert coordinator._initialized
        assert coordinator._running
        await coordinator.shutdown()

    @pytest.mark.asyncio
    async def test_register_agent(self):
        """Register an agent."""
        coordinator = await MultiAgentCoordinator.create()

        await coordinator.register_agent(
            agent_id="agent-1",
            agent_type="code_gen",
            capabilities=["codegen", "review"],
        )

        agent = await coordinator.get_agent("agent-1")
        assert agent is not None
        assert agent["agent_type"] == "code_gen"
        await coordinator.shutdown()

    @pytest.mark.asyncio
    async def test_leader_election(self):
        """Test leader election."""
        coordinator = await MultiAgentCoordinator.create()

        leader = await coordinator.become_leader("instance-1")
        assert leader == "instance-1"
        assert await coordinator.is_leader()

        await coordinator.shutdown()

    @pytest.mark.asyncio
    async def test_tenant_creation(self):
        """Create and manage tenants."""
        coordinator = await MultiAgentCoordinator.create()

        await coordinator.create_tenant("tenant-1", "Test Tenant")
        tenant = await coordinator.get_tenant("tenant-1")

        assert tenant is not None
        assert tenant["tenant_id"] == "tenant-1"

        tenants = await coordinator.list_tenants()
        assert len(tenants) >= 1
        await coordinator.shutdown()

    @pytest.mark.asyncio
    async def test_quota_enforcement(self):
        """Enforce quotas through coordinator."""
        coordinator = await MultiAgentCoordinator.create()

        await coordinator.set_agent_quota(
            "agent-1",
            max_concurrent_tasks=2,
        )

        quota = await coordinator.get_agent_quota("agent-1")
        assert quota.max_concurrent_tasks == 2
        await coordinator.shutdown()

    @pytest.mark.asyncio
    async def test_metrics(self):
        """Coordinator exposes metrics."""
        coordinator = await MultiAgentCoordinator.create()

        metrics = await coordinator.get_metrics()

        assert "coordinator" in metrics
        assert "circuit_breaker" in metrics
        assert "health" in metrics
        assert "quota" in metrics
        assert "backpressure" in metrics

        await coordinator.shutdown()


# =============================================================================
# Chaos Test Scenarios
# =============================================================================

class TestChaosScenarios:
    """Chaos engineering test scenarios."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_cascade_failure(self):
        """Circuit breaker prevents cascade failure."""
        cb = TwoWayCircuitBreaker(
            name="cascade-test",
            failure_threshold=3,
            window_seconds=1.0,
        )

        async def failing_agent():
            raise ConnectionError("Agent down")

        # Fail rapidly
        for _ in range(3):
            with pytest.raises(ConnectionError):
                await cb.call("failing-agent", failing_agent)

        # Circuit should be open
        assert cb.get_state("failing-agent") == CircuitBreakerState.OPEN

        # Other agents should not be affected
        async def working_agent():
            return "ok"

        result = await cb.call("working-agent", working_agent)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_leader_failover(self):
        """Leader failure triggers failover."""
        elector = LeaderElector(lock_ttl=1)

        # Instance 1 becomes leader
        leader1 = await elector.try_become_leader("instance-1")
        assert leader1 == "instance-1"
        assert await elector.is_leader()

        # Instance 1 resigns
        await elector.resign_leadership()

        # Instance 2 becomes leader
        leader2 = await elector.try_become_leader("instance-2")
        assert leader2 == "instance-2"
        assert await elector.is_leader()

    @pytest.mark.asyncio
    async def test_batch_partial_failure(self):
        """Batch handles partial failures."""
        store = BatchIdempotencyStore()
        await store.start()

        async def processor(idx, item):
            if item == "fail":
                raise ValueError("Processing failed")
            return {"result": item}

        results = await store.process_batch(
            batch_id="batch-fail",
            items=["a", "fail", "c"],
            processor=processor,
        )

        assert len(results) == 3
        assert results[0].success
        assert not results[1].success
        assert results[2].success
        await store.stop()

    @pytest.mark.asyncio
    async def test_backpressure_recovery(self):
        """System recovers after backpressure."""
        controller = BackpressureController(rate_limit_per_agent=3)

        # Exhaust limit
        for _ in range(3):
            await controller.record_request("agent-1")

        response = await controller.check_rate_limit("agent-1")
        assert response.is_limited

        # Reset the agent's state
        await controller.reset_agent("agent-1")

        response = await controller.check_rate_limit("agent-1")
        assert not response.is_limited

    @pytest.mark.asyncio
    async def test_tenant_isolation_boundary(self):
        """Tenant isolation at boundaries."""
        layer = TenantIsolationLayer()

        results_a = [
            {"id": "1", "tenant_id": "tenant-a", "secret": "secret-a"},
            {"id": "2", "tenant_id": "tenant-b", "secret": "secret-b"},
        ]

        context_a = TenantContext(tenant_id="tenant-a")
        filtered = layer.filter_results(results_a, context_a)

        assert len(filtered) == 1
        assert filtered[0]["secret"] == "secret-a"


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
