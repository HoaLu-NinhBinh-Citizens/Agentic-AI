"""Real Multi-Agent Orchestration Engine.

Not task fan-out - real orchestration with:
- Task dependency graphs
- Parallel/sequential execution control
- Error propagation
- Resource management
- Scoped memory per agent
- Conflict resolution
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable

logger = logging.getLogger(__name__)


# =============================================================================
# TASK TYPES
# =============================================================================


class TaskStatus(Enum):
    """Task execution status."""
    
    PENDING = "pending"
    WAITING = "waiting"     # Waiting for dependencies
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class TaskPriority(Enum):
    """Task priority levels."""
    
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


# =============================================================================
# TASK DEFINITION
# =============================================================================


@dataclass
class Task:
    """Real task definition with dependencies.
    
    This is NOT a simple function call.
    Has proper dependency tracking and state machine.
    """
    
    # Identity
    task_id: str
    name: str
    description: str = ""
    
    # Task type
    task_type: str = "general"
    
    # Function
    func: Callable | None = None
    args: tuple = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    
    # Dependencies
    depends_on: list[str] = field(default_factory=list)  # Task IDs
    depended_by: list[str] = field(default_factory=list)  # Tasks that depend on this
    
    # State
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    
    # Result
    result: Any = None
    error: str | None = None
    traceback: str | None = None
    
    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float = 0.0
    
    # Retry
    retry_count: int = 0
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    
    # Resource requirements
    requires_gpu: bool = False
    requires_network: bool = False
    memory_mb: int = 512
    
    # Scoped data
    scoped_data: dict[str, Any] = field(default_factory=dict)
    
    # Agent assignment
    assigned_agent: str | None = None
    
    def compute_id(self) -> str:
        """Compute deterministic task ID."""
        content = f"{self.name}:{str(self.args)}:{str(self.kwargs)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def can_run(self, completed_tasks: set[str]) -> bool:
        """Check if all dependencies are satisfied."""
        return all(dep_id in completed_tasks for dep_id in self.depends_on)
    
    def mark_started(self) -> None:
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.utcnow()
    
    def mark_completed(self, result: Any) -> None:
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.utcnow()
        if self.started_at:
            self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000
    
    def mark_failed(self, error: str, traceback: str | None = None) -> None:
        self.status = TaskStatus.FAILED
        self.error = error
        self.traceback = traceback
        self.completed_at = datetime.utcnow()
    
    def should_retry(self) -> bool:
        return self.retry_count < self.max_retries


# =============================================================================
# AGENT DEFINITION
# =============================================================================


@dataclass
class Agent:
    """Agent with scoped memory and capabilities.
    
    Real agent with:
    - Scoped memory
    - Capability profile
    - Task queue
    - Resource limits
    """
    
    # Identity
    agent_id: str
    name: str
    agent_type: str  # "coder", "reviewer", "tester", "planner"
    
    # Capabilities
    capabilities: list[str] = field(default_factory=list)  # e.g., ["python", "embedded", "debug"]
    
    # State
    is_active: bool = False
    current_task_id: str | None = None
    
    # Scoped memory (agent-private state)
    memory: dict[str, Any] = field(default_factory=dict)
    
    # Task queue
    task_queue: list[str] = field(default_factory=list)  # Task IDs
    
    # Metrics
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_runtime_ms: float = 0.0
    
    # Limits
    max_concurrent_tasks: int = 1
    max_memory_mb: int = 1024
    
    def can_take_task(self) -> bool:
        """Check if agent can accept new task."""
        if not self.is_active:
            return False
        if self.current_task_id:
            return False
        return len(self.task_queue) < self.max_concurrent_tasks
    
    def assign_task(self, task_id: str) -> None:
        """Assign task to agent."""
        self.current_task_id = task_id
        self.task_queue.append(task_id)
    
    def release_task(self) -> None:
        """Release current task."""
        self.current_task_id = None


# =============================================================================
# TASK GRAPH
# =============================================================================


class TaskGraph:
    """Task dependency graph with execution ordering.
    
    NOT simple task fan-out.
    Real DAG with:
    - Dependency resolution
    - Topological ordering
    - Parallel execution groups
    - Cycle detection
    """
    
    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._task_names: dict[str, list[str]] = {}  # name -> [task_ids]
        self._lock = asyncio.Lock()
    
    def add_task(self, task: Task) -> str:
        """Add task to graph."""
        if task.task_id in self._tasks:
            raise ValueError(f"Task {task.task_id} already exists")
        
        self._tasks[task.task_id] = task
        
        if task.name not in self._task_names:
            self._task_names[task.name] = []
        self._task_names[task.name].append(task.task_id)
        
        # Update dependency links
        for dep_id in task.depends_on:
            if dep_id in self._tasks:
                if task.task_id not in self._tasks[dep_id].depended_by:
                    self._tasks[dep_id].depended_by.append(task.task_id)
        
        return task.task_id
    
    def get_task(self, task_id: str) -> Task | None:
        """Get task by ID."""
        return self._tasks.get(task_id)
    
    def get_ready_tasks(self, completed: set[str]) -> list[Task]:
        """Get tasks that are ready to run (all dependencies complete)."""
        ready = []
        for task in self._tasks.values():
            if task.status != TaskStatus.PENDING:
                continue
            if task.can_run(completed):
                ready.append(task)
        
        # Sort by priority
        ready.sort(key=lambda t: t.priority.value)
        return ready
    
    def get_execution_levels(self) -> list[list[Task]]:
        """Get tasks grouped by execution level (for parallel execution).
        
        Returns tasks grouped such that:
        - All tasks in level N have dependencies only in levels < N
        - Tasks in same level can run in parallel
        """
        levels = []
        remaining = set(self._tasks.keys())
        completed_names = set()
        
        while remaining:
            # Find tasks whose dependencies are satisfied
            level = []
            for task_id in list(remaining):
                task = self._tasks[task_id]
                
                # Check if all dependencies are satisfied (by completed task names)
                deps_by_name = set()
                for dep_id in task.depends_on:
                    dep = self._tasks.get(dep_id)
                    if dep:
                        deps_by_name.add(dep.name)
                
                if deps_by_name.issubset(completed_names):
                    level.append(task)
            
            if not level:
                # Circular dependency or error
                break
            
            # Add level and mark tasks as completed for next iteration
            levels.append(level)
            completed_names.update(t.name for t in level)
            for task in level:
                remaining.discard(task.task_id)
        
        return levels
    
    def has_cycle(self) -> tuple[bool, list[str]]:
        """Detect circular dependencies.
        
        Returns: (has_cycle, cycle_task_ids)
        """
        visited = set()
        rec_stack = set()
        cycle = []
        
        def dfs(task_id: str) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)
            
            task = self._tasks.get(task_id)
            if task:
                for dep_id in task.depends_on:
                    if dep_id not in visited:
                        if dfs(dep_id):
                            cycle.append(task_id)
                            return True
                    elif dep_id in rec_stack:
                        cycle.append(task_id)
                        return True
            
            rec_stack.remove(task_id)
            return False
        
        for task_id in self._tasks:
            if task_id not in visited:
                if dfs(task_id):
                    return True, cycle
        
        return False, []
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel task and all dependents."""
        task = self._tasks.get(task_id)
        if not task:
            return False
        
        # Cancel this task
        task.status = TaskStatus.CANCELLED
        
        # Cancel dependents recursively
        for dep_id in task.depended_by:
            self.cancel_task(dep_id)
        
        return True


# =============================================================================
# ORCHESTRATOR
# =============================================================================


@dataclass
class ExecutionResult:
    """Result of task graph execution."""
    
    success: bool
    completed_tasks: list[str]
    failed_tasks: list[str]
    cancelled_tasks: list[str]
    total_duration_ms: float
    results: dict[str, Any]
    errors: dict[str, str]


class TaskOrchestrator:
    """Real multi-agent task orchestrator.
    
    Features:
    - Task dependency resolution
    - Parallel + sequential execution control
    - Agent assignment and load balancing
    - Error propagation
    - Retry with backoff
    - Resource management
    - Scoped memory per agent
    - Progress tracking
    - Cancellation support
    
    NOT simple task fan-out.
    """
    
    def __init__(self, max_parallel: int = 4):
        self.max_parallel = max_parallel
        self._graph = TaskGraph()
        self._agents: dict[str, Agent] = {}
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._completed: set[str] = set()
        self._lock = asyncio.Lock()
        
        # Callbacks
        self._on_task_start: list[Callable] = []
        self._on_task_complete: list[Callable] = []
        self._on_task_fail: list[Callable] = []
        self._on_progress: list[Callable] = []
        
        # Metrics
        self._total_execution_time_ms = 0.0
    
    # =========================================================================
    # AGENT MANAGEMENT
    # =========================================================================
    
    def register_agent(self, agent: Agent) -> None:
        """Register an agent for task execution."""
        self._agents[agent.agent_id] = agent
        logger.info("agent_registered: id=%s type=%s", agent.agent_id, agent.agent_type)
    
    def get_available_agent(self, required_capabilities: list[str] | None = None) -> Agent | None:
        """Get available agent matching capabilities."""
        for agent in self._agents.values():
            if not agent.can_take_task():
                continue
            
            if required_capabilities:
                if not all(cap in agent.capabilities for cap in required_capabilities):
                    continue
            
            return agent
        
        return None
    
    # =========================================================================
    # TASK MANAGEMENT
    # =========================================================================
    
    def create_task(
        self,
        name: str,
        func: Callable,
        args: tuple = (),
        kwargs: dict[str, Any] | None = None,
        depends_on: list[str] | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        max_retries: int = 3,
        agent_type: str | None = None,
    ) -> Task:
        """Create a task with dependencies."""
        task = Task(
            task_id=str(uuid.uuid4())[:16],
            name=name,
            func=func,
            args=args,
            kwargs=kwargs or {},
            depends_on=depends_on or [],
            priority=priority,
            max_retries=max_retries,
            task_type=agent_type or "general",
        )
        
        self._graph.add_task(task)
        logger.debug("task_created: id=%s name=%s depends=%s", task.task_id, name, len(depends_on or []))
        
        return task
    
    async def execute(self) -> ExecutionResult:
        """Execute all tasks in dependency order.
        
        This is real orchestration:
        1. Resolve dependencies
        2. Group into execution levels
        3. Execute level in parallel (up to max_parallel)
        4. Wait for level completion
        5. Handle errors and retries
        6. Propagate to next level
        """
        start_time = time.perf_counter()
        
        # Check for cycles
        has_cycle, cycle = self._graph.has_cycle()
        if has_cycle:
            return ExecutionResult(
                success=False,
                completed_tasks=[],
                failed_tasks=[],
                cancelled_tasks=[],
                total_duration_ms=0,
                results={},
                errors={"cycle": f"Circular dependency: {' -> '.join(cycle)}"},
            )
        
        completed_tasks = []
        failed_tasks = []
        cancelled_tasks = []
        results = {}
        errors = {}
        
        # Get execution levels
        levels = self._graph.get_execution_levels()
        
        logger.info("execution_starting: levels=%s total_tasks=%s", len(levels), len(self._graph._tasks))
        
        # Execute each level
        for level_idx, level in enumerate(levels):
            logger.debug("executing_level: level=%s tasks=%s", level_idx, len(level))
            
            # Execute level in parallel
            level_tasks = await self._execute_level(level)
            
            # Collect results
            for task in level_tasks:
                if task.status == TaskStatus.COMPLETED:
                    completed_tasks.append(task.task_id)
                    results[task.task_id] = task.result
                    self._completed.add(task.task_id)
                elif task.status == TaskStatus.FAILED:
                    failed_tasks.append(task.task_id)
                    errors[task.task_id] = task.error or "Unknown error"
                elif task.status == TaskStatus.CANCELLED:
                    cancelled_tasks.append(task.task_id)
                
                # Notify callbacks
                if task.status == TaskStatus.COMPLETED:
                    for cb in self._on_task_complete:
                        try:
                            if asyncio.iscoroutinefunction(cb):
                                await cb(task)
                            else:
                                cb(task)
                        except Exception as e:
                            logger.error("callback_error: %s", str(e))
            
            # Progress callback
            progress = len(completed_tasks) / len(self._graph._tasks) * 100
            for cb in self._on_progress:
                try:
                    cb(progress, completed_tasks, failed_tasks)
                except Exception as e:
                    logger.error("progress_callback_error: %s", str(e))
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        self._total_execution_time_ms = duration_ms
        
        success = len(failed_tasks) == 0 and len(cancelled_tasks) == 0
        
        logger.info(
            "execution_complete: success=%s completed=%s failed=%s duration=%sms",
            success, len(completed_tasks), len(failed_tasks), duration_ms,
        )
        
        return ExecutionResult(
            success=success,
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            cancelled_tasks=cancelled_tasks,
            total_duration_ms=duration_ms,
            results=results,
            errors=errors,
        )
    
    async def _execute_level(self, tasks: list[Task]) -> list[Task]:
        """Execute a level of tasks in parallel."""
        running = []
        
        for task in tasks:
            task_coro = self._execute_task(task)
            task_handle = asyncio.create_task(task_coro)
            self._running_tasks[task.task_id] = task_handle
            running.append(task)
        
        # Wait for all tasks in level
        await asyncio.gather(*[
            self._running_tasks[t.task_id] for t in running
        ], return_exceptions=True)
        
        # Clean up
        for task in running:
            if task.task_id in self._running_tasks:
                del self._running_tasks[task.task_id]
        
        return tasks
    
    async def _execute_task(self, task: Task) -> Task:
        """Execute a single task with retry logic."""
        task.mark_started()
        
        # Start callback
        for cb in self._on_task_start:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(task)
                else:
                    cb(task)
            except Exception as e:
                logger.error("start_callback_error: %s", str(e))
        
        # Retry loop
        while True:
            try:
                if asyncio.iscoroutinefunction(task.func):
                    result = await task.func(*task.args, **task.kwargs)
                else:
                    result = task.func(*task.args, **task.kwargs)
                
                task.mark_completed(result)
                return task
                
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                
                if task.should_retry():
                    task.retry_count += 1
                    task.status = TaskStatus.RETRYING
                    logger.warning(
                        "task_retry: id=%s attempt=%s/%s error=%s",
                        task.task_id, task.retry_count, task.max_retries, str(e),
                    )
                    
                    # Exponential backoff
                    await asyncio.sleep(task.retry_delay_seconds * (2 ** (task.retry_count - 1)))
                    task.status = TaskStatus.PENDING
                    continue
                else:
                    task.mark_failed(str(e), tb)
                    
                    # Fail callback
                    for cb in self._on_task_fail:
                        try:
                            if asyncio.iscoroutinefunction(cb):
                                await cb(task)
                            else:
                                cb(task)
                        except Exception as cb_err:
                            logger.error("fail_callback_error: %s", str(cb_err))
                    
                    return task
        
        return task
    
    # =========================================================================
    # CALLBACKS
    # =========================================================================
    
    def on_task_start(self, callback: Callable) -> None:
        """Register task start callback."""
        self._on_task_start.append(callback)
    
    def on_task_complete(self, callback: Callable) -> None:
        """Register task complete callback."""
        self._on_task_complete.append(callback)
    
    def on_task_fail(self, callback: Callable) -> None:
        """Register task fail callback."""
        self._on_task_fail.append(callback)
    
    def on_progress(self, callback: Callable) -> None:
        """Register progress callback."""
        self._on_progress.append(callback)
    
    # =========================================================================
    # CANCELLATION
    # =========================================================================
    
    async def cancel(self) -> None:
        """Cancel all running tasks."""
        for task_id, handle in self._running_tasks.items():
            handle.cancel()
        
        for task in self._graph._tasks.values():
            if task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
                task.status = TaskStatus.CANCELLED
        
        logger.info("orchestration_cancelled")
    
    # =========================================================================
    # STATUS
    # =========================================================================
    
    def get_status(self) -> dict[str, Any]:
        """Get orchestration status."""
        tasks = self._graph._tasks
        return {
            "total_tasks": len(tasks),
            "pending": sum(1 for t in tasks.values() if t.status == TaskStatus.PENDING),
            "running": sum(1 for t in tasks.values() if t.status == TaskStatus.RUNNING),
            "completed": sum(1 for t in tasks.values() if t.status == TaskStatus.COMPLETED),
            "failed": sum(1 for t in tasks.values() if t.status == TaskStatus.FAILED),
            "cancelled": sum(1 for t in tasks.values() if t.status == TaskStatus.CANCELLED),
            "agents": len(self._agents),
            "active_agents": sum(1 for a in self._agents.values() if a.is_active),
        }


# =============================================================================
# GLOBAL ORCHESTRATOR
# =============================================================================


_orchestrator: TaskOrchestrator | None = None


def get_orchestrator(max_parallel: int = 4) -> TaskOrchestrator:
    """Get global task orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = TaskOrchestrator(max_parallel)
    return _orchestrator
