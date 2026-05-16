"""LLMAgentService for hybrid LLM agent with autonomous tool calling.

This service orchestrates the entire agent flow including provider selection,
streaming responses, tool execution, and context management.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from domain.models.execution import ExecutionContext
from infrastructure.llm.provider import (
    LLMProvider,
    StreamEvent,
    StreamEventType,
    ToolCall,
    ToolResult,
)
from infrastructure.llm.router import LLMRouter
from infrastructure.llm.tool_accumulator import ToolCallAccumulator

logger = logging.getLogger(__name__)


EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class AgentConfig:
    """Configuration for the LLM agent service."""

    max_tool_rounds: int = 10
    max_concurrent_tools: int = 5
    max_context_tokens: int = 8000
    tool_timeout_seconds: float = 30.0
    consecutive_failure_limit: int = 3
    system_prompt: str = """You are an AI assistant with access to tools. Use tools when needed.
After receiving tool results, provide a final answer.
If a tool fails, explain the error and try a different approach.
Always be helpful and precise."""

    tokens_per_message: int = 4
    tokens_per_tool_result: int = 50

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> AgentConfig:
        """Create config from dictionary.

        Args:
            config: Configuration dictionary.

        Returns:
            AgentConfig instance.
        """
        agent_config = config.get("agent", {})
        return cls(
            max_tool_rounds=agent_config.get("max_tool_rounds", 10),
            max_concurrent_tools=agent_config.get("max_concurrent_tools", 5),
            max_context_tokens=agent_config.get("max_context_tokens", 8000),
            tool_timeout_seconds=agent_config.get("tool_timeout_seconds", 30.0),
            consecutive_failure_limit=agent_config.get("consecutive_failure_limit", 3),
            system_prompt=agent_config.get(
                "system_prompt",
                cls.system_prompt,
            ),
        )


@dataclass
class ToolExecutor:
    """Interface for tool execution."""

    execute_tool: Callable[..., Awaitable[Any]]

    async def __call__(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        call_id: str,
        session_id: str,
        client_id: str,
        trace_id: str,
    ) -> ToolResult:
        """Execute a tool call.

        Args:
            tool_name: Name of the tool.
            arguments: Tool arguments.
            call_id: Unique call identifier.
            session_id: Session identifier.
            client_id: Client identifier.
            trace_id: Trace identifier.

        Returns:
            ToolResult with execution outcome.
        """
        start_time = time.monotonic()
        try:
            result = await self.execute_tool(
                session_id=session_id,
                tool_name=tool_name,
                arguments=arguments,
                call_id=call_id,
                client_id=client_id,
                trace_id=trace_id,
            )

            duration_ms = (time.monotonic() - start_time) * 1000

            if hasattr(result, "success"):
                return ToolResult(
                    call_id=call_id,
                    tool_name=tool_name,
                    success=result.success,
                    content=getattr(result, "content", None),
                    error=getattr(result, "error", None),
                    duration_ms=duration_ms,
                )

            return ToolResult(
                call_id=call_id,
                tool_name=tool_name,
                success=True,
                content=str(result),
                duration_ms=duration_ms,
            )

        except asyncio.TimeoutError:
            duration_ms = (time.monotonic() - start_time) * 1000
            return ToolResult(
                call_id=call_id,
                tool_name=tool_name,
                success=False,
                error="Tool execution timed out",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            logger.error("Tool execution failed: %s", str(e), extra={"tool_name": tool_name})
            return ToolResult(
                call_id=call_id,
                tool_name=tool_name,
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )


class LLMAgentService:
    """Hybrid LLM agent service with autonomous tool calling.

    Orchestrates the complete agent flow including:
    - Provider selection and fallback
    - Token-based context management
    - Parallel tool execution with timeouts
    - Streaming responses to clients
    """

    def __init__(
        self,
        router: LLMRouter,
        tool_executor: ToolExecutor,
        config: AgentConfig | None = None,
    ) -> None:
        """Initialize the agent service.

        Args:
            router: LLM router for provider selection.
            tool_executor: Tool execution interface.
            config: Agent configuration.
        """
        self._router = router
        self._tool_executor = tool_executor
        self._config = config or AgentConfig()

    async def process_message(
        self,
        session_id: str,
        client_id: str,
        trace_id: str,
        messages: list[dict[str, str]],
        event_callback: EventCallback,
        provider_hint: str | None = None,
    ) -> None:
        """Process a user message and stream the response.

        Args:
            session_id: Session identifier.
            client_id: Client identifier.
            trace_id: Trace identifier for correlation.
            messages: List of conversation messages.
            event_callback: Callback for streaming events.
            provider_hint: Optional provider preference.
        """
        full_messages = [{"role": "system", "content": self._config.system_prompt}]
        full_messages.extend(messages)

        full_messages = self._truncate_by_tokens(full_messages, self._config.max_context_tokens)

        tools = []

        current_provider: LLMProvider | None = None
        round_count = 0
        consecutive_failures = 0
        start_time = time.monotonic()

        while round_count < self._config.max_tool_rounds:
            try:
                if current_provider is None:
                    current_provider = await self._router.select_provider(
                        message=messages[-1]["content"] if messages else "",
                        tools=tools,
                        client_hint=provider_hint,
                    )

                    if current_provider is None:
                        await event_callback("error", {
                            "code": "NO_PROVIDER",
                            "message": "No LLM provider available",
                        })
                        return

                await event_callback("provider_selected", {
                    "provider": current_provider.name,
                    "round": round_count,
                })

                tool_accumulator = ToolCallAccumulator()
                response_text = ""

                async for event in current_provider.stream_chat(full_messages, tools):
                    if event.type == StreamEventType.TOKEN:
                        response_text += event.data["content"]
                        await event_callback("token", {
                            "content": event.data["content"],
                            "provider": current_provider.name,
                        })

                    elif event.type == StreamEventType.TOOL_CALL_START:
                        tool_accumulator.add_tool_call_start(
                            index=event.data["index"],
                            call_id=event.data["call_id"],
                            function_name=event.data["function_name"],
                        )

                    elif event.type == StreamEventType.TOOL_CALL_DELTA:
                        tool_accumulator.add_tool_call_delta(
                            index=event.data["index"],
                            call_id=event.data["call_id"],
                            function_name=event.data.get("function_name"),
                            arguments=event.data["arguments"],
                        )

                    elif event.type == StreamEventType.DONE:
                        break

                    elif event.type == StreamEventType.ERROR:
                        await event_callback("error", {
                            "code": event.data["code"],
                            "message": event.data["message"],
                            "provider": current_provider.name,
                        })

                tool_calls = tool_accumulator.finalize()

                if not tool_calls:
                    await event_callback("done", {
                        "success": True,
                        "content": response_text,
                        "provider": current_provider.name,
                        "rounds": round_count + 1,
                    })
                    return

                assistant_msg = {
                    "role": "assistant",
                    "content": response_text,
                    "tool_calls": [
                        {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                        for tc in tool_calls
                    ],
                }
                full_messages.append(assistant_msg)

                tool_results = await self._execute_tool_calls(
                    tool_calls=tool_calls,
                    session_id=session_id,
                    client_id=client_id,
                    trace_id=trace_id,
                    event_callback=event_callback,
                )

                failed_count = sum(1 for r in tool_results if not r.success)
                if failed_count > 0:
                    consecutive_failures += 1
                    if consecutive_failures >= self._config.consecutive_failure_limit:
                        await event_callback("error", {
                            "code": "TOOL_FAILURE_LIMIT",
                            "message": f"Too many tool failures ({consecutive_failures})",
                        })
                        return
                else:
                    consecutive_failures = 0

                for tr in tool_results:
                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": tr.call_id,
                        "content": tr.content if tr.success else f"Error: {tr.error}",
                    }
                    full_messages.append(tool_msg)

                round_count += 1

                full_messages = self._truncate_by_tokens(
                    full_messages,
                    self._config.max_context_tokens,
                )

            except Exception as e:
                logger.error(
                    "Provider error in round %d: %s",
                    round_count,
                    str(e),
                    extra={"provider": current_provider.name if current_provider else "unknown"},
                )

                if current_provider:
                    self._router.record_failure(current_provider.name, e)

                if self._config.max_tool_rounds and self._router._config.fallback_enabled:
                    fallback_provider = self._router._providers.get("local")
                    if fallback_provider and fallback_provider != current_provider:
                        logger.info("Falling back to local provider")
                        current_provider = fallback_provider
                        continue

                await event_callback("error", {
                    "code": "LLM_FAILURE",
                    "message": str(e),
                    "provider": current_provider.name if current_provider else "unknown",
                })
                return

        await event_callback("error", {
            "code": "MAX_TOOL_ROUNDS",
            "message": f"Exceeded {self._config.max_tool_rounds} rounds",
            "rounds": round_count,
        })

        duration_ms = (time.monotonic() - start_time) * 1000
        logger.info(
            "Agent request completed",
            extra={
                "session_id": session_id,
                "trace_id": trace_id,
                "duration_ms": duration_ms,
                "rounds": round_count,
                "provider": current_provider.name if current_provider else "unknown",
            },
        )

    async def _execute_tool_calls(
        self,
        tool_calls: list[ToolCall],
        session_id: str,
        client_id: str,
        trace_id: str,
        event_callback: EventCallback,
    ) -> list[ToolResult]:
        """Execute tool calls in parallel with concurrency limits.

        Args:
            tool_calls: List of tool calls to execute.
            session_id: Session identifier.
            client_id: Client identifier.
            trace_id: Trace identifier.
            event_callback: Callback for streaming events.

        Returns:
            List of tool results.
        """
        semaphore = asyncio.Semaphore(self._config.max_concurrent_tools)

        async def execute_single(tc: ToolCall) -> ToolResult:
            async with semaphore:
                start = time.monotonic()

                await event_callback("tool_call_start", {
                    "call_id": tc.id,
                    "tool_name": tc.name,
                    "arguments": tc.arguments,
                })

                try:
                    result = await asyncio.wait_for(
                        self._tool_executor(
                            tool_name=tc.name,
                            arguments=tc.arguments,
                            call_id=tc.id,
                            session_id=session_id,
                            client_id=client_id,
                            trace_id=trace_id,
                        ),
                        timeout=self._config.tool_timeout_seconds,
                    )

                    duration_ms = (time.monotonic() - start) * 1000

                    if result.success:
                        await event_callback("tool_call_result", {
                            "call_id": tc.id,
                            "tool_name": tc.name,
                            "content": result.content,
                            "duration_ms": duration_ms,
                        })
                    else:
                        await event_callback("tool_call_error", {
                            "call_id": tc.id,
                            "tool_name": tc.name,
                            "error": result.error,
                            "code": "TOOL_ERROR",
                            "duration_ms": duration_ms,
                        })

                    return result

                except asyncio.TimeoutError:
                    duration_ms = (time.monotonic() - start) * 1000
                    await event_callback("tool_call_error", {
                        "call_id": tc.id,
                        "tool_name": tc.name,
                        "error": "Tool execution timed out",
                        "code": "TIMEOUT",
                        "duration_ms": duration_ms,
                    })
                    return ToolResult(
                        call_id=tc.id,
                        tool_name=tc.name,
                        success=False,
                        error="Tool execution timed out",
                        duration_ms=duration_ms,
                    )

        return await asyncio.gather(*[execute_single(tc) for tc in tool_calls])

    def _truncate_by_tokens(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> list[dict[str, str]]:
        """Truncate messages by token count.

        Uses a simple heuristic: 1 token ≈ 4 characters.

        Args:
            messages: List of messages.
            max_tokens: Maximum tokens to keep.

        Returns:
            Truncated message list.
        """
        total_tokens = 0
        truncated = []

        for msg in reversed(messages):
            content = msg.get("content", "")
            tokens = len(content) // self._config.tokens_per_message

            if total_tokens + tokens > max_tokens:
                break

            truncated.insert(0, msg)
            total_tokens += tokens

        return truncated

    async def get_stats(self) -> dict[str, Any]:
        """Get agent service statistics.

        Returns:
            Dictionary with service stats.
        """
        return {
            "config": {
                "max_tool_rounds": self._config.max_tool_rounds,
                "max_concurrent_tools": self._config.max_concurrent_tools,
                "max_context_tokens": self._config.max_context_tokens,
                "tool_timeout_seconds": self._config.tool_timeout_seconds,
            },
            "router_stats": self._router.get_stats(),
        }
