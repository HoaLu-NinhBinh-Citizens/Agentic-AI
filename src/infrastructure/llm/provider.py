"""Provider interface for LLM backends with streaming and tool call support.

This module defines the unified interface that all LLM providers must implement
to ensure consistent behavior across different backends.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


class StreamEventType(Enum):
    """Types of events in a streaming response."""

    TOKEN = "token"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_START = "tool_call_start"
    DONE = "done"
    ERROR = "error"


@dataclass
class StreamToken:
    """A text token in the stream."""

    content: str
    index: int = 0


@dataclass
class StreamToolCallDelta:
    """A delta update for a tool call's arguments."""

    index: int
    call_id: str
    function_name: str
    arguments: str


@dataclass
class StreamToolCallStart:
    """Indicates the start of a tool call."""

    index: int
    call_id: str
    function_name: str


@dataclass
class StreamDone:
    """Indicates the stream is complete."""

    finish_reason: str
    completion_tokens: int | None = None


@dataclass
class StreamError:
    """Indicates an error during streaming."""

    code: str
    message: str


@dataclass
class StreamEvent:
    """A unified stream event."""

    type: StreamEventType
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def token(cls, content: str, index: int = 0) -> StreamEvent:
        return cls(type=StreamEventType.TOKEN, data={"content": content, "index": index})

    @classmethod
    def tool_call_delta(
        cls,
        index: int,
        call_id: str,
        function_name: str,
        arguments: str,
    ) -> StreamEvent:
        return cls(
            type=StreamEventType.TOOL_CALL_DELTA,
            data={
                "index": index,
                "call_id": call_id,
                "function_name": function_name,
                "arguments": arguments,
            },
        )

    @classmethod
    def tool_call_start(
        cls,
        index: int,
        call_id: str,
        function_name: str,
    ) -> StreamEvent:
        return cls(
            type=StreamEventType.TOOL_CALL_START,
            data={
                "index": index,
                "call_id": call_id,
                "function_name": function_name,
            },
        )

    @classmethod
    def done(cls, finish_reason: str, completion_tokens: int | None = None) -> StreamEvent:
        return cls(
            type=StreamEventType.DONE,
            data={"finish_reason": finish_reason, "completion_tokens": completion_tokens},
        )

    @classmethod
    def error(cls, code: str, message: str) -> StreamEvent:
        return cls(type=StreamEventType.ERROR, data={"code": code, "message": message})


@dataclass
class ToolCall:
    """A parsed tool call from LLM response."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    """Result from executing a tool call."""

    call_id: str
    tool_name: str
    success: bool
    content: str | None = None
    error: str | None = None
    duration_ms: float = 0.0
    retry_count: int = 0


@dataclass
class LLMProviderConfig:
    """Configuration for LLM providers with timeout and retry settings."""
    
    # Timeout settings (in seconds)
    connect_timeout: float = 15.0
    read_timeout: float = 120.0
    total_timeout: float = 180.0  # Max total time for a request
    
    # Retry settings
    max_retries: int = 3
    retry_backoff_base: float = 1.0  # Exponential backoff base
    retry_jitter: float = 0.1  # Random jitter factor
    
    # Rate limiting
    requests_per_minute: int = 60
    requests_per_second: int = 10


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    All providers must implement streaming and tool call support.
    
    FIX: Added timeout configuration and timeout enforcement.
    """

    def __init__(self, name: str, config: LLMProviderConfig | None = None) -> None:
        """Initialize the provider.

        Args:
            name: Unique identifier for this provider.
            config: Provider configuration with timeouts.
        """
        self._name = name
        self._circuit_state = "closed"
        self._config = config or LLMProviderConfig()
    
    @property
    def config(self) -> LLMProviderConfig:
        """Get provider configuration."""
        return self._config
    
    @property
    def name(self) -> str:
        """Get provider name."""
        return self._name

    @property
    def circuit_state(self) -> str:
        """Get circuit breaker state."""
        return self._circuit_state

    @circuit_state.setter
    def circuit_state(self, value: str) -> None:
        """Set circuit breaker state."""
        self._circuit_state = value
    
    def get_timeout(self, prompt_length: int = 0) -> tuple[float, float]:
        """Get connect and read timeouts.
        
        Can be overridden by providers to adjust based on request size.
        
        Args:
            prompt_length: Length of prompt in characters.
            
        Returns:
            Tuple of (connect_timeout, read_timeout) in seconds.
        """
        return self._config.connect_timeout, self._config.read_timeout

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream chat completion with tool call support.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            tools: Optional list of tool definitions.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.

        Yields:
            StreamEvent objects representing the response.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is available and healthy.

        Returns:
            True if provider is healthy.
        """
        pass

    def supports_tools(self) -> bool:
        """Check if provider supports tool calling.

        Returns:
            True if tool calling is supported.
        """
        return True

    def supports_streaming(self) -> bool:
        """Check if provider supports streaming.

        Returns:
            True if streaming is supported.
        """
        return True
