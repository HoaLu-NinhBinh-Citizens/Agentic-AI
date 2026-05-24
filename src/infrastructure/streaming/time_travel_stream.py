"""Advanced streaming with time-travel rules.

Features:
- Token buffering with smart flushing
- Backpressure handling
- Stream recovery
- Edit history with undo
- Content chunking
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Callable


class FlushStrategy(Enum):
    """When to flush buffered content."""
    ON_TOKEN = "on_token"
    ON_WORD = "on_word"
    ON_SENTENCE = "on_sentence"
    ON_PHRASE = "on_phrase"
    ON_TIMEOUT = "on_timeout"
    ON_TOOL_CALL = "on_tool_call"
    ON_DONE = "on_done"


@dataclass
class StreamToken:
    """A token in the stream."""
    content: str
    index: int
    timestamp: datetime = field(default_factory=datetime.now)
    token_type: str = "text"  # text, tool_call, error, done


@dataclass
class StreamChunk:
    """A chunk of streamed content."""
    content: str
    start_index: int
    end_index: int
    flush_reason: FlushStrategy = FlushStrategy.ON_TOKEN
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class StreamSnapshot:
    """A snapshot of stream state for time-travel."""
    content: str
    index: int
    timestamp: datetime
    tool_calls: list[dict]


class TimeTravelStreamBuffer:
    """Buffer with time-travel capability.
    
    Allows rewinding and replaying the stream.
    """
    
    def __init__(
        self,
        flush_strategy: FlushStrategy = FlushStrategy.ON_SENTENCE,
        flush_timeout: float = 0.5,
        max_buffer_size: int = 1000,
    ):
        self.flush_strategy = flush_strategy
        self.flush_timeout = flush_timeout
        self.max_buffer_size = max_buffer_size
        
        self._content: list[str] = []
        self._buffer: str = ""
        self._index: int = 0
        self._snapshots: list[StreamSnapshot] = []
        self._tool_calls: list[dict] = []
        self._last_flush: datetime = datetime.now()
        self._callbacks: list[Callable] = []
        self._finalized: bool = False
    
    def add_callback(self, callback: Callable) -> None:
        """Add a callback for new chunks."""
        self._callbacks.append(callback)
    
    async def add_token(self, token: StreamToken) -> list[StreamChunk]:
        """Add a token and return any flushed chunks."""
        chunks = []
        
        if token.token_type == "tool_call":
            # Flush buffer on tool call
            if self._buffer:
                chunk = self._flush_buffer(FlushStrategy.ON_TOOL_CALL)
                if chunk:
                    chunks.append(chunk)
            
            # Record tool call
            self._tool_calls.append({
                "index": self._index,
                "content": token.content,
                "timestamp": token.timestamp.isoformat(),
            })
            
        elif token.token_type == "error":
            # Flush on error
            if self._buffer:
                chunk = self._flush_buffer(FlushStrategy.ON_DONE)
                if chunk:
                    chunks.append(chunk)
        
        elif token.token_type == "text":
            # Add to buffer
            self._buffer += token.content
            self._content.append(token.content)
            self._index += 1
            
            # Check flush conditions
            if self._should_flush(token.content):
                chunk = self._flush_buffer(self.flush_strategy)
                if chunk:
                    chunks.append(chunk)
        
        elif token.token_type == "done":
            # Final flush
            if self._buffer:
                chunk = self._flush_buffer(FlushStrategy.ON_DONE)
                if chunk:
                    chunks.append(chunk)
            self._finalized = True
        
        # Fire callbacks
        for chunk in chunks:
            for callback in self._callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(chunk)
                    else:
                        callback(chunk)
                except:
                    pass
        
        return chunks
    
    def _should_flush(self, content: str) -> bool:
        """Check if buffer should be flushed."""
        if self.flush_strategy == FlushStrategy.ON_WORD:
            return content.strip() and not content[-1].isalnum()
        elif self.flush_strategy == FlushStrategy.ON_SENTENCE:
            return content in ".!?"
        elif self.flush_strategy == FlushStrategy.ON_PHRASE:
            return content in ".,;:!?\n"
        elif self.flush_strategy == FlushStrategy.ON_TIMEOUT:
            elapsed = (datetime.now() - self._last_flush).total_seconds()
            return elapsed >= self.flush_timeout
        elif self.flush_strategy == FlushStrategy.ON_TOKEN:
            return True
        return False
    
    def _flush_buffer(self, reason: FlushStrategy) -> StreamChunk | None:
        """Flush the buffer and return a chunk."""
        if not self._buffer:
            return None
        
        content = self._buffer
        start = self._index - len(content)
        
        chunk = StreamChunk(
            content=content,
            start_index=start,
            end_index=self._index,
            flush_reason=reason,
        )
        
        self._buffer = ""
        self._last_flush = datetime.now()
        
        return chunk
    
    def take_snapshot(self) -> StreamSnapshot:
        """Take a snapshot of current state."""
        snapshot = StreamSnapshot(
            content="".join(self._content),
            index=self._index,
            timestamp=datetime.now(),
            tool_calls=self._tool_calls.copy(),
        )
        self._snapshots.append(snapshot)
        return snapshot
    
    def travel_to(self, snapshot: StreamSnapshot) -> str:
        """Travel to a previous snapshot and return content."""
        # Find snapshot index
        idx = None
        for i, s in enumerate(self._snapshots):
            if s.timestamp == snapshot.timestamp:
                idx = i
                break
        
        if idx is None:
            raise ValueError("Snapshot not found")
        
        # Restore state
        self._content = list(snapshot.content)
        self._index = snapshot.index
        self._tool_calls = snapshot.tool_calls.copy()
        self._buffer = ""
        
        return snapshot.content
    
    def rewind(self, num_tokens: int) -> str:
        """Rewind by num_tokens and return content."""
        if num_tokens >= len(self._content):
            # Rewind all
            content = "".join(self._content)
            self._content = []
            self._index = 0
            return content
        
        # Rewind partial
        new_content = self._content[:-num_tokens]
        self._content = new_content
        self._index -= num_tokens
        
        return "".join(new_content)
    
    @property
    def content(self) -> str:
        """Get current content."""
        return "".join(self._content)
    
    @property
    def is_finalized(self) -> bool:
        """Check if stream is finalized."""
        return self._finalized


class StreamingFormatter:
    """Formats streamed content for display."""
    
    def __init__(self):
        self._formatters: dict[str, Callable] = {
            "code": self._format_code,
            "markdown": self._format_markdown,
            "json": self._format_json,
            "xml": self._format_xml,
            "table": self._format_table,
        }
    
    def format(self, content: str, format_type: str = "auto") -> str:
        """Format content based on type."""
        if format_type == "auto":
            format_type = self._detect_format(content)
        
        formatter = self._formatters.get(format_type, self._format_plain)
        return formatter(content)
    
    def _detect_format(self, content: str) -> str:
        """Auto-detect format."""
        content = content.strip()
        
        if content.startswith("```"):
            return "code"
        if content.startswith("{"):
            return "json"
        if content.startswith("<"):
            return "xml"
        if "\n|" in content and "---" in content:
            return "table"
        if "#" in content or "**" in content or "`" in content:
            return "markdown"
        
        return "plain"
    
    def _format_plain(self, content: str) -> str:
        """Format as plain text."""
        return content
    
    def _format_code(self, content: str) -> str:
        """Format code blocks."""
        # Extract language if present
        match = re.match(r"```(\w+)?\n?", content)
        if match:
            lang = match.group(1) or "text"
            content = content[match.end():]
            if content.endswith("```"):
                content = content[:-3]
            return f"```{lang}\n{content.strip()}\n```"
        return content
    
    def _format_markdown(self, content: str) -> str:
        """Format markdown with ANSI colors."""
        lines = content.split("\n")
        formatted = []
        
        for line in lines:
            if line.startswith("# "):
                formatted.append(f"\033[1;36m{line}\033[0m")  # Cyan bold
            elif line.startswith("## "):
                formatted.append(f"\033[1;35m{line}\033[0m")  # Magenta bold
            elif line.startswith("### "):
                formatted.append(f"\033[1;34m{line}\033[0m")  # Blue bold
            elif line.startswith("-"):
                formatted.append(f"  \033[33m•\033[0m {line[1:].strip()}")
            elif line.startswith("1."):
                formatted.append(f"  \033[32m{line[:2]}\033[0m{line[2:]}")
            elif "**" in line:
                # Bold
                line = re.sub(r"\*\*(.+?)\*\*", r"\033[1m\1\033[0m", line)
                formatted.append(line)
            elif "`" in line:
                # Inline code
                line = re.sub(r"`([^`]+)`", r"\033[33m\1\033[0m", line)
                formatted.append(line)
            else:
                formatted.append(line)
        
        return "\n".join(formatted)
    
    def _format_json(self, content: str) -> str:
        """Format JSON with colors."""
        import json
        
        try:
            data = json.loads(content)
            formatted = json.dumps(data, indent=2)
            
            # Simple syntax highlighting
            formatted = re.sub(
                r'"([^"]+)":',
                r'\033[33m"\1"\033[0m:',
                formatted
            )
            formatted = re.sub(
                r': "([^"]*)"',
                r': \033[32m"\1"\033[0m',
                formatted
            )
            formatted = re.sub(
                r': (\d+)',
                r': \033[36m\1\033[0m',
                formatted
            )
            formatted = re.sub(
                r': (true|false|null)',
                r': \033[35m\1\033[0m',
                formatted
            )
            
            return formatted
        except:
            return content
    
    def _format_xml(self, content: str) -> str:
        """Format XML with colors."""
        # Simple XML highlighting
        content = re.sub(
            r"</(\w+)>",
            r"\033[31m</\1>\033[0m",
            content
        )
        content = re.sub(
            r"<(\w+)",
            r"\033[34m<\1\033[0m",
            content
        )
        content = re.sub(
            r'(\w+)="([^"]*)"',
            r'\033[33m\1\033[0m="\033[32m\2\033[0m"',
            content
        )
        return content
    
    def _format_table(self, content: str) -> str:
        """Format table with borders."""
        lines = content.split("\n")
        formatted = []
        
        for line in lines:
            if "---" in line:
                formatted.append("\033[90m" + line + "\033[0m")
            elif "|" in line:
                parts = [p.strip() for p in line.split("|")]
                formatted.append("│ " + " │ ".join(parts) + " │")
            else:
                formatted.append(line)
        
        return "\n".join(formatted)


class StreamingPipeline:
    """Pipeline for processing streams."""
    
    def __init__(self, buffer: TimeTravelStreamBuffer):
        self.buffer = buffer
        self.formatter = StreamingFormatter()
        self._handlers: list[Callable] = []
    
    def add_handler(self, handler: Callable) -> None:
        """Add a handler for processed chunks."""
        self._handlers.append(handler)
    
    async def process(self, tokens: AsyncIterator[StreamToken]) -> str:
        """Process a stream of tokens."""
        content_parts = []
        
        async for token in tokens:
            chunks = await self.buffer.add_token(token)
            
            for chunk in chunks:
                # Format chunk
                formatted = self.formatter.format(chunk.content)
                
                # Apply handlers
                for handler in self._handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(formatted, chunk)
                        else:
                            handler(formatted, chunk)
                    except:
                        pass
                
                content_parts.append(formatted)
        
        return "".join(content_parts)


# Utility functions

async def stream_with_typing(
    tokens: AsyncIterator[str],
    typing_delay: float = 0.02,
) -> AsyncIterator[str]:
    """Stream tokens with typing effect."""
    import asyncio
    
    async for token in tokens:
        for char in token:
            yield char
            await asyncio.sleep(typing_delay)


async def stream_with_highlighting(
    tokens: AsyncIterator[str],
    language: str = "auto",
) -> AsyncIterator[str]:
    """Stream tokens with syntax highlighting."""
    formatter = StreamingFormatter()
    buffer = ""
    
    async for token in tokens:
        buffer += token
        
        # Try to format accumulated content
        try:
            formatted = formatter.format(buffer, language)
            yield formatted
        except:
            yield token


def chunk_text(text: str, chunk_size: int = 100) -> list[str]:
    """Split text into chunks."""
    words = text.split()
    chunks = []
    current = []
    current_len = 0
    
    for word in words:
        if current_len + len(word) + 1 > chunk_size and current:
            chunks.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += len(word) + 1
    
    if current:
        chunks.append(" ".join(current))
    
    return chunks
