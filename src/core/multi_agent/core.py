"""
Core types and base classes for the multi-agent system.

Exports:
- Enums: AgentStatus, AgentType
- Dataclasses: AgentMessage, Task, ExecutionTrace
- Base: BaseAgent, MessageBus
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    IDLE = "idle"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING = "waiting"


class AgentType(Enum):
    ORCHESTRATOR = "orchestrator"
    CODE_GEN = "code_gen"
    REVIEW = "review"
    SECURITY = "security"
    TEST = "test"
    DEVOPS = "devops"
    MONITORING = "monitoring"
    FIRMWARE = "firmware"


@dataclass
class AgentMessage:
    id: str = field(default_factory=lambda: str(uuid4()))
    sender: AgentType = AgentType.ORCHESTRATOR
    receiver: Optional[AgentType] = None
    content: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    reply_to: Optional[str] = None
    priority: int = 0


@dataclass
class Task:
    id: str = field(default_factory=lambda: str(uuid4()))
    type: str = ""
    description: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    status: AgentStatus = AgentStatus.IDLE
    assigned_to: Optional[AgentType] = None
    result: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    dependencies: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


@dataclass
class ExecutionTrace:
    task_id: str
    agent_type: AgentType
    action: str
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    success: bool
    duration_ms: float
    timestamp: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None


class BaseAgent(ABC):
    def __init__(self, agent_type: AgentType, model_router=None):
        self.agent_type = agent_type
        self.status = AgentStatus.IDLE
        self.model_router = model_router
        self.message_queue: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self.traces: List[ExecutionTrace] = []
        self._running = False

    @abstractmethod
    async def process(self, task: Task) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def can_handle(self, task: Task) -> bool:
        pass

    async def execute(self, task: Task) -> Dict[str, Any]:
        start = datetime.now()
        self.status = AgentStatus.WORKING
        try:
            result = await self.process(task)
            duration = (datetime.now() - start).total_seconds() * 1000
            self.traces.append(ExecutionTrace(
                task_id=task.id,
                agent_type=self.agent_type,
                action="process",
                input_data={"task_type": task.type, "description": task.description},
                output_data=result,
                success=True,
                duration_ms=duration,
            ))
            task.result = result
            task.status = AgentStatus.COMPLETED
            task.completed_at = datetime.now()
            self.status = AgentStatus.IDLE
            return result
        except Exception as exc:
            duration = (datetime.now() - start).total_seconds() * 1000
            self.traces.append(ExecutionTrace(
                task_id=task.id,
                agent_type=self.agent_type,
                action="process",
                input_data={"task_type": task.type, "description": task.description},
                output_data={},
                success=False,
                duration_ms=duration,
                error=str(exc),
            ))
            task.status = AgentStatus.FAILED
            self.status = AgentStatus.IDLE
            raise

    def get_capabilities(self) -> List[str]:
        return []

    def get_learning_data(self) -> List[Dict[str, Any]]:
        return [
            {
                "agent_type": t.agent_type.value,
                "action": t.action,
                "success": t.success,
                "duration_ms": t.duration_ms,
                "error": t.error,
            }
            for t in self.traces[-50:]
        ]


class MessageBus:
    def __init__(self):
        self.subscribers: Dict[AgentType, asyncio.Queue[AgentMessage]] = {}
        self.history: List[AgentMessage] = []
        self._lock = asyncio.Lock()

    def subscribe(self, agent_type: AgentType) -> asyncio.Queue[AgentMessage]:
        if agent_type not in self.subscribers:
            self.subscribers[agent_type] = asyncio.Queue()
        return self.subscribers[agent_type]

    async def publish(self, message: AgentMessage):
        async with self._lock:
            self.history.append(message)
        if message.receiver and message.receiver in self.subscribers:
            await self.subscribers[message.receiver].put(message)
        elif message.receiver is None:
            for queue in self.subscribers.values():
                await queue.put(message)

    async def receive(self, agent_type: AgentType, timeout: float = 30) -> Optional[AgentMessage]:
        if agent_type not in self.subscribers:
            return None
        try:
            return await asyncio.wait_for(
                self.subscribers[agent_type].get(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return None
