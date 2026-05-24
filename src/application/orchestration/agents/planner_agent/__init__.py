"""Planner Agent — decomposes tasks into structured execution plans.

Responsibilities:
- Parse user intent into structured task decomposition
- Create ordered execution plan with dependencies
- Assign agents to each plan step
- Track plan progress and handle failures
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

from src.core.agent.reasoning_loop import ReasoningContext, ReasoningLoop
from src.core.agent.reflection import Reflection, ReflectionResult
from src.domain.knowledge.kb import KnowledgeBase, KBEntryType, KBQuery

logger = structlog.get_logger(__name__)


class TaskType(Enum):
    """High-level task categories."""
    HARDWARE_INIT = "hardware_init"       # Peripheral initialization
    CODE_GENERATION = "code_generation"   # Generate embedded C
    DEBUGGING = "debugging"               # Diagnose and fix issues
    ANALYSIS = "analysis"                 # Analyze hardware/code
    PLANNING = "planning"                # Multi-step planning
    REFACTOR = "refactor"               # Code refactoring
    TESTING = "testing"                 # Generate/running tests
    BUILD = "build"                     # Build/flash firmware


class PlanStatus(Enum):
    """Plan execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"     # Waiting on dependency
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PlanStep:
    """A single step in an execution plan."""
    step_id: str
    name: str
    description: str
    task_type: TaskType
    assigned_agent: str | None = None
    status: PlanStatus = PlanStatus.PENDING
    dependencies: list[str] = field(default_factory=list)  # step_ids this depends on
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    retry_count: int = 0
    max_retries: int = 2

    @property
    def duration_ms(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return None


@dataclass
class ExecutionPlan:
    """A complete execution plan with steps and metadata."""
    plan_id: str
    original_task: str
    steps: list[PlanStep]
    status: PlanStatus = PlanStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    @property
    def pending_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == PlanStatus.PENDING]

    @property
    def blocked_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == PlanStatus.BLOCKED]

    @property
    def completed_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == PlanStatus.COMPLETED]

    @property
    def failed_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == PlanStatus.FAILED]


class PlannerAgent:
    """
    Planner Agent — decomposes tasks and creates execution plans.

    Uses:
    - ReasoningLoop for formal task decomposition
    - KnowledgeBase for similar past plans
    - Reflection for plan quality improvement

    Usage:
        planner = PlannerAgent()
        plan = await planner.plan("Initialize CAN1 for EngineCar at 500kbps")
        for step in plan.steps:
            print(f"{step.step_id}: {step.name}")
    """

    def __init__(
        self,
        reasoning_loop: ReasoningLoop | None = None,
        knowledge_base: KnowledgeBase | None = None,
    ):
        self._reasoning = reasoning_loop
        self._kb = knowledge_base

    async def plan(self, task: str, context: dict[str, Any] | None = None) -> ExecutionPlan:
        """
        Create an execution plan from a task description.

        Args:
            task: Natural language task description
            context: Optional context (chip_family, project, etc.)

        Returns:
            ExecutionPlan with ordered steps
        """
        import uuid
        context = context or {}
        plan_id = str(uuid.uuid4())[:8]

        logger.info("planner_start", task=task, plan_id=plan_id)

        # Step 1: Classify task type
        task_type = self._classify_task(task)
        logger.debug("task_classified", type=task_type.value, plan_id=plan_id)

        # Step 2: Query KB for similar past plans
        past_plans = await self._query_similar_plans(task, context)

        # Step 3: Decompose into steps
        if task_type == TaskType.HARDWARE_INIT:
            steps = await self._decompose_hardware_init(task, context)
        elif task_type == TaskType.CODE_GENERATION:
            steps = await self._decompose_code_gen(task, context)
        elif task_type == TaskType.DEBUGGING:
            steps = await self._decompose_debugging(task, context)
        elif task_type == TaskType.ANALYSIS:
            steps = await self._decompose_analysis(task, context)
        else:
            steps = await self._decompose_generic(task, context)

        # Step 4: Add dependencies based on hardware constraints
        steps = self._resolve_dependencies(steps, task_type)

        # Step 5: Assign agents to steps
        steps = self._assign_agents(steps, task_type)

        plan = ExecutionPlan(
            plan_id=plan_id,
            original_task=task,
            steps=steps,
        )

        logger.info(
            "plan_created",
            plan_id=plan_id,
            steps=len(steps),
            task_type=task_type.value,
        )

        return plan

    def _classify_task(self, task: str) -> TaskType:
        """Classify task into high-level type."""
        t = task.lower()

        if any(k in t for k in ["init", "initialize", "configure", "setup", "enable"]):
            if any(k in t for k in ["can", "uart", "spi", "i2c", "gpio", "timer", "dma", "interrupt"]):
                return TaskType.HARDWARE_INIT

        if any(k in t for k in ["generate", "implement", "write", "create", "add"]):
            if any(k in t for k in ["code", "driver", "function", "handler"]):
                return TaskType.CODE_GENERATION

        if any(k in t for k in ["debug", "fix", "bug", "error", "issue", "problem", "crash", "hang"]):
            return TaskType.DEBUGGING

        if any(k in t for k in ["analyze", "check", "review", "examine", "inspect"]):
            return TaskType.ANALYSIS

        if any(k in t for k in ["refactor", "improve", "optimize", "clean"]):
            return TaskType.REFACTOR

        if any(k in t for k in ["test", "verify", "validate"]):
            return TaskType.TESTING

        if any(k in t for k in ["build", "compile", "flash", "upload"]):
            return TaskType.BUILD

        return TaskType.PLANNING

    async def _query_similar_plans(
        self, task: str, context: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Query KB for similar past plans."""
        if not self._kb:
            return []

        results = await self._kb.query_by_text(
            text=task,
            chip_family=context.get("chip_family"),
            top_k=3,
        )

        return [
            {"title": r.entry.title, "content": r.entry.content, "score": r.score}
            for r in results
        ]

    # ─── Task Decomposition ───────────────────────────────────────────

    async def _decompose_hardware_init(
        self, task: str, context: dict[str, Any]
    ) -> list[PlanStep]:
        """Decompose hardware initialization into steps."""
        t = task.lower()
        steps: list[PlanStep] = []
        import uuid

        # Always start with analysis
        steps.append(PlanStep(
            step_id=str(uuid.uuid4())[:8],
            name="Analyze hardware requirements",
            description=f"Analyze task and identify required peripherals: {task}",
            task_type=TaskType.ANALYSIS,
        ))

        if "can" in t:
            steps.extend([
                PlanStep(
                    step_id=str(uuid.uuid4())[:8],
                    name="Validate CAN clock configuration",
                    description="Check APB1 clock speed, calculate bit timing for target baudrate",
                    task_type=TaskType.ANALYSIS,
                ),
                PlanStep(
                    step_id=str(uuid.uuid4())[:8],
                    name="Plan CAN pin routing",
                    description="Determine TX/RX pins, validate AF mapping, check availability",
                    task_type=TaskType.PLANNING,
                ),
                PlanStep(
                    step_id=str(uuid.uuid4())[:8],
                    name="Generate CAN initialization code",
                    description="Generate register-level or HAL CAN initialization sequence",
                    task_type=TaskType.CODE_GENERATION,
                ),
            ])
        elif "uart" in t or "usart" in t or "serial" in t:
            steps.extend([
                PlanStep(
                    step_id=str(uuid.uuid4())[:8],
                    name="Calculate UART baudrate",
                    description="Verify baudrate against APB2 clock, calculate BRR value",
                    task_type=TaskType.ANALYSIS,
                ),
                PlanStep(
                    step_id=str(uuid.uuid4())[:8],
                    name="Plan UART pin routing",
                    description="Configure TX/RX pins with correct alternate function",
                    task_type=TaskType.PLANNING,
                ),
                PlanStep(
                    step_id=str(uuid.uuid4())[:8],
                    name="Generate UART code",
                    description="Generate UART initialization and TX/RX functions",
                    task_type=TaskType.CODE_GENERATION,
                ),
            ])
        elif "gpio" in t or "led" in t or "button" in t:
            steps.extend([
                PlanStep(
                    step_id=str(uuid.uuid4())[:8],
                    name="Verify GPIO pin availability",
                    description="Check pin is not reserved, validate voltage/current limits",
                    task_type=TaskType.ANALYSIS,
                ),
                PlanStep(
                    step_id=str(uuid.uuid4())[:8],
                    name="Generate GPIO code",
                    description="Generate GPIO initialization and read/write functions",
                    task_type=TaskType.CODE_GENERATION,
                ),
            ])
        elif "timer" in t or "pwm" in t:
            steps.extend([
                PlanStep(
                    step_id=str(uuid.uuid4())[:8],
                    name="Calculate timer clock and prescaler",
                    description="Determine TIM clock source, calculate PSC and ARR for target frequency",
                    task_type=TaskType.ANALYSIS,
                ),
                PlanStep(
                    step_id=str(uuid.uuid4())[:8],
                    name="Generate PWM/timer code",
                    description="Generate timer initialization and PWM configuration",
                    task_type=TaskType.CODE_GENERATION,
                ),
            ])
        elif "dma" in t:
            steps.extend([
                PlanStep(
                    step_id=str(uuid.uuid4())[:8],
                    name="Plan DMA channel and request mapping",
                    description="Select DMA channel compatible with peripheral request",
                    task_type=TaskType.PLANNING,
                ),
                PlanStep(
                    step_id=str(uuid.uuid4())[:8],
                    name="Generate DMA code",
                    description="Generate DMA configuration and transfer functions",
                    task_type=TaskType.CODE_GENERATION,
                ),
            ])
        elif "interrupt" in t or "irq" in t:
            steps.extend([
                PlanStep(
                    step_id=str(uuid.uuid4())[:8],
                    name="Verify IRQ availability",
                    description="Check NVIC priority, confirm IRQ line not used",
                    task_type=TaskType.ANALYSIS,
                ),
                PlanStep(
                    step_id=str(uuid.uuid4())[:8],
                    name="Generate interrupt handler",
                    description="Generate NVIC configuration and ISR implementation",
                    task_type=TaskType.CODE_GENERATION,
                ),
            ])

        # Always end with validation
        steps.append(PlanStep(
            step_id=str(uuid.uuid4())[:8],
            name="Validate generated code",
            description="Run hardware validation against rules, check for conflicts",
            task_type=TaskType.ANALYSIS,
        ))

        return steps

    async def _decompose_code_gen(
        self, task: str, context: dict[str, Any]
    ) -> list[PlanStep]:
        """Decompose code generation into steps."""
        import uuid
        steps = [
            PlanStep(
                step_id=str(uuid.uuid4())[:8],
                name="Understand code requirements",
                description=f"Parse code generation request: {task}",
                task_type=TaskType.ANALYSIS,
            ),
            PlanStep(
                step_id=str(uuid.uuid4())[:8],
                name="Generate code",
                description="Generate C code based on requirements",
                task_type=TaskType.CODE_GENERATION,
            ),
            PlanStep(
                step_id=str(uuid.uuid4())[:8],
                name="Validate generated code",
                description="Validate against hardware constraints",
                task_type=TaskType.ANALYSIS,
            ),
        ]
        return steps

    async def _decompose_debugging(
        self, task: str, context: dict[str, Any]
    ) -> list[PlanStep]:
        """Decompose debugging into steps."""
        import uuid
        steps = [
            PlanStep(
                step_id=str(uuid.uuid4())[:8],
                name="Categorize issue",
                description=f"Identify issue type from symptom: {task}",
                task_type=TaskType.ANALYSIS,
            ),
            PlanStep(
                step_id=str(uuid.uuid4())[:8],
                name="Query past issues",
                description="Search KB for similar known issues",
                task_type=TaskType.ANALYSIS,
            ),
            PlanStep(
                step_id=str(uuid.uuid4())[:8],
                name="Perform root cause analysis",
                description="Apply debugging reasoning to identify root cause",
                task_type=TaskType.DEBUGGING,
            ),
            PlanStep(
                step_id=str(uuid.uuid4())[:8],
                name="Generate fix",
                description="Produce fix recommendations with code snippets",
                task_type=TaskType.CODE_GENERATION,
            ),
        ]
        return steps

    async def _decompose_analysis(
        self, task: str, context: dict[str, Any]
    ) -> list[PlanStep]:
        """Decompose analysis into steps."""
        import uuid
        return [
            PlanStep(
                step_id=str(uuid.uuid4())[:8],
                name="Gather context",
                description=f"Gather hardware and code context: {task}",
                task_type=TaskType.ANALYSIS,
            ),
            PlanStep(
                step_id=str(uuid.uuid4())[:8],
                name="Perform analysis",
                description="Run formal reasoning and KB queries",
                task_type=TaskType.ANALYSIS,
            ),
        ]

    async def _decompose_generic(
        self, task: str, context: dict[str, Any]
    ) -> list[PlanStep]:
        """Generic decomposition for unknown task types."""
        import uuid
        return [
            PlanStep(
                step_id=str(uuid.uuid4())[:8],
                name="Understand task",
                description=f"Parse and understand: {task}",
                task_type=TaskType.PLANNING,
            ),
            PlanStep(
                step_id=str(uuid.uuid4())[:8],
                name="Execute task",
                description="Perform the requested task",
                task_type=TaskType.PLANNING,
            ),
        ]

    # ─── Dependency Resolution ────────────────────────────────────────

    def _resolve_dependencies(
        self, steps: list[PlanStep], task_type: TaskType
    ) -> list[PlanStep]:
        """Add implicit dependencies based on hardware constraints."""
        # ANALYSIS steps must complete before CODE_GENERATION steps
        analysis_ids = {s.step_id for s in steps if s.task_type == TaskType.ANALYSIS}
        planning_ids = {s.step_id for s in steps if s.task_type == TaskType.PLANNING}
        code_ids = {s.step_id for s in steps if s.task_type == TaskType.CODE_GENERATION}
        debug_ids = {s.step_id for s in steps if s.task_type == TaskType.DEBUGGING}

        for step in steps:
            if step.task_type == TaskType.CODE_GENERATION:
                # Code gen depends on analysis/planning
                deps = list(analysis_ids | planning_ids)
                step.dependencies = list(set(step.dependencies + deps))

            if step.task_type == TaskType.DEBUGGING:
                # Debugging: fix depends on diagnose
                if step.name.lower().startswith("generate fix"):
                    diagnose_ids = {s.step_id for s in steps if "diagnose" in s.name.lower() or "categorize" in s.name.lower()}
                    step.dependencies = list(set(step.dependencies + list(diagnose_ids)))

        return steps

    def _assign_agents(
        self, steps: list[PlanStep], task_type: TaskType
    ) -> list[PlanStep]:
        """Assign agent types to each step."""
        agent_mapping = {
            TaskType.ANALYSIS: "analyzer",
            TaskType.PLANNING: "planner",
            TaskType.CODE_GENERATION: "coder",
            TaskType.DEBUGGING: "debugger",
        }

        for step in steps:
            if step.assigned_agent is None:
                step.assigned_agent = agent_mapping.get(step.task_type, "general")

        return steps

    # ─── Plan Execution Support ───────────────────────────────────────

    def get_next_ready_steps(self, plan: ExecutionPlan) -> list[PlanStep]:
        """Get steps that are ready to execute (dependencies met)."""
        completed_ids = {s.step_id for s in plan.completed_steps}
        ready = []

        for step in plan.steps:
            if step.status != PlanStatus.PENDING:
                continue
            # Check all dependencies are completed
            if all(dep_id in completed_ids for dep_id in step.dependencies):
                ready.append(step)

        return ready

    def get_plan_progress(self, plan: ExecutionPlan) -> dict[str, Any]:
        """Get plan execution progress."""
        total = len(plan.steps)
        completed = len(plan.completed_steps)
        failed = len(plan.failed_steps)
        pending = len(plan.pending_steps)

        return {
            "plan_id": plan.plan_id,
            "total_steps": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "progress_pct": round(completed / total * 100, 1) if total > 0 else 0,
            "status": plan.status.value,
        }
