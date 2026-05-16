"""Runtime performance benchmarks."""

import pytest
import time
from ai_support.core.agent.core import AgentCore


@pytest.mark.benchmark
async def test_agent_response_time():
    agent = AgentCore()
    
    start = time.perf_counter()
    await agent.process("Hello")
    elapsed = time.perf_counter() - start
    
    assert elapsed < 5.0, f"Response took {elapsed:.2f}s"


@pytest.mark.benchmark
async def test_concurrent_tasks():
    agent = AgentCore()
    
    start = time.perf_counter()
    tasks = [agent.process(f"Task {i}") for i in range(10)]
    await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - start
    
    assert elapsed < 30.0
