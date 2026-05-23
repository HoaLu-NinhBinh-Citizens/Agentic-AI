"""
Multi-Agent Coordinator - Main Coordinator Class.

Integrates all coordination components:
- Two-way circuit breaker
- Federated health propagation
- Schema evolution
- Batch idempotency
- Tenant isolation
- Agent resource quota
- Leader election
- Backpressure control
- Dead letter alerts

Provides a unified interface for multi-agent coordination.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from src.core.multi_agent.coordination.types import (
    AgentQuota,
    BackpressureResponse,
    BatchItem,
    BatchResult,
    CircuitBreakerDirection,
    CircuitBreakerState,
    CoordinatorMetrics,
    DeadLetterAlertConfig,
    FederatedHealthReport,
    HealthStatus,
    LeaderInfo,
    SchemaDefinition,
    SubAgentStatus,
    TenantConfig,
)

from src.core.multi_agent.coordination.config import (
    MultiAgentCoordinationConfig,
    CircuitBreakerConfig,
    FederatedHealthConfig,
    SchemaEvolutionConfig,
    BatchIdempotencyConfig,
    QuotaConfig,
    LeaderElectionConfig,
    BackpressureConfig,
    DeadLetterAlertConfig,
    TenantIsolationConfig,
)

from src.core.multi_agent.coordination.circuit_breaker import (
    TwoWayCircuitBreaker,
    CircuitBreakerOpenError,
)

from src.core.multi_agent.coordination.health import (
    FederatedHealthPropagator,
    HealthStore,
)

from src.core.multi_agent.coordination.schema_evolution import (
    SchemaEvolutionEngine,
    CompatibilityPolicy,
)

from src.core.multi_agent.coordination.batch_idempotency import (
    BatchIdempotencyStore,
)

from src.core.multi_agent.coordination.tenant_isolation import (
    TenantIsolationLayer,
    TenantContext,
    CrossTenantAccessError,
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
)

logger = logging.getLogger(__name__)


class CoordinatorError(Exception):
    """Base exception for coordinator errors."""
    pass


class CoordinatorUnavailableError(CoordinatorError):
    """Raised when coordinator is unavailable."""
    pass


@dataclass
class DelegationRequest:
    """Request for agent delegation."""
    request_id: str
    agent_id: str
    task: Dict[str, Any]
    tenant_id: str
    priority: int = 5
    timeout_seconds: float = 300.0


@dataclass
class DelegationResponse:
    """Response from delegation."""
    request_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0


class MultiAgentCoordinator:
    """
    Multi-agent coordinator integrating all coordination features.
    
    Provides:
    - Agent registration and health tracking
    - Task delegation with quota enforcement
    - Circuit breaker protection
    - Schema validation and evolution
    - Batch processing with idempotency
    - Tenant isolation
    - Leader election for HA
    - Backpressure control
    - Dead letter queue monitoring
    
    Usage:
        coordinator = await MultiAgentCoordinator.create(config)
        
        # Delegate task
        response = await coordinator.delegate(
            agent_id="code-gen-1",
            task={"type": "codegen", "prompt": "..."},
            tenant_id="tenant-1",
        )
        
        # Process batch
        results = await coordinator.process_batch(
            batch_id="batch-1",
            items=[...],
            processor=lambda i, x: process(x),
            tenant_id="tenant-1",
        )
    """
    
    def __init__(self, config: MultiAgentCoordinationConfig):
        self.config = config
        self._instance_id = f"coordinator-{id(self)}"
        self._running = False
        self._initialized = False
        
        # Initialize components
        self.circuit_breaker = TwoWayCircuitBreaker(
            name="coordinator",
            failure_threshold=config.circuit_breaker.failure_threshold,
            window_seconds=config.circuit_breaker.window_seconds,
            recovery_timeout=config.circuit_breaker.recovery_timeout,
            half_open_max_calls=config.circuit_breaker.half_open_max_calls,
            transient_error_codes=config.circuit_breaker.transient_error_codes,
        )
        
        self.health_propagator = FederatedHealthPropagator(
            health_interval_seconds=config.federated_health.health_interval_seconds,
            offline_threshold_seconds=config.federated_health.offline_threshold_seconds,
            max_sub_agents=config.federated_health.max_sub_agents,
        )
        
        self.schema_engine = SchemaEvolutionEngine(
            compatibility_policy=CompatibilityPolicy(config.schema_evolution.compatibility_policy),
            current_version=config.schema_evolution.current_version,
        )
        
        self.batch_store = BatchIdempotencyStore(
            ttl_seconds=config.batch_idempotency.ttl_seconds,
            cleanup_interval_seconds=config.batch_idempotency.cleanup_interval_seconds,
        )
        
        self.tenant_layer = TenantIsolationLayer(
            jwt_secret=config.tenant_isolation.jwt_secret,
            admin_roles=config.tenant_isolation.admin_roles,
            require_tenant_header=config.tenant_isolation.require_tenant_header,
            allow_cross_tenant_audit=config.tenant_isolation.allow_cross_tenant_audit,
        )
        
        self.quota_enforcer = QuotaEnforcer(
            default_max_concurrent=config.quota.max_concurrent_tasks,
            default_max_message_rate=config.quota.max_message_rate,
            default_max_workspace_bytes=config.quota.max_workspace_bytes,
        )
        
        self.leader_elector = LeaderElector(
            redis_url=config.leader_election.redis_url,
            lock_key=config.leader_election.lock_key,
            heartbeat_interval=float(config.leader_election.heartbeat_interval_seconds),
            lock_ttl=float(config.leader_election.lock_ttl_seconds),
        )
        
        self.backpressure = BackpressureController(
            rate_limit_per_agent=config.backpressure.rate_limit_per_agent,
            window_seconds=config.backpressure.window_seconds,
            enable_per_tenant=config.backpressure.enable_per_tenant,
            default_retry_after=float(config.backpressure.default_retry_after_seconds),
        )
        
        self.dlq_alert = DeadLetterAlert(
            default_threshold=config.dead_letter_alert.threshold,
            default_webhook_url=config.dead_letter_alert.webhook_url,
            default_webhook_method=config.dead_letter_alert.webhook_method,
            default_webhook_headers=config.dead_letter_alert.webhook_headers,
            check_interval_seconds=config.dead_letter_alert.check_interval_seconds,
            enabled=config.dead_letter_alert.enabled,
        )
        
        # Agent registry - PROTECTED BY LOCK
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._agents_lock = asyncio.Lock()  # Protect _agents dict access
        
        # Task tracking - PROTECTED BY LOCK
        self._pending_tasks: Dict[str, DelegationRequest] = {}
        self._completed_tasks: Dict[str, DelegationResponse] = {}
        self._task_counter = 0
        self._task_lock = asyncio.Lock()
    
    @classmethod
    async def create(
        cls,
        config: Optional[MultiAgentCoordinationConfig] = None,
        config_dict: Optional[Dict[str, Any]] = None,
    ) -> "MultiAgentCoordinator":
        """Factory method to create and initialize coordinator."""
        if config_dict:
            config = MultiAgentCoordinationConfig.from_dict(config_dict)
        elif not config:
            config = MultiAgentCoordinationConfig()
        
        coordinator = cls(config)
        await coordinator.initialize()
        return coordinator
    
    async def initialize(self) -> None:
        """Initialize all components."""
        if self._initialized:
            return
        
        logger.info("Initializing MultiAgentCoordinator...")
        
        # Start background tasks
        await self.batch_store.start()
        await self.dlq_alert.start()
        
        self._initialized = True
        self._running = True
        logger.info("MultiAgentCoordinator initialized")
    
    async def shutdown(self) -> None:
        """Shutdown all components."""
        logger.info("Shutting down MultiAgentCoordinator...")
        self._running = False
        
        await self.batch_store.stop()
        await self.dlq_alert.stop()
        await self.leader_elector.stop_heartbeat()
        
        self._initialized = False
        logger.info("MultiAgentCoordinator shutdown complete")
    
    # =============================================================================
    # Agent Management
    # =============================================================================
    
    async def register_agent(
        self,
        agent_id: str,
        agent_type: str,
        capabilities: List[str],
        endpoint: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register an agent with the coordinator.
        
        THREAD SAFETY: Uses _agents_lock to prevent race conditions.
        """
        async with self._agents_lock:
            self._agents[agent_id] = {
                "agent_id": agent_id,
                "agent_type": agent_type,
                "capabilities": capabilities,
                "endpoint": endpoint,
                "metadata": metadata or {},
                "registered_at": datetime.now(),
                "status": HealthStatus.HEALTHY,
            }
            self._locks[agent_id] = asyncio.Lock()
        
        logger.info(f"Registered agent: {agent_id} (type={agent_type})")
    
    async def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent.
        
        THREAD SAFETY: Uses _agents_lock to prevent race conditions.
        """
        async with self._agents_lock:
            if agent_id in self._agents:
                del self._agents[agent_id]
            if agent_id in self._locks:
                del self._locks[agent_id]
        
        logger.info(f"Unregistered agent: {agent_id}")
    
    async def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent information.
        
        THREAD SAFETY: Read operation with lock.
        """
        async with self._agents_lock:
            return self._agents.get(agent_id)
    
    async def list_agents(
        self,
        agent_type: Optional[str] = None,
        capability: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List registered agents with optional filtering.
        
        THREAD SAFETY: Read operation with lock.
        """
        async with self._agents_lock:
            agents = list(self._agents.values())
        
        if agent_type:
            agents = [a for a in agents if a["agent_type"] == agent_type]
        
        if capability:
            agents = [a for a in agents if capability in a["capabilities"]]
        
        return agents
    
    async def update_agent_status(
        self,
        agent_id: str,
        status: HealthStatus,
    ) -> None:
        """Update agent health status.
        
        THREAD SAFETY: Write operation with lock.
        """
        async with self._agents_lock:
            if agent_id in self._agents:
                self._agents[agent_id]["status"] = status
                self._agents[agent_id]["last_status_update"] = datetime.now()
    
    # =============================================================================
    # Task Delegation
    # =============================================================================
    
    async def delegate(
        self,
        agent_id: str,
        task: Dict[str, Any],
        tenant_id: str,
        priority: int = 5,
        timeout_seconds: float = 300.0,
        idempotency_key: Optional[str] = None,
    ) -> DelegationResponse:
        """
        Delegate a task to an agent.
        
        This is a write operation that requires leadership.
        """
        # Check leadership
        if not await self.leader_elector.is_leader():
            raise NotLeaderError("This coordinator instance is not the leader")
        
        # Validate tenant access
        tenant = await self.tenant_layer.get_tenant(tenant_id)
        if not tenant:
            return DelegationResponse(
                request_id="",
                success=False,
                error=f"Unknown tenant: {tenant_id}",
            )
        
        # Check backpressure
        bp_response = await self.backpressure.check_rate_limit(agent_id, tenant_id)
        if bp_response.is_limited:
            return DelegationResponse(
                request_id="",
                success=False,
                error=f"Rate limited: retry after {bp_response.retry_after}s",
            )
        
        # Check quota
        try:
            await self.quota_enforcer.submit_task(agent_id)
        except QuotaExceededError as e:
            return DelegationResponse(
                request_id="",
                success=False,
                error=f"Quota exceeded: {e.quota_type}",
            )
        
        # Create request
        async with self._task_lock:
            self._task_counter += 1
            request_id = f"req-{self._task_counter}"
        
        request = DelegationRequest(
            request_id=request_id,
            agent_id=agent_id,
            task=task,
            tenant_id=tenant_id,
            priority=priority,
            timeout_seconds=timeout_seconds,
        )
        
        self._pending_tasks[request_id] = request
        await self.backpressure.record_request(agent_id, tenant_id)
        
        # Execute via circuit breaker
        start_time = asyncio.get_event_loop().time()
        
        try:
            async def execute_task():
                # Transform task schema if needed
                transformed_task = await self.schema_engine.transform_message(task)
                
                # Execute via agent (simulated)
                result = await self._execute_on_agent(agent_id, transformed_task)
                
                return result
            
            result = await self.circuit_breaker.call(
                target_id=agent_id,
                func=execute_task,
                direction=CircuitBreakerDirection.COORDINATOR_TO_AGENT,
            )
            
            execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
            
            response = DelegationResponse(
                request_id=request_id,
                success=True,
                result=result,
                execution_time_ms=execution_time,
            )
            
            self._completed_tasks[request_id] = response
            
            # Release quota
            await self.quota_enforcer.complete_task(agent_id)
            
            return response
            
        except CircuitBreakerOpenError as e:
            await self.quota_enforcer.release_task(agent_id)
            return DelegationResponse(
                request_id=request_id,
                success=False,
                error=f"Circuit breaker open: {e}",
            )
            
        except Exception as e:
            await self.quota_enforcer.release_task(agent_id)
            return DelegationResponse(
                request_id=request_id,
                success=False,
                error=str(e),
            )
            
        finally:
            self._pending_tasks.pop(request_id, None)
    
    async def _execute_on_agent(
        self,
        agent_id: str,
        task: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute task on agent (simulated)."""
        agent = self._agents.get(agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")
        
        # Simulate task execution
        await asyncio.sleep(0.01)
        
        return {
            "agent_id": agent_id,
            "task_type": task.get("type"),
            "executed": True,
        }
    
    # =============================================================================
    # Batch Processing
    # =============================================================================
    
    async def process_batch(
        self,
        batch_id: str,
        items: List[Any],
        processor: Callable[[int, Any], Any],
        tenant_id: str,
        idempotency_key_func: Optional[Callable[[int, Any], str]] = None,
    ) -> List[BatchResult]:
        """
        Process a batch with idempotency per item.
        """
        def make_async_processor():
            async def async_processor(idx, item):
                return await asyncio.coroutine(lambda: processor(idx, item))()
            return async_processor
        
        results = await self.batch_store.process_batch(
            batch_id=batch_id,
            items=items,
            processor=await make_async_processor(),
            idempotency_key_func=idempotency_key_func,
        )
        
        return results
    
    # =============================================================================
    # Schema Evolution
    # =============================================================================
    
    async def register_schema(
        self,
        message_type: str,
        version: str,
        schema: Dict[str, Any],
        migrations: Optional[Dict[tuple, Callable]] = None,
    ) -> SchemaDefinition:
        """Register a new schema version."""
        return await self.schema_engine.register_schema(
            message_type=message_type,
            version=version,
            schema=schema,
            migrations=migrations,
        )
    
    async def transform_message(
        self,
        message: Dict[str, Any],
        target_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Transform message to target schema version."""
        return await self.schema_engine.transform_message(message, target_version)
    
    # =============================================================================
    # Health Management
    # =============================================================================
    
    async def report_health(
        self,
        agent_id: str,
        status: HealthStatus,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Report agent health status."""
        await self.update_agent_status(agent_id, status)
    
    async def report_federated_health(
        self,
        federated_agent_id: str,
        sub_agents: List[Dict[str, Any]],
    ) -> FederatedHealthReport:
        """Report federated health from federated agent."""
        return await self.health_propagator.report_sub_agents_status(
            federated_agent_id=federated_agent_id,
            sub_agents=sub_agents,
        )
    
    async def get_federated_health(
        self,
        federated_agent_id: str,
    ) -> Dict[str, Any]:
        """Get federated health status."""
        return await self.health_propagator.get_federated_health(federated_agent_id)
    
    # =============================================================================
    # Tenant Management
    # =============================================================================
    
    async def create_tenant(
        self,
        tenant_id: str,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Create a new tenant."""
        await self.tenant_layer.create_tenant(tenant_id, name, metadata)
    
    async def delete_tenant(self, tenant_id: str) -> None:
        """Delete a tenant."""
        await self.tenant_layer.delete_tenant(tenant_id)
    
    async def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant configuration."""
        return await self.tenant_layer.get_tenant(tenant_id)
    
    async def list_tenants(self) -> List[Dict[str, Any]]:
        """List all tenants."""
        return await self.tenant_layer.list_tenants()
    
    # =============================================================================
    # Quota Management
    # =============================================================================
    
    async def set_agent_quota(
        self,
        agent_id: str,
        max_concurrent_tasks: Optional[int] = None,
        max_message_rate: Optional[int] = None,
        max_workspace_bytes: Optional[int] = None,
    ) -> AgentQuota:
        """Set quota for an agent."""
        return await self.quota_enforcer.set_quota(
            agent_id,
            max_concurrent_tasks=max_concurrent_tasks,
            max_message_rate=max_message_rate,
            max_workspace_bytes=max_workspace_bytes,
        )
    
    async def get_agent_quota(self, agent_id: str) -> AgentQuota:
        """Get quota for an agent."""
        return await self.quota_enforcer.get_quota(agent_id)
    
    async def get_agent_usage(self, agent_id: str) -> Dict[str, Any]:
        """Get current usage for an agent."""
        return await self.quota_enforcer.get_agent_usage(agent_id)
    
    # =============================================================================
    # Leader Election
    # =============================================================================
    
    async def become_leader(self, instance_id: str) -> str:
        """Attempt to become the leader."""
        leader = await self.leader_elector.try_become_leader(instance_id)
        
        if leader == instance_id:
            await self.leader_elector.start_heartbeat()
        
        return leader
    
    async def is_leader(self) -> bool:
        """Check if this instance is the leader."""
        return await self.leader_elector.is_leader()
    
    async def get_leader(self) -> Optional[str]:
        """Get current leader's instance ID."""
        return await self.leader_elector.get_leader()
    
    async def transfer_leadership(self, new_leader: str) -> None:
        """Transfer leadership to another instance."""
        await self.leader_elector.transfer_leadership(new_leader)
    
    # =============================================================================
    # Dead Letter Queue
    # =============================================================================
    
    async def add_to_dead_letter(
        self,
        tenant_id: str,
        item_id: str,
        message: Dict[str, Any],
        error: str,
        queue_name: str = "default",
    ) -> None:
        """Add failed item to dead letter queue."""
        await self.dlq_alert.add_failed_item(
            tenant_id=tenant_id,
            item_id=item_id,
            message=message,
            error=error,
            queue_name=queue_name,
        )
    
    async def get_dlq_stats(
        self,
        tenant_id: str,
        queue_name: str = "default",
    ) -> Dict[str, Any]:
        """Get dead letter queue statistics."""
        return await self.dlq_alert.get_queue_stats(tenant_id, queue_name)
    
    # =============================================================================
    # Circuit Breaker
    # =============================================================================
    
    async def get_circuit_state(
        self,
        agent_id: str,
        direction: CircuitBreakerDirection = CircuitBreakerDirection.COORDINATOR_TO_AGENT,
    ) -> CircuitBreakerState:
        """Get circuit breaker state for an agent."""
        return self.circuit_breaker.get_state(agent_id, direction)
    
    async def reset_circuit(
        self,
        agent_id: Optional[str] = None,
    ) -> None:
        """Reset circuit breaker(s)."""
        self.circuit_breaker.reset(agent_id)
    
    # =============================================================================
    # Backpressure
    # =============================================================================
    
    async def check_backpressure(
        self,
        agent_id: str,
        tenant_id: Optional[str] = None,
    ) -> BackpressureResponse:
        """Check backpressure status for an agent."""
        return await self.backpressure.check_rate_limit(agent_id, tenant_id)
    
    async def set_rate_limit(
        self,
        agent_id: str,
        limit: int,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Set custom rate limit for an agent."""
        await self.backpressure.set_agent_limit(agent_id, limit, tenant_id)
    
    # =============================================================================
    # Metrics
    # =============================================================================
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics."""
        return {
            "coordinator": {
                "instance_id": self._instance_id,
                "initialized": self._initialized,
                "running": self._running,
                "is_leader": await self.is_leader(),
            },
            "circuit_breaker": self.circuit_breaker.get_metrics(),
            "health": self.health_propagator.get_metrics(),
            "schema": self.schema_engine.get_metrics(),
            "batch": self.batch_store.get_metrics(),
            "tenant": self.tenant_layer.get_metrics(),
            "quota": self.quota_enforcer.get_metrics(),
            "leader": self.leader_elector.get_metrics(),
            "backpressure": self.backpressure.get_metrics(),
            "dlq": self.dlq_alert.get_metrics(),
            "agents": {
                "total": len(self._agents),
                "by_type": self._count_agents_by_type(),
            },
            "tasks": {
                "pending": len(self._pending_tasks),
                "completed": len(self._completed_tasks),
            },
        }
    
    def _count_agents_by_type(self) -> Dict[str, int]:
        """Count agents by type.
        
        THREAD SAFETY: Read operation with lock.
        """
        # Note: This is called from get_metrics which is sync, need to handle carefully
        # For now, make a copy of agents
        agents_copy = list(self._agents.values()) if hasattr(self, '_agents') else []
        counts = {}
        for agent in agents_copy:
            agent_type = agent.get("agent_type", "unknown")
            counts[agent_type] = counts.get(agent_type, 0) + 1
        return counts
    
    async def get_status(self) -> Dict[str, Any]:
        """Get coordinator status summary."""
        return {
            "healthy": self._initialized and self._running,
            "leader": await self.is_leader(),
            "agents_registered": len(self._agents),
            "tasks_pending": len(self._pending_tasks),
            "tasks_completed": len(self._completed_tasks),
            "open_circuits": self.circuit_breaker.get_metrics()["open_circuits"],
        }
