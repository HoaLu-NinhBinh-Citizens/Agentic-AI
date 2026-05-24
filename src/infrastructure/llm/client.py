"""LLM client for Agentic-AI CLI.

Unified LLM interface with:
- Multiple provider support (Ollama, OpenAI, Anthropic)
- Streaming responses
- Tool calling
- Role-based routing (default, smol, slow, plan)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


class Provider(Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GROQ = "groq"
    GEMINI = "gemini"


class ModelRole(Enum):
    """LLM role for routing."""
    DEFAULT = "default"  # Normal turns
    SMOL = "smol"  # Cheap subagent fan-out
    SLOW = "slow"  # Deep reasoning
    PLAN = "plan"  # Plan mode
    COMMIT = "commit"  # Changelogs


@dataclass
class Message:
    """A message in the conversation."""
    role: str  # "system", "user", "assistant", "tool_result"
    content: str
    name: str | None = None
    tool_call_id: str | None = None


@dataclass
class ToolCall:
    """A tool call from the model."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMConfig:
    """Configuration for LLM provider."""
    provider: Provider = Provider.OLLAMA
    model: str = "qwen2.5-coder:7b"
    base_url: str = "http://localhost:11434"
    api_key: str | None = None
    temperature: float = 0.1
    max_tokens: int = 4096
    timeout: float = 120.0
    
    # Role-specific settings
    smol_model: str = "qwen2.5-coder:1.5b"
    slow_model: str = "qwen2.5-coder:14b"
    
    def get_model_for_role(self, role: ModelRole) -> str:
        """Get model name for role."""
        if role == ModelRole.SMOL:
            return self.smol_model
        elif role == ModelRole.SLOW:
            return self.slow_model
        return self.model


@dataclass
class LLMResponse:
    """Response from LLM."""
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] | None = None
    model: str = ""
    
    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMClient:
    """Unified LLM client.
    
    Supports multiple providers with a consistent interface.
    """
    
    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()
        self._client = None
    
    async def generate(
        self,
        messages: list[Message],
        role: ModelRole = ModelRole.DEFAULT,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        stream: bool = False,
    ) -> LLMResponse:
        """Generate a response.
        
        Args:
            messages: Conversation messages
            role: Model role for routing
            tools: Tool definitions (OpenAI format)
            temperature: Override default temperature
            stream: Enable streaming
            
        Returns:
            LLMResponse with content and tool calls
        """
        model = self.config.get_model_for_role(role)
        
        if self.config.provider == Provider.OLLAMA:
            return await self._generate_ollama(model, messages, tools, temperature, stream)
        elif self.config.provider == Provider.OPENAI:
            return await self._generate_openai(model, messages, tools, temperature)
        elif self.config.provider == Provider.ANTHROPIC:
            return await self._generate_anthropic(model, messages, tools, temperature)
        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")
    
    async def _generate_ollama(
        self,
        model: str,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
        stream: bool,
    ) -> LLMResponse:
        """Generate using Ollama."""
        import httpx
        
        payload = {
            "model": model,
            "messages": [self._format_message(m) for m in messages],
            "stream": stream,
            "options": {
                "temperature": temperature or self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }
        
        # Add tools if provided
        if tools:
            payload["tools"] = tools
        
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(
                    f"{self.config.base_url}/api/chat",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                
                content = data.get("message", {}).get("content", "")
                tool_calls = []
                
                # Parse tool calls
                if "tool_calls" in data.get("message", {}):
                    for tc in data["message"]["tool_calls"]:
                        tool_calls.append(ToolCall(
                            id=tc.get("id", ""),
                            name=tc.get("function", {}).get("name", ""),
                            arguments=json.loads(tc.get("function", {}).get("arguments", "{}")),
                        ))
                
                return LLMResponse(
                    content=content,
                    tool_calls=tool_calls,
                    model=model,
                )
                
        except httpx.HTTPError as e:
            logger.error(f"Ollama HTTP error: {e}")
            raise
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            raise
    
    async def _generate_openai(
        self,
        model: str,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
    ) -> LLMResponse:
        """Generate using OpenAI-compatible API."""
        import httpx
        
        payload = {
            "model": model,
            "messages": [self._format_message(m) for m in messages],
            "temperature": temperature or self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(
                    f"{self.config.base_url}/v1/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
                
                choice = data["choices"][0]
                content = choice.get("message", {}).get("content", "") or ""
                
                tool_calls = []
                for tc in choice.get("message", {}).get("tool_calls", []):
                    tool_calls.append(ToolCall(
                        id=tc["id"],
                        name=tc["function"]["name"],
                        arguments=json.loads(tc["function"]["arguments"]),
                    ))
                
                return LLMResponse(
                    content=content,
                    tool_calls=tool_calls,
                    finish_reason=choice.get("finish_reason", "stop"),
                    usage=data.get("usage"),
                    model=data.get("model", model),
                )
                
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            raise
    
    async def _generate_anthropic(
        self,
        model: str,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
    ) -> LLMResponse:
        """Generate using Anthropic API."""
        import httpx
        
        # Convert messages format
        anthropic_messages = []
        for m in messages:
            if m.role == "system":
                continue  # Handle separately
            anthropic_messages.append({
                "role": m.role,
                "content": m.content,
            })
        
        payload = {
            "model": model,
            "messages": anthropic_messages,
            "temperature": temperature or self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        
        if tools:
            payload["tools"] = tools
        
        headers = {"Content-Type": "application/json", "x-api-key": self.config.api_key}
        if self.config.api_key:
            headers["anthropic-version"] = "2023-06-01"
        
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
                
                content = ""
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        content += block.get("text", "")
                
                return LLMResponse(
                    content=content,
                    model=model,
                    usage={
                        "input_tokens": data.get("usage", {}).get("input_tokens"),
                        "output_tokens": data.get("usage", {}).get("output_tokens"),
                    },
                )
                
        except Exception as e:
            logger.error(f"Anthropic error: {e}")
            raise
    
    def _format_message(self, message: Message) -> dict[str, Any]:
        """Format message for API."""
        result = {
            "role": message.role,
            "content": message.content,
        }
        
        if message.name:
            result["name"] = message.name
        
        if message.tool_call_id:
            result["tool_call_id"] = message.tool_call_id
        
        return result
    
    async def stream(
        self,
        messages: list[Message],
        role: ModelRole = ModelRole.DEFAULT,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """Stream response tokens.
        
        Args:
            messages: Conversation messages
            role: Model role for routing
            tools: Tool definitions
            
        Yields:
            Individual tokens
        """
        import httpx
        
        model = self.config.get_model_for_role(role)
        
        if self.config.provider == Provider.OLLAMA:
            url = f"{self.config.base_url}/api/chat"
            payload = {
                "model": model,
                "messages": [self._format_message(m) for m in messages],
                "stream": True,
            }
            if tools:
                payload["tools"] = tools
            
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                async with client.stream("POST", url, json=payload) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                token = data.get("message", {}).get("content", "")
                                if token:
                                    yield token
                            except json.JSONDecodeError:
                                continue
        
        elif self.config.provider == Provider.OPENAI:
            url = f"{self.config.base_url}/v1/chat/completions"
            payload = {
                "model": model,
                "messages": [self._format_message(m) for m in messages],
                "stream": True,
            }
            if tools:
                payload["tools"] = tools
            
            headers = {"Content-Type": "application/json"}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                choices = data.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    token = delta.get("content", "")
                                    if token:
                                        yield token
                            except json.JSONDecodeError:
                                continue
    
    async def health_check(self) -> bool:
        """Check if provider is available."""
        import httpx
        
        if self.config.provider == Provider.OLLAMA:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"{self.config.base_url}/api/tags")
                    return response.status_code == 200
            except:
                return False
        
        elif self.config.provider == Provider.OPENAI:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    headers = {}
                    if self.config.api_key:
                        headers["Authorization"] = f"Bearer {self.config.api_key}"
                    response = await client.get(
                        f"{self.config.base_url}/v1/models",
                        headers=headers,
                    )
                    return response.status_code == 200
            except:
                return False
        
        return False


# Global client instance
_client: LLMClient | None = None


def get_llm_client(config: LLMConfig | None = None) -> LLMClient:
    """Get or create global LLM client."""
    global _client
    if _client is None or config is not None:
        _client = LLMClient(config)
    return _client


def configure_llm(config: LLMConfig) -> None:
    """Configure global LLM client."""
    global _client
    _client = LLMClient(config)
