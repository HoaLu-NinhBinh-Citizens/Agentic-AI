"""Streaming Output System - Real-time agent response streaming.

This module provides streaming output similar to Codex/ChatGPT:
- Token-by-token streaming
- SSE (Server-Sent Events) support
- WebSocket support
- Progress updates
- Chunk buffering
"""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Optional

import structlog

logger = structlog.get_logger(__name__)


class StreamEventType(Enum):
    """Types of streaming events."""
    TOKEN = "token"
    CHUNK = "chunk"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    STEP_START = "step_start"
    STEP_END = "step_end"
    ERROR = "error"
    COMPLETE = "complete"
    METADATA = "metadata"


@dataclass
class StreamEvent:
    """A streaming event."""
    type: StreamEventType
    content: str = ""
    data: Optional[dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)
    chunk_id: Optional[str] = None
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps({
            "type": self.type.value,
            "content": self.content,
            "data": self.data,
            "timestamp": self.timestamp,
            "chunk_id": self.chunk_id,
        })
    
    @classmethod
    def from_json(cls, json_str: str) -> StreamEvent:
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls(
            type=StreamEventType(data["type"]),
            content=data.get("content", ""),
            data=data.get("data"),
            timestamp=data.get("timestamp", time.time()),
            chunk_id=data.get("chunk_id"),
        )


@dataclass
class StreamConfig:
    """Configuration for streaming."""
    buffer_size: int = 10  # Tokens before flush
    flush_interval: float = 0.1  # Seconds
    include_timestamps: bool = True
    include_token_count: bool = True
    chunk_delimiter: str = ""


class StreamBuffer:
    """Buffer for accumulating streaming tokens."""
    
    def __init__(self, config: Optional[StreamConfig] = None):
        self.config = config or StreamConfig()
        self._buffer: list[str] = []
        self._last_flush: float = time.time()
        self._token_count: int = 0
    
    def add(self, token: str) -> list[str]:
        """Add token to buffer, return chunks to flush."""
        self._buffer.append(token)
        self._token_count += 1
        
        # Flush conditions
        should_flush = (
            len(self._buffer) >= self.config.buffer_size or
            time.time() - self._last_flush >= self.config.flush_interval
        )
        
        if should_flush:
            return self.flush()
        return []
    
    def flush(self) -> list[str]:
        """Flush buffer and return content."""
        if not self._buffer:
            return []
        
        content = self.config.chunk_delimiter.join(self._buffer)
        self._buffer = []
        self._last_flush = time.time()
        return [content]
    
    @property
    def token_count(self) -> int:
        """Get total token count."""
        return self._token_count


class StreamSink(ABC):
    """Abstract base for streaming destinations."""
    
    @abstractmethod
    async def send(self, event: StreamEvent) -> None:
        """Send an event."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close the stream."""
        pass


class AsyncIteratorSink(StreamSink):
    """Stream to an async iterator (for WebSocket/SSE)."""
    
    def __init__(self):
        self._queue: asyncio.Queue[Optional[StreamEvent]] = asyncio.Queue()
        self._closed: bool = False
    
    async def send(self, event: StreamEvent) -> None:
        """Queue an event."""
        if not self._closed:
            await self._queue.put(event)
    
    async def close(self) -> None:
        """Close and signal end."""
        self._closed = True
        await self._queue.put(None)  # Signal end
    
    async def __aiter__(self) -> AsyncGenerator[StreamEvent, None]:
        """Iterate over events."""
        while True:
            event = await self._queue.get()
            if event is None:
                break
            yield event


class CallbackSink(StreamSink):
    """Stream to a callback function."""
    
    def __init__(self, callback: Callable[[StreamEvent], None]):
        self._callback = callback
    
    async def send(self, event: StreamEvent) -> None:
        """Send via callback."""
        self._callback(event)
    
    async def close(self) -> None:
        """No-op for callback."""
        pass


class PrintSink(StreamSink):
    """Stream to stdout for debugging."""
    
    def __init__(self, prefix: str = ""):
        self.prefix = prefix
        self._count = 0
    
    async def send(self, event: StreamEvent) -> None:
        """Print event."""
        if event.type == StreamEventType.TOKEN:
            print(f"{self.prefix}{event.content}", end="", flush=True)
        elif event.type == StreamEventType.THOUGHT:
            print(f"{self.prefix}[THINKING] {event.content}", flush=True)
        elif event.type == StreamEventType.TOOL_CALL:
            print(f"{self.prefix}[TOOL] {event.content}", flush=True)
        elif event.type == StreamEventType.ERROR:
            print(f"{self.prefix}[ERROR] {event.content}", flush=True)
        self._count += 1
    
    async def close(self) -> None:
        """End line."""
        print()


class StreamingAgent:
    """
    Agent with streaming output support.
    
    Usage:
        async def main():
            sink = PrintSink("[AI] ")
            agent = StreamingAgent(sink=sink)
            
            await agent.run("Analyze CARV firmware")
            await sink.close()
        
        asyncio.run(main())
    """
    
    def __init__(
        self,
        sink: Optional[StreamSink] = None,
        config: Optional[StreamConfig] = None,
    ):
        self.sink = sink or PrintSink()
        self.config = config or StreamConfig()
        self.buffer = StreamBuffer(self.config)
    
    async def _emit(self, event: StreamEvent) -> None:
        """Emit a stream event."""
        await self.sink.send(event)
    
    async def stream_token(self, token: str) -> None:
        """Stream a single token."""
        event = StreamEvent(
            type=StreamEventType.TOKEN,
            content=token,
        )
        
        # Buffer tokens
        chunks = self.buffer.add(token)
        for chunk in chunks:
            chunk_event = StreamEvent(
                type=StreamEventType.CHUNK,
                content=chunk,
                data={"token_count": self.buffer.token_count},
            )
            await self._emit(chunk_event)
    
    async def stream_thinking(self, thought: str) -> None:
        """Stream a thinking/reasoning step."""
        event = StreamEvent(
            type=StreamEventType.THINKING,
            content=thought,
        )
        await self._emit(event)
    
    async def stream_tool_call(self, tool: str, args: dict[str, Any]) -> None:
        """Stream a tool call."""
        event = StreamEvent(
            type=StreamEventType.TOOL_CALL,
            content=f"{tool}({args})",
            data={"tool": tool, "args": args},
        )
        await self._emit(event)
    
    async def stream_tool_result(self, tool: str, result: Any) -> None:
        """Stream a tool result."""
        result_str = str(result)[:200]  # Truncate
        event = StreamEvent(
            type=StreamEventType.TOOL_RESULT,
            content=result_str,
            data={"tool": tool, "result": result},
        )
        await self._emit(event)
    
    async def stream_step(self, step: str, start: bool = True) -> None:
        """Stream step start/end."""
        event = StreamEvent(
            type=StreamEventType.STEP_START if start else StreamEventType.STEP_END,
            content=step,
        )
        await self._emit(event)
    
    async def stream_error(self, error: str) -> None:
        """Stream an error."""
        event = StreamEvent(
            type=StreamEventType.ERROR,
            content=error,
        )
        await self._emit(event)
    
    async def stream_complete(self, summary: str = "") -> None:
        """Stream completion."""
        # Flush buffer
        remaining = self.buffer.flush()
        for chunk in remaining:
            event = StreamEvent(
                type=StreamEventType.CHUNK,
                content=chunk,
            )
            await self._emit(event)
        
        event = StreamEvent(
            type=StreamEventType.COMPLETE,
            content=summary,
            data={
                "total_tokens": self.buffer.token_count,
                "timestamp": datetime.now().isoformat(),
            },
        )
        await self._emit(event)
    
    async def stream_metadata(self, key: str, value: Any) -> None:
        """Stream metadata."""
        event = StreamEvent(
            type=StreamEventType.METADATA,
            content="",
            data={key: value},
        )
        await self._emit(event)
    
    async def close(self) -> None:
        """Close the stream."""
        await self.sink.close()


class SSEServer:
    """
    SSE (Server-Sent Events) streaming server.
    
    Usage:
        from aiohttp import web
        
        async def handler(request):
            sink = AsyncIteratorSink()
            agent = StreamingAgent(sink=sink)
            
            # Start agent in background
            asyncio.create_task(agent.run(request['task']))
            
            # Stream as SSE
            response = web.StreamResponse(
                status=200,
                reason='OK',
                headers={'Content-Type': 'text/event-stream'},
            )
            await response.prepare(request)
            
            async for event in sink:
                await response.write(f"data: {event.to_json()}\n\n".encode())
            
            await response.write_eof()
            return response
    """
    
    @staticmethod
    def format_sse(event: StreamEvent) -> bytes:
        """Format event as SSE data."""
        return f"data: {event.to_json()}\n\n".encode()
    
    @staticmethod
    def parse_accept(accept_header: str) -> bool:
        """Check if client accepts SSE."""
        return "text/event-stream" in accept_header


class WebSocketStream:
    """
    WebSocket streaming support.
    
    Usage:
        async with WebSocketStream(ws) as ws_stream:
            agent = StreamingAgent(sink=ws_stream)
            await agent.run("Analyze CARV firmware")
    """
    
    def __init__(self, websocket):
        self.ws = websocket
        self._sink = AsyncIteratorSink()
    
    async def __aenter__(self) -> StreamingAgent:
        """Enter context."""
        return StreamingAgent(sink=self._sink)
    
    async def __aexit__(self, *args) -> None:
        """Exit context."""
        await self._sink.close()
    
    async def send(self, event: StreamEvent) -> None:
        """Send via WebSocket."""
        await self.ws.send_str(event.to_json())


async def stream_text(
    text: str,
    sink: StreamSink,
    delay: float = 0.02,
) -> None:
    """
    Stream text character by character.
    
    Usage:
        await stream_text("Hello, world!", PrintSink())
    """
    buffer = StreamBuffer()
    
    for char in text:
        await sink.send(StreamEvent(
            type=StreamEventType.TOKEN,
            content=char,
        ))
        await asyncio.sleep(delay)


async def stream_tokens(
    tokens: list[str],
    sink: StreamSink,
) -> None:
    """Stream tokens."""
    for token in tokens:
        await sink.send(StreamEvent(
            type=StreamEventType.TOKEN,
            content=token,
        ))
    await sink.close()


if __name__ == "__main__":
    async def demo():
        print("Streaming Demo")
        print("=" * 40)
        
        sink = PrintSink("[AI] ")
        agent = StreamingAgent(sink=sink)
        
        await agent.stream_thinking("Let me analyze the CARV firmware...")
        await asyncio.sleep(0.5)
        
        await agent.stream_tool_call("analyze_firmware", {"project": "EngineCar"})
        await asyncio.sleep(0.3)
        
        await agent.stream_tool_result("analyze_firmware", "STM32F407, FreeRTOS, HAL")
        
        await agent.stream_token("Analyzed successfully!")
        await agent.stream_token(" Found ")
        await agent.stream_token("5 components.")
        
        await agent.stream_complete("Analysis complete")
        await agent.close()
        
        print("\n" + "=" * 40)
        print("Done!")
    
    asyncio.run(demo())
