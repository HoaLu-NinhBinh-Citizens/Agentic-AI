"""Test orchestrator for multi-board parallel testing (Phase 7.5).

Orchestrates test execution across multiple boards:
- Parallel test scheduling
- Resource allocation
- Result aggregation
- Failure handling
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class TestStatus(Enum):
    """Test execution status."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    TIMEOUT = "timeout"


class TestPriority(Enum):
    """Test priority levels."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class TestTask:
    """Test task to execute."""
    task_id: str
    test_name: str
    test_command: str
    target_board: str = ""
    priority: TestPriority = TestPriority.NORMAL
    timeout_minutes: int = 30
    retries: int = 0
    max_retries: int = 2
    
    # Dependencies
    depends_on: list[str] = field(default_factory=list)
    
    # State
    status: TestStatus = TestStatus.PENDING
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_seconds: float = 0.0
    error_message: str = ""
    attempts: int = 0


@dataclass
class TestResult:
    """Result of test execution."""
    task_id: str
    status: TestStatus
    duration_seconds: float
    output: str = ""
    error: str = ""
    board_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TestBatch:
    """Batch of tests for execution."""
    batch_id: str
    tasks: list[TestTask]
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    @property
    def total_tasks(self) -> int:
        return len(self.tasks)
    
    @property
    def completed_tasks(self) -> int:
        return sum(1 for t in self.tasks if t.status in [
            TestStatus.PASSED, TestStatus.FAILED, TestStatus.SKIPPED, TestStatus.ERROR
        ])
    
    @property
    def progress(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.completed_tasks / self.total_tasks


class TestExecutor:
    """Executes a single test task."""
    
    def __init__(self) -> None:
        self._running: dict[str, asyncio.Task] = {}
    
    async def execute(self, task: TestTask) -> TestResult:
        """Execute a single test task."""
        import subprocess
        import shlex
        
        task.status = TestStatus.RUNNING
        task.start_time = datetime.now()
        task.attempts += 1
        
        logger.info("Executing test", task_id=task.task_id, name=task.test_name)
        
        try:
            # Execute test command
            args = shlex.split(task.test_command) if isinstance(task.test_command, str) else task.test_command
            
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            self._running[task.task_id] = asyncio.current_task()
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=task.timeout_minutes * 60,
                )
                
                task.end_time = datetime.now()
                task.duration_seconds = (task.end_time - task.start_time).total_seconds()
                
                if proc.returncode == 0:
                    task.status = TestStatus.PASSED
                    return TestResult(
                        task_id=task.task_id,
                        status=TestStatus.PASSED,
                        duration_seconds=task.duration_seconds,
                        output=stdout.decode() if stdout else "",
                    )
                else:
                    task.status = TestStatus.FAILED
                    return TestResult(
                        task_id=task.task_id,
                        status=TestStatus.FAILED,
                        duration_seconds=task.duration_seconds,
                        output=stdout.decode() if stdout else "",
                        error=stderr.decode() if stderr else "",
                    )
            except asyncio.TimeoutError:
                proc.kill()
                task.status = TestStatus.TIMEOUT
                task.end_time = datetime.now()
                task.duration_seconds = (task.end_time - task.start_time).total_seconds()
                return TestResult(
                    task_id=task.task_id,
                    status=TestStatus.TIMEOUT,
                    duration_seconds=task.duration_seconds,
                    error="Test timed out",
                )
            
        except Exception as e:
            task.status = TestStatus.ERROR
            task.end_time = datetime.now()
            task.duration_seconds = (task.end_time - task.start_time).total_seconds()
            task.error_message = str(e)
            return TestResult(
                task_id=task.task_id,
                status=TestStatus.ERROR,
                duration_seconds=task.duration_seconds,
                error=str(e),
            )
        
        finally:
            self._running.pop(task.task_id, None)
        
        return TestResult(
            task_id=task.task_id,
            status=task.status,
            duration_seconds=task.duration_seconds,
        )
    
    async def cancel(self, task_id: str) -> bool:
        """Cancel a running test."""
        if task_id in self._running:
            self._running[task_id].cancel()
            return True
        return False


class TestOrchestrator:
    """Orchestrates parallel test execution across multiple boards.
    
    Phase 7.5: Test orchestrator - Multi-board parallel testing
    """
    
    def __init__(self, max_parallel: int = 4) -> None:
        self._max_parallel = max_parallel
        self._executor = TestExecutor()
        self._batches: dict[str, TestBatch] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._results: dict[str, list[TestResult]] = {}
        self._callbacks: dict[str, list[Callable]] = {
            "task_complete": [],
            "batch_complete": [],
            "task_failed": [],
        }
    
    def register_callback(
        self,
        event: str,
        callback: Callable[[TestResult | TestBatch], None],
    ) -> None:
        """Register callback for events."""
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _emit(self, event: str, data: Any) -> None:
        """Emit event to callbacks."""
        for callback in self._callbacks.get(event, []):
            try:
                callback(data)
            except Exception as e:
                logger.error("Callback error", event=event, error=str(e))
    
    def create_batch(
        self,
        batch_id: str,
        tasks: list[TestTask],
    ) -> TestBatch:
        """Create a new test batch."""
        batch = TestBatch(batch_id=batch_id, tasks=tasks)
        self._batches[batch_id] = batch
        self._results[batch_id] = []
        return batch
    
    def get_ready_tasks(self, batch: TestBatch) -> list[TestTask]:
        """Get tasks that are ready to run (dependencies satisfied)."""
        ready = []
        for task in batch.tasks:
            if task.status != TestStatus.PENDING:
                continue
            
            # Check dependencies
            deps_satisfied = True
            for dep_id in task.depends_on:
                dep_task = next((t for t in batch.tasks if t.task_id == dep_id), None)
                if dep_task and dep_task.status not in [TestStatus.PASSED, TestStatus.SKIPPED]:
                    deps_satisfied = False
                    break
            
            if deps_satisfied:
                ready.append(task)
        
        return ready
    
    async def run_batch(
        self,
        batch_id: str,
        board_allocator: Callable[[], str | None] | None = None,
    ) -> TestBatch:
        """Run a test batch with parallel execution."""
        if batch_id not in self._batches:
            raise ValueError(f"Batch {batch_id} not found")
        
        batch = self._batches[batch_id]
        batch.started_at = datetime.now()
        
        logger.info("Starting batch", batch_id=batch_id, tasks=batch.total_tasks)
        
        # Sort tasks by priority
        batch.tasks.sort(key=lambda t: t.priority.value, reverse=True)
        
        # Main execution loop
        while batch.completed_tasks < batch.total_tasks:
            # Get ready tasks
            ready_tasks = self.get_ready_tasks(batch)
            
            # Limit parallel execution
            running_count = sum(1 for t in batch.tasks if t.status == TestStatus.RUNNING)
            available_slots = self._max_parallel - running_count
            
            # Execute ready tasks
            for task in ready_tasks[:available_slots]:
                # Allocate board if needed
                if board_allocator and not task.target_board:
                    board = board_allocator()
                    if board:
                        task.target_board = board
                    else:
                        # No board available, skip for now
                        continue
                
                # Execute task
                coro = self._execute_task(batch, task)
                task_handle = asyncio.create_task(coro)
                self._running[task.task_id] = task_handle
            
            # Wait for any task to complete
            if self._running:
                done, _ = await asyncio.wait(
                    self._running.values(),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                
                for task_handle in done:
                    task_id = next(
                        (tid for tid, th in self._running.items() if th == task_handle),
                        None,
                    )
                    if task_id:
                        del self._running[task_id]
            
            # Check for retries
            for task in batch.tasks:
                if task.status in [TestStatus.FAILED, TestStatus.ERROR, TestStatus.TIMEOUT]:
                    if task.attempts < task.max_retries:
                        task.status = TestStatus.PENDING
                        task.retries += 1
                        logger.info("Retrying task", task_id=task.task_id, attempt=task.attempts + 1)
        
        batch.completed_at = datetime.now()
        logger.info("Batch completed", batch_id=batch_id, duration=(batch.completed_at - batch.started_at).total_seconds())
        
        self._emit("batch_complete", batch)
        return batch
    
    async def _execute_task(self, batch: TestBatch, task: TestTask) -> TestResult:
        """Execute a single task and record result."""
        result = await self._executor.execute(task)
        result.board_id = task.target_board
        self._results[batch.batch_id].append(result)
        
        self._emit("task_complete", result)
        
        if result.status in [TestStatus.FAILED, TestStatus.ERROR]:
            self._emit("task_failed", result)
        
        return result
    
    def get_batch_status(self, batch_id: str) -> TestBatch | None:
        """Get batch status."""
        return self._batches.get(batch_id)
    
    def get_results(self, batch_id: str) -> list[TestResult]:
        """Get all results for a batch."""
        return self._results.get(batch_id, [])
    
    def cancel_batch(self, batch_id: str) -> bool:
        """Cancel a running batch."""
        if batch_id not in self._batches:
            return False
        
        # Cancel running tasks
        for task in self._batches[batch_id].tasks:
            if task.status == TestStatus.RUNNING:
                self._executor.cancel(task.task_id)
                task.status = TestStatus.SKIPPED
        
        # Cancel coroutines
        for task_id, handle in list(self._running.items()):
            if any(t.task_id == task_id for t in self._batches[batch_id].tasks):
                handle.cancel()
        
        logger.info("Batch cancelled", batch_id=batch_id)
        return True
    
    def get_statistics(self, batch_id: str | None = None) -> dict[str, Any]:
        """Get execution statistics."""
        if batch_id:
            batches = [self._batches.get(batch_id)]
        else:
            batches = list(self._batches.values())
        
        results = self._results.get(batch_id, []) if batch_id else [
            r for results in self._results.values() for r in results
        ]
        
        return {
            "total_batches": len(batches),
            "total_tasks": sum(b.total_tasks for b in batches if b),
            "completed_tasks": sum(b.completed_tasks for b in batches if b),
            "running_tasks": len(self._running),
            "results_by_status": {
                s.value: sum(1 for r in results if r.status == s)
                for s in TestStatus
            },
            "total_duration": sum(r.duration_seconds for r in results),
            "avg_duration": sum(r.duration_seconds for r in results) / len(results) if results else 0,
        }


# Global singleton
_orchestrator: TestOrchestrator | None = None


def get_test_orchestrator(max_parallel: int = 4) -> TestOrchestrator:
    """Get global test orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = TestOrchestrator(max_parallel)
    return _orchestrator


if __name__ == "__main__":
    async def main():
        orchestrator = get_test_orchestrator(max_parallel=2)
        
        # Create test tasks
        tasks = [
            TestTask(
                task_id="test_001",
                test_name="UART test",
                test_command="python -m pytest tests/test_uart.py",
                priority=TestPriority.HIGH,
            ),
            TestTask(
                task_id="test_002",
                test_name="GPIO test",
                test_command="python -m pytest tests/test_gpio.py",
                priority=TestPriority.NORMAL,
            ),
            TestTask(
                task_id="test_003",
                test_name="Integration test",
                test_command="python -m pytest tests/test_integration.py",
                priority=TestPriority.LOW,
                depends_on=["test_001", "test_002"],
            ),
        ]
        
        # Create and run batch
        batch = orchestrator.create_batch("batch_001", tasks)
        
        print(f"Running batch with {batch.total_tasks} tasks...")
        result = await orchestrator.run_batch("batch_001")
        
        print(f"\nBatch completed!")
        print(f"  Progress: {result.progress:.0%}")
        
        # Results
        for r in orchestrator.get_results("batch_001"):
            print(f"  [{r.status.value}] {r.task_id}: {r.duration_seconds:.2f}s")
    
    asyncio.run(main())
