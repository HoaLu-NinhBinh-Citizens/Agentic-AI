"""
Unit Tests for Phase 5: Distributed Multi-Agent
"""

import asyncio
from datetime import datetime

import pytest

from src.distributed.registry import (
    AgentRegistry,
    AgentInfo,
    AgentStatus,
)
from src.distributed.message import (
    AgentMessage,
    MessageType,
    MessagePriority,
    MessageBuilder,
)
from src.distributed.load_balancer import (
    LoadBalancer,
    LoadBalancingStrategy,
)
from src.distributed.consensus import (
    ConsensusModule,
    ConsensusState,
)


# ============ AgentRegistry Tests ============

class TestAgentRegistry:
    @pytest.mark.asyncio
    async def test_registry_creation(self):
        """Test registry creation."""
        registry = AgentRegistry()
        assert registry is not None
        assert registry.count() == 0

    @pytest.mark.asyncio
    async def test_register_agent(self):
        """Test agent registration."""
        registry = AgentRegistry()

        agent = AgentInfo(
            id="agent-1",
            name="Test Agent",
            capabilities=["build", "test"],
        )

        agent_id = await registry.register(agent)
        assert agent_id == "agent-1"
        assert registry.count() == 1

    @pytest.mark.asyncio
    async def test_unregister_agent(self):
        """Test agent unregistration."""
        registry = AgentRegistry()

        agent = AgentInfo(id="agent-1", name="Test Agent")
        await registry.register(agent)

        result = await registry.unregister("agent-1")
        assert result is True
        assert registry.count() == 0

    @pytest.mark.asyncio
    async def test_heartbeat(self):
        """Test agent heartbeat."""
        registry = AgentRegistry()

        agent = AgentInfo(id="agent-1", name="Test Agent")
        await registry.register(agent)

        result = await registry.heartbeat("agent-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_discover_by_capability(self):
        """Test capability-based discovery."""
        registry = AgentRegistry()

        await registry.register(AgentInfo(
            id="agent-1",
            name="Builder",
            capabilities=["build", "test"],
        ))

        await registry.register(AgentInfo(
            id="agent-2",
            name="Tester",
            capabilities=["test"],
        ))

        builders = registry.discover(capabilities=["build"])
        assert len(builders) == 1
        assert builders[0].id == "agent-1"

    @pytest.mark.asyncio
    async def test_get_healthy_agents(self):
        """Test getting healthy agents."""
        registry = AgentRegistry()

        await registry.register(AgentInfo(
            id="agent-1",
            name="Healthy",
            status=AgentStatus.HEALTHY,
        ))

        await registry.register(AgentInfo(
            id="agent-2",
            name="Offline",
            status=AgentStatus.OFFLINE,
        ))

        healthy = registry.get_healthy_agents()
        assert len(healthy) == 1


# ============ AgentMessage Tests ============

class TestAgentMessage:
    def test_message_creation(self):
        """Test message creation."""
        message = AgentMessage(
            sender="agent-1",
            receivers=["agent-2"],
            type=MessageType.REQUEST,
            payload={"data": "test"},
        )

        assert message.sender == "agent-1"
        assert message.receivers == ["agent-2"]
        assert message.type == MessageType.REQUEST

    def test_message_broadcast(self):
        """Test broadcast message."""
        message = AgentMessage(
            sender="agent-1",
            receivers=[],
            type=MessageType.BROADCAST,
            payload={"event": "shutdown"},
        )

        assert message.is_broadcast()

    def test_message_ttl(self):
        """Test TTL handling."""
        message = AgentMessage(
            sender="agent-1",
            receivers=["agent-2"],
            ttl=3,
        )

        assert message.ttl == 3
        assert not message.has_ttl_expired()

        message.decrement_ttl()
        assert message.ttl == 2

    def test_create_reply(self):
        """Test creating reply message."""
        original = AgentMessage(
            sender="agent-1",
            receivers=["agent-2"],
            payload={"query": "test"},
        )

        reply = original.create_reply({"answer": "result"})

        assert reply.sender == "agent-2"
        assert reply.receivers == ["agent-1"]
        assert reply.type == MessageType.RESPONSE
        assert reply.reply_to == original.id


class TestMessageBuilder:
    def test_create_task_request(self):
        """Test creating task request."""
        msg = MessageBuilder.create_task_request(
            sender="agent-1",
            receiver="agent-2",
            task_id="task-1",
            task_data={"action": "build"},
        )

        assert msg.type == MessageType.TASK_ASSIGN
        assert msg.sender == "agent-1"
        assert msg.receivers == ["agent-2"]
        assert msg.payload["task_id"] == "task-1"

    def test_create_notification(self):
        """Test creating notification."""
        msg = MessageBuilder.create_notification(
            sender="agent-1",
            receivers=["agent-2", "agent-3"],
            notification_type="status_update",
            data={"status": "completed"},
        )

        assert msg.type == MessageType.NOTIFICATION
        assert len(msg.receivers) == 2

    def test_create_broadcast(self):
        """Test creating broadcast."""
        msg = MessageBuilder.create_broadcast(
            sender="agent-1",
            broadcast_type="system_shutdown",
            data={"reason": "maintenance"},
        )

        assert msg.is_broadcast()
        assert msg.ttl == 5

    def test_create_heartbeat(self):
        """Test creating heartbeat."""
        msg = MessageBuilder.create_heartbeat(
            sender="agent-1",
            status="healthy",
        )

        assert msg.type == MessageType.HEARTBEAT


# ============ LoadBalancer Tests ============

class TestLoadBalancer:
    def test_balancer_creation(self):
        """Test load balancer creation."""
        lb = LoadBalancer()
        assert lb is not None
        assert lb.strategy == LoadBalancingStrategy.LEAST_LOADED

    def test_least_loaded_strategy(self):
        """Test least loaded strategy."""
        lb = LoadBalancer(strategy=LoadBalancingStrategy.LEAST_LOADED)

        lb.add_agent(AgentInfo(id="a1", name="High", status=AgentStatus.HEALTHY, load=0.9))
        lb.add_agent(AgentInfo(id="a2", name="Low", status=AgentStatus.HEALTHY, load=0.1))

        selected = lb.select()
        assert selected is not None
        assert selected.id == "a2"

    def test_record_request(self):
        """Test recording requests."""
        lb = LoadBalancer()

        agent = AgentInfo(id="agent-1", name="Test", status=AgentStatus.HEALTHY)
        lb.add_agent(agent)

        lb.record_request_start("agent-1")
        stats = lb.get_agent_stats("agent-1")

        assert stats is not None
        assert stats["active_connections"] == 1

        lb.record_request_end("agent-1")
        stats = lb.get_agent_stats("agent-1")

        assert stats["active_connections"] == 0


# ============ ConsensusModule Tests ============

class TestConsensusModule:
    def test_consensus_creation(self):
        """Test consensus module creation."""
        consensus = ConsensusModule(
            node_id="node-1",
            peers=["node-2", "node-3"],
        )

        assert consensus.node_id == "node-1"
        assert consensus.state == ConsensusState.FOLLOWER
        assert consensus.term == 0

    def test_is_leader(self):
        """Test leader check."""
        consensus = ConsensusModule(node_id="node-1")
        assert not consensus.is_leader()

    def test_get_state(self):
        """Test getting state."""
        consensus = ConsensusModule(node_id="node-1", peers=["node-2"])

        state = consensus.get_state()

        assert state["node_id"] == "node-1"
        assert state["state"] == "follower"
        assert state["term"] == 0

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Test starting and stopping consensus."""
        consensus = ConsensusModule(node_id="node-1")

        await consensus.start()
        assert consensus._running

        await consensus.stop()
        assert not consensus._running

    @pytest.mark.asyncio
    async def test_vote_request(self):
        """Test handling vote request."""
        consensus = ConsensusModule(node_id="node-2")

        granted = consensus.handle_vote_request(
            candidate_id="node-1",
            term=1,
            last_log_index=0,
            last_log_term=0,
        )

        assert granted
        assert consensus.term == 1
        assert consensus._voted_for == "node-1"


class TestConsensusState:
    def test_consensus_state_values(self):
        """Test consensus state values."""
        assert ConsensusState.FOLLOWER.value == "follower"
        assert ConsensusState.CANDIDATE.value == "candidate"
        assert ConsensusState.LEADER.value == "leader"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
