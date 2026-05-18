"""
Enhanced Federated Health State Machine.

Extends health states to include:
- HEALTHY: normal operation
- DEGRADED: partial capability
- SATURATED: overloaded
- DRAINING: shutting down gracefully
- QUARANTINED: isolated due to issues
- DEAD: unreachable

Transitions follow a state machine with defined rules.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class AgentHealthState(str, Enum):
    """
    Agent health states.
    
    HEALTHY: Normal operation, all capabilities available
    DEGRADED: Partial capability, some features degraded
    SATURATED: Overloaded, accepting minimal work
    DRAINING: Graceful shutdown in progress
    QUARANTINED: Isolated due to issues, not accepting work
    DEAD: Unreachable, presumed failed
    """
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    SATURATED = "saturated"
    DRAINING = "draining"
    QUARANTINED = "quarantined"
    DEAD = "dead"


class HealthTransitionError(Exception):
    """Raised when invalid health state transition is attempted."""
    pass


@dataclass
class HealthTransition:
    """Represents a health state transition."""
    from_state: AgentHealthState
    to_state: AgentHealthState
    reason: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthMetrics:
    """Health metrics for an agent."""
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    active_tasks: int = 0
    queue_depth: int = 0
    error_rate: float = 0.0
    latency_p99_ms: float = 0.0
    success_rate: float = 1.0
    last_error: Optional[str] = None


@dataclass
class AgentHealth:
    """Agent health state and metadata."""
    agent_id: str
    state: AgentHealthState
    last_heartbeat: datetime
    health_score: float = 1.0  # 0.0 to 1.0
    metrics: HealthMetrics = field(default_factory=HealthMetrics)
    capabilities: List[str] = field(default_factory=list)
    degraded_capabilities: List[str] = field(default_factory=list)
    state_history: List[HealthTransition] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_healthy(self) -> bool:
        return self.state == AgentHealthState.HEALTHY
    
    @property
    def is_accepting_work(self) -> bool:
        return self.state in {
            AgentHealthState.HEALTHY,
            AgentHealthState.DEGRADED,
        }
    
    @property
    def is_alive(self) -> bool:
        return self.state not in {
            AgentHealthState.DEAD,
            AgentHealthState.QUARANTINED,
        }


class HealthStateMachine:
    """
    State machine for agent health transitions.
    
    Defines valid transitions and transition conditions:
    
    HEALTHY -> DEGRADED: error_rate > threshold OR latency > threshold
    HEALTHY -> SATURATED: cpu/memory > threshold
    HEALTHY -> DRAINING: graceful shutdown requested
    
    DEGRADED -> HEALTHY: metrics improve
    DEGRADED -> SATURATED: overload detected
    DEGRADED -> QUARANTINED: repeated errors
    DEGRADED -> DEAD: heartbeat timeout
    
    SATURATED -> HEALTHY: load decreases
    SATURATED -> DEGRADED: partial recovery
    SATURATED -> DEAD: overload persists
    
    DRAINING -> DEAD: drain complete OR timeout
    
    QUARANTINED -> HEALTHY: admin clearance
    QUARANTINED -> DEAD: timeout
    
    DEAD: terminal state
    """
    
    # Define valid transitions
    VALID_TRANSITIONS: Dict[AgentHealthState, Set[AgentHealthState]] = {
        AgentHealthState.HEALTHY: {
            AgentHealthState.DEGRADED,
            AgentHealthState.SATURATED,
            AgentHealthState.DRAINING,
        },
        AgentHealthState.DEGRADED: {
            AgentHealthState.HEALTHY,
            AgentHealthState.SATURATED,
            AgentHealthState.QUARANTINED,
            AgentHealthState.DEAD,
        },
        AgentHealthState.SATURATED: {
            AgentHealthState.HEALTHY,
            AgentHealthState.DEGRADED,
            AgentHealthState.DEAD,
        },
        AgentHealthState.DRAINING: {
            AgentHealthState.DEAD,
        },
        AgentHealthState.QUARANTINED: {
            AgentHealthState.HEALTHY,
            AgentHealthState.DEAD,
        },
        AgentHealthState.DEAD: set(),  # Terminal state
    }
    
    def __init__(
        self,
        error_rate_threshold: float = 0.05,
        latency_threshold_ms: float = 1000.0,
        cpu_threshold: float = 0.8,
        memory_threshold: float = 0.9,
        heartbeat_timeout_seconds: float = 60.0,
        drain_timeout_seconds: float = 300.0,
        quarantine_timeout_seconds: float = 600.0,
    ):
        self.error_rate_threshold = error_rate_threshold
        self.latency_threshold_ms = latency_threshold_ms
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self.drain_timeout_seconds = drain_timeout_seconds
        self.quarantine_timeout_seconds = quarantine_timeout_seconds
    
    def can_transition(
        self,
        from_state: AgentHealthState,
        to_state: AgentHealthState,
    ) -> bool:
        """Check if transition is valid."""
        return to_state in self.VALID_TRANSITIONS.get(from_state, set())
    
    def evaluate_transition(
        self,
        current_state: AgentHealthState,
        metrics: HealthMetrics,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AgentHealthState]:
        """
        Evaluate if state transition is needed based on metrics.
        
        Returns the new state if transition is needed, None otherwise.
        """
        metadata = metadata or {}
        now = datetime.now()
        
        # Dead detection
        if metadata.get("last_heartbeat"):
            elapsed = (now - metadata["last_heartbeat"]).total_seconds()
            if elapsed > self.heartbeat_timeout_seconds:
                if current_state != AgentHealthState.DEAD:
                    return AgentHealthState.DEAD
        
        # Drain complete check
        if current_state == AgentHealthState.DRAINING:
            drain_start = metadata.get("drain_start_time")
            if drain_start:
                elapsed = (now - drain_start).total_seconds()
                if elapsed > self.drain_timeout_seconds:
                    return AgentHealthState.DEAD
        
        # Evaluate based on current state
        if current_state == AgentHealthState.HEALTHY:
            # Check for degradation
            if metrics.error_rate > self.error_rate_threshold:
                return AgentHealthState.DEGRADED
            if metrics.latency_p99_ms > self.latency_threshold_ms:
                return AgentHealthState.DEGRADED
            if metrics.cpu_usage > self.cpu_threshold:
                return AgentHealthState.SATURATED
            if metrics.memory_usage > self.memory_threshold:
                return AgentHealthState.SATURATED
        
        elif current_state == AgentHealthState.DEGRADED:
            # Check for recovery
            if (metrics.error_rate < self.error_rate_threshold * 0.5 and
                metrics.latency_p99_ms < self.latency_threshold_ms * 0.8):
                return AgentHealthState.HEALTHY
            # Check for saturation
            if metrics.cpu_usage > self.cpu_threshold or metrics.memory_usage > self.memory_threshold:
                return AgentHealthState.SATURATED
            # Check for quarantine
            if metrics.error_rate > self.error_rate_threshold * 3:
                return AgentHealthState.QUARANTINED
        
        elif current_state == AgentHealthState.SATURATED:
            # Check for recovery
            if (metrics.cpu_usage < self.cpu_threshold * 0.7 and
                metrics.memory_usage < self.memory_threshold * 0.7):
                return AgentHealthState.HEALTHY
            elif metrics.cpu_usage < self.cpu_threshold or metrics.memory_usage < self.memory_threshold:
                return AgentHealthState.DEGRADED
        
        elif current_state == AgentHealthState.QUARANTINED:
            # Only admin can clear quarantine (external action needed)
            pass
        
        elif current_state == AgentHealthState.DRAINING:
            # Monitor drain progress
            if metrics.active_tasks == 0:
                return AgentHealthState.DEAD
        
        return None
    
    def create_transition(
        self,
        from_state: AgentHealthState,
        to_state: AgentHealthState,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HealthTransition:
        """Create a health transition record."""
        return HealthTransition(
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            timestamp=datetime.now(),
            metadata=metadata or {},
        )


class EnhancedFederatedHealthPropagator:
    """
    Enhanced federated health propagator with state machine.
    
    Features:
    - Multi-state health (HEALTHY, DEGRADED, SATURATED, DRAINING, QUARANTINED, DEAD)
    - Automatic state transitions based on metrics
    - State history tracking
    - Quarantine and recovery
    - Graceful draining
    """
    
    def __init__(
        self,
        state_machine: Optional[HealthStateMachine] = None,
        health_interval_seconds: int = 10,
        offline_threshold_seconds: int = 30,
        max_sub_agents: int = 100,
    ):
        self.state_machine = state_machine or HealthStateMachine()
        self.health_interval_seconds = health_interval_seconds
        self.offline_threshold_seconds = offline_threshold_seconds
        self.max_sub_agents = max_sub_agents
        
        self._lock = asyncio.Lock()
        self._agents: Dict[str, AgentHealth] = {}
        self._transition_callbacks: List[Callable[[HealthTransition], None]] = []
        self._state_history: List[HealthTransition] = []
    
    def register_transition_callback(
        self,
        callback: Callable[[HealthTransition], None],
    ) -> None:
        """Register callback for health state transitions."""
        self._transition_callbacks.append(callback)
    
    async def report_health(
        self,
        agent_id: str,
        state: AgentHealthState,
        metrics: Optional[HealthMetrics] = None,
        capabilities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentHealth:
        """
        Report health status for an agent.
        
        This may trigger state transitions based on the state machine.
        """
        async with self._lock:
            now = datetime.now()
            metrics = metrics or HealthMetrics()
            metadata = metadata or {}
            
            # Get or create agent health
            if agent_id in self._agents:
                agent = self._agents[agent_id]
                old_state = agent.state
                
                # Check for state transition
                if state != old_state:
                    if self.state_machine.can_transition(old_state, state):
                        transition = self.state_machine.create_transition(
                            old_state, state,
                            reason=metadata.get("reason", "state_change"),
                            metadata=metadata,
                        )
                        agent.state_history.append(transition)
                        self._state_history.append(transition)
                        await self._notify_transition(transition)
                    else:
                        logger.warning(
                            f"Invalid transition {old_state} -> {state} for {agent_id}"
                        )
                        state = old_state
                
                # Update metrics
                agent.metrics = metrics
                agent.last_heartbeat = now
                agent.health_score = self._calculate_health_score(state, metrics)
                
            else:
                # New agent
                agent = AgentHealth(
                    agent_id=agent_id,
                    state=state,
                    last_heartbeat=now,
                    metrics=metrics,
                    capabilities=capabilities or [],
                )
                self._agents[agent_id] = agent
            
            # Update capabilities
            if capabilities:
                agent.capabilities = capabilities
                agent.degraded_capabilities = metadata.get("degraded_capabilities", [])
            
            return agent
    
    async def update_metrics(
        self,
        agent_id: str,
        metrics: HealthMetrics,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AgentHealth]:
        """
        Update metrics and evaluate state transition.
        
        This is called periodically to evaluate if state should change.
        """
        async with self._lock:
            if agent_id not in self._agents:
                return None
            
            agent = self._agents[agent_id]
            metadata = metadata or {}
            metadata["last_heartbeat"] = agent.last_heartbeat
            
            # Evaluate transition
            new_state = self.state_machine.evaluate_transition(
                agent.state, metrics, metadata
            )
            
            if new_state and new_state != agent.state:
                if self.state_machine.can_transition(agent.state, new_state):
                    transition = self.state_machine.create_transition(
                        agent.state, new_state,
                        reason="metrics_evaluation",
                        metadata={"metrics": metrics.__dict__},
                    )
                    agent.state_history.append(transition)
                    self._state_history.append(transition)
                    agent.state = new_state
                    await self._notify_transition(transition)
                    
                    logger.info(
                        f"Agent {agent_id} transitioned {agent.state} -> {new_state}"
                    )
            
            # Update metrics
            agent.metrics = metrics
            agent.last_heartbeat = datetime.now()
            agent.health_score = self._calculate_health_score(agent.state, metrics)
            
            return agent
    
    def _calculate_health_score(
        self,
        state: AgentHealthState,
        metrics: HealthMetrics,
    ) -> float:
        """Calculate overall health score."""
        base_scores = {
            AgentHealthState.HEALTHY: 1.0,
            AgentHealthState.DEGRADED: 0.6,
            AgentHealthState.SATURATED: 0.4,
            AgentHealthState.DRAINING: 0.3,
            AgentHealthState.QUARANTINED: 0.1,
            AgentHealthState.DEAD: 0.0,
        }
        
        base = base_scores.get(state, 0.5)
        
        # Adjust based on metrics
        if state == AgentHealthState.HEALTHY:
            # Penalize for high error rate
            base *= (1.0 - metrics.error_rate)
        
        return max(0.0, min(1.0, base))
    
    async def initiate_drain(
        self,
        agent_id: str,
        reason: str = "graceful_shutdown",
    ) -> bool:
        """Initiate graceful drain for an agent."""
        async with self._lock:
            if agent_id not in self._agents:
                return False
            
            agent = self._agents[agent_id]
            
            if not self.state_machine.can_transition(agent.state, AgentHealthState.DRAINING):
                return False
            
            metadata = {
                "reason": reason,
                "drain_start_time": datetime.now(),
            }
            
            transition = self.state_machine.create_transition(
                agent.state, AgentHealthState.DRAINING,
                reason=reason,
                metadata=metadata,
            )
            
            agent.state = AgentHealthState.DRAINING
            agent.state_history.append(transition)
            self._state_history.append(transition)
            
            await self._notify_transition(transition)
            
            logger.info(f"Initiated drain for agent {agent_id}: {reason}")
            return True
    
    async def quarantine_agent(
        self,
        agent_id: str,
        reason: str = "isolated",
        duration_seconds: Optional[float] = None,
    ) -> bool:
        """Quarantine an agent."""
        async with self._lock:
            if agent_id not in self._agents:
                return False
            
            agent = self._agents[agent_id]
            
            if not self.state_machine.can_transition(agent.state, AgentHealthState.QUARANTINED):
                return False
            
            transition = self.state_machine.create_transition(
                agent.state, AgentHealthState.QUARANTINED,
                reason=reason,
                metadata={"duration_seconds": duration_seconds},
            )
            
            agent.state = AgentHealthState.QUARANTINED
            agent.state_history.append(transition)
            self._state_history.append(transition)
            
            await self._notify_transition(transition)
            
            logger.warning(f"Quarantined agent {agent_id}: {reason}")
            return True
    
    async def clear_quarantine(
        self,
        agent_id: str,
        admin_id: str,
    ) -> bool:
        """Clear quarantine (admin action)."""
        async with self._lock:
            if agent_id not in self._agents:
                return False
            
            agent = self._agents[agent_id]
            
            if agent.state != AgentHealthState.QUARANTINED:
                return False
            
            transition = self.state_machine.create_transition(
                AgentHealthState.QUARANTINED, AgentHealthState.HEALTHY,
                reason=f"cleared_by_admin:{admin_id}",
            )
            
            agent.state = AgentHealthState.HEALTHY
            agent.state_history.append(transition)
            self._state_history.append(transition)
            
            await self._notify_transition(transition)
            
            logger.info(f"Admin {admin_id} cleared quarantine for {agent_id}")
            return True
    
    async def get_agent_health(self, agent_id: str) -> Optional[AgentHealth]:
        """Get health status for an agent."""
        async with self._lock:
            return self._agents.get(agent_id)
    
    async def get_all_health(self) -> List[AgentHealth]:
        """Get health status for all agents."""
        async with self._lock:
            return list(self._agents.values())
    
    async def get_agents_by_state(
        self,
        state: AgentHealthState,
    ) -> List[AgentHealth]:
        """Get agents in a specific state."""
        async with self._lock:
            return [a for a in self._agents.values() if a.state == state]
    
    async def get_available_agents(self) -> List[AgentHealth]:
        """Get agents that can accept work."""
        async with self._lock:
            return [a for a in self._agents.values() if a.is_accepting_work]
    
    async def get_federated_health(
        self,
        federated_agent_id: str,
    ) -> Dict[str, Any]:
        """Get aggregated health for a federated agent."""
        agents = await self.get_all_health()
        
        state_counts = defaultdict(int)
        for agent in agents:
            state_counts[agent.state] += 1
        
        healthy_count = sum(
            1 for a in agents if a.state == AgentHealthState.HEALTHY
        )
        
        return {
            "federated_agent_id": federated_agent_id,
            "total_agents": len(agents),
            "healthy_agents": healthy_count,
            "health_score": sum(a.health_score for a in agents) / max(1, len(agents)),
            "state_distribution": dict(state_counts),
            "available_for_work": len(await self.get_available_agents()),
        }
    
    async def _notify_transition(self, transition: HealthTransition) -> None:
        """Notify callbacks of state transition."""
        for callback in self._transition_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(transition)
                else:
                    callback(transition)
            except Exception as e:
                logger.error(f"Transition callback failed: {e}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get health propagator metrics."""
        state_counts = defaultdict(int)
        for agent in self._agents.values():
            state_counts[agent.state] += 1
        
        return {
            "total_agents": len(self._agents),
            "state_distribution": dict(state_counts),
            "healthy_agents": state_counts[AgentHealthState.HEALTHY],
            "degraded_agents": state_counts[AgentHealthState.DEGRADED],
            "saturated_agents": state_counts[AgentHealthState.SATURATED],
            "draining_agents": state_counts[AgentHealthState.DRAINING],
            "quarantined_agents": state_counts[AgentHealthState.QUARANTINED],
            "dead_agents": state_counts[AgentHealthState.DEAD],
            "available_for_work": sum(
                1 for a in self._agents.values() if a.is_accepting_work
            ),
        }
