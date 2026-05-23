"""Tests for test orchestrator."""

import pytest
from src.infrastructure.hil.test_orchestrator import (
    TestOrchestrator,
    TestPriority,
    TestStatus,
    TestTask,
)


class TestTestTask:
    def test_task_creation(self):
        task = TestTask(
            task_id="test_001",
            test_name="UART test",
            test_command="pytest tests/test_uart.py",
        )
        assert task.task_id == "test_001"
        assert task.status == TestStatus.PENDING
        assert task.priority == TestPriority.NORMAL


class TestTestOrchestrator:
    def test_create_batch(self):
        orchestrator = TestOrchestrator(max_parallel=2)
        
        tasks = [
            TestTask(task_id="t1", test_name="Test 1", test_command="echo 1"),
            TestTask(task_id="t2", test_name="Test 2", test_command="echo 2"),
        ]
        
        batch = orchestrator.create_batch("batch_001", tasks)
        assert batch.batch_id == "batch_001"
        assert batch.total_tasks == 2

    def test_get_ready_tasks_no_dependencies(self):
        orchestrator = TestOrchestrator()
        
        tasks = [
            TestTask(task_id="t1", test_name="Test 1", test_command="echo 1"),
            TestTask(task_id="t2", test_name="Test 2", test_command="echo 2"),
        ]
        
        batch = orchestrator.create_batch("batch_001", tasks)
        ready = orchestrator.get_ready_tasks(batch)
        
        assert len(ready) == 2

    def test_get_ready_tasks_with_dependencies(self):
        orchestrator = TestOrchestrator()
        
        tasks = [
            TestTask(task_id="t1", test_name="Test 1", test_command="echo 1"),
            TestTask(
                task_id="t2",
                test_name="Test 2",
                test_command="echo 2",
                depends_on=["t1"],
            ),
        ]
        
        batch = orchestrator.create_batch("batch_001", tasks)
        ready = orchestrator.get_ready_tasks(batch)
        
        # Only t1 should be ready initially
        assert len(ready) == 1
        assert ready[0].task_id == "t1"

    def test_cancel_batch(self):
        orchestrator = TestOrchestrator()
        
        tasks = [
            TestTask(task_id="t1", test_name="Test 1", test_command="sleep 100"),
        ]
        
        orchestrator.create_batch("batch_001", tasks)
        assert orchestrator.cancel_batch("batch_001") is True

    def test_get_statistics(self):
        orchestrator = TestOrchestrator()
        
        orchestrator.create_batch("batch_001", [
            TestTask(task_id="t1", test_name="Test 1", test_command="echo 1"),
        ])
        
        stats = orchestrator.get_statistics()
        assert "total_batches" in stats
        assert stats["total_batches"] == 1
