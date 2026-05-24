"""Unified Streaming Agent - Agent with real LLM + streaming.

This module combines:
- Real LLM integration (OpenAI/Anthropic/Ollama)
- Streaming output
- Tool execution
- CARV hardware access
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Optional

import structlog

from src.core.agent_runtime import AgentHarness
from src.core.streaming.stream import StreamEvent, StreamEventType, StreamingAgent, StreamSink
from src.infrastructure.llm.llm_manager import (
    create_llm_manager, LLMManager, Message, LLMConfig, ModelProvider
)
from src.infrastructure.carv import CARVTools, CarProject, BuildTarget

logger = structlog.get_logger(__name__)


@dataclass
class StreamingAgentConfig:
    """Configuration for streaming agent."""
    llm_provider: str = "openai"
    llm_model: str = "gpt-4"
    llm_api_key: Optional[str] = None
    streaming_enabled: bool = True
    stream_delay: float = 0.02
    max_tokens: int = 4096
    temperature: float = 0.7


class StreamingAgentLoop:
    """
    Streaming Agent with real LLM + tool execution.
    
    This is the closest to Codex:
    - Real LLM (GPT-4, Claude, Ollama)
    - Streaming token output
    - Tool execution with results
    - CARV hardware access
    
    Usage:
        config = StreamingAgentConfig(
            llm_provider="openai",
            llm_model="gpt-4",
        )
        agent = StreamingAgentLoop(config)
        
        # Stream response
        async for event in agent.run("Analyze EngineCar firmware"):
            print(event.content, end="", flush=True)
        
        # Or with sink
        agent = StreamingAgentLoop(config, sink=my_sink)
        await agent.run("Build EngineCar")
    """
    
    def __init__(
        self,
        config: Optional[StreamingAgentConfig] = None,
        sink: Optional[StreamSink] = None,
        llm_manager: Optional[LLMManager] = None,
    ):
        self.config = config or StreamingAgentConfig()
        self.sink = sink or StreamingAgent(sink=StreamSink())  # Dummy sink
        
        # LLM
        self.llm = llm_manager or create_llm_manager(
            provider=self.config.llm_provider,
            model=self.config.llm_model,
            api_key=self.config.llm_api_key,
        )
        
        # CARV tools
        self.carv_tools = CARVTools()
        
        # Agent harness
        self.harness = AgentHarness()
        
        # System prompt
        self.system_prompt = """You are AI_SUPPORT, an embedded systems engineering AI assistant.

Your capabilities:
- Analyze firmware (STM32, FreeRTOS, HAL)
- Build and flash firmware to hardware
- Debug embedded systems
- Understand hardware semantics
- Read and modify C code

Always:
- Be precise about hardware registers and peripherals
- Validate dependencies before modifying code
- Explain your reasoning
- Use tools appropriately

Available tools:
- analyze_firmware(project, target) - Analyze CARV firmware
- build_firmware(project, target) - Build CARV firmware
- search_code(project, pattern) - Search code in project
"""

    async def run(self, prompt: str) -> list[StreamEvent]:
        """
        Run agent with streaming.
        
        Returns list of stream events.
        """
        events = []
        
        # Stream thinking
        await self.sink.send(StreamEvent(
            type=StreamEventType.THINKING,
            content="Analyzing task...",
        ))
        events.append(StreamEvent(type=StreamEventType.THINKING, content="Analyzing task..."))
        
        # Build messages
        messages = [
            Message(role="system", content=self.system_prompt),
            Message(role="user", content=prompt),
        ]
        
        # Generate with streaming
        full_response = ""
        
        async for chunk in self.llm.stream(prompt, system=self.system_prompt):
            if chunk.content:
                full_response += chunk.content
                
                event = StreamEvent(
                    type=StreamEventType.TOKEN,
                    content=chunk.content,
                )
                await self.sink.send(event)
                events.append(event)
        
        # Complete
        await self.sink.send(StreamEvent(
            type=StreamEventType.COMPLETE,
            content=f"Response completed: {len(full_response)} chars",
            data={"total_tokens": len(full_response.split())},
        ))
        events.append(StreamEvent(
            type=StreamEventType.COMPLETE,
            content="Response completed",
        ))
        
        return events
    
    async def run_with_tools(self, prompt: str) -> dict[str, Any]:
        """
        Run agent with tool execution.
        
        Uses LLM to decide when to call tools.
        """
        messages = [
            Message(role="system", content=self.system_prompt),
            Message(role="user", content=prompt),
        ]
        
        # Initial generation
        response = await self.llm.generate(prompt, system=self.system_prompt)
        
        result = {
            "response": response.content,
            "tools_called": [],
            "final_response": response.content,
        }
        
        # Check if tools should be called
        # (In production, this would use function calling)
        
        return result
    
    async def analyze_and_stream(self, project: str, target: str) -> AsyncGenerator[StreamEvent, None]:
        """
        Analyze firmware with streaming.
        
        Usage:
            async for event in agent.analyze_and_stream("EngineCar", "CarEngine"):
                if event.type == StreamEventType.TOKEN:
                    print(event.content, end="")
        """
        # Stream thinking
        yield StreamEvent(
            type=StreamEventType.THINKING,
            content=f"Analyzing {project}/{target}...",
        )
        
        # Call analysis
        yield StreamEvent(
            type=StreamEventType.TOOL_CALL,
            content=f"analyze_firmware({project}, {target})",
        )
        
        analysis = await self.carv_tools.analyze_firmware(
            project=CarProject[project.upper()] if hasattr(CarProject, project.upper()) else CarProject.ENGINE_CAR,
            target=BuildTarget[target.upper()] if hasattr(BuildTarget, target.upper()) else BuildTarget.CAR_ENGINE,
        )
        
        # Stream results
        yield StreamEvent(
            type=StreamEventType.TOOL_RESULT,
            content=f"MCU: {analysis.mcu}",
        )
        
        yield StreamEvent(
            type=StreamEventType.TOKEN,
            content=f"\n\nAnalysis Results:\n",
        )
        
        yield StreamEvent(
            type=StreamEventType.TOKEN,
            content=f"- MCU: {analysis.mcu}\n",
        )
        
        yield StreamEvent(
            type=StreamEventType.TOKEN,
            content=f"- Components: {', '.join(analysis.components)}\n",
        )
        
        yield StreamEvent(
            type=StreamEventType.TOKEN,
            content=f"- Tasks: {', '.join(analysis.tasks)}\n",
        )
        
        yield StreamEvent(
            type=StreamEventType.TOKEN,
            content=f"- GPIO Pins: {', '.join(analysis.gpio_pins)}\n",
        )
        
        yield StreamEvent(
            type=StreamEventType.COMPLETE,
            content="Analysis complete",
        )


# CLI for testing
async def main():
    """CLI entry point."""
    import sys
    
    print("=" * 60)
    print("AI_SUPPORT Streaming Agent")
    print("=" * 60)
    print()
    
    # Create agent
    config = StreamingAgentConfig(
        llm_provider="openai",
        llm_model="gpt-4",
    )
    
    # Check for API key
    import os
    if not os.getenv("OPENAI_API_KEY"):
        print("Note: OPENAI_API_KEY not set, using mock LLM")
        print()
    
    agent = StreamingAgentLoop(config)
    
    # Get task from args or prompt
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
        task = "Analyze EngineCar firmware structure"
    
    print(f"Task: {task}")
    print()
    print("-" * 40)
    
    # Run with streaming
    from src.core.streaming.stream import PrintSink
    
    sink = PrintSink("[AI] ")
    agent.sink = StreamingAgent(sink=sink)
    
    await agent.run(task)
    
    print()
    print("-" * 40)
    print()
    
    # Analyze firmware
    print("Firmware Analysis:")
    print("-" * 40)
    
    async for event in agent.analyze_and_stream("EngineCar", "CarEngine"):
        if event.type == StreamEventType.TOKEN:
            print(event.content, end="")
        elif event.type == StreamEventType.THOUGHT:
            print(f"\n[Thinking] {event.content}")
    
    print()
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
