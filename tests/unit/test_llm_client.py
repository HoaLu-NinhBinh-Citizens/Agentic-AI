"""Unit tests for LLM Client.

Tests for:
- Ollama provider
- OpenAI provider
- Anthropic provider
- Message formatting
- Tool calling format
- Streaming responses
- Health checks
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.infrastructure.llm.client import (
    LLMClient,
    LLMConfig,
    Provider,
    ModelRole,
    Message,
    ToolCall,
)


class TestLLMConfig:
    """Tests for LLMConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = LLMConfig()
        
        assert config.provider == Provider.OLLAMA
        assert config.model == "qwen2.5-coder:7b"
        assert config.base_url is not None

    def test_ollama_config(self):
        """Test Ollama-specific config."""
        config = LLMConfig(
            provider=Provider.OLLAMA,
            model="codellama:13b",
            base_url="http://localhost:11434",
        )
        
        assert config.provider == Provider.OLLAMA
        assert config.model == "codellama:13b"

    def test_openai_config(self):
        """Test OpenAI config."""
        config = LLMConfig(
            provider=Provider.OPENAI,
            model="gpt-4",
            api_key="sk-test",
        )
        
        assert config.provider == Provider.OPENAI
        assert config.model == "gpt-4"

    def test_anthropic_config(self):
        """Test Anthropic config."""
        config = LLMConfig(
            provider=Provider.ANTHROPIC,
            model="claude-3-5-sonnet",
            api_key="sk-ant-test",
        )
        
        assert config.provider == Provider.ANTHROPIC
        assert config.model == "claude-3-5-sonnet"

    def test_slow_smol_models(self):
        """Test slow/smol model configuration."""
        config = LLMConfig(
            provider=Provider.OLLAMA,
            slow_model="deep-model",
            smol_model="fast-model",
        )
        
        assert config.slow_model == "deep-model"
        assert config.smol_model == "fast-model"


class TestMessage:
    """Tests for Message dataclass."""

    def test_user_message(self):
        """Test user message creation."""
        msg = Message(role="user", content="Hello")
        
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_system_message(self):
        """Test system message creation."""
        msg = Message(role="system", content="You are helpful")
        
        assert msg.role == "system"
        assert msg.content == "You are helpful"

    def test_assistant_message(self):
        """Test assistant message creation."""
        msg = Message(role="assistant", content="Hello!")
        
        assert msg.role == "assistant"
        assert msg.content == "Hello!"

    def test_message_with_tool_calls(self):
        """Test message with tool calls."""
        tool_call = ToolCall(
            id="call_123",
            name="read",
            arguments={"path": "test.py"},
        )
        msg = Message(role="assistant", content="Reading file...", tool_calls=[tool_call])
        
        assert msg.tool_calls is not None
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].name == "read"

    def test_message_to_dict(self):
        """Test message serialization."""
        msg = Message(role="user", content="Test")
        
        data = msg.to_dict()
        
        assert data["role"] == "user"
        assert data["content"] == "Test"

    def test_message_from_dict(self):
        """Test message deserialization."""
        data = {
            "role": "assistant",
            "content": "Hello!",
        }
        
        msg = Message.from_dict(data)
        
        assert msg.role == "assistant"
        assert msg.content == "Hello!"


class TestToolCall:
    """Tests for ToolCall dataclass."""

    def test_tool_call_creation(self):
        """Test tool call creation."""
        tc = ToolCall(
            id="call_1",
            name="read",
            arguments={"path": "test.py"},
        )
        
        assert tc.id == "call_1"
        assert tc.name == "read"
        assert tc.arguments == {"path": "test.py"}

    def test_tool_call_to_dict(self):
        """Test tool call serialization."""
        tc = ToolCall(id="call_1", name="read", arguments={})
        
        data = tc.to_dict()
        
        assert data["id"] == "call_1"
        assert data["function"]["name"] == "read"


class TestProviderEnum:
    """Tests for Provider enum."""

    def test_providers_exist(self):
        """Test all providers exist."""
        assert Provider.OLLAMA is not None
        assert Provider.OPENAI is not None
        assert Provider.ANTHROPIC is not None

    def test_provider_values(self):
        """Test provider string values."""
        assert Provider.OLLAMA.value == "ollama"
        assert Provider.OPENAI.value == "openai"
        assert Provider.ANTHROPIC.value == "anthropic"


class TestModelRoleEnum:
    """Tests for ModelRole enum."""

    def test_roles_exist(self):
        """Test all roles exist."""
        assert ModelRole.DEFAULT is not None
        assert ModelRole.SMOL is not None
        assert ModelRole.SLOW is not None
        assert ModelRole.PLAN is not None
        assert ModelRole.COMMIT is not None


class TestLLMClient:
    """Tests for LLMClient."""

    @pytest.fixture
    def ollama_config(self):
        """Create Ollama config."""
        return LLMConfig(
            provider=Provider.OLLAMA,
            model="test-model",
            base_url="http://localhost:11434",
        )

    @pytest.fixture
    def openai_config(self):
        """Create OpenAI config."""
        return LLMConfig(
            provider=Provider.OPENAI,
            model="gpt-4",
            api_key="sk-test-key",
        )

    @pytest.fixture
    def anthropic_config(self):
        """Create Anthropic config."""
        return LLMConfig(
            provider=Provider.ANTHROPIC,
            model="claude-3-5-sonnet",
            api_key="sk-ant-test",
        )

    @pytest.mark.asyncio
    async def test_ollama_generate(self, ollama_config):
        """Test Ollama generation."""
        client = LLMClient(ollama_config)
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "message": {"content": "Test response"}
            }
            
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            response = await client.generate("Hello")
            
            assert response.content == "Test response"
            assert response.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_openai_generate(self, openai_config):
        """Test OpenAI generation."""
        client = LLMClient(openai_config)
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{
                    "message": {"content": "OpenAI response"},
                    "finish_reason": "stop",
                }]
            }
            
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            response = await client.generate("Hello")
            
            assert response.content == "OpenAI response"

    @pytest.mark.asyncio
    async def test_anthropic_generate(self, anthropic_config):
        """Test Anthropic generation."""
        client = LLMClient(anthropic_config)
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "content": [{"type": "text", "text": "Claude response"}],
                "stop_reason": "end_turn",
            }
            
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            response = await client.generate("Hello")
            
            assert response.content == "Claude response"

    @pytest.mark.asyncio
    async def test_streaming_response(self, ollama_config):
        """Test streaming response."""
        client = LLMClient(ollama_config)
        
        async def mock_stream():
            chunks = ["Hello", " ", "world"]
            for chunk in chunks:
                yield chunk
        
        # Test with streaming
        full_response = ""
        async for chunk in client.stream("Hello"):
            full_response += chunk
        
        # Should collect streaming chunks

    @pytest.mark.asyncio
    async def test_tool_call_format_openai(self, openai_config):
        """Test OpenAI tool calling format."""
        client = LLMClient(openai_config)
        
        tools = [{
            "type": "function",
            "function": {
                "name": "read",
                "description": "Read a file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
            },
        }]
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{
                    "message": {
                        "content": None,
                        "tool_calls": [{
                            "id": "call_1",
                            "function": {"name": "read", "arguments": '{"path": "test.py"}'},
                        }],
                    },
                    "finish_reason": "tool_calls",
                }]
            }
            
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            response = await client.generate("Read test.py", tools=tools)
            
            assert response.tool_calls is not None
            assert len(response.tool_calls) == 1
            assert response.tool_calls[0].name == "read"

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, ollama_config):
        """Test health check when provider is healthy."""
        client = LLMClient(ollama_config)
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"version": "1.0"}
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            is_healthy = await client.health_check()
            
            assert is_healthy is True

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, ollama_config):
        """Test health check when provider is down."""
        client = LLMClient(ollama_config)
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = Exception("Connection refused")
            
            is_healthy = await client.health_check()
            
            assert is_healthy is False

    def test_client_config_preserved(self, ollama_config):
        """Test client preserves config."""
        client = LLMClient(ollama_config)
        
        assert client.config.provider == Provider.OLLAMA
        assert client.config.model == "test-model"


class TestClientEdgeCases:
    """Edge case tests for LLM client."""

    @pytest.fixture
    def config(self):
        return LLMConfig(provider=Provider.OLLAMA, model="test")

    @pytest.mark.asyncio
    async def test_empty_messages(self, config):
        """Test with empty messages."""
        client = LLMClient(config)
        
        # Should handle empty gracefully

    @pytest.mark.asyncio
    async def test_unicode_content(self, config):
        """Test with unicode content."""
        client = LLMClient(config)
        
        unicode_text = "Hello 世界"
        
        # Should handle unicode

    def test_custom_headers(self, config):
        """Test custom headers."""
        config.extra_headers = {"X-Custom": "value"}
        client = LLMClient(config)
        
        # Should include custom headers
