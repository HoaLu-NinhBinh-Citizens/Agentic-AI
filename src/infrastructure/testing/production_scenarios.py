"""Production Load Test Scenarios.

Realistic workload simulations for AI_SUPPORT production testing.
Run with: python -m src.infrastructure.testing.load_test run --scenario=flash_operations
"""

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Any

from src.infrastructure.testing.load_test import (
    LoadTestRunner,
    LoadTestScenario,
    LoadProfile,
)


# ============================================================================
# Flash Operations Load Tests
# ============================================================================

async def flash_write_scenario(user_id: int, iteration: int) -> None:
    """Simulate flash write operation."""
    from src.infrastructure.hardware.flash.transaction_manager import FlashTransactionManager
    from unittest.mock import MagicMock
    
    # Mock hardware
    mock_hsm = MagicMock()
    mock_hsm.sign = lambda *args, **kwargs: b"signature_64_bytes" * 4
    mock_hsm.verify = lambda *args, **kwargs: True
    mock_hsm.get_counter = lambda *args, **kwargs: 1
    mock_hsm.increment_counter = lambda *args, **kwargs: 2
    mock_hsm.is_locked = lambda *args, **kwargs: False
    
    mock_probe = MagicMock()
    mock_probe.write_memory = lambda *args, **kwargs: True
    mock_probe.read_memory = lambda *args, **kwargs: b"\xFF" * 256
    
    manager = FlashTransactionManager(hsm=mock_hsm, probe=mock_probe)
    
    # Execute flash write
    firmware_data = f"Firmware v1.0 User{user_id} Iter{iteration}".encode() * 10
    
    await manager.execute_transaction(
        address=0x8000000 + (user_id * 0x10000),
        data=firmware_data,
        verify=True,
    )


async def flash_verify_scenario(user_id: int, iteration: int) -> None:
    """Simulate flash verification."""
    from src.domain.hardware.flash.secure_boot import SecureBootValidator
    from unittest.mock import MagicMock
    
    mock_hsm = MagicMock()
    mock_hsm.sign = lambda *args, **kwargs: b"signature" * 4
    mock_hsm.verify = lambda *args, **kwargs: True
    
    validator = SecureBootValidator(hsm=mock_hsm)
    
    firmware_hash = f"hash_user{user_id}_iter{iteration}".encode() * 2
    signature = b"sig" * 16
    
    await validator.verify_firmware(
        firmware_hash=firmware_hash,
        signature=signature,
        public_key_slot=user_id % 4,
    )


# ============================================================================
# Agent Operations Load Tests
# ============================================================================

async def agent_reasoning_scenario(user_id: int, iteration: int) -> None:
    """Simulate agent reasoning operation."""
    from src.core.agent.reasoning_loop import ReasoningLoop
    from unittest.mock import MagicMock
    
    # Mock LLM with realistic latency
    async def mock_llm(*args, **kwargs):
        await asyncio.sleep(random.uniform(0.05, 0.2))  # 50-200ms
        return f"Reasoning result for user {user_id} iteration {iteration}"
    
    mock_llm_provider = MagicMock()
    mock_llm_provider.generate = mock_llm
    
    loop = ReasoningLoop(llm=mock_llm_provider, timeout=30.0)
    
    await loop.execute(
        prompt=f"Analyze this firmware crash: offset={user_id*100} signal={iteration}"
    )


async def multi_agent_scenario(user_id: int, iteration: int) -> None:
    """Simulate multi-agent coordination."""
    from src.core.multi_agent.coordination.coordinator import AgentCoordinator
    
    coordinator = AgentCoordinator()
    
    # Register agents
    num_agents = min(5, user_id + 1)
    for i in range(num_agents):
        await coordinator.register_agent(
            f"agent_{i}",
            {"type": ["debugger", "analyzer", "reporter"][i % 3]}
        )
    
    # Send message through chain
    await coordinator.send_message(
        from_agent="agent_0",
        to_agent=f"agent_{num_agents - 1}",
        message={
            "type": "analysis",
            "user": user_id,
            "iteration": iteration,
        }
    )


# ============================================================================
# Retrieval Operations Load Tests  
# ============================================================================

async def semantic_search_scenario(user_id: int, iteration: int) -> None:
    """Simulate semantic search."""
    from src.infrastructure.vector_db.abstraction import VectorStoreWithFallback
    from unittest.mock import MagicMock
    
    # Mock vector store
    mock_primary = MagicMock()
    mock_primary.search = lambda *args, **kwargs: [{"score": 0.95, "id": f"result_{user_id}"}]
    
    mock_fallback = MagicMock()
    mock_fallback.search = lambda *args, **kwargs: [{"id": "fallback"}]
    
    store = VectorStoreWithFallback(primary=mock_primary, fallback=mock_fallback)
    
    await store.search(
        query=f"firmware crash analysis user {user_id}",
        top_k=10,
    )


async def code_indexing_scenario(user_id: int, iteration: int) -> None:
    """Simulate code indexing."""
    from src.infrastructure.indexing.tree_sitter import SafeTreeSitterIndexer
    
    indexer = SafeTreeSitterIndexer()
    
    # Mock file content
    code = f"""
    void firmware_main() {{
        // User {user_id} iteration {iteration}
        initialize_hardware();
        run_main_loop();
    }}
    """
    
    await indexer.index_file(
        path=f"/firmware/user_{user_id}/module_{iteration}.c",
        content=code,
    )


# ============================================================================
# Session Management Load Tests
# ============================================================================

async def session_operations_scenario(user_id: int, iteration: int) -> None:
    """Simulate session operations."""
    from src.core.session.session_manager import SessionManager
    from src.core.session.session_store import InMemorySessionStore
    from unittest.mock import MagicMock
    
    store = InMemorySessionStore()
    manager = SessionManager(store=store)
    
    # Create session
    session = await manager.create_session(
        user_id=f"user_{user_id}",
        metadata={"iteration": iteration},
    )
    
    # Update state
    await manager.update_session(
        session_id=session.id,
        updates={
            "analysis_count": iteration,
            "last_activity": time.time(),
        }
    )
    
    # Save
    await manager.save_session(session)


# ============================================================================
# MCP Tool Execution Load Tests
# ============================================================================

async def mcp_tool_execution_scenario(user_id: int, iteration: int) -> None:
    """Simulate MCP tool execution."""
    from src.infrastructure.mcp.manager import MCPManager
    from unittest.mock import MagicMock, AsyncMock
    
    manager = MCPManager()
    
    # Mock MCP server
    mock_server = MagicMock()
    mock_server.name = "mock_server"
    mock_server.tools = ["flash_write", "debug_halt", "memory_read"]
    mock_server.call_tool = AsyncMock(return_value={"result": "success"})
    mock_server.list_tools = AsyncMock(return_value=[
        {"name": "flash_write", "description": "Write to flash"}
    ])
    
    await manager.add_server(mock_server)
    
    # Call tool
    await manager.call_tool(
        server_name="mock_server",
        tool_name="flash_write",
        arguments={
            "address": 0x8000000,
            "data": f"data_{user_id}_{iteration}",
        },
        timeout=5.0,
    )


# ============================================================================
# Workflow Orchestration Load Tests
# ============================================================================

async def workflow_execution_scenario(user_id: int, iteration: int) -> None:
    """Simulate workflow execution."""
    from src.core.execution.workflow_engine import WorkflowEngine
    from unittest.mock import MagicMock
    
    engine = WorkflowEngine()
    
    workflow_def = {
        "id": f"workflow_{user_id}_{iteration}",
        "steps": [
            {"id": "step1", "action": "analyze", "timeout": 10},
            {"id": "step2", "action": "flash", "timeout": 30},
            {"id": "step3", "action": "verify", "timeout": 10},
        ]
    }
    
    await engine.execute_workflow(
        workflow=workflow_def,
        context={"user_id": user_id, "iteration": iteration},
    )


# ============================================================================
# Register All Scenarios
# ============================================================================

def register_all_scenarios(runner: LoadTestRunner) -> None:
    """Register all load test scenarios."""
    
    # Flash operations
    runner.register_scenario("flash_write", flash_write_scenario)
    runner.register_scenario("flash_verify", flash_verify_scenario)
    
    # Agent operations
    runner.register_scenario("agent_reasoning", agent_reasoning_scenario)
    runner.register_scenario("multi_agent", multi_agent_scenario)
    
    # Retrieval
    runner.register_scenario("semantic_search", semantic_search_scenario)
    runner.register_scenario("code_indexing", code_indexing_scenario)
    
    # Session
    runner.register_scenario("session_ops", session_operations_scenario)
    
    # MCP
    runner.register_scenario("mcp_tool", mcp_tool_execution_scenario)
    
    # Workflow
    runner.register_scenario("workflow_exec", workflow_execution_scenario)
    
    # Combined "realistic" scenario
    async def realistic_scenario(user_id: int, iteration: int):
        """Realistic mixed workload."""
        scenarios = [
            flash_write_scenario,
            agent_reasoning_scenario,
            semantic_search_scenario,
            session_operations_scenario,
        ]
        scenario = random.choice(scenarios)
        await scenario(user_id, iteration)
    
    runner.register_scenario("realistic_mixed", realistic_scenario)


# ============================================================================
# Run Load Tests
# ============================================================================

async def run_all_load_tests():
    """Run all load test scenarios."""
    runner = LoadTestRunner()
    register_all_scenarios(runner)
    
    # Test profiles
    profiles = {
        "smoke": LoadProfile(
            scenario=LoadTestScenario.SMOKE,
            duration_seconds=10,
            virtual_users=5,
            spawn_rate=2,
        ),
        "normal": LoadProfile(
            scenario=LoadTestScenario.NORMAL,
            duration_seconds=60,
            virtual_users=50,
            spawn_rate=5,
            max_response_time_ms=500,
            max_error_rate_percent=1.0,
        ),
        "peak": LoadProfile(
            scenario=LoadTestScenario.PEAK,
            duration_seconds=120,
            virtual_users=200,
            spawn_rate=20,
            max_response_time_ms=1000,
            max_error_rate_percent=5.0,
        ),
        "sustained": LoadProfile(
            scenario=LoadTestScenario.SUSTAINED,
            duration_seconds=300,  # 5 minutes
            virtual_users=100,
            spawn_rate=10,
            max_response_time_ms=500,
            max_error_rate_percent=2.0,
        ),
    }
    
    results = {}
    
    for scenario_name in ["flash_write", "agent_reasoning", "realistic_mixed"]:
        for profile_name, profile in profiles.items():
            print(f"\nRunning {scenario_name} with {profile_name} profile...")
            
            result = await runner.run_scenario(scenario_name, profile)
            results[f"{scenario_name}_{profile_name}"] = result
            
            print(f"  Error rate: {result.metrics.error_rate_percent:.2f}%")
            print(f"  P99 latency: {result.metrics.latency_p99_ms:.0f}ms")
            print(f"  Throughput: {result.metrics.throughput_rps:.0f} rps")
            print(f"  SLA met: {result.metrics.sla_met}")
    
    # Summary
    print("\n" + "="*60)
    print("LOAD TEST SUMMARY")
    print("="*60)
    
    total_tests = len(results)
    passed_tests = sum(1 for r in results.values() if r.passed)
    
    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    
    return results


if __name__ == "__main__":
    asyncio.run(run_all_load_tests())
