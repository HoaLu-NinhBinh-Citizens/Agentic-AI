"""
Message Ordering and Delivery Guarantees.

Provides:
- FIFO per-agent ordering
- Causal ordering
- Sequence numbers
- Exactly-once vs at-least-once semantics
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

logger = logging.getLogger(__name__)


class OrderingGuarantee(str):
    """Message ordering guarantee levels."""
    AT_MOST_ONCE = "at_most_once"  # May drop messages
    AT_LEAST_ONCE = "at_least_once"  # May duplicate
    EXACTLY_ONCE = "exactly_once"  # Once and only once


@dataclass
class SequenceNumber:
    """Sequence number for ordering."""
    counter: int
    timestamp: float
    node_id: str
    
    def __lt__(self, other: "SequenceNumber") -> bool:
        """Compare sequence numbers using hybrid logical clocks."""
        if self.counter != other.counter:
            return self.counter < other.counter
        return self.timestamp < other.timestamp


@dataclass
class OrderedMessage:
    """Message with ordering metadata."""
    message_id: str
    sender: str
    receiver: str
    content: Dict[str, Any]
    sequence: SequenceNumber
    causal_dependencies: List[str] = field(default_factory=list)  # Message IDs this depends on
    guarantee: OrderingGuarantee = OrderingGuarantee.AT_LEAST_ONCE
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class CausalOrderTracker:
    """
    Tracks causal dependencies between messages.
    
    Uses vector clock-like tracking to ensure causal ordering.
    A message can only be delivered after all its dependencies are delivered.
    """
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self._vector_clock: Dict[str, int] = defaultdict(int)
        self._pending: Dict[str, List[OrderedMessage]] = defaultdict(list)
        self._delivered: Set[str] = set()
        self._lock = asyncio.Lock()
    
    def increment_clock(self) -> int:
        """Increment local logical clock."""
        self._vector_clock[self.node_id] += 1
        return self._vector_clock[self.node_id]
    
    def merge_clock(self, other_clock: Dict[str, int]) -> None:
        """Merge another node's vector clock."""
        for node, counter in other_clock.items():
            self._vector_clock[node] = max(self._vector_clock[node], counter)
    
    def get_clock(self) -> Dict[str, int]:
        """Get current vector clock."""
        return dict(self._vector_clock)
    
    def is_ready(self, message: OrderedMessage) -> bool:
        """Check if message is ready to deliver based on causal dependencies."""
        # All dependencies must be delivered
        for dep_id in message.causal_dependencies:
            if dep_id not in self._delivered:
                return False
        
        # Vector clock must show all dependencies happened before this
        sender_clock = message.metadata.get("vector_clock", {})
        for node, counter in sender_clock.items():
            if self._vector_clock.get(node, 0) < counter:
                return False
        
        return True
    
    async def receive(self, message: OrderedMessage) -> bool:
        """
        Receive a message.
        
        Returns True if message should be delivered, False if pending.
        """
        async with self._lock:
            # Merge vector clock
            sender_clock = message.metadata.get("vector_clock", {})
            self.merge_clock(sender_clock)
            
            # Increment local clock
            self.increment_clock()
            
            # Check if ready
            if self.is_ready(message):
                self._delivered.add(message.message_id)
                return True
            
            # Add to pending
            self._pending[message.receiver].append(message)
            return False
    
    async def check_pending(self, receiver: str) -> List[OrderedMessage]:
        """Check and return any messages that are now ready."""
        async with self._lock:
            ready = []
            still_pending = []
            
            for msg in self._pending.get(receiver, []):
                if self.is_ready(msg):
                    ready.append(msg)
                    self._delivered.add(msg.message_id)
                else:
                    still_pending.append(msg)
            
            self._pending[receiver] = still_pending
            return ready
    
    async def get_pending_count(self, receiver: str) -> int:
        """Get count of pending messages for a receiver."""
        async with self._lock:
            return len(self._pending.get(receiver, []))


class FIFOMailbox:
    """
    FIFO mailbox for per-agent message ordering.
    
    Ensures messages to the same agent are delivered in order.
    """
    
    def __init__(
        self,
        agent_id: str,
        max_queue_size: int = 10000,
        delivery_callback: Optional[Callable[[OrderedMessage], None]] = None,
    ):
        self.agent_id = agent_id
        self.max_queue_size = max_queue_size
        self.delivery_callback = delivery_callback
        
        self._queue: deque[OrderedMessage] = deque()
        self._last_delivered_sequence: Dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()
        self._delivered_count = 0
        self._dropped_count = 0
    
    async def enqueue(self, message: OrderedMessage) -> bool:
        """
        Enqueue a message.
        
        Returns True if enqueued, False if dropped (queue full).
        """
        async with self._lock:
            # Check queue size
            if len(self._queue) >= self.max_queue_size:
                self._dropped_count += 1
                logger.warning(f"Mailbox {self.agent_id} full, dropping message")
                return False
            
            # Check sequence number (must be > last delivered)
            expected_seq = self._last_delivered_sequence.get(message.sender, 0)
            if message.sequence.counter <= expected_seq:
                # Out of order, still queue but mark
                logger.debug(
                    f"Out-of-order message {message.message_id} "
                    f"seq={message.sequence.counter} expected>{expected_seq}"
                )
            
            self._queue.append(message)
            return True
    
    async def dequeue(self) -> Optional[OrderedMessage]:
        """
        Dequeue the next message in order.
        
        Returns None if queue is empty.
        """
        async with self._lock:
            if not self._queue:
                return None
            
            # Find the next message in sequence order
            best_msg = None
            best_idx = -1
            
            for i, msg in enumerate(self._queue):
                sender_expected = self._last_delivered_sequence.get(msg.sender, 0)
                
                # Prefer messages in order from each sender
                if msg.sequence.counter > sender_expected:
                    if best_msg is None or msg.sequence < best_msg.sequence:
                        best_msg = msg
                        best_idx = i
            
            if best_idx >= 0:
                self._queue.remove(best_msg)
                self._last_delivered_sequence[best_msg.sender] = best_msg.sequence.counter
                self._delivered_count += 1
                return best_msg
            
            return None
    
    async def process_batch(self, max_messages: int = 100) -> List[OrderedMessage]:
        """Process up to max_messages."""
        messages = []
        for _ in range(max_messages):
            msg = await self.dequeue()
            if msg is None:
                break
            messages.append(msg)
        return messages
    
    async def get_queue_depth(self) -> int:
        """Get current queue depth."""
        async with self._lock:
            return len(self._queue)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get mailbox metrics."""
        return {
            "agent_id": self.agent_id,
            "queue_depth": len(self._queue),
            "max_queue_size": self.max_queue_size,
            "delivered_count": self._delivered_count,
            "dropped_count": self._dropped_count,
        }


class MessageOrderingController:
    """
    Controls message ordering across the multi-agent system.
    
    Features:
    - FIFO per-agent delivery
    - Causal ordering with vector clocks
    - Sequence number tracking
    - Delivery guarantees (exactly-once, at-least-once, at-most-once)
    - Duplicate detection
    """
    
    def __init__(
        self,
        node_id: str,
        max_mailbox_size: int = 10000,
    ):
        self.node_id = node_id
        self.max_mailbox_size = max_mailbox_size
        
        self._causal_tracker = CausalOrderTracker(node_id)
        self._mailboxes: Dict[str, FIFOMailbox] = {}
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._delivered_ids: Set[str] = set()
        self._lock = asyncio.Lock()
        
        # Delivery callbacks per agent
        self._delivery_callbacks: Dict[str, Callable] = {}
    
    def register_callback(
        self,
        agent_id: str,
        callback: Callable[[OrderedMessage], None],
    ) -> None:
        """Register delivery callback for an agent."""
        self._delivery_callbacks[agent_id] = callback
    
    def _get_or_create_mailbox(self, agent_id: str) -> FIFOMailbox:
        """Get or create mailbox for an agent."""
        if agent_id not in self._mailboxes:
            self._mailboxes[agent_id] = FIFOMailbox(
                agent_id=agent_id,
                max_queue_size=self.max_mailbox_size,
            )
        return self._mailboxes[agent_id]
    
    async def send(
        self,
        receiver: str,
        content: Dict[str, Any],
        causal_dependencies: Optional[List[str]] = None,
        guarantee: OrderingGuarantee = OrderingGuarantee.AT_LEAST_ONCE,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OrderedMessage:
        """
        Send a message with ordering metadata.
        
        This should be called by the sender side.
        """
        # Create sequence number
        counter = self._causal_tracker.increment_clock()
        sequence = SequenceNumber(
            counter=counter,
            timestamp=time.time(),
            node_id=self.node_id,
        )
        
        message = OrderedMessage(
            message_id=str(uuid4()),
            sender=self.node_id,
            receiver=receiver,
            content=content,
            sequence=sequence,
            causal_dependencies=causal_dependencies or [],
            guarantee=guarantee,
            metadata={
                **(metadata or {}),
                "vector_clock": self._causal_tracker.get_clock(),
            },
        )
        
        return message
    
    async def receive(self, message: OrderedMessage) -> bool:
        """
        Receive a message for delivery.
        
        This should be called by the receiver side.
        """
        # Check for duplicates
        async with self._lock:
            if message.message_id in self._delivered_ids:
                if message.guarantee == OrderingGuarantee.EXACTLY_ONCE:
                    return True  # Already delivered
                return False  # Skip duplicate
        
        # Check causal dependencies
        is_ready = await self._causal_tracker.receive(message)
        
        if not is_ready:
            return False  # Waiting for dependencies
        
        # Enqueue for FIFO delivery
        mailbox = self._get_or_create_mailbox(message.receiver)
        enqueued = await mailbox.enqueue(message)
        
        if not enqueued:
            logger.warning(f"Failed to enqueue message {message.message_id}")
        
        return enqueued
    
    async def deliver_to(self, agent_id: str) -> List[OrderedMessage]:
        """
        Deliver messages to an agent.
        
        Returns messages that were delivered.
        """
        mailbox = self._get_or_create_mailbox(agent_id)
        delivered = []
        
        while True:
            message = await mailbox.dequeue()
            if message is None:
                break
            
            # Mark as delivered (for exactly-once)
            async with self._lock:
                self._delivered_ids.add(message.message_id)
            
            delivered.append(message)
            
            # Call delivery callback
            if agent_id in self._delivery_callbacks:
                try:
                    callback = self._delivery_callbacks[agent_id]
                    if asyncio.iscoroutinefunction(callback):
                        await callback(message)
                    else:
                        callback(message)
                except Exception as e:
                    logger.error(f"Delivery callback failed: {e}")
        
        # Check for newly ready messages
        pending_ready = await self._causal_tracker.check_pending(agent_id)
        for msg in pending_ready:
            await mailbox.enqueue(msg)
        
        return delivered
    
    async def get_mailbox_status(self, agent_id: str) -> Dict[str, Any]:
        """Get status of an agent's mailbox."""
        mailbox = self._mailboxes.get(agent_id)
        if not mailbox:
            return {"agent_id": agent_id, "queue_depth": 0}
        
        return mailbox.get_metrics()
    
    async def get_all_mailbox_status(self) -> Dict[str, Any]:
        """Get status of all mailboxes."""
        return {
            agent_id: mailbox.get_metrics()
            for agent_id, mailbox in self._mailboxes.items()
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get ordering controller metrics."""
        total_queue = sum(len(m._queue) for m in self._mailboxes.values())
        
        return {
            "node_id": self.node_id,
            "mailbox_count": len(self._mailboxes),
            "total_queue_depth": total_queue,
            "delivered_count": len(self._delivered_ids),
            "vector_clock": self._causal_tracker.get_clock(),
        }
