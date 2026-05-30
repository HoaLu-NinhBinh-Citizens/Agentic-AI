"""Agent registry for distributed multi-agent coordination."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class AgentStatus(Enum):
    """Agent status enumeration."""
    HEALTHY = "healthy"
    BUSY = "busy"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass
class AgentInfo:
    """Agent information record."""
    id: str
    name: str
    capabilities: List[str] = field(default_factory=list)
    status: AgentStatus = AgentStatus.UNKNOWN
    load: float = 0.0
    last_heartbeat: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)


class AgentRegistry:
    """Registry for tracking distributed agents."""

    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}
        self._lock = asyncio.Lock()

    def count(self) -> int:
        return len(self._agents)

    async def register(self, agent: AgentInfo) -> str:
        async with self._lock:
            self._agents[agent.id] = agent
        return agent.id

    async def unregister(self, agent_id: str) -> bool:
        async with self._lock:
            if agent_id in self._agents:
                del self._agents[agent_id]
                return True
        return False

    async def heartbeat(self, agent_id: str) -> bool:
        async with self._lock:
            if agent_id in self._agents:
                self._agents[agent_id].last_heartbeat = time.time()
                return True
        return False

    def discover(self, capabilities: Optional[List[str]] = None) -> List[AgentInfo]:
        result = []
        for agent in self._agents.values():
            if capabilities:
                if any(c in agent.capabilities for c in capabilities):
                    result.append(agent)
            else:
                result.append(agent)
        return result

    def get_healthy_agents(self) -> List[AgentInfo]:
        return [
            agent for agent in self._agents.values()
            if agent.status == AgentStatus.HEALTHY
        ]
