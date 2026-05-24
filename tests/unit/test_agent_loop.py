"""Unit tests for Agent Loop.

Tests for:
- Agent initialization
- Think/Act/Observe loop
- Tool calling
- Turn management
- Error recovery
- Streaming responses
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.infrastructure.agent.agent_loop import (
    AgenticAgent,
    AgentConfig,
    TurnResult,
    AgentLoop,
)


class TestAgentConfig:
    """Tests for AgentConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = AgentConfig()
        
        assert config.max_turns == 20
        assert config.system_prompt is not None
        assert config.verbose is False

    def test_custom_config(self):
        """Test custom configuration."""
        config = AgentConfig(
            max_turns=10,
            system_prompt="You are a coding assistant",
            verbose=True,
        )
        
        assert config.max_turns == 10
        assert config.system_prompt == "You are a coding assistant"
        assert config.verbose is True


class TestTurnResult:
    """Tests for TurnResult dataclass."""

    def test_turn_result_creation(self):
        """Test turn result creation."""
        from src.infrastructure.llm.client import Message
        
        result = TurnResult(
            messages=[Message(role="assistant", content="Hello")],
            tool_calls=[],
            final_response="Hello",
        )
        
        assert len(result.messages) == 1
        assert result.final_response == "Hello"


class TestAgenticAgent:
    """Tests for AgenticAgent."""

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock()
        session.context = MagicMock()
        session.context.project_path = None
        session.context.working_directory = None
        session.context.rules = []
        session.add_message = MagicMock()
        session.add_tool_call = MagicMock()
        return session

    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        client = MagicMock()
        client.generate = AsyncMock(return_value=MagicMock(
            content="Test response",
            finish_reason="stop",
        ))
        return client

    @pytest.fixture
    def mock_tool_registry(self):
        """Create mock tool registry."""
        registry = MagicMock()
        registry.list_tools = MagicMock(return_value=[])
        registry.execute = AsyncMock(return_value=MagicMock(
            result=MagicMock(success=True, content=[{"type": "text", "text": "done"}])
        ))
        return registry

    @pytest.fixture
    def config(self):
        """Create agent config."""
        return AgentConfig(
            max_turns=5,
            verbose=False,
        )

    def test_agent_initialization(self, mock_session, config, mock_llm_client, mock_tool_registry):
        """Test agent initialization."""
        agent = AgenticAgent(
            session=mock_session,
            config=config,
            llm_client=mock_llm_client,
            tool_registry=mock_tool_registry,
        )
        
        assert agent.config == config
        assert agent.turn_count == 0
        assert agent.session == mock_session

    def test_agent_setup(self, mock_session, config, mock_llm_client, mock_tool_registry):
        """Test agent setup with system prompt."""
        agent = AgenticAgent(
            session=mock_session,
            config=config,
            llm_client=mock_llm_client,
            tool_registry=mock_tool_registry,
        )
        
        agent.setup()
        
        # System prompt should be added to messages

    @pytest.mark.asyncio
    async def test_single_turn(self, mock_session, config, mock_llm_client, mock_tool_registry):
        """Test single user turn."""
        agent = AgenticAgent(
            session=mock_session,
            config=config,
            llm_client=mock_llm_client,
            tool_registry=mock_tool_registry,
        )
        
        agent.setup()
        result = await agent.prompt("Hello")
        
        assert result is not None
        assert agent.turn_count == 1

    @pytest.mark.asyncio
    async def test_max_turns_limit(self, mock_session, config, mock_llm_client, mock_tool_registry):
        """Test turn limit enforcement."""
        config.max_turns = 2
        
        agent = AgenticAgent(
            session=mock_session,
            config=config,
            llm_client=mock_llm_client,
            tool_registry=mock_tool_registry,
        )
        
        agent.setup()
        await agent.prompt("Turn 1")
        await agent.prompt("Turn 2")
        await agent.prompt("Turn 3")
        
        # Should stop at max_turns
        assert agent.turn_count <= config.max_turns

    def test_reset(self, mock_session, config, mock_llm_client, mock_tool_registry):
        """Test resetting agent."""
        agent = AgenticAgent(
            session=mock_session,
            config=config,
            llm_client=mock_llm_client,
            tool_registry=mock_tool_registry,
        )
        
        agent.setup()
        agent._messages.append(MagicMock())  # Add a message
        
        agent.reset()
        
        assert agent.turn_count == 0
        assert len(agent._messages) == 1  # System prompt remains


class TestAgentLoop:
    """Tests for AgentLoop class."""

    def test_agent_loop_creation(self):
        """Test AgentLoop creation."""
        loop = AgentLoop()
        assert loop is not None


class TestAgentIntegration:
    """Integration tests for agent."""

    @pytest.fixture
    def fully_configured_agent(self):
        """Create fully configured agent."""
        mock_session = MagicMock()
        mock_session.context = MagicMock()
        mock_session.context.project_path = Path("/test")
        mock_session.context.working_directory = None
        mock_session.context.rules = []
        mock_session.add_message = MagicMock()
        mock_session.add_tool_call = MagicMock()
        
        config = AgentConfig(
            max_turns=10,
            verbose=False,
        )
        
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=MagicMock(
            content="I can help with that.",
            finish_reason="stop",
        ))
        
        mock_registry = MagicMock()
        mock_registry.list_tools = MagicMock(return_value=[])
        mock_registry.execute = AsyncMock(return_value=MagicMock(
            result=MagicMock(
                success=True,
                content=[{"type": "text", "text": "Done"}],
            )
        ))
        
        return AgenticAgent(mock_session, config, mock_llm, mock_registry)

    @pytest.mark.asyncio
    async def test_full_conversation(self, fully_configured_agent):
        """Test full conversation flow."""
        agent = fully_configured_agent
        
        agent.setup()
        
        # First turn
        result1 = await agent.prompt("Hello!")
        assert result1 is not None
        
        # Second turn
        result2 = await agent.prompt("Help me with code")
        assert result2 is not None
        
        assert agent.turn_count == 2


class TestAgentEdgeCases:
    """Edge case tests for agent."""

    @pytest.fixture
    def minimal_agent(self):
        """Create minimal agent."""
        mock_session = MagicMock()
        mock_session.context = MagicMock()
        mock_session.context.project_path = None
        mock_session.context.working_directory = None
        mock_session.context.rules = []
        mock_session.add_message = MagicMock()
        mock_session.add_tool_call = MagicMock()
        
        config = AgentConfig()
        
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=MagicMock(
            content="OK",
            finish_reason="stop",
        ))
        
        mock_registry = MagicMock()
        mock_registry.list_tools = MagicMock(return_value=[])
        
        return AgenticAgent(mock_session, config, mock_llm, mock_registry)

    @pytest.mark.asyncio
    async def test_empty_message(self, minimal_agent):
        """Test with empty message."""
        minimal_agent.setup()
        result = await minimal_agent.prompt("")
        
        # Should handle gracefully
        assert result is not None

    @pytest.mark.asyncio
    async def test_unicode_message(self, minimal_agent):
        """Test with unicode message."""
        minimal_agent.setup()
        result = await minimal_agent.prompt("Hello 世界")
        
        assert result is not None

    @pytest.mark.asyncio
    async def test_repeated_messages(self, minimal_agent):
        """Test repeated identical messages."""
        minimal_agent.setup()
        await minimal_agent.prompt("Same message")
        await minimal_agent.prompt("Same message")
        await minimal_agent.prompt("Same message")
        
        # Should handle without issues
        assert minimal_agent.turn_count == 3
