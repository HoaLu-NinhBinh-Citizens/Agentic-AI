"""Unified Codex-like Agent - Full autonomous coding assistant.

This is the main agent class that combines all capabilities:
- LLM with streaming
- File editing
- Terminal execution
- Git operations
- Vision analysis
- Codebase understanding
- CARV hardware access
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

import structlog

from src.core.agent_runtime import AgentHarness
from src.core.streaming.stream import StreamEvent, StreamEventType, StreamingAgent, StreamSink
from src.core.tools.vscode_integration import VSCodeIntegration
from src.core.tools.vision import VisionProvider, CodebaseUnderstanding
from src.infrastructure.llm.llm_manager import (
    create_llm_manager, LLMManager, Message
)
from src.infrastructure.carv import CARVTools, CarProject, BuildTarget

logger = structlog.get_logger(__name__)


class AgentMode(Enum):
    """Agent operation mode."""
    ASSISTANT = "assistant"  # Help user
    AUTONOMOUS = "autonomous"  # Self-directed


@dataclass
class CodexAgentConfig:
    """Configuration for Codex-like agent."""
    workspace_root: str = "."
    
    # LLM
    llm_provider: str = "openai"
    llm_model: str = "gpt-4"
    llm_api_key: Optional[str] = None
    
    # Behavior
    mode: AgentMode = AgentMode.ASSISTANT
    autonomous_max_iterations: int = 5
    stream_output: bool = True
    
    # Safety
    allow_destructive: bool = False
    require_confirmation: bool = True
    
    # Capabilities
    enable_vision: bool = True
    enable_git: bool = True
    enable_terminal: bool = True
    enable_hardware: bool = True


@dataclass
class Action:
    """An action performed by the agent."""
    type: str  # "read", "write", "execute", "git", "llm", "analyze"
    description: str
    success: bool
    result: Any
    duration: float


@dataclass
class Session:
    """A coding session."""
    id: str
    started_at: datetime
    actions: list[Action] = field(default_factory=list)
    files_created: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    commands_executed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    
    @property
    def total_actions(self) -> int:
        return len(self.actions)
    
    @property
    def success_rate(self) -> float:
        if not self.actions:
            return 0.0
        successes = sum(1 for a in self.actions if a.success)
        return successes / len(self.actions)


class CodexAgent:
    """
    Codex-like Agent - Full autonomous coding assistant.
    
    This combines:
    - Real LLM with streaming (GPT-4, Claude, Ollama)
    - File system operations
    - Terminal/command execution
    - Git operations
    - Vision analysis
    - Codebase understanding
    - CARV hardware integration
    
    Usage:
        agent = CodexAgent(
            workspace_root=".",
            llm_provider="openai",
            llm_model="gpt-4",
        )
        
        # Interactive mode
        async for event in agent.chat_stream("Implement LED blink"):
            print(event.content, end="")
        
        # Autonomous mode
        result = await agent.run_autonomous(
            "Add UART debugging to CARV firmware"
        )
        
        # Direct tool access
        await agent.read_file("main.c")
        await agent.run_command("make build")
        await agent.analyze_image("circuit.png")
    """
    
    def __init__(
        self,
        config: Optional[CodexAgentConfig] = None,
        sink: Optional[StreamSink] = None,
    ):
        self.config = config or CodexAgentConfig()
        
        # Initialize components
        self.llm = create_llm_manager(
            provider=self.config.llm_provider,
            model=self.config.llm_model,
            api_key=self.config.llm_api_key,
        )
        
        self.vscode = VSCodeIntegration(self.config.workspace_root)
        self.vision = VisionProvider()
        self.codebase = CodebaseUnderstanding(self.config.workspace_root)
        self.carv = CARVTools()
        
        self._streaming_agent = StreamingAgent(
            sink=sink or StreamSink()
        )
        
        # Session management
        self._session: Optional[Session] = None
        
        # System prompt
        self._system_prompt = """You are AI_SUPPORT, an advanced embedded systems engineering AI.

Your capabilities:
- Embedded firmware development (STM32, FreeRTOS, HAL)
- Hardware debugging and validation
- Code analysis and generation
- Git operations
- Build and flash firmware
- Real-time problem solving

Your principles:
1. Always validate hardware dependencies
2. Never hallucinate register addresses or peripheral configs
3. Explain reasoning before acting
4. Use tools appropriately
5. Be precise about hardware semantics

Available actions:
- read_file(path) - Read file contents
- write_file(path, content) - Write file
- edit_file(path, content) - Edit file
- run_command(cmd) - Execute shell command
- git_operations (status, commit, push, pull)
- analyze_firmware(project, target) - Analyze CARV
- build_firmware(project, target) - Build CARV
- search_code(pattern) - Search in codebase
- analyze_image(path) - Analyze image/diagram
"""
    
    # ============================================
    # Session Management
    # ============================================
    
    def start_session(self) -> Session:
        """Start a new session."""
        import uuid
        self._session = Session(
            id=str(uuid.uuid4())[:8],
            started_at=datetime.now(),
        )
        logger.info(f"Session started: {self._session.id}")
        return self._session
    
    def get_session(self) -> Optional[Session]:
        """Get current session."""
        return self._session
    
    def _add_action(self, action: Action) -> None:
        """Add action to session."""
        if self._session:
            self._session.actions.append(action)
    
    # ============================================
    # File Operations
    # ============================================
    
    async def read_file(self, path: str) -> str:
        """Read a file."""
        start = datetime.now()
        try:
            content = await self.vscode.read_file(path)
            self._add_action(Action(
                type="read",
                description=f"Read {path}",
                success=True,
                result={"size": len(content)},
                duration=(datetime.now() - start).total_seconds(),
            ))
            return content
        except Exception as e:
            self._add_action(Action(
                type="read",
                description=f"Read {path}",
                success=False,
                result=str(e),
                duration=(datetime.now() - start).total_seconds(),
            ))
            raise
    
    async def write_file(self, path: str, content: str) -> bool:
        """Write a file."""
        start = datetime.now()
        try:
            await self.vscode.write_file(path, content)
            
            if self._session and path not in self._session.files_created:
                self._session.files_created.append(path)
            
            self._add_action(Action(
                type="write",
                description=f"Write {path}",
                success=True,
                result={"size": len(content)},
                duration=(datetime.now() - start).total_seconds(),
            ))
            return True
        except Exception as e:
            self._add_action(Action(
                type="write",
                description=f"Write {path}",
                success=False,
                result=str(e),
                duration=(datetime.now() - start).total_seconds(),
            ))
            raise
    
    async def edit_file(self, path: str, content: str) -> bool:
        """Edit a file (with backup)."""
        start = datetime.now()
        try:
            change = await self.vscode.edit_file(path, content)
            
            if self._session and path not in self._session.files_modified:
                self._session.files_modified.append(path)
            
            self._add_action(Action(
                type="edit",
                description=f"Edit {path}",
                success=True,
                result={"size": len(content)},
                duration=(datetime.now() - start).total_seconds(),
            ))
            return True
        except Exception as e:
            self._add_action(Action(
                type="edit",
                description=f"Edit {path}",
                success=False,
                result=str(e),
                duration=(datetime.now() - start).total_seconds(),
            ))
            raise
    
    # ============================================
    # Terminal Operations
    # ============================================
    
    async def run_command(
        self,
        command: str,
        timeout: float = 30.0,
    ) -> tuple[int, str, str]:
        """Run a shell command."""
        start = datetime.now()
        
        if self._session:
            self._session.commands_executed.append(command)
        
        exit_code, stdout, stderr = await self.vscode.run_command(
            command,
            timeout=timeout,
        )
        
        self._add_action(Action(
            type="execute",
            description=f"Execute: {command[:50]}",
            success=exit_code == 0,
            result={"exit_code": exit_code, "stdout_size": len(stdout)},
            duration=(datetime.now() - start).total_seconds(),
        ))
        
        return exit_code, stdout, stderr
    
    async def run_command_stream(
        self,
        command: str,
    ) -> AsyncGenerator[str, None]:
        """Run command with streaming output."""
        async for line in self.vscode.stream_output(command):
            yield line
    
    # ============================================
    # Git Operations
    # ============================================
    
    async def git_status(self) -> str:
        """Get git status."""
        return await self.vscode.git_status()
    
    async def git_commit(self, message: str) -> bool:
        """Git commit."""
        return await self.vscode.git_commit(message)
    
    async def git_push(self) -> bool:
        """Git push."""
        return await self.vscode.git_push()
    
    async def git_pull(self) -> bool:
        """Git pull."""
        return await self.vscode.git_pull()
    
    # ============================================
    # Analysis Operations
    # ============================================
    
    async def analyze_image(self, image_path: str) -> dict[str, Any]:
        """Analyze an image."""
        start = datetime.now()
        
        try:
            result = await self.vision.analyze_image(image_path)
            
            self._add_action(Action(
                type="analyze",
                description=f"Analyze image: {image_path}",
                success=True,
                result={"description": result.description},
                duration=(datetime.now() - start).total_seconds(),
            ))
            
            return {
                "description": result.description,
                "objects": result.objects,
                "text": result.text,
                "confidence": result.confidence,
            }
        except Exception as e:
            self._add_action(Action(
                type="analyze",
                description=f"Analyze image: {image_path}",
                success=False,
                result=str(e),
                duration=(datetime.now() - start).total_seconds(),
            ))
            raise
    
    async def analyze_firmware(
        self,
        project: str = "EngineCar",
        target: str = "CarEngine",
    ) -> dict[str, Any]:
        """Analyze CARV firmware."""
        start = datetime.now()
        
        try:
            proj = CarProject[project.upper()] if hasattr(CarProject, project.upper()) else CarProject.ENGINE_CAR
            tgt = BuildTarget[target.upper()] if hasattr(BuildTarget, target.upper()) else BuildTarget.CAR_ENGINE
            
            result = await self.carv.analyze_firmware(proj, tgt)
            
            self._add_action(Action(
                type="analyze",
                description=f"Analyze firmware: {project}/{target}",
                success=True,
                result={"mcu": result.mcu, "components": result.components},
                duration=(datetime.now() - start).total_seconds(),
            ))
            
            return {
                "mcu": result.mcu,
                "components": result.components,
                "tasks": result.tasks,
                "gpio_pins": result.gpio_pins,
                "clock_config": result.clock_config,
            }
        except Exception as e:
            self._add_action(Action(
                type="analyze",
                description=f"Analyze firmware: {project}/{target}",
                success=False,
                result=str(e),
                duration=(datetime.now() - start).total_seconds(),
            ))
            raise
    
    async def build_firmware(
        self,
        project: str = "EngineCar",
        target: str = "CarEngine",
    ) -> dict[str, Any]:
        """Build CARV firmware."""
        start = datetime.now()
        
        try:
            proj = CarProject[project.upper()] if hasattr(CarProject, project.upper()) else CarProject.ENGINE_CAR
            tgt = BuildTarget[target.upper()] if hasattr(BuildTarget, target.upper()) else BuildTarget.CAR_ENGINE
            
            result = await self.carv.build_firmware(proj, tgt)
            
            self._add_action(Action(
                type="build",
                description=f"Build firmware: {project}/{target}",
                success=result["success"],
                result=result,
                duration=(datetime.now() - start).total_seconds(),
            ))
            
            return result
        except Exception as e:
            self._add_action(Action(
                type="build",
                description=f"Build firmware: {project}/{target}",
                success=False,
                result=str(e),
                duration=(datetime.now() - start).total_seconds(),
            ))
            raise
    
    async def search_code(self, pattern: str) -> list[dict[str, Any]]:
        """Search in codebase."""
        return await self.codebase.find_symbol(pattern)
    
    # ============================================
    # LLM Operations
    # ============================================
    
    async def generate(
        self,
        prompt: str,
        stream: bool = True,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Generate response with optional streaming."""
        if stream:
            async for chunk in self.llm.stream(prompt, system=self._system_prompt):
                yield StreamEvent(
                    type=StreamEventType.TOKEN if chunk.content else StreamEventType.COMPLETE,
                    content=chunk.content,
                )
        else:
            response = await self.llm.generate(prompt, system=self._system_prompt)
            yield StreamEvent(
                type=StreamEventType.COMPLETE,
                content=response.content,
            )
    
    # ============================================
    # High-Level Operations
    # ============================================
    
    async def chat(self, message: str) -> str:
        """Chat with the agent."""
        response = await self.llm.generate(
            message,
            system=self._system_prompt,
        )
        return response.content
    
    async def chat_stream(self, message: str) -> AsyncGenerator[str, None]:
        """Chat with streaming."""
        async for chunk in self.llm.stream(message, system=self._system_prompt):
            if chunk.content:
                yield chunk.content
    
    async def run_autonomous(
        self,
        task: str,
        max_iterations: int = 5,
    ) -> dict[str, Any]:
        """
        Run autonomous task with self-correction.
        
        Similar to Codex's autonomous mode.
        """
        self.start_session()
        
        logger.info(f"Autonomous task: {task}")
        
        # Use harness
        harness = AgentHarness()
        
        result = await harness.run_autonomous(
            task=task,
            project="EngineCar",
            target="CarEngine",
            max_iterations=max_iterations,
        )
        
        return {
            "success": result.success,
            "iterations": result.iterations,
            "duration": result.total_duration,
            "message": result.final_message,
            "steps": [s.step for s in result.steps],
            "errors": [e.message for e in result.errors],
        }
    
    # ============================================
    # Session Summary
    # ============================================
    
    def get_summary(self) -> dict[str, Any]:
        """Get session summary."""
        if not self._session:
            return {"status": "no session"}
        
        return {
            "session_id": self._session.id,
            "duration": (datetime.now() - self._session.started_at).total_seconds(),
            "total_actions": self._session.total_actions,
            "success_rate": self._session.success_rate,
            "files_created": len(self._session.files_created),
            "files_modified": len(self._session.files_modified),
            "commands_executed": len(self._session.commands_executed),
            "errors": len(self._session.errors),
        }


# ============================================
# CLI Interface
# ============================================

async def main():
    """CLI entry point."""
    import sys
    
    print("=" * 60)
    print("AI_SUPPORT - Codex-like Agent")
    print("=" * 60)
    
    # Create agent
    agent = CodexAgent(
        workspace_root=".",
        llm_provider="openai",
        llm_model="gpt-4",
    )
    
    agent.start_session()
    
    # Get task
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
        task = "Show git status and analyze EngineCar firmware"
    
    print(f"\nTask: {task}")
    print("-" * 40)
    
    # Parse and execute commands
    if "git status" in task.lower():
        print("\n[Git Status]")
        status = await agent.git_status()
        print(status)
    
    if "analyze" in task.lower() and "firmware" in task.lower():
        print("\n[Firmware Analysis]")
        analysis = await agent.analyze_firmware("EngineCar", "CarEngine")
        print(f"MCU: {analysis['mcu']}")
        print(f"Components: {', '.join(analysis['components'])}")
        print(f"Tasks: {', '.join(analysis['tasks'])}")
    
    if "chat" in task.lower():
        print("\n[Chat]")
        async for token in agent.chat_stream(task):
            print(token, end="", flush=True)
        print()
    
    # Summary
    print("\n" + "=" * 40)
    summary = agent.get_summary()
    print(f"Session: {summary['session_id']}")
    print(f"Actions: {summary['total_actions']}")
    print(f"Success Rate: {summary['success_rate']:.0%}")


if __name__ == "__main__":
    asyncio.run(main())
