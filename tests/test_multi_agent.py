"""
Tests for Multi-Agent System
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.multi_agent.agent import (
    AgentType,
    AgentStatus,
    BaseAgent,
    MessageBus,
    OrchestratorAgent,
    Task,
    AgentMessage,
    CodeGenAgent,
    ReviewAgent,
    SecurityAgent,
    TestAgent,
    DevOpsAgent,
    MonitoringAgent,
    UnifiedAgent,
)


class MockBaseAgent(BaseAgent):
    """Test implementation of BaseAgent"""

    async def process(self, task: Task):
        return {"result": f"Processed: {task.description}"}

    async def can_handle(self, task: Task):
        return True


class TestOrchestratorAgent:
    """Tests for OrchestratorAgent"""

    @pytest.fixture
    def orchestrator(self):
        return OrchestratorAgent()

    @pytest.fixture
    def test_agent(self):
        return MockBaseAgent(AgentType.CODE_GEN)

    def test_orchestrator_initialization(self, orchestrator):
        assert orchestrator.status == AgentStatus.IDLE
        assert len(orchestrator.agents) == 0

    def test_register_agent(self, orchestrator, test_agent):
        orchestrator.register_agent(test_agent)
        assert AgentType.CODE_GEN in orchestrator.agents
        assert orchestrator.agents[AgentType.CODE_GEN] == test_agent

    @pytest.mark.asyncio
    async def test_process_task(self, orchestrator, test_agent):
        orchestrator.register_agent(test_agent)

        task = Task(
            type="codegen",
            description="Test task",
            context={},
            assigned_to=AgentType.CODE_GEN,
        )

        result = await orchestrator.process(task)
        assert result.get("result") == "Processed: Test task"

    def test_decompose_task_build(self, orchestrator):
        task = Task(
            type="build",
            description="Build project",
            context={},
        )
        sub_tasks = orchestrator._decompose_task(task)

        assert len(sub_tasks) == 2
        assert all(st.assigned_to for st in sub_tasks)

    def test_get_system_status(self, orchestrator, test_agent):
        orchestrator.register_agent(test_agent)
        status = orchestrator.get_system_status()

        assert "registered_agents" in status


class TestCodeGenAgent:
    """Tests for CodeGenAgent"""

    @pytest.fixture
    def agent(self):
        return CodeGenAgent()

    @pytest.mark.asyncio
    async def test_can_handle(self, agent):
        task = Task(type="codegen", description="Generate code")
        assert await agent.can_handle(task) is True

    @pytest.mark.asyncio
    async def test_process_task(self, agent):
        task = Task(
            type="codegen",
            description="Generate UART driver",
            context={"language": "c", "project": "EngineCar"},
        )

        result = await agent.process(task)
        assert "language" in result
        assert result["language"] == "c"


class TestReviewAgent:
    """Tests for ReviewAgent"""

    @pytest.fixture
    def agent(self):
        return ReviewAgent()

    @pytest.mark.asyncio
    async def test_can_handle(self, agent):
        task = Task(type="review", description="Review code")
        assert await agent.can_handle(task) is True

    @pytest.mark.asyncio
    async def test_process_no_files(self, agent):
        task = Task(
            type="review",
            description="Review code",
            context={},
        )

        result = await agent.process(task)
        assert result["success"] is False
        assert "No files" in result.get("error", "")


class TestSecurityAgent:
    """Tests for SecurityAgent"""

    @pytest.fixture
    def agent(self):
        return SecurityAgent()

    @pytest.mark.asyncio
    async def test_can_handle(self, agent):
        task = Task(type="security", description="Scan vulnerabilities")
        assert await agent.can_handle(task) is True

    @pytest.mark.asyncio
    async def test_scan_no_vulnerabilities(self, agent):
        task = Task(
            type="security",
            description="Security scan",
            context={"scan_type": "static", "files": []},
        )

        result = await agent.process(task)
        assert "scan_type" in result
        assert result["scan_type"] == "static"

    def test_calculate_risk_score(self, agent):
        results = {
            "static_analysis": {"by_severity": {"critical": 0, "high": 0, "medium": 1}},
            "secret_scan": {"blocked": False},
            "dependency_scan": {"vulnerable_dependencies": []},
        }

        score = agent._calculate_risk_score(results)
        assert score >= 0
        assert score <= 100


class TestDevOpsAgent:
    """Tests for DevOpsAgent"""

    @pytest.fixture
    def agent(self):
        return DevOpsAgent()

    @pytest.mark.asyncio
    async def test_can_handle(self, agent):
        task = Task(type="deploy", description="Deploy to staging")
        assert await agent.can_handle(task) is True

    @pytest.mark.asyncio
    async def test_get_deployment_status(self, agent):
        task = Task(
            type="devops",
            description="Get status",
            context={"action": "deploy"},
        )

        result = await agent.process(task)
        assert "success" in result


class TestMonitoringAgent:
    """Tests for MonitoringAgent"""

    @pytest.fixture
    def agent(self):
        return MonitoringAgent()

    @pytest.mark.asyncio
    async def test_can_handle(self, agent):
        task = Task(type="monitor", description="Health check")
        assert await agent.can_handle(task) is True

    @pytest.mark.asyncio
    async def test_health_check(self, agent):
        task = Task(
            type="monitor",
            description="Health check",
            context={"action": "health_check", "services": ["api", "database"]},
        )

        result = await agent.process(task)
        assert "healthy" in result
        assert "services" in result


class TestMessageBus:
    """Tests for MessageBus"""

    @pytest.fixture
    def bus(self):
        return MessageBus()

    @pytest.mark.asyncio
    async def test_subscribe(self, bus):
        queue = bus.subscribe(AgentType.CODE_GEN)
        assert queue is not None

    @pytest.mark.asyncio
    async def test_publish_and_receive(self, bus):
        queue = bus.subscribe(AgentType.CODE_GEN)

        message = AgentMessage(
            sender=AgentType.ORCHESTRATOR,
            receiver=AgentType.CODE_GEN,
            content={"test": "data"},
        )

        await bus.publish(message)
        received = await bus.receive(AgentType.CODE_GEN, timeout=1)

        assert received is not None
        assert received.content["test"] == "data"


class TestUnifiedAgent:
    """Tests for UnifiedAgent"""

    @pytest.mark.asyncio
    async def test_create(self):
        agent = await UnifiedAgent.create()
        assert agent is not None
        assert agent._initialized is True

    @pytest.mark.asyncio
    async def test_process_task(self):
        agent = await UnifiedAgent.create()

        result = await agent.process_task("Analyze code quality")
        assert "success" in result or "error" in result

    @pytest.mark.asyncio
    async def test_classify_task(self):
        agent = await UnifiedAgent.create()

        task = agent._classify_task("Generate UART driver for EngineCar STM32F407", {})
        assert task.type == "codegen"
        assert task.context.get("project") == "EngineCar"
        assert task.context.get("chip") == "STM32F407"

    def test_classify_task_devops(self):
        agent = UnifiedAgent()

        task = agent._classify_task("Deploy to production", {})
        assert task.type == "devops"

    def test_classify_task_security(self):
        agent = UnifiedAgent()

        task = agent._classify_task("Scan for vulnerabilities", {})
        assert task.type == "security"

    @pytest.mark.asyncio
    async def test_monitor_health(self):
        agent = await UnifiedAgent.create()

        health = await agent.monitor_health()
        assert "ai_brain" in health
        assert "memory_stats" in health

    def test_get_status(self):
        agent = UnifiedAgent()
        status = agent.get_status()

        assert "initialized" in status
        assert "orchestrator" in status
        assert "ai_brain" in status


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
