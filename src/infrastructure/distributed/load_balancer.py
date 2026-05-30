"""Load balancer for distributed agent task routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from src.infrastructure.distributed.registry import AgentInfo


class LoadBalancingStrategy(Enum):
    """Load balancing strategy types."""
    ROUND_ROBIN = "round_robin"
    LEAST_LOADED = "least_loaded"
    RANDOM = "random"
    WEIGHTED = "weighted"


@dataclass
class AgentStats:
    """Per-agent load statistics."""
    agent_id: str
    active_connections: int = 0
    total_requests: int = 0
    avg_latency_ms: float = 0.0


class LoadBalancer:
    """Load balancer for distributing work across agents."""

    def __init__(self, strategy: LoadBalancingStrategy = LoadBalancingStrategy.LEAST_LOADED):
        self.strategy = strategy
        self._agents: Dict[str, AgentInfo] = {}
        self._stats: Dict[str, AgentStats] = {}
        self._round_robin_index: int = 0

    def add_agent(self, agent: AgentInfo) -> None:
        self._agents[agent.id] = agent
        self._stats[agent.id] = AgentStats(agent_id=agent.id)

    def remove_agent(self, agent_id: str) -> None:
        self._agents.pop(agent_id, None)
        self._stats.pop(agent_id, None)

    def select(self) -> Optional[AgentInfo]:
        if not self._agents:
            return None

        if self.strategy == LoadBalancingStrategy.LEAST_LOADED:
            return min(
                self._agents.values(),
                key=lambda a: self._stats.get(a.id, AgentStats(a.id)).active_connections,
            )
        elif self.strategy == LoadBalancingStrategy.ROUND_ROBIN:
            agents = list(self._agents.values())
            if not agents:
                return None
            selected = agents[self._round_robin_index % len(agents)]
            self._round_robin_index += 1
            return selected
        elif self.strategy == LoadBalancingStrategy.RANDOM:
            import random
            return random.choice(list(self._agents.values()))
        else:
            return next(iter(self._agents.values()))

    def record_request_start(self, agent_id: str) -> None:
        if agent_id in self._stats:
            self._stats[agent_id].active_connections += 1

    def record_request_end(self, agent_id: str) -> None:
        if agent_id in self._stats and self._stats[agent_id].active_connections > 0:
            self._stats[agent_id].active_connections -= 1
            self._stats[agent_id].total_requests += 1

    def get_agent_stats(self, agent_id: str) -> Optional[Dict]:
        if agent_id not in self._stats:
            return None
        stats = self._stats[agent_id]
        return {
            "agent_id": stats.agent_id,
            "active_connections": stats.active_connections,
            "total_requests": stats.total_requests,
            "avg_latency_ms": stats.avg_latency_ms,
        }
