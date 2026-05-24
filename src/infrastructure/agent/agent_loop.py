"""Agent loop for Agentic-AI CLI.

Inspired by oh-my-pi's agent loop:
- Think/Act/Observe pattern
- Tool calling with result injection
- Streaming responses
- Session state management
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator

from .llm.client import (
    LLMClient,
    LLMConfig,
    LLMResponse,
    Message,
    ModelRole,
    get_llm_client,
    configure_llm,
)
from .session.session_manager import Session
from .tools.tool_registry import ToolRegistry, ToolCallRequest, ToolCallResponse

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for agent behavior."""
    max_turns: int = 20
    max_tool_calls_per_turn: int = 10
    timeout_per_tool: float = 60.0
    verbose: bool = False
    
    # System prompt
    system_prompt: str = """You are Agentic-AI, a helpful coding assistant.

You have access to these tools:
- read: Read file content
- write: Write file content
- edit: Edit file content using old/new content
- find: Find files by glob pattern
- search: Search for regex pattern in files
- bash: Execute shell commands

Use tools when needed to help the user. Be concise and helpful."""


@dataclass
class TurnResult:
    """Result of a single turn."""
    messages: list[Message]
    tool_calls: list[dict[str, Any]]
    final_response: str


class AgenticAgent:
    """Agent loop with tool calling.
    
    Like omp's agent:
    - Takes user prompts
    - Calls LLM with tool definitions
    - Executes tools
    - Returns responses
    """
    
    def __init__(
        self,
        session: Session,
        config: AgentConfig | None = None,
        llm_client: LLMClient | None = None,
        tool_registry: ToolRegistry | None = None,
    ):
        self.session = session
        self.config = config or AgentConfig()
        self.llm = llm_client or get_llm_client()
        self.tools = tool_registry
        
        # State
        self.turn_count = 0
        self._messages: list[Message] = []
        self._current_tool_calls: list[dict[str, Any]] = []
    
    def setup(self) -> None:
        """Setup agent with system prompt and tools."""
        # Add system prompt
        self._messages.append(Message(
            role="system",
            content=self.config.system_prompt,
        ))
        
        # Add project context if available
        if self.session.context.project_path:
            context = f"\n\nCurrent project: {self.session.context.project_path}\n"
            context += f"Working directory: {self.session.context.working_directory or self.session.context.project_path}\n"
            
            if self.session.context.rules:
                context += f"\nDiscovered rules:\n"
                for rule in self.session.context.rules:
                    context += f"  - {rule}\n"
            
            self._messages.append(Message(
                role="system",
                content=context,
            ))
    
    async def prompt(self, user_input: str) -> TurnResult:
        """Process a user prompt.
        
        Args:
            user_input: The user's message
            
        Returns:
            TurnResult with messages, tool calls, and final response
        """
        self.turn_count += 1
        self._current_tool_calls = []
        
        # Add user message
        self._messages.append(Message(
            role="user",
            content=user_input,
        ))
        
        # Convert to session messages
        self.session.add_message("user", user_input)
        
        if self.config.verbose:
            print(f"\n[Turn {self.turn_count}]")
        
        # Run the loop
        try:
            await self._run_loop()
        except Exception as e:
            logger.exception("Agent loop error")
            error_msg = f"Error: {str(e)}"
            self._messages.append(Message(role="assistant", content=error_msg))
            return TurnResult(
                messages=self._messages[-1:],
                tool_calls=self._current_tool_calls,
                final_response=error_msg,
            )
        
        # Get final response
        final_msg = self._messages[-1] if self._messages else Message("assistant", "")
        
        return TurnResult(
            messages=self._messages[-10:],  # Last 10 messages
            tool_calls=self._current_tool_calls,
            final_response=final_msg.content,
        )
    
    async def _run_loop(self) -> None:
        """Run the think-act-observe loop."""
        while self.turn_count <= self.config.max_turns:
            # Generate response
            response = await self._generate()
            
            # Add assistant message
            self._messages.append(Message(
                role="assistant",
                content=response.content,
            ))
            
            # Check for tool calls
            if not response.tool_calls:
                # No tool calls, we're done
                break
            
            # Execute tool calls
            for tc in response.tool_calls:
                await self._execute_tool_call(tc)
            
            # Add user message to continue loop
            # The LLM will see tool results in context
    
    async def _generate(self) -> LLMResponse:
        """Generate LLM response."""
        # Get tool definitions
        tools = None
        if self.tools:
            tools = self.tools.to_openai_format()
        
        # Generate
        response = await self.llm.generate(
            messages=self._messages,
            tools=tools,
        )
        
        return response
    
    async def _execute_tool_call(self, tool_call) -> None:
        """Execute a tool call."""
        name = tool_call.name
        args = tool_call.arguments
        
        if self.config.verbose:
            print(f"\n  [Tool: {name}]")
            if len(str(args)) < 200:
                print(f"  [Args: {args}]")
        
        # Create request
        request = ToolCallRequest(
            name=name,
            arguments=args,
            call_id=tool_call.id,
            timeout_seconds=self.config.timeout_per_tool,
        )
        
        # Execute
        if self.tools:
            response = await self.tools.execute(request)
        else:
            response = ToolCallResponse(
                request=request,
                result=self._execute_builtin_tool(name, args),
            )
        
        # Format result
        result_content = self._format_tool_result(response.result)
        
        # Add tool result message
        self._messages.append(Message(
            role="tool_result",
            content=result_content,
            name=name,
            tool_call_id=tool_call.id,
        ))
        
        # Record in session
        tc_record = self.session.add_tool_call(name, args)
        tc_record.complete(result=result_content)
        self._current_tool_calls.append({
            "id": tool_call.id,
            "name": name,
            "arguments": args,
            "result": result_content,
        })
        
        # Print result
        if self.config.verbose:
            if len(result_content) < 300:
                print(f"  [Result: {result_content}]")
            else:
                print(f"  [Result: {result_content[:300]}...]")
    
    def _execute_builtin_tool(self, name: str, args: dict[str, Any]):
        """Execute built-in tools when no registry."""
        from ..tools.tool_registry import ToolResult
        
        # Simple file tools
        if name == "read":
            from pathlib import Path
            path = Path(args.get("path", ""))
            if path.exists():
                content = path.read_text(encoding="utf-8", errors="replace")
                return ToolResult(
                    tool_name=name,
                    success=True,
                    content=[{"type": "text", "text": content[:5000]}],
                )
            return ToolResult(tool_name=name, success=False, error="File not found", is_error=True)
        
        elif name == "write":
            from pathlib import Path
            path = Path(args.get("path", ""))
            content = args.get("content", "")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return ToolResult(
                tool_name=name,
                success=True,
                content=[{"type": "text", "text": f"Wrote {len(content)} bytes to {path}"}],
            )
        
        elif name == "bash":
            import subprocess
            result = subprocess.run(
                args.get("command", ""),
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_per_tool,
            )
            return ToolResult(
                tool_name=name,
                success=result.returncode == 0,
                content=[{"type": "text", "text": result.stdout + result.stderr}],
            )
        
        elif name == "search":
            import re
            from pathlib import Path
            
            pattern = args.get("pattern", "")
            paths = args.get("paths", ["."])
            
            matches = []
            for path_str in paths:
                path = Path(path_str)
                if path.is_file():
                    try:
                        content = path.read_text(encoding="utf-8", errors="ignore")
                        for i, line in enumerate(content.splitlines(), 1):
                            if re.search(pattern, line):
                                matches.append(f"{path}:{i}: {line.rstrip()}")
                    except:
                        pass
            
            return ToolResult(
                tool_name=name,
                success=True,
                content=[{"type": "text", "text": "\n".join(matches[:100]) or "No matches"}],
            )
        
        return ToolResult(
            tool_name=name,
            success=False,
            error=f"Unknown tool: {name}",
            is_error=True,
        )
    
    def _format_tool_result(self, result) -> str:
        """Format tool result for LLM."""
        if result.is_error:
            return f"Error: {result.error}"
        
        if result.content:
            texts = []
            for block in result.content:
                if block.get("type") == "text":
                    texts.append(block["text"])
            return "\n".join(texts)
        
        if result.details:
            return str(result.details)
        
        return "Tool executed successfully"
    
    async def stream_prompt(self, user_input: str) -> AsyncIterator[str]:
        """Stream response for a prompt.
        
        Args:
            user_input: The user's message
            
        Yields:
            Response tokens as they arrive
        """
        self.turn_count += 1
        
        # Add user message
        self._messages.append(Message(role="user", content=user_input))
        self.session.add_message("user", user_input)
        
        # Stream LLM response
        async for token in self.llm.stream(self._messages):
            yield token
        
        # Note: Full streaming with tool calls requires more complex handling
        # This is simplified for now


class AgentLoop:
    """Factory for creating agent loops."""
    
    @staticmethod
    def create(
        session: Session,
        llm_config: LLMConfig | None = None,
        agent_config: AgentConfig | None = None,
    ) -> AgenticAgent:
        """Create an agent with standard configuration."""
        if llm_config:
            configure_llm(llm_config)
        
        return AgenticAgent(
            session=session,
            config=agent_config,
            llm_client=get_llm_client(),
        )
