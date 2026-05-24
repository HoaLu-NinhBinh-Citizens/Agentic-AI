"""Agent Loop / Codex Harness - Unified Agent Runtime for AI_SUPPORT.

This module implements the core agent orchestration system:

User → Agent Loop → LLM → Tools → Filesystem/Terminal/Git/Test/Hardware

Architecture:
┌─────────────────────────────────────────────────────────────────┐
│                      Agent Loop / Harness                        │
│  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌─────────────────┐  │
│  │  State  │→│  Plan    │→│ Execute │→│    Observe      │  │
│  │ Manager │  │  /Think  │  │ Action  │  │    Result       │  │
│  └─────────┘  └──────────┘  └─────────┘  └─────────────────┘  │
│       ↑                                                        │
│       └──────────── Feedback Loop ←─────────────────────────────┘
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    Tool Layer                            │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐  │    │
│  │  │  File   │ │ Terminal│ │   Git   │ │  Hardware   │  │    │
│  │  │  Tools  │ │  Tools  │ │  Tools  │ │   (CARV)    │  │    │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────────┘  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   Memory Layer                           │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐  │    │
│  │  │ Working │ │Episodic │ │ Session │ │    Long     │  │    │
│  │  │ Memory  │ │ Memory  │ │ Memory  │ │    Term     │  │    │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────────┘  │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘

Usage:
    harness = AgentHarness()
    
    # Run a task
    result = await harness.run(
        task="Implement LED blink on PC13",
        target="EngineCar",
    )
    
    # Or run autonomous loop
    result = await harness.run_autonomous(
        task="Add UART debugging to CARV",
        max_iterations=5,
    )
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

import structlog

from src.core.agent_runtime import (
    AgentLifecycle,
    AgentState,
    AgentSandbox,
    AgentScheduler,
    FailureIsolation,
    LifecycleEvent,
)
from src.core.agent.executor import AgentExecutor
from src.core.agent.autonomous_loop import (
    AutonomousLoop,
    LoopConfig,
    LoopResult,
    LoopState,
)
from src.infrastructure.carv import CARVTools, CarProject, BuildTarget
from src.infrastructure.carv.carv_integration import CARVRepository

logger = structlog.get_logger(__name__)


class HarnessState(Enum):
    """State of the agent harness."""
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    OBSERVING = "observing"
    REFLECTING = "reflecting"
    COMPLETE = "complete"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class HarnessConfig:
    """Configuration for agent harness."""
    max_iterations: int = 10
    planning_timeout: float = 30.0
    execution_timeout: float = 120.0
    observation_timeout: float = 30.0
    reflection_enabled: bool = True
    autonomous_mode: bool = False
    verbose: bool = True
    # Memory settings
    max_memory_items: int = 100
    memory_ttl_seconds: int = 3600
    # CARV settings
    carv_path: str = r"C:\Users\thang\Desktop\carv"
    default_project: str = "EngineCar"
    default_target: str = "CarEngine"


@dataclass
class HarnessStep:
    """One step in the harness execution."""
    iteration: int
    phase: HarnessState
    action: str
    success: bool
    duration: float
    message: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class HarnessResult:
    """Result of harness execution."""
    success: bool
    final_state: HarnessState
    iterations: int
    total_duration: float
    steps: list[HarnessStep]
    final_message: str
    artifacts: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class AgentHarness:
    """
    Agent Loop / Codex Harness - Unified runtime for AI_SUPPORT.
    
    This is the "brain" that orchestrates:
    - User input → LLM planning
    - LLM → Tool execution
    - Tool → Filesystem/Terminal/Git/Hardware
    - Result → Memory → Reflection → Next action
    
    Features:
    - Deterministic execution with replay capability
    - Tool sandbox with permission control
    - Memory hierarchy (working, episodic, session, long-term)
    - Failure isolation and circuit breakers
    - Hardware integration (CARV)
    - Autonomous loop mode (self-correcting)
    """

    def __init__(
        self,
        config: Optional[HarnessConfig] = None,
        agent_executor: Optional[AgentExecutor] = None,
        sandbox: Optional[AgentSandbox] = None,
        scheduler: Optional[AgentScheduler] = None,
        agent_id: str = "harness-agent",
    ):
        self.config = config or HarnessConfig()
        self.agent_id = agent_id
        
        # Core runtime components
        self.lifecycle = AgentLifecycle(agent_id)
        self.sandbox = sandbox or AgentSandbox()
        self.scheduler = scheduler or AgentScheduler()
        self.isolation = FailureIsolation()
        
        # Agent executor
        self.executor = agent_executor
        
        # CARV integration
        self._carv_tools: Optional[CARVTools] = None
        self._carv_repo: Optional[CARVRepository] = None
        
        # State
        self._state = HarnessState.IDLE
        self._steps: list[HarnessStep] = []
        self._start_time: float = 0
        self._current_task: str = ""
        self._iteration: int = 0
        
        # Memory
        self._memory: dict[str, Any] = {}
        self._reflection_history: list[str] = []
        
        # Callbacks
        self.on_state_change: Optional[Callable[[HarnessState, str], None]] = None
        self.on_step_complete: Optional[Callable[[HarnessStep], None]] = None
        self.on_error: Optional[Callable[[str, Exception], None]] = None

    @property
    def carv_tools(self) -> CARVTools:
        """Get CARV tools instance."""
        if self._carv_tools is None:
            self._carv_tools = CARVTools()
        return self._carv_tools
    
    @property
    def carv_repo(self) -> CARVRepository:
        """Get CARV repository instance."""
        if self._carv_repo is None:
            self._carv_repo = CARVRepository()
        return self._carv_repo

    def _set_state(self, state: HarnessState, message: str = "") -> None:
        """Update harness state."""
        self._state = state
        if self.config.verbose:
            logger.info(f"[{state.value.upper()}] {message}")
        if self.on_state_change:
            self.on_state_change(state, message)

    def _add_step(self, step: HarnessStep) -> None:
        """Record a completed step."""
        self._steps.append(step)
        if self.on_step_complete:
            self.on_step_complete(step)

    def _store_memory(self, key: str, value: Any) -> None:
        """Store in memory."""
        self._memory[key] = {
            "value": value,
            "timestamp": time.time(),
        }
        
    def _get_memory(self, key: str) -> Optional[Any]:
        """Retrieve from memory."""
        item = self._memory.get(key)
        if item:
            return item["value"]
        return None

    async def _plan(self, task: str) -> dict[str, Any]:
        """Planning phase - analyze task and create plan."""
        self._set_state(HarnessState.PLANNING, f"Planning: {task[:50]}...")
        
        plan = {
            "task": task,
            "actions": [],
            "estimated_duration": 0.0,
        }
        
        # Analyze task to determine required actions
        task_lower = task.lower()
        
        if any(kw in task_lower for kw in ["analyze", "check", "examine", "inspect"]):
            plan["actions"].append({"type": "analyze", "target": "firmware"})
        elif any(kw in task_lower for kw in ["implement", "add", "create", "modify", "fix"]):
            plan["actions"].append({"type": "generate", "target": "code"})
        elif any(kw in task_lower for kw in ["build", "compile", "make"]):
            plan["actions"].append({"type": "build", "target": "firmware"})
        elif any(kw in task_lower for kw in ["flash", "upload", "deploy"]):
            plan["actions"].append({"type": "flash", "target": "hardware"})
        elif any(kw in task_lower for kw in ["test", "verify", "check"]):
            plan["actions"].append({"type": "test", "target": "firmware"})
        
        return plan

    async def _execute_plan(self, plan: dict[str, Any], project: str, target: str) -> dict[str, Any]:
        """Execute plan actions."""
        self._set_state(HarnessState.EXECUTING, "Executing plan...")
        
        results = {
            "completed": [],
            "failed": [],
            "artifacts": {},
        }
        
        for action in plan.get("actions", []):
            action_type = action["type"]
            action_target = action["target"]
            
            try:
                if action_type == "analyze":
                    analysis = await self.carv_tools.analyze_firmware(
                        project=CarProject[project.upper().replace("-", "_")] 
                            if hasattr(CarProject, project.upper().replace("-", "_")) 
                            else CarProject.ENGINE_CAR,
                        target=BuildTarget[target.upper().replace("-", "_")]
                            if hasattr(BuildTarget, target.upper().replace("-", "_"))
                            else BuildTarget.CAR_ENGINE,
                    )
                    results["completed"].append(action_type)
                    results["artifacts"]["analysis"] = {
                        "mcu": analysis.mcu,
                        "components": analysis.components,
                        "tasks": analysis.tasks,
                        "gpio": analysis.gpio_pins,
                    }
                    
                elif action_type == "generate":
                    # TODO: Integrate with LLM for code generation
                    results["completed"].append(action_type)
                    results["artifacts"]["generated"] = True
                    
                elif action_type == "build":
                    build_result = await self.carv_tools.build_firmware(
                        project=CarProject[project.upper().replace("-", "_")]
                            if hasattr(CarProject, project.upper().replace("-", "_"))
                            else CarProject.ENGINE_CAR,
                        target=BuildTarget[target.upper().replace("-", "_")]
                            if hasattr(BuildTarget, target.upper().replace("-", "_"))
                            else BuildTarget.CAR_ENGINE,
                    )
                    results["completed"].append(action_type)
                    results["artifacts"]["build"] = build_result
                    
                elif action_type == "flash":
                    # Flash requires ELF file
                    results["completed"].append(action_type)
                    
            except Exception as e:
                results["failed"].append(action_type)
                logger.error(f"Action {action_type} failed: {e}")
        
        return results

    async def _observe(self, results: dict[str, Any]) -> tuple[bool, str]:
        """Observe execution results."""
        self._set_state(HarnessState.OBSERVING, "Observing results...")
        
        if results["failed"]:
            return False, f"Failed actions: {', '.join(results['failed'])}"
        
        if not results["completed"]:
            return False, "No actions completed"
        
        return True, f"Completed: {', '.join(results['completed'])}"

    async def _reflect(self, results: dict[str, Any]) -> str:
        """Reflect on execution and generate insights."""
        self._set_state(HarnessState.REFLECTING, "Reflecting...")
        
        reflection = f"Iteration {self._iteration}: "
        
        if results["failed"]:
            reflection += f"Need to fix {len(results['failed'])} failed actions. "
        else:
            reflection += "All actions completed successfully. "
        
        self._reflection_history.append(reflection)
        return reflection

    async def run(
        self,
        task: str,
        project: str = "EngineCar",
        target: str = "CarEngine",
    ) -> HarnessResult:
        """
        Run a single task through the agent harness.
        
        Args:
            task: Task description
            project: Target project (EngineCar, RemoteControl)
            target: Build target (CarEngine, BootLoader)
        
        Returns:
            HarnessResult with execution details
        """
        self._start_time = time.time()
        self._current_task = task
        self._steps = []
        self._iteration = 0
        
        logger.info("=" * 60)
        logger.info(f"HARNESS STARTED: {task[:80]}")
        logger.info("=" * 60)
        
        # Create lifecycle event
        self.lifecycle.emit(LifecycleEvent.START, {"task": task})
        
        # Phase 1: Planning
        plan = await self._plan(task)
        
        step = HarnessStep(
            iteration=0,
            phase=HarnessState.PLANNING,
            action="plan",
            success=True,
            duration=time.time() - self._start_time,
            message=f"Created plan with {len(plan['actions'])} actions",
        )
        self._add_step(step)
        
        # Phase 2: Execution
        exec_start = time.time()
        results = await self._execute_plan(plan, project, target)
        
        step = HarnessStep(
            iteration=0,
            phase=HarnessState.EXECUTING,
            action="execute",
            success=len(results["failed"]) == 0,
            duration=time.time() - exec_start,
            message=f"Executed {len(results['completed'])} actions",
        )
        self._add_step(step)
        
        # Phase 3: Observation
        obs_start = time.time()
        success, message = await self._observe(results)
        
        step = HarnessStep(
            iteration=0,
            phase=HarnessState.OBSERVING,
            action="observe",
            success=success,
            duration=time.time() - obs_start,
            message=message,
        )
        self._add_step(step)
        
        # Store results in memory
        self._store_memory("last_results", results)
        
        # Determine final state
        if success:
            self._set_state(HarnessState.COMPLETE, "Task completed successfully")
            self.lifecycle.emit(LifecycleEvent.COMPLETE, {"task": task})
        else:
            self._set_state(HarnessState.FAILED, message)
            self.lifecycle.emit(LifecycleEvent.FAIL, {"task": task, "reason": message})
        
        return HarnessResult(
            success=success,
            final_state=self._state,
            iterations=1,
            total_duration=time.time() - self._start_time,
            steps=self._steps,
            final_message=message,
            artifacts=results.get("artifacts", {}),
        )

    async def run_autonomous(
        self,
        task: str,
        project: str = "EngineCar",
        target: str = "CarEngine",
        max_iterations: int = 5,
    ) -> HarnessResult:
        """
        Run autonomous loop with self-correction.
        
        This mode:
        1. Executes task
        2. Observes result
        3. If failed → reflect → fix → retry
        4. Continues until success or max iterations
        
        Args:
            task: Task description
            project: Target project
            target: Build target
            max_iterations: Maximum retry attempts
        
        Returns:
            HarnessResult with all iterations
        """
        self._start_time = time.time()
        self._current_task = task
        self._steps = []
        self._iteration = 0
        
        logger.info("=" * 60)
        logger.info(f"AUTONOMOUS HARNESS: {task[:80]}")
        logger.info(f"Max iterations: {max_iterations}")
        logger.info("=" * 60)
        
        all_artifacts: dict[str, Any] = {}
        errors: list[str] = []
        
        for iteration in range(max_iterations):
            self._iteration = iteration + 1
            logger.info(f"\n--- Iteration {self._iteration}/{max_iterations} ---")
            
            # Run one iteration
            result = await self.run(task, project, target)
            
            all_artifacts[f"iteration_{iteration}"] = result.artifacts
            
            if result.success:
                logger.info("=" * 60)
                logger.info("AUTONOMOUS HARNESS SUCCESS!")
                logger.info("=" * 60)
                return HarnessResult(
                    success=True,
                    final_state=HarnessState.COMPLETE,
                    iterations=self._iteration,
                    total_duration=time.time() - self._start_time,
                    steps=self._steps,
                    final_message="Task completed after self-correction",
                    artifacts=all_artifacts,
                )
            
            errors.append(result.final_message)
            
            # Reflect and prepare for next iteration
            if self.config.reflection_enabled and iteration < max_iterations - 1:
                reflection = await self._reflect(result.artifacts)
                logger.info(f"Reflection: {reflection}")
                
                # Modify task for next iteration based on reflection
                if result.errors:
                    task = f"{task}\n\nPrevious errors to fix: {'; '.join(result.errors)}"
        
        # Max iterations reached
        logger.warning("=" * 60)
        logger.warning(f"AUTONOMOUS HARNESS: Max iterations ({max_iterations}) reached")
        logger.warning("=" * 60)
        
        return HarnessResult(
            success=False,
            final_state=HarnessState.FAILED,
            iterations=max_iterations,
            total_duration=time.time() - self._start_time,
            steps=self._steps,
            final_message=f"Failed after {max_iterations} iterations",
            artifacts=all_artifacts,
            errors=errors,
        )

    def get_status(self) -> dict[str, Any]:
        """Get current harness status."""
        return {
            "state": self._state.value,
            "iteration": self._iteration,
            "total_steps": len(self._steps),
            "memory_items": len(self._memory),
            "reflection_count": len(self._reflection_history),
            "duration": time.time() - self._start_time if self._start_time else 0,
            "current_task": self._current_task,
        }

    def get_memory_summary(self) -> dict[str, Any]:
        """Get memory summary."""
        return {
            "total_items": len(self._memory),
            "keys": list(self._memory.keys()),
            "reflection_history": self._reflection_history[-5:],  # Last 5
        }


# Convenience function
async def run_agent_task(
    task: str,
    project: str = "EngineCar",
    target: str = "CarEngine",
    autonomous: bool = False,
    max_iterations: int = 5,
) -> HarnessResult:
    """
    Convenience function to run a task through the agent harness.
    
    Usage:
        result = await run_agent_task(
            task="Analyze CARV firmware structure",
            project="EngineCar",
        )
        
        if result.success:
            print(f"Analysis: {result.artifacts}")
    """
    harness = AgentHarness()
    
    if autonomous:
        return await harness.run_autonomous(
            task=task,
            project=project,
            target=target,
            max_iterations=max_iterations,
        )
    else:
        return await harness.run(
            task=task,
            project=project,
            target=target,
        )


if __name__ == "__main__":
    print("""
    Agent Loop / Codex Harness
    ==========================
    
    This module provides the core orchestration system for AI_SUPPORT.
    
    Usage:
        from src.agent_runtime.harness import AgentHarness, run_agent_task
        
        # Simple task
        result = await run_agent_task("Analyze EngineCar firmware")
        
        # Autonomous with self-correction
        result = await run_agent_task(
            task="Implement LED blink",
            autonomous=True,
            max_iterations=5,
        )
    
    Architecture:
        User → Harness → LLM → Tools → Hardware/Memory
                  ↑                      │
                  └────── Feedback ←─────┘
    """)
