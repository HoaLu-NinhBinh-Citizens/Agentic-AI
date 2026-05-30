"""Agent message types and builders for distributed messaging."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class MessageType(Enum):
    """Message type enumeration."""
    REQUEST = "request"
    RESPONSE = "response"
    BROADCAST = "broadcast"
    NOTIFICATION = "notification"
    HEARTBEAT = "heartbeat"
    TASK_ASSIGN = "task_assign"
    TASK_RESULT = "task_result"


class MessagePriority(Enum):
    """Message priority levels."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class AgentMessage:
    """Agent inter-process message."""
    sender: str
    receivers: List[str]
    type: MessageType = MessageType.REQUEST
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: MessagePriority = MessagePriority.NORMAL
    ttl: int = 10
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reply_to: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    _ttl_remaining: int = field(default=None, repr=False)

    def __post_init__(self):
        object.__setattr__(self, "_ttl_remaining", self.ttl)

    def is_broadcast(self) -> bool:
        return self.type == MessageType.BROADCAST or len(self.receivers) == 0

    def has_ttl_expired(self) -> bool:
        return self._ttl_remaining <= 0

    def decrement_ttl(self) -> bool:
        if self._ttl_remaining > 0:
            object.__setattr__(self, "_ttl_remaining", self._ttl_remaining - 1)
            return True
        return False

    def create_reply(self, payload: Dict[str, Any]) -> "AgentMessage":
        return AgentMessage(
            sender=self.receivers[0] if self.receivers else self.sender,
            receivers=[self.sender],
            type=MessageType.RESPONSE,
            payload=payload,
            priority=self.priority,
            reply_to=self.id,
        )


class MessageBuilder:
    """Factory for creating typed agent messages."""

    @staticmethod
    def create_task_request(
        sender: str,
        receiver: str,
        task_id: str,
        task_data: Dict[str, Any],
    ) -> AgentMessage:
        return AgentMessage(
            sender=sender,
            receivers=[receiver],
            type=MessageType.TASK_ASSIGN,
            payload={"task_id": task_id, "data": task_data},
        )

    @staticmethod
    def create_notification(
        sender: str,
        receivers: List[str],
        notification_type: str,
        data: Dict[str, Any],
    ) -> AgentMessage:
        return AgentMessage(
            sender=sender,
            receivers=receivers,
            type=MessageType.NOTIFICATION,
            payload={"notification_type": notification_type, "data": data},
        )

    @staticmethod
    def create_broadcast(
        sender: str,
        broadcast_type: str,
        data: Dict[str, Any],
    ) -> AgentMessage:
        return AgentMessage(
            sender=sender,
            receivers=[],
            type=MessageType.BROADCAST,
            payload={"broadcast_type": broadcast_type, "data": data},
            ttl=5,
        )

    @staticmethod
    def create_heartbeat(sender: str, status: str) -> AgentMessage:
        return AgentMessage(
            sender=sender,
            receivers=[],
            type=MessageType.HEARTBEAT,
            payload={"status": status},
            ttl=3,
        )
